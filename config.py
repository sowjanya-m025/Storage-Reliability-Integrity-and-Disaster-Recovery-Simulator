"""Central configuration for the Storage Reliability & Data Protection Simulator."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR / "storage_sim"          # everything the simulator creates lives here
DISK_DIR = ROOT / "disks"                # simulated disks (plain folders)
META_DIR = ROOT / "manifest"             # baseline manifest + state (kept OUTSIDE the disks)
LOG_DIR = ROOT / "logs"
REPORT_DIR = ROOT / "reports"
SAMPLE_DIR = BASE_DIR / "sample_data"

STATE_FILE = META_DIR / "state.json"
MANIFEST_FILE = META_DIR / "baseline_manifest.json"
MANIFEST_COPY = META_DIR / "baseline_manifest.copy.json"
LOG_FILE = LOG_DIR / "operations.log"

MB = 1024 * 1024

# Simulated disks: key -> properties
DISKS = {
    "disk_a":       {"label": "DISK-A",       "role": "RAID1 member (primary)", "capacity": 50 * MB},
    "disk_b":       {"label": "DISK-B",       "role": "RAID1 member (mirror)",  "capacity": 50 * MB},
    "replica_disk": {"label": "REPLICA-SITE", "role": "Replication target",     "capacity": 50 * MB},
    "backup_disk":  {"label": "BACKUP-VAULT", "role": "Backup storage",         "capacity": 100 * MB},
}

# Capacity alert thresholds (percent used)
WARN_PCT = 70
CRIT_PCT = 90

# Disaster-recovery objectives used in the DR analysis
RTO_TARGET_SEC = 5.0      # Recovery Time Objective (simulated, software only)
RPO_TARGET_FILES = 0      # Recovery Point Objective: files of data loss allowed

# Benchmark settings
BENCH_SIZES = [4 * 1024, 64 * 1024, 1 * MB, 5 * MB]
BENCH_RUNS = 5


def ensure_dirs():
    for d in (DISK_DIR, META_DIR, LOG_DIR, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)
