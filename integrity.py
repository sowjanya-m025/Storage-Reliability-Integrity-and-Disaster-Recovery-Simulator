"""SHA-256 integrity engine + trusted baseline manifest."""
import hashlib
import json
from datetime import datetime
import config
import ui
from logger import log


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_manifest():
    m = _read_json(config.MANIFEST_FILE)
    if m is None:
        m = _read_json(config.MANIFEST_COPY)   # fall back to the safety copy
        if m is not None:
            log("Primary manifest unreadable, using manifest copy", "WARN")
    return m or {}


def save_manifest(m):
    config.META_DIR.mkdir(parents=True, exist_ok=True)
    for p in (config.MANIFEST_FILE, config.MANIFEST_COPY):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=2, sort_keys=True)


def manifest_trusted():
    a, b = _read_json(config.MANIFEST_FILE), _read_json(config.MANIFEST_COPY)
    return a is not None and a == b


def register(rel, data):
    m = load_manifest()
    m[rel] = {"sha256": sha256_bytes(data), "size": len(data),
              "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    save_manifest(m)


def unregister(rel):
    m = load_manifest()
    m.pop(rel, None)
    save_manifest(m)


def verify_array(raid):
    """Compare every RAID member's copy with the baseline checksum."""
    manifest = load_manifest()
    rows = []
    for rel in sorted(manifest):
        st = raid.copy_status(rel, manifest[rel]["sha256"])
        online = [s for s in st.values() if s != "OFFLINE"]
        if online and all(s == "OK" for s in online):
            overall = "OK"
        elif any(s == "OK" for s in online):
            overall = "REPAIRABLE"
        else:
            overall = "DAMAGED"
        rows.append({"file": rel, "status": st, "overall": overall})
    # files present on a disk but not in the baseline
    seen = set(manifest)
    for d in raid.online_members():
        for rel in d.files():
            if rel not in seen:
                seen.add(rel)
                rows.append({"file": rel, "status": {d.name: "UNTRACKED"}, "overall": "UNTRACKED"})
    return rows


def run_check(raid, show=True):
    rows = verify_array(raid)
    if show:
        ui.banner("INTEGRITY CHECK (SHA-256 vs trusted baseline)")
        print("Manifest copy matches primary manifest: %s" % ("YES" if manifest_trusted() else "NO - manifest may be tampered!"))
        print("RAID 1 array state: %s\n" % raid.state())
        names = [d.name for d in raid.members]
        table_rows = [[r["file"]] + [r["status"].get(n, "-") for n in names] + [r["overall"]] for r in rows]
        ui.table(["File"] + names + ["Result"], table_rows)
        counts = {}
        for r in rows:
            counts[r["overall"]] = counts.get(r["overall"], 0) + 1
        print("Summary: " + ", ".join("%s=%d" % (k, v) for k, v in sorted(counts.items())))
    bad = [r for r in rows if r["overall"] not in ("OK", "UNTRACKED")]
    log("Integrity check: %d files, %d with issues" % (len(rows), len(bad)),
        "WARN" if bad else "INFO")
    return rows
