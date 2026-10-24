"""Text / CSV / optional graph reports."""
import csv
from datetime import datetime
import config
import integrity
import logger


def generate(app):
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    lines = []
    w = lines.append
    w("STORAGE RELIABILITY & DATA PROTECTION REPORT")
    w("Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    w("(All RAID / replication / failover behaviour is SIMULATED in software.)\n")
    w("1. DISK CAPACITY AND HEALTH")
    for r in app.sm.health_rows():
        w("   %-13s %-24s %-7s cap=%sMB used=%sMB free=%sMB (%s) alert=%s" % tuple(r))
    w("\n2. RAID 1 STATE: %s | ACTIVE SITE: %s" % (app.raid.state(), app.sm.active_site))
    w("\n3. INTEGRITY RESULTS")
    rows = integrity.verify_array(app.raid)
    names = [d.name for d in app.raid.members]
    for r in rows:
        w("   %-34s %s -> %s" % (r["file"], ", ".join("%s:%s" % (n, r["status"].get(n, "-")) for n in names), r["overall"]))
    w("\n4. REPLICATION")
    lag = app.repl.lag()
    w("   Replica lag: %s" % ("replica offline" if lag is None else "%d file(s) out of sync" % len(lag)))
    w("\n5. BACKUPS")
    ids = app.backups.list_backups()
    w("   %d backup(s): %s" % (len(ids), ", ".join(ids[-3:]) if ids else "none"))
    w("\n6. RECENT OPERATIONS")
    for l in logger.tail(15):
        w("   " + l)
    txt = config.REPORT_DIR / ("storage_report_%s.txt" % ts)
    txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    csv_path = config.REPORT_DIR / ("integrity_%s.csv" % ts)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        cw = csv.writer(f)
        cw.writerow(["file"] + names + ["overall"])
        for r in rows:
            cw.writerow([r["file"]] + [r["status"].get(n, "-") for n in names] + [r["overall"]])

    outputs = [txt, csv_path]
    try:                                    # optional graph (only if matplotlib is installed)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        labels = [d.name for d in app.sm.disks.values()]
        used = [d.used() / config.MB if d.online() else 0 for d in app.sm.disks.values()]
        cap = [d.capacity / config.MB for d in app.sm.disks.values()]
        plt.figure(figsize=(7, 4))
        plt.bar(labels, cap, label="Capacity (MB)", alpha=0.35)
        plt.bar(labels, used, label="Used (MB)")
        plt.title("Disk capacity utilisation"); plt.legend(); plt.tight_layout()
        png = config.REPORT_DIR / ("capacity_%s.png" % ts)
        plt.savefig(str(png)); plt.close()
        outputs.append(png)
    except Exception:
        pass
    logger.log("Report generated: %s" % txt.name)
    return outputs
