"""Simulated disks and the storage manager (capacity + health monitoring)."""
import json
import shutil
import config
from logger import log


class DiskError(Exception):
    pass


class Disk:
    """A 'disk' is a folder with a fixed capacity and an ONLINE/FAILED status."""

    def __init__(self, key, spec, status="ONLINE"):
        self.key = key
        self.name = spec["label"]
        self.role = spec["role"]
        self.capacity = spec["capacity"]
        self.status = status
        self.path = config.DISK_DIR / key
        self.path.mkdir(parents=True, exist_ok=True)

    def online(self):
        return self.status == "ONLINE"

    def _check(self):
        if not self.online():
            raise DiskError("%s is %s" % (self.name, self.status))

    def used(self):
        return sum(f.stat().st_size for f in self.path.rglob("*") if f.is_file())

    def free(self):
        return max(self.capacity - self.used(), 0)

    def usage_pct(self):
        return 100.0 * self.used() / self.capacity

    def files(self):
        self._check()
        return sorted(p.relative_to(self.path).as_posix()
                      for p in self.path.rglob("*") if p.is_file())

    def exists(self, rel):
        self._check()
        return (self.path / rel).is_file()

    def read(self, rel):
        self._check()
        p = self.path / rel
        if not p.is_file():
            raise FileNotFoundError(rel)
        return p.read_bytes()

    def write(self, rel, data):
        self._check()
        p = self.path / rel
        existing = p.stat().st_size if p.is_file() else 0
        if self.used() - existing + len(data) > self.capacity:
            raise DiskError("%s: capacity exceeded, cannot write %s" % (self.name, rel))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def delete(self, rel):
        self._check()
        p = self.path / rel
        if p.is_file():
            p.unlink()

    def wipe(self):
        if self.path.exists():
            shutil.rmtree(self.path)
        self.path.mkdir(parents=True, exist_ok=True)


class StorageManager:
    def __init__(self):
        config.ensure_dirs()
        self.state = self._load()
        self.disks = {}
        for key, spec in config.DISKS.items():
            self.disks[key] = Disk(key, spec, self.state["disks"].get(key, "ONLINE"))

    def _load(self):
        if config.STATE_FILE.exists():
            try:
                with open(config.STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (ValueError, OSError):
                pass
        return {"disks": {}, "active_site": "PRIMARY"}

    def save(self):
        self.state["disks"] = {k: d.status for k, d in self.disks.items()}
        with open(config.STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    @property
    def active_site(self):
        return self.state.get("active_site", "PRIMARY")

    def set_active_site(self, site):
        self.state["active_site"] = site
        self.save()
        log("Active site switched to %s" % site)

    def set_status(self, key, status):
        self.disks[key].status = status
        self.save()
        log("%s status -> %s" % (self.disks[key].name, status),
            "WARN" if status != "ONLINE" else "INFO")

    def fail_disk(self, key):
        self.set_status(key, "FAILED")

    def replace_disk(self, key):
        """Simulates swapping in a brand-new empty disk."""
        self.disks[key].wipe()
        self.set_status(key, "ONLINE")
        log("%s replaced with a new empty disk" % self.disks[key].name)

    def alert_level(self, disk):
        if not disk.online():
            return "OFFLINE"
        pct = disk.usage_pct()
        if pct >= config.CRIT_PCT:
            return "CRITICAL"
        if pct >= config.WARN_PCT:
            return "WARNING"
        return "OK"

    def health_rows(self):
        rows = []
        for d in self.disks.values():
            if d.online():
                used = "%.2f" % (d.used() / config.MB)
                free = "%.2f" % (d.free() / config.MB)
                pct = "%.1f%%" % d.usage_pct()
            else:
                used = free = pct = "N/A"
            rows.append([d.name, d.role, d.status, "%d" % (d.capacity / config.MB),
                         used, free, pct, self.alert_level(d)])
        return rows

    def reset_all(self):
        for d in self.disks.values():
            d.wipe()
            d.status = "ONLINE"
        self.state = {"disks": {}, "active_site": "PRIMARY"}
        self.save()
        for f in (config.MANIFEST_FILE, config.MANIFEST_COPY):
            if f.exists():
                f.unlink()
        log("System reset: all disks wiped and set ONLINE")
