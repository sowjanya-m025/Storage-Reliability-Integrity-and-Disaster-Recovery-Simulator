"""Automatic recovery pipeline: RAID mirror -> replica -> backup."""
import time
import integrity
import ui
from logger import log


def auto_recover(app, quiet=False):
    t0 = time.perf_counter()
    res = {"healthy": 0, "healed": [], "unrecoverable": [], "error": None}
    if app.raid.state() == "FAILED":
        res["error"] = "RAID array FAILED - replace the failed disks first (or use failover)."
        res["seconds"] = 0.0
        if not quiet:
            print(res["error"])
        return res
    for rel, meta in sorted(integrity.load_manifest().items()):
        exp = meta["sha256"]
        st = app.raid.copy_status(rel, exp)
        online = [s for s in st.values() if s != "OFFLINE"]
        if all(s == "OK" for s in online):
            res["healthy"] += 1
            continue
        if any(s == "OK" for s in online):
            app.raid.self_heal(rel, exp)
            res["healed"].append((rel, "RAID mirror"))
            continue
        data = app.repl.fetch_verified(rel, exp)
        if data is not None:
            app.raid.write_file(rel, data, log_op=False)
            res["healed"].append((rel, "Replica site"))
            continue
        data, bid = app.backups.fetch_verified(rel, exp)
        if data is not None:
            app.raid.write_file(rel, data, log_op=False)
            res["healed"].append((rel, "Backup " + bid))
            continue
        res["unrecoverable"].append(rel)
    res["seconds"] = time.perf_counter() - t0
    log("Auto-recovery: %d recovered, %d unrecoverable, %.3fs" %
        (len(res["healed"]), len(res["unrecoverable"]), res["seconds"]),
        "WARN" if res["unrecoverable"] else "INFO")
    if not quiet:
        ui.banner("AUTOMATIC RECOVERY")
        print("Order of recovery: 1) RAID mirror  2) Replica site  3) Verified backup\n")
        if res["healed"]:
            ui.table(["File", "Recovered from"], res["healed"])
        else:
            print("Nothing needed recovery.")
        print("Healthy files: %d | Recovered: %d | Unrecoverable: %d | Time: %.3f s" %
              (res["healthy"], len(res["healed"]), len(res["unrecoverable"]), res["seconds"]))
        for rel in res["unrecoverable"]:
            print("  [LOST] %s (no verified copy anywhere)" % rel)
    return res
