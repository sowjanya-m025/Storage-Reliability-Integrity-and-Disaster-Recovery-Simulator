"""Interactive web dashboard (runs locally in your browser, standard library only).

Run:   macOS:  python3 web_app.py        Windows:  py web_app.py
Opens  http://127.0.0.1:8000  (only reachable from your own computer).
"""
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import benchmark
import config
import dr_analysis
import faults
import integrity
import recovery
import reports
import logger
from storage import DiskError
from system import System

LOCK = threading.Lock()
WEB_DIR = config.BASE_DIR / "web"
RAID_KEYS = ("disk_a", "disk_b")


# ------------------------------------------------------------------ state
def get_state(app):
    manifest = integrity.load_manifest()
    rows = {r["file"]: r for r in integrity.verify_array(app.raid)}
    replica = dict(app.repl.verify_replica())
    names = [d.name for d in app.raid.members]
    files = []
    for rel in sorted(rows):
        r = rows[rel]
        exp = manifest.get(rel, {}).get("sha256")
        bk = None
        if exp:
            _, bid = app.backups.fetch_verified(rel, exp)
            bk = bid
        files.append({
            "name": rel, "size": manifest.get(rel, {}).get("size", 0),
            "a": r["status"].get(names[0], "-"), "b": r["status"].get(names[1], "-"),
            "overall": r["overall"], "replica": replica.get(rel, "-"),
            "backup": bk[-15:] if bk else None,
        })
    disks = []
    for key, d in app.sm.disks.items():
        disks.append({"key": key, "name": d.name, "role": d.role, "status": d.status,
                      "capacity_mb": d.capacity / config.MB,
                      "used_mb": round(d.used() / config.MB, 2) if d.online() else None,
                      "pct": round(d.usage_pct(), 1) if d.online() else None,
                      "alert": app.sm.alert_level(d)})
    backups = []
    for bid in app.backups.list_backups():
        v = app.backups.verify(bid)
        backups.append({"id": bid, "files": len(v), "bad": len([x for x in v if x[1] != "OK"])})
    lag = app.repl.lag()
    return {"disks": disks, "raid": app.raid.state(), "site": app.sm.active_site,
            "files": files, "backups": backups, "lag": lag,
            "manifest_trusted": integrity.manifest_trusted(),
            "log": logger.tail(30), "thresholds": [config.WARN_PCT, config.CRIT_PCT]}


# ------------------------------------------------------------------ actions
def safe_name(name):
    name = (name or "").strip().replace("\\", "/")
    if not name or name.startswith("/") or ".." in name.split("/") or len(name) > 100 or ":" in name:
        raise ValueError("Invalid file name. Use something like notes/todo.txt")
    return name


def handle(app, req):
    a = req.get("action")
    sm = app.sm

    def dkey():
        k = req.get("disk")
        if k not in config.DISKS:
            raise ValueError("Unknown disk")
        return k

    def fname():
        f = req.get("file")
        if f not in integrity.load_manifest() and f != "_filler.bin":
            raise ValueError("Unknown file")
        return f

    if a == "init":
        r = app.initialize()
        return {"message": "System reset: %d files stored on RAID 1, replicated and backed up." % r["files"]}
    if a == "fail_disk":
        k = dkey()
        sm.fail_disk(k)
        msg = "%s FAILED." % sm.disks[k].name
        if k in RAID_KEYS:
            msg += " RAID is now %s." % app.raid.state()
        return {"message": msg}
    if a == "replace_disk":
        k = dkey()
        sm.replace_disk(k)
        msg = "%s replaced with a new empty disk." % sm.disks[k].name
        if k in RAID_KEYS and sm.active_site == "PRIMARY" and app.raid.state() == "OPTIMAL":
            r = app.raid.rebuild(integrity.load_manifest())
            msg += " Mirror rebuilt: %d files copied." % len(r["rebuilt"])
            if r["failed"]:
                msg += " %d file(s) had no good copy - run Recover." % len(r["failed"])
        elif k in RAID_KEYS and sm.active_site == "REPLICA":
            msg += " Use 'Fail back' to restore data from the replica."
        elif k == "replica_disk":
            msg += " Run 'Sync' to repopulate it."
        elif k == "backup_disk":
            msg += " All old backups are gone - create a new backup."
        return {"message": msg}
    if a == "corrupt":
        ok = faults.corrupt(sm.disks[dkey()], fname())
        return {"ok": ok, "message": "Silent corruption injected." if ok else "Disk offline or file missing there."}
    if a == "delete":
        ok = faults.delete(sm.disks[dkey()], fname())
        return {"ok": ok, "message": "File deleted." if ok else "Disk offline or file missing there."}
    if a in ("delete_array", "delete_all"):
        f = fname()
        keys = list(RAID_KEYS) + (["replica_disk"] if a == "delete_all" else [])
        n = sum(1 for k in keys if faults.delete(sm.disks[k], f))
        return {"message": "Deleted %s from %d location(s)." % (f, n)}
    if a == "fill":
        n = faults.fill(sm.disks["disk_a"])
        return {"message": "DISK-A filled to 92%% (%.1f MB filler)." % (n / config.MB) if n else "Already above 92%."}
    if a == "unfill":
        return {"message": "Filler removed." if faults.remove_filler(sm.disks["disk_a"]) else "No filler present."}
    if a == "sync":
        s = app.repl.sync()
        return {"message": "Replication: %d copied, %d up to date, %d rejected (no verified source)." %
                (len(s["copied"]), s["up_to_date"], len(s["rejected"]))}
    if a == "failover":
        app.repl.failover()
        return {"message": "FAILOVER: users are now served from the replica site."}
    if a == "failback":
        for k in RAID_KEYS:
            if not sm.disks[k].online():
                sm.replace_disk(k)
        r = app.repl.failback()
        return {"message": "FAILBACK: %d files restored to primary, %d failed." % (len(r["restored"]), len(r["failed"]))}
    if a == "backup":
        bid, n, skipped = app.backups.create()
        return {"message": "Backup %s created (%d files%s)." % (bid, n, ", %d skipped" % len(skipped) if skipped else "")}
    if a == "restore_file":
        f = fname()
        data, bid = app.backups.fetch_verified(f, integrity.load_manifest()[f]["sha256"])
        if data is None:
            return {"ok": False, "message": "No backup holds a version matching the trusted checksum."}
        app.raid.write_file(f, data)
        return {"message": "Restored %s from %s." % (f, bid)}
    if a == "recover":
        r = recovery.auto_recover(app, quiet=True)
        if r["error"]:
            return {"ok": False, "message": r["error"]}
        parts = ["%s <- %s" % (rel, src) for rel, src in r["healed"]]
        msg = "Recovery: %d recovered, %d healthy, %d lost." % (len(r["healed"]), r["healthy"], len(r["unrecoverable"]))
        if parts:
            msg += " " + "; ".join(parts)
        if r["unrecoverable"]:
            msg += " LOST: " + ", ".join(r["unrecoverable"])
        return {"ok": not r["unrecoverable"], "message": msg}
    if a == "add_file":
        name, text = safe_name(req.get("name")), str(req.get("content", ""))
        if len(text) > 100000:
            raise ValueError("Content too large (100 KB max)")
        app.add_file(name, (text + "\n").encode("utf-8"))
        return {"message": "%s written to the array; checksum recorded. It is NOT replicated/backed up until you sync/backup." % name}
    if a == "view_file":
        f = req.get("file")
        m = integrity.load_manifest()
        if f in m:
            data = app.repl.read_active(f, m[f]["sha256"])
            src = "%s site (verified)" % sm.active_site
        else:
            got = app.raid.read_file(f)
            data, src = (got[0], got[1] + " (untracked)") if got else (None, "")
        if data is None:
            return {"ok": False, "message": "No valid copy is available right now."}
        text = "(binary file, %d bytes)" % len(data) if b"\x00" in data[:2000] or len(data) > 4000 and not data[:2000].isascii() \
            else data[:3000].decode("utf-8", "replace")
        return {"message": "Read %d bytes from %s." % (len(data), src), "view": {"name": f, "text": text,
                "sha256": integrity.sha256_bytes(data), "source": src}}
    if a == "benchmark":
        if app.raid.state() != "OPTIMAL":
            return {"ok": False, "message": "Benchmark needs a healthy RAID array."}
        return {"message": "Benchmark complete (CSV saved in storage_sim/reports).", "bench": benchmark.run(app, show=False)}
    if a == "dr":
        if app.raid.state() != "OPTIMAL" or sm.active_site != "PRIMARY":
            return {"ok": False, "message": "DR analysis needs a healthy system. Repair the array / fail back first."}
        for k in config.DISKS:
            if not sm.disks[k].online():
                return {"ok": False, "message": "All four disks must be online for the DR analysis."}
        return {"message": "DR analysis complete (CSV saved in storage_sim/reports).",
                "dr": dr_analysis.run(app, show=False), "objectives": [config.RTO_TARGET_SEC, config.RPO_TARGET_FILES]}
    if a == "report":
        return {"message": "Saved: " + ", ".join(p.name for p in reports.generate(app)) + " (in storage_sim/reports)"}
    raise ValueError("Unknown action")


# ------------------------------------------------------------------ server
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self):
        if self.path == "/api/state":
            with LOCK:
                try:
                    self._json(get_state(self.server.app))
                except Exception as e:  # keep dashboard alive
                    self._json({"error": str(e)}, 500)
        elif self.path in ("/", "/index.html"):
            self._send(200, (WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/action":
            return self._send(404, b"Not found", "text/plain")
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._json({"ok": False, "message": "Bad request"}, 400)
        with LOCK:
            try:
                res = handle(self.server.app, req)
                res.setdefault("ok", True)
            except (DiskError, ValueError) as e:
                res = {"ok": False, "message": str(e)}
            except FileNotFoundError as e:
                res = {"ok": False, "message": "File not found: %s" % e}
            except Exception as e:
                res = {"ok": False, "message": "Unexpected error: %s" % e}
        self._json(res)


def serve(port=8000, open_browser=True):
    app = System()
    if not integrity.load_manifest():
        print("First run: initialising simulated storage ...")
        app.initialize()
    server = None
    for p in range(port, port + 10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            break
        except OSError:
            continue
    if server is None:
        print("Could not find a free port.")
        return
    server.app = app
    url = "http://127.0.0.1:%d" % server.server_address[1]
    print("Dashboard running at %s   (press Ctrl+C to stop)" % url)
    if open_browser:git init

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    port = 8000
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    serve(port, "--no-browser" not in sys.argv)


