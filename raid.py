"""RAID 1 (mirroring) simulation across DISK-A and DISK-B."""
from storage import DiskError
from integrity import sha256_bytes
from logger import log


class Raid1:
    def __init__(self, sm):
        self.sm = sm
        self.members = [sm.disks["disk_a"], sm.disks["disk_b"]]

    def online_members(self):
        return [d for d in self.members if d.online()]

    def state(self):
        return {2: "OPTIMAL", 1: "DEGRADED", 0: "FAILED"}[len(self.online_members())]

    def write_file(self, rel, data, log_op=True):
        online = self.online_members()
        if not online:
            raise DiskError("RAID1 array FAILED: no online member disks")
        for d in online:
            d.write(rel, data)
        if log_op:
            log("RAID1 write %s (%d bytes) -> %s" % (rel, len(data), ", ".join(d.name for d in online)))
        return [d.name for d in online]

    def read_file(self, rel, expected=None):
        """Return (data, disk_name) from the first good copy, else None."""
        for d in self.online_members():
            try:
                data = d.read(rel)
            except FileNotFoundError:
                continue
            if expected is None or sha256_bytes(data) == expected:
                return data, d.name
            log("RAID1: checksum mismatch for %s on %s, trying mirror" % (rel, d.name), "WARN")
        return None

    def copy_status(self, rel, expected):
        res = {}
        for d in self.members:
            if not d.online():
                res[d.name] = "OFFLINE"
                continue
            try:
                data = d.read(rel)
            except FileNotFoundError:
                res[d.name] = "MISSING"
                continue
            res[d.name] = "OK" if sha256_bytes(data) == expected else "CORRUPT"
        return res

    def self_heal(self, rel, expected):
        """Repair bad/missing copies from a good mirror. Returns list of healed disks."""
        st = self.copy_status(rel, expected)
        good = [d for d in self.online_members() if st[d.name] == "OK"]
        if not good:
            return None
        data = good[0].read(rel)
        healed = []
        for d in self.online_members():
            if st[d.name] in ("MISSING", "CORRUPT"):
                d.write(rel, data)
                healed.append(d.name)
                log("RAID1 self-heal: %s repaired on %s from %s" % (rel, d.name, good[0].name))
        return healed

    def rebuild(self, manifest):
        """Re-synchronise the mirror (used after a failed disk is replaced)."""
        rebuilt, failed = [], []
        for rel, meta in manifest.items():
            r = self.self_heal(rel, meta["sha256"])
            if r is None:
                failed.append(rel)
            elif r:
                rebuilt.append(rel)
        log("RAID1 rebuild finished: %d files rebuilt, %d unrecoverable" % (len(rebuilt), len(failed)))
        return {"rebuilt": rebuilt, "failed": failed}
