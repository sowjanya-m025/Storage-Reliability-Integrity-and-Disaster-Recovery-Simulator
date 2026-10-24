"""Disaster-recovery analysis: inject failures, recover, measure RTO / RPO."""
import csv
import time
from datetime import datetime
import config
import faults
import integrity
import recovery
import ui
from logger import log


def _all_ok(app):
    return all(r["overall"] in ("OK", "UNTRACKED") for r in integrity.verify_array(app.raid))


def _readable(app, files, manifest):
    return sum(1 for f in files if app.repl.read_active(f, manifest[f]["sha256"]) is not None)


def run(app, show=True):
    if app.raid.state() != "OPTIMAL" or app.sm.active_site != "PRIMARY":
        print("DR analysis needs a healthy system. Replace failed disks / fail back, or reset (option 1).")
        return []
    app.repl.sync()
    app.backups.create()
    manifest = integrity.load_manifest()
    files = sorted(manifest)
    a, b = app.sm.disks["disk_a"], app.sm.disks["disk_b"]
    out = []

    def add(name, affected, lost, secs, avail, note):
        out.append({"scenario": name, "files_affected": affected, "recovered": affected - lost,
                    "data_lost": lost, "recovery_time_s": round(secs, 4),
                    "availability_pct": round(avail, 1),
                    "RTO_met": "YES" if secs <= config.RTO_TARGET_SEC else "NO",
                    "RPO_met": "YES" if lost <= config.RPO_TARGET_FILES else "NO", "note": note})

    # 1. silent corruption on one mirror
    faults.corrupt(a, files[0])
    r = recovery.auto_recover(app, quiet=True)
    add("1. Silent corruption on DISK-A", 1, len(r["unrecoverable"]), r["seconds"], 100.0,
        "Mirror self-heal; reads served from DISK-B meanwhile")

    # 2. file lost from both mirrors
    faults.delete(a, files[1]); faults.delete(b, files[1])
    r = recovery.auto_recover(app, quiet=True)
    src = r["healed"][0][1] if r["healed"] else "none"
    add("2. File deleted from both disks", 1, len(r["unrecoverable"]), r["seconds"], 0.0,
        "RAID cannot help; recovered from: " + src)

    # 3. single disk failure + replacement
    app.sm.fail_disk("disk_b")
    avail = 100.0 * _readable(app, files, manifest) / len(files)
    t0 = time.perf_counter()
    app.sm.replace_disk("disk_b")
    rb = app.raid.rebuild(manifest)
    dt = time.perf_counter() - t0
    add("3. DISK-B hardware failure", len(files), len(rb["failed"]), dt, avail,
        "Array DEGRADED but fully available; mirror rebuilt on new disk")

    # 4. total primary array loss -> failover -> failback
    app.sm.fail_disk("disk_a"); app.sm.fail_disk("disk_b")
    t0 = time.perf_counter()
    app.repl.failover()
    avail = 100.0 * _readable(app, files, manifest) / len(files)
    t_service = time.perf_counter() - t0
    app.sm.replace_disk("disk_a"); app.sm.replace_disk("disk_b")
    fb = app.repl.failback()
    dt = time.perf_counter() - t0
    add("4. Whole primary array lost", len(files), len(fb["failed"]), dt, avail,
        "Failover restored service in %.4f s; primary rebuilt from replica" % t_service)

    # 5. data created after the last sync/backup, then lost (RPO test)
    new = "documents/new_unprotected.txt"
    app.add_file(new, b"Created after the last replication and backup.\n" * 50)
    faults.delete(a, new); faults.delete(b, new)
    r = recovery.auto_recover(app, quiet=True)
    add("5. New data lost before next sync/backup", 1, len(r["unrecoverable"]), r["seconds"], 0.0,
        "RPO breach: data written after the last copy cannot be recovered")
    integrity.unregister(new)

    healthy = _all_ok(app)
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.REPORT_DIR / ("dr_analysis_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    log("DR analysis completed (%d scenarios), report %s" % (len(out), path.name))
    if show:
        ui.banner("DISASTER RECOVERY ANALYSIS")
        print("Objectives: RTO <= %.1f s, RPO = %d files of data loss\n" % (config.RTO_TARGET_SEC, config.RPO_TARGET_FILES))
        ui.table(["Scenario", "Affected", "Recovered", "Lost", "Time (s)", "Avail %", "RTO", "RPO"],
                 [[o["scenario"], o["files_affected"], o["recovered"], o["data_lost"],
                   o["recovery_time_s"], o["availability_pct"], o["RTO_met"], o["RPO_met"]] for o in out])
        print("")
        for o in out:
            print("- %s: %s" % (o["scenario"], o["note"]))
        print("\nSystem healthy after analysis: %s" % ("YES" if healthy else "NO"))
        print("Note: times cover software recovery only; real RTO also includes hardware replacement.")
        print("Report saved to: %s" % path)
    return out
