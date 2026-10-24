"""Creates the sample dataset (if missing) that gets stored on the RAID array."""
import random
import config


def ensure_sample_data():
    root = config.SAMPLE_DIR
    if root.exists() and any(root.rglob("*")):
        return
    rnd = random.Random(42)
    (root / "documents").mkdir(parents=True, exist_ok=True)
    (root / "database").mkdir(parents=True, exist_ok=True)
    (root / "media").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)

    (root / "documents" / "project_report.txt").write_text(
        "Storage Area Network - Project Report\n" + "RAID, replication and backups protect data.\n" * 120,
        encoding="utf-8")
    (root / "documents" / "meeting_notes.txt").write_text(
        "Meeting notes\n" + "".join("Item %d: review storage capacity\n" % i for i in range(1, 80)),
        encoding="utf-8")

    with open(root / "database" / "students.csv", "w", encoding="utf-8", newline="") as f:
        f.write("id,name,marks\n")
        for i in range(1, 301):
            f.write("%d,Student_%d,%d\n" % (i, i, rnd.randint(35, 100)))
    with open(root / "database" / "transactions.csv", "w", encoding="utf-8", newline="") as f:
        f.write("txn_id,account,amount\n")
        for i in range(1, 3001):
            f.write("%d,AC%04d,%.2f\n" % (i, rnd.randint(1, 500), rnd.uniform(5, 5000)))

    (root / "media" / "image_sample.bin").write_bytes(bytes(rnd.getrandbits(8) for _ in range(300 * 1024)))
    (root / "logs" / "server.log").write_text(
        "".join("2026-01-%02d 10:%02d:00 INFO request served\n" % (1 + i % 28, i % 60) for i in range(600)),
        encoding="utf-8")
