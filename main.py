"""Storage Reliability, Integrity and Disaster Recovery Simulator (SAN concepts, software simulation).

Run:   macOS:   python3 main.py          Windows:  py main.py
Demo:  macOS:   python3 main.py --demo   Windows:  py main.py --demo
"""
import sys
import time
import integrity
import faults
import recovery
import benchmark
import dr_analysis
import reports
import ui
import logger
from storage import DiskError
from system import System

try:  # make sure Windows consoles can print everything
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DISCLAIMER = "NOTE: RAID, replication and failover are SOFTWARE SIMULATIONS (folders as disks), not physical SAN hardware."


# ---------------------------------------------------------------- helpers
def ask(prompt):
    return input(prompt).strip()


def pick_file():
    files = sorted(integrity.load_manifest())
    if not files:
        print("No tracked files yet. Run option 1 first.")
        return None
    for i, f in enumerate(files, 1):
        print("  %d. %s" % (i, f))
    try:
        return files[int(ask("File number: ")) - 1]
    except (ValueError, IndexError):
        print("Invalid choice.")
        return None


def pick_disk(app, which=("disk_a", "disk_b")):
    for i, k in enumerate(which, 1):
        print("  %d. %s" % (i, app.sm.disks[k].name))
    try:
        return which[int(ask("Disk number: ")) - 1]
    except (ValueError, IndexError):
        print("Invalid choice.")
        return None


def show_health(app):
    ui.banner("STORAGE HEALTH AND CAPACITY MONITOR")
    ui.table(["Disk", "Role", "Status", "Cap MB", "Used MB", "Free MB", "Used %", "Alert"], app.sm.health_rows())
    print("RAID 1 array: %s | Active site: %s" % (app.raid.state(), app.sm.active_site))
    alerts = [r for r in app.sm.health_rows() if r[7] in ("WARNING", "CRITICAL", "OFFLINE")]
    for r in alerts:
        print("  [ALERT] %s is %s" % (r[0], r[7]))


def safe(fn, *a):
    try:
        return fn(*a)
    except DiskError as e:
        print("  [ERROR] %s" % e)
    except FileNotFoundError as e:
        print("  [ERROR] file not found: %s" % e)


# ---------------------------------------------------------------- submenus
def menu_raid(app):
    while True:
        ui.banner("RAID 1 MIRRORING (simulation)  |  array state: %s" % app.raid.state())
        print("1. Show RAID status and copy comparison\n2. Fail a disk\n3. Replace failed disk and rebuild mirror"
              "\n4. Write a new file to the array\n5. Read a file (shows which disk served it)\n0. Back")
        c = ask("Choice: ")
        if c == "1":
            integrity.run_check(app.raid)
        elif c == "2":
            k = pick_disk(app)
            if k:
                app.sm.fail_disk(k)
                print("%s FAILED -> array is now %s. Data is still available from the mirror." %
                      (app.sm.disks[k].name, app.raid.state()))
        elif c == "3":
            failed = [k for k in ("disk_a", "disk_b") if not app.sm.disks[k].online()]
            if not failed:
                print("No failed disks.")
            for k in failed:
                app.sm.replace_disk(k)
                print("%s replaced with a new empty disk." % app.sm.disks[k].name)
            if failed:
                t = time.perf_counter()
                r = app.raid.rebuild(integrity.load_manifest())
                print("Rebuild done in %.3f s: %d files copied to the new disk, %d unrecoverable." %
                      (time.perf_counter() - t, len(r["rebuilt"]), len(r["failed"])))
        elif c == "4":
            name = ask("New file name (e.g. notes_new.txt): ")
            if name:
                text = ask("File content: ")
                safe(app.add_file, name, (text + "\n").encode("utf-8"))
                print("Written to %s and checksum recorded." % ", ".join(d.name for d in app.raid.online_members()))
        elif c == "5":
            f = pick_file()
            if f:
                got = app.raid.read_file(f, integrity.load_manifest()[f]["sha256"])
                print("Served from %s (%d bytes, checksum verified)." % (got[1], len(got[0])) if got
                      else "No valid copy available on the array!")
        elif c == "0":
            return


def menu_replication(app):
    while True:
        ui.banner("REPLICATION AND FAILOVER  |  active site: %s" % app.sm.active_site)
        print("1. Synchronise primary -> replica\n2. Show replica status / lag\n3. Simulate primary failure and FAIL OVER"
              "\n4. Read a file from the active site\n5. Repair primary and FAIL BACK\n0. Back")
        c = ask("Choice: ")
        if c == "1":
            s = safe(app.repl.sync)
            if s:
                print("Copied: %d | Already up to date: %d | Rejected (no verified source): %d" %
                      (len(s["copied"]), s["up_to_date"], len(s["rejected"])))
                for f in s["copied"]:
                    print("   replicated", f)
        elif c == "2":
            ui.table(["File", "Replica status"], app.repl.verify_replica())
            lag = app.repl.lag()
            print("Replication lag: %s" % ("replica offline" if lag is None else "%d file(s)" % len(lag)))
        elif c == "3":
            app.sm.fail_disk("disk_a"); app.sm.fail_disk("disk_b")
            print("Primary array lost (both RAID disks FAILED).")
            if safe(app.repl.failover) is None and app.sm.active_site == "REPLICA":
                m = integrity.load_manifest()
                ok = sum(1 for f in m if app.repl.read_active(f, m[f]["sha256"]) is not None)
                print("FAILOVER complete. Service continues from the replica: %d/%d files readable." % (ok, len(m)))
        elif c == "4":
            f = pick_file()
            if f:
                d = app.repl.read_active(f, integrity.load_manifest()[f]["sha256"])
                print("Read OK from %s site (%d bytes)." % (app.sm.active_site, len(d)) if d else "File unavailable!")
        elif c == "5":
            for k in ("disk_a", "disk_b"):
                if not app.sm.disks[k].online():
                    app.sm.replace_disk(k)
                    print("%s replaced." % app.sm.disks[k].name)
            r = safe(app.repl.failback)
            if r:
                print("FAILBACK done: %d files restored to the primary array, %d failed." % (len(r["restored"]), len(r["failed"])))
        elif c == "0":
            return


def menu_backup(app):
    while True:
        ui.banner("BACKUP AND RESTORE")
        print("1. Create a verified backup\n2. Verify all backups\n3. List backups\n4. Restore a file from backup\n0. Back")
        c = ask("Choice: ")
        if c == "1":
            r = safe(app.backups.create)
            if r:
                print("Backup %s created: %d files%s" % (r[0], r[1], (" (skipped: %s)" % ", ".join(r[2])) if r[2] else ""))
        elif c == "2":
            safe(app.backups.verify_all)
        elif c == "3":
            ids = safe(app.backups.list_backups) or []
            print("\n".join(ids) if ids else "No backups.")
        elif c == "4":
            f = pick_file()
            if f:
                data, bid = app.backups.fetch_verified(f, integrity.load_manifest()[f]["sha256"])
                if data is None:
                    print("No backup holds a version matching the trusted checksum.")
                else:
                    safe(app.raid.write_file, f, data)
                    print("Restored %s from %s." % (f, bid))
        elif c == "0":
            return


def menu_faults(app):
    while True:
        ui.banner("FAULT INJECTION (simulate real problems)")
        print("1. Corrupt a file on DISK-A\n2. Corrupt a file on DISK-B\n3. Delete a file from one disk"
              "\n4. Delete a file from BOTH disks\n5. Fill DISK-A to 92% (low-space alert)\n6. Remove the filler file\n0. Back")
        c = ask("Choice: ")
        if c in ("1", "2"):
            f = pick_file()
            if f:
                d = app.sm.disks["disk_a" if c == "1" else "disk_b"]
                print("Corruption injected." if faults.corrupt(d, f) else "Could not (disk offline or file missing).")
        elif c == "3":
            f = pick_file()
            k = pick_disk(app) if f else None
            if k:
                print("Deleted." if faults.delete(app.sm.disks[k], f) else "Could not delete.")
        elif c == "4":
            f = pick_file()
            if f:
                for k in ("disk_a", "disk_b"):
                    faults.delete(app.sm.disks[k], f)
                print("Deleted from both online disks.")
        elif c == "5":
            n = safe(faults.fill, app.sm.disks["disk_a"])
            print("Filler added. Check the health monitor (option 2)." if n else "Not added.")
        elif c == "6":
            print("Filler removed." if faults.remove_filler(app.sm.disks["disk_a"]) else "No filler present.")
        elif c == "0":
            return


# ---------------------------------------------------------------- demo
def step(n, text):
    ui.banner("DEMO STEP %d: %s" % (n, text))


def run_demo(app):
    print(DISCLAIMER)
    step(1, "Initialise system (RAID 1 + replica + backup)")
    print(app.initialize())
    step(2, "Storage health and capacity")
    show_health(app)
    step(3, "Integrity check on a healthy system")
    integrity.run_check(app.raid)
    files = sorted(integrity.load_manifest())
    m = integrity.load_manifest()

    step(4, "Silent corruption on DISK-A -> detect -> RAID self-heal")
    faults.corrupt(app.sm.disks["disk_a"], files[0])
    integrity.run_check(app.raid)
    got = app.raid.read_file(files[0], m[files[0]]["sha256"])
    print("\nRead of %s still succeeds, served by %s (corrupt copy skipped)." % (files[0], got[1]))
    recovery.auto_recover(app)

    step(5, "DISK-B fails -> RAID degraded but available -> replace and rebuild")
    app.sm.fail_disk("disk_b")
    print("Array state:", app.raid.state())
    print("Files still readable:", sum(1 for f in files if app.raid.read_file(f, m[f]["sha256"])), "/", len(files))
    app.sm.replace_disk("disk_b")
    print("Rebuild result:", {k: len(v) for k, v in app.raid.rebuild(m).items()})
    print("Array state:", app.raid.state())

    step(6, "Replication, primary-site failure and failover")
    app.add_file("documents/new_report.txt", b"Updated project report.\n" * 40)
    print("Replica lag before sync:", app.repl.lag())
    s = app.repl.sync()
    print("Synced files:", s["copied"])
    app.sm.fail_disk("disk_a"); app.sm.fail_disk("disk_b")
    app.repl.failover()
    m = integrity.load_manifest()
    print("Primary array", app.raid.state(), "- files readable from replica:",
          sum(1 for f in m if app.repl.read_active(f, m[f]["sha256"]) is not None), "/", len(m))
    app.sm.replace_disk("disk_a"); app.sm.replace_disk("disk_b")
    fb = app.repl.failback()
    print("Failback restored", len(fb["restored"]), "files. Active site:", app.sm.active_site)

    step(7, "Backup verification and restore after deleting a file everywhere")
    app.backups.create()
    app.backups.verify_all()
    victim = "database/students.csv"
    for k in ("disk_a", "disk_b", "replica_disk"):
        faults.delete(app.sm.disks[k], victim)
    print("\nDeleted %s from RAID and replica." % victim)
    recovery.auto_recover(app)

    step(8, "Performance benchmark")
    benchmark.run(app)
    step(9, "Disaster recovery analysis")
    dr_analysis.run(app)
    step(10, "Final report")
    for p in reports.generate(app):
        print("Saved:", p)
    print("\nDEMO COMPLETE. " + DISCLAIMER)


# ---------------------------------------------------------------- main menu
def main():
    if "--web" in sys.argv:
        import web_app
        web_app.serve()
        return
    app = System()
    if "--demo" in sys.argv:
        run_demo(app)
        return
    if "--reset" in sys.argv or not integrity.load_manifest():
        print("First run: initialising the simulated storage system ...")
        print(app.initialize())
    while True:
        ui.banner("STORAGE RELIABILITY, INTEGRITY & DISASTER RECOVERY SIMULATOR")
        print(DISCLAIMER)
        print("""
 1. Reset / initialise system with sample data
 2. Storage health and capacity monitor
 3. Integrity check (SHA-256)
 4. RAID 1 mirroring simulator
 5. Replication and failover
 6. Backup and restore
 7. Fault injection (corruption, deletion, low space)
 8. Automatic recovery (RAID -> replica -> backup)
 9. Performance benchmark
10. Disaster recovery analysis (RTO / RPO)
11. Generate reports
12. View operation log
13. Run full automated demo
14. Launch interactive WEB dashboard (browser)
 0. Exit
""")
        c = ask("Choice: ")
        if c == "1":
            print(app.initialize())
        elif c == "2":
            show_health(app)
        elif c == "3":
            safe(integrity.run_check, app.raid)
        elif c == "4":
            menu_raid(app)
        elif c == "5":
            menu_replication(app)
        elif c == "6":
            menu_backup(app)
        elif c == "7":
            menu_faults(app)
        elif c == "8":
            recovery.auto_recover(app)
        elif c == "9":
            safe(benchmark.run, app)
        elif c == "10":
            safe(dr_analysis.run, app)
        elif c == "11":
            for p in reports.generate(app):
                print("Saved:", p)
        elif c == "12":
            print("\n".join(logger.tail(25)) or "Log is empty.")
        elif c == "13":
            run_demo(app)
        elif c == "14":
            import web_app
            web_app.serve()
        elif c == "0":
            print("Goodbye.")
            return


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nExited.")
