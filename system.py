"""Ties all modules together into one storage system."""
import config
import integrity
from storage import StorageManager
from raid import Raid1
from replication import Replicator
from backup import BackupManager
from sample_data import ensure_sample_data
from logger import log


class System:
    def __init__(self):
        self.sm = StorageManager()
        self.raid = Raid1(self.sm)
        self.repl = Replicator(self.sm, self.raid)
        self.backups = BackupManager(self.sm, self.raid, self.repl)

    def add_file(self, rel, data):
        """Write (or update) a file on the array and record its trusted checksum."""
        self.raid.write_file(rel, data)
        integrity.register(rel, data)

    def initialize(self):
        """Reset everything, load the sample dataset, replicate and back it up."""
        ensure_sample_data()
        self.sm.reset_all()
        manifest = {}
        for p in sorted(config.SAMPLE_DIR.rglob("*")):
            if p.is_file():
                rel = p.relative_to(config.SAMPLE_DIR).as_posix()
                data = p.read_bytes()
                self.raid.write_file(rel, data, log_op=False)
                manifest[rel] = {"sha256": integrity.sha256_bytes(data), "size": len(data),
                                 "updated": "baseline"}
        integrity.save_manifest(manifest)
        stats = self.repl.sync()
        bid, n, _ = self.backups.create()
        log("System initialised with %d files" % len(manifest))
        return {"files": len(manifest), "replicated": len(stats["copied"]), "backup": bid}
