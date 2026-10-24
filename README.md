# Storage Reliability, Integrity and Disaster Recovery Simulator

A Python project for a SAN (Storage Area Network) course. It simulates how enterprise storage
protects data: monitoring, RAID 1 mirroring, replication and failover, verified backups,
integrity checking, disaster recovery and performance benchmarking.

> **Honest scope:** RAID, replication and failover are **software simulations** (each "disk" is a
> folder with a capacity and ONLINE/FAILED status). No physical SAN hardware is configured.

Requirements: **Python 3.8+** only (standard library). `matplotlib` is optional (adds a capacity graph).

## How to run

### macOS (Terminal)
```
cd path/to/san_simulator
python3 main.py              # interactive menu
python3 main.py --demo       # automatic full demonstration
python3 main.py --reset      # re-initialise the sample data, then open the menu
```

### Windows (Command Prompt or PowerShell)
```
cd path\to\san_simulator
py main.py                   # interactive menu
py main.py --demo            # automatic full demonstration
py main.py --reset           # re-initialise the sample data, then open the menu
```
(If `py` is not found, use `python main.py`.)

## Interactive web dashboard (recommended for the demo)
```
python3 web_app.py           # macOS
py web_app.py                # Windows
```
browser opens at http://127.0.0.1:8000 (only reachable from your own computer; press Ctrl+C in the terminal to stop).
Options: `--port 9000` to change the port, `--no-browser` to not auto-open. `main.py --web` or menu option 14 also launch it.

In the dashboard you can click a disk to fail or replace it, corrupt or delete any file on any disk, fill a disk to trigger
capacity alerts, sync/back up/fail over/fail back, run recovery, add your own files, run the benchmark and the DR analysis,
and watch the status chips, capacity bars and activity log update live. A hint bar tells you what to do next.

## Modules

| File | Purpose | SAN concept |
|------|---------|-------------|
| `storage.py` | Simulated disks, capacity, health, alerts | Storage monitoring, capacity management |
| `integrity.py` | SHA-256 baseline manifest + checking | Data integrity |
| `raid.py` | RAID 1 mirroring, self-heal, rebuild | Redundancy, fault tolerance |
| `replication.py` | Primary-replica sync, failover, failback | Replication, high availability |
| `backup.py` | Verified, versioned backups and restore | Backup and recovery |
| `recovery.py` | Auto recovery: mirror -> replica -> backup | Data recovery |
| `faults.py` | Corruption, deletion, low-space injection | Failure simulation |
| `benchmark.py` | Single disk vs RAID 1 read/write speed | Performance analysis |
| `dr_analysis.py` | 5 disaster scenarios, RTO / RPO check | Business continuity |
| `reports.py` | Text report, CSV, optional graph | Reporting |
| `main.py` | Console menu + automated demo | - |
| `web_app.py` + `web/index.html` | Interactive browser dashboard | - |

Generated files appear in `storage_sim/` (`disks/`, `manifest/`, `logs/operations.log`, `reports/`).

## Suggested 5-minute demonstration
1. Run `--demo`, or in the menu: **1** (initialise) then **2** (health/capacity).
2. **7 -> 1** corrupt a file on DISK-A, then **3** shows `CORRUPT / REPAIRABLE`, then **8** self-heals from the mirror.
3. **4 -> 2** fail a disk (array DEGRADED, data still readable), **4 -> 3** replace and rebuild.
4. **5 -> 3** primary failure and failover, then **5 -> 5** failback.
5. **7 -> 4** delete a file from both disks, then **8** restores it from replica/backup.
6. **7 -> 5** fill DISK-A to 92% and see the CRITICAL capacity alert in **2**.
7. **9** benchmark, **10** disaster recovery analysis, **11** reports.

## Points to explain in the project review
1. **SHA-256** gives each file a fixed-length fingerprint; any change alters it.
2. **Integrity checking** compares current checksums with the trusted baseline manifest (a second copy of the manifest is kept so tampering is detectable).
3. **RAID 1** writes every file to two disks; if one fails or is corrupt, the other copy serves reads and repairs it. RAID is not a backup: deleting a file deletes it from both disks.
4. **Replication** copies only *verified* data to a second site, so corruption is never replicated. **Failover** switches service to the replica; **failback** returns to the repaired primary.
5. **Backups** are timestamped and verified against recorded checksums, so a bad backup is detected before it is needed.
6. **Recovery order:** mirror -> replica -> backup; anything with no verified copy is reported as lost.
7. **RTO/RPO:** scenario 5 deliberately shows an RPO breach: data written after the last sync/backup cannot be recovered.
8. **Limitation:** everything runs on local folders; timings are for the simulation, not real hardware.
