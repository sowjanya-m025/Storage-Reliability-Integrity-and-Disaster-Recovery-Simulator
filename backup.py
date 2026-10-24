"""Verified backups and restoration."""
import json
from datetime import datetime
import ui
from integrity import sha256_bytes, load_manifest
from logger import log

META_NAME = "_backup_manifest.json"


class BackupManager:
    def __init__(self, sm, raid, repl):
        self.vault = sm.disks["backup_disk"]
        self.raid = raid
        self.repl = repl

    def list_backups(self):
        if not self.vault.online():
            return []
        return sorted({f.split("/")[0] for f in self.vault.files() if f.endswith("/" + META_NAME)})

    def create(self):
        manifest = load_manifest()
        base = datetime.now().strftime("backup_%Y%m%d_%H%M%S")
        bid, n = base, 1
        while bid in self.list_backups():
            n += 1
            bid = "%s_%d" % (base, n)
        record, skipped = {}, []
        for rel, meta in manifest.items():
            exp = meta["sha256"]
            got = self.raid.read_file(rel, exp)
            data = got[0] if got else self.repl.fetch_verified(rel, exp)
            if data is None:
                skipped.append(rel)
                continue
            self.vault.write("%s/%s" % (bid, rel), data)
            record[rel] = {"sha256": exp, "size": len(data)}
        info = {"id": bid, "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "files": record}
        self.vault.write("%s/%s" % (bid, META_NAME), json.dumps(info, indent=2).encode("utf-8"))
        log("Backup %s created: %d files, %d skipped" % (bid, len(record), len(skipped)))
        return bid, len(record), skipped

    def verify(self, bid):
        info = json.loads(self.vault.read("%s/%s" % (bid, META_NAME)).decode("utf-8"))
        rows = []
        for rel, meta in sorted(info["files"].items()):
            try:
                ok = sha256_bytes(self.vault.read("%s/%s" % (bid, rel))) == meta["sha256"]
                rows.append([rel, "OK" if ok else "CORRUPT"])
            except FileNotFoundError:
                rows.append([rel, "MISSING"])
        return rows

    def verify_all(self):
        ui.banner("BACKUP VERIFICATION")
        if not self.vault.online():
            print("Backup vault is OFFLINE.")
            return
        ids = self.list_backups()
        if not ids:
            print("No backups found.")
            return
        table_rows = []
        for bid in ids:
            rows = self.verify(bid)
            bad = [r for r in rows if r[1] != "OK"]
            table_rows.append([bid, len(rows), len(bad), "VALID" if not bad else "INVALID"])
        ui.table(["Backup ID", "Files", "Bad files", "Status"], table_rows)

    def fetch_verified(self, rel, exp):
        """Newest backup whose copy matches the baseline checksum exactly."""
        if not self.vault.online():
            return None, None
        for bid in reversed(self.list_backups()):
            try:
                data = self.vault.read("%s/%s" % (bid, rel))
            except FileNotFoundError:
                continue
            if sha256_bytes(data) == exp:
                return data, bid
        return None, None
