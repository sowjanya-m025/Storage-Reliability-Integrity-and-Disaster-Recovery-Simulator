"""Storage performance benchmark: single disk vs RAID 1."""
import csv
import os
import time
from datetime import datetime
import config
import ui
from storage import DiskError
from logger import log


def run(app, show=True):
    disk = app.sm.disks["disk_a"]
    raid = app.raid
    if raid.state() != "OPTIMAL":
        print("Benchmark needs a healthy RAID array (state is %s)." % raid.state())
        return []
    rows = []
    try:
        for size in config.BENCH_SIZES:
            payload = os.urandom(size)
            rel = "__bench__/b_%d.bin" % size
            for label, w, r in (
                ("Single disk", lambda: disk.write(rel, payload), lambda: disk.read(rel)),
                ("RAID 1 mirror", lambda: raid.write_file(rel, payload, log_op=False),
                 lambda: raid.read_file(rel)),
            ):
                wt, rt = [], []
                for _ in range(config.BENCH_RUNS):
                    t = time.perf_counter(); w(); wt.append(time.perf_counter() - t)
                    t = time.perf_counter(); r(); rt.append(time.perf_counter() - t)
                mb = size / float(config.MB)
                aw, ar = sum(wt) / len(wt), sum(rt) / len(rt)
                rows.append({"size_kb": size // 1024, "config": label,
                             "write_ms": aw * 1000, "read_ms": ar * 1000,
                             "write_mbps": mb / aw, "read_mbps": mb / ar})
    except DiskError as e:
        print("Benchmark aborted: %s" % e)
    finally:
        for d in raid.online_members():
            for s in config.BENCH_SIZES:
                try:
                    d.delete("__bench__/b_%d.bin" % s)
                except Exception:
                    pass
            bd = d.path / "__bench__"
            if bd.exists():
                try:
                    bd.rmdir()
                except OSError:
                    pass
    if not rows:
        return rows
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = config.REPORT_DIR / ("benchmark_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log("Benchmark completed, saved %s" % out.name)
    if show:
        ui.banner("STORAGE PERFORMANCE BENCHMARK (%d runs per test)" % config.BENCH_RUNS)
        ui.table(["Size (KB)", "Configuration", "Write ms", "Read ms", "Write MB/s", "Read MB/s"],
                 [[r["size_kb"], r["config"], "%.2f" % r["write_ms"], "%.2f" % r["read_ms"],
                   "%.1f" % r["write_mbps"], "%.1f" % r["read_mbps"]] for r in rows])
        top = max(r["write_mbps"] for r in rows)
        print("\nWrite throughput (longer bar = faster):")
        for r in rows:
            print("%7d KB %-14s %s %.1f" % (r["size_kb"], r["config"],
                                            ui.bar(r["write_mbps"], top).ljust(30), r["write_mbps"]))
        print("\nObservation: RAID 1 writes to two disks, so writes cost more than a single disk,")
        print("while reads can be served from either copy. Results saved to: %s" % out)
        print("(Timings are for the simulation on your computer; OS caching affects absolute values.)")
    return rows
