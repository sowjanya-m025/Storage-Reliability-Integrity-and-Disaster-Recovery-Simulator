"""Primary -> replica replication, failover and failback."""
from storage import DiskError
from integrity import sha256_bytes, load_manifest
from logger import log


class Replicator:
    def __init__(self, sm, raid):
        self.sm = sm
        self.raid = raid
        self.replica = sm.disks["replica_disk"]

    def _replica_ok(self, rel, exp):
        try:
            return sha256_bytes(self.replica.read(rel)) == exp
        except FileNotFoundError:
            return False

    def sync(self):
        """Copy changed files to the replica. Only VERIFIED data is replicated,
        so silent corruption on the primary is never propagated."""
        if self.sm.active_site != "PRIMARY":
            raise DiskError("Sync disabled while running on the replica (failover active)")
        if not self.replica.online():
            raise DiskError("Replica site is offline")
        stats = {"copied": [], "up_to_date": 0, "rejected": []}
        for rel, meta in load_manifest().items():
            exp = meta["sha256"]
            if self._replica_ok(rel, exp):
                stats["up_to_date"] += 1
                continue
            got = self.raid.read_file(rel, exp)
            if got is None:
                stats["rejected"].append(rel)
                continue
            self.replica.write(rel, got[0])
            stats["copied"].append(rel)
        log("Replication sync: %d copied, %d up to date, %d rejected" %
            (len(stats["copied"]), stats["up_to_date"], len(stats["rejected"])))
        return stats

    def lag(self):
        """Files whose replica copy differs from the baseline (replication lag)."""
        if not self.replica.online():
            return None
        return [rel for rel, m in load_manifest().items() if not self._replica_ok(rel, m["sha256"])]

    def fetch_verified(self, rel, exp):
        if not self.replica.online():
            return None
        try:
            data = self.replica.read(rel)
        except FileNotFoundError:
            return None
        return data if sha256_bytes(data) == exp else None

    def verify_replica(self):
        rows = []
        for rel, m in sorted(load_manifest().items()):
            if not self.replica.online():
                rows.append([rel, "OFFLINE"])
            elif not self.replica.exists(rel):
                rows.append([rel, "MISSING"])
            else:
                rows.append([rel, "OK" if self._replica_ok(rel, m["sha256"]) else "STALE/CORRUPT"])
        return rows

    def failover(self):
        if not self.replica.online():
            raise DiskError("Cannot fail over: replica site is offline")
        self.sm.set_active_site("REPLICA")
        log("FAILOVER: services now served from replica site", "WARN")

    def read_active(self, rel, exp):
        if self.sm.active_site == "PRIMARY":
            got = self.raid.read_file(rel, exp)
            return got[0] if got else None
        return self.fetch_verified(rel, exp)

    def failback(self):
        """Repopulate the (repaired) primary array from the replica and switch back."""
        if self.raid.state() != "OPTIMAL":
            raise DiskError("Primary array must be OPTIMAL (replace failed disks) before failback")
        restored, failed = [], []
        for rel, m in load_manifest().items():
            data = self.fetch_verified(rel, m["sha256"])
            if data is None:
                failed.append(rel)
            else:
                self.raid.write_file(rel, data, log_op=False)
                restored.append(rel)
        self.sm.set_active_site("PRIMARY")
        log("FAILBACK complete: %d files restored to primary, %d failed" % (len(restored), len(failed)))
        return {"restored": restored, "failed": failed}
