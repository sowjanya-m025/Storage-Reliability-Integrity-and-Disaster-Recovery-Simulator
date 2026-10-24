# Demonstration Guide (about 7 minutes)

> RAID, replication and failover are software simulations (folders as disks), not physical SAN hardware. Say this at the start.

## Before you present
1. Open a terminal in the project folder.
2. Mac: `python3 web_app.py`   |   Windows: `py web_app.py`
3. The dashboard opens at http://127.0.0.1:8000. Click **Reset system** once so you start from a clean state.
4. Backup plan: if the browser fails, run `python3 main.py --demo` (Windows: `py main.py --demo`) - it runs the whole story automatically.

## Demo flow (dashboard)

| # | Click | What you should see | What to say |
|---|-------|--------------------|-------------|
| 1 | Nothing yet | 4 disk cards, RAID **OPTIMAL**, serving from **PRIMARY**, green hint bar | "Two disks form a RAID 1 mirror. One replica site and one backup vault protect against bigger failures." |
| 2 | **Corrupt A** on any file | DISK-A chip turns **CORRUPT**, result **REPAIRABLE**, hint bar turns red | "A silent bit-flip. SHA-256 detects it because the checksum no longer matches the trusted baseline." |
| 3 | Click the file name (preview) | File opens, shows source and hash | "The read still succeeds - RAID skips the corrupt copy and serves the verified mirror copy." |
| 4 | **Recover all** | Message: recovered from RAID mirror; chips back to **OK** | "Self-healing: the good copy overwrites the bad one." |
| 5 | **Fail this disk** on DISK-B | RAID **DEGRADED**, orange hint | "Hardware failure. Data stays available from DISK-A, but redundancy is lost." |
| 6 | **Replace disk** on DISK-B | Message: mirror rebuilt, RAID **OPTIMAL** | "A new empty disk is rebuilt from the surviving mirror." |
| 7 | **Fill DISK-A to 92%** | DISK-A bar turns red, **CRITICAL** | "Capacity monitoring and alerts." Then click **Remove filler**. |
| 8 | Add a file (right panel), **Write to RAID array** | New file shows replica **MISSING**, backup **none** | "New data is unprotected until it is replicated and backed up. This is the RPO concept." |
| 9 | **Replicate to replica (Sync)**, then **Create verified backup** | Replica and Backup columns turn green | "Only verified data is replicated, so corruption is never copied to the replica." |
| 10 | **Fail this disk** on DISK-A and DISK-B | RAID **FAILED**, files show UNAVAILABLE | "Total loss of the primary array." |
| 11 | **Fail over to replica** | Serving from **REPLICA**; open a file preview - it still works | "Failover: service continues from the secondary site." |
| 12 | **Repair primary & fail back** | RAID **OPTIMAL**, back to **PRIMARY** | "Disks replaced, data restored from the replica, service returned to primary." |
| 13 | **Del everywhere** on a file, then **Recover all** | Message: recovered from Backup | "RAID is not a backup - deleting a file deletes it from both mirrors. The verified backup saves it." |
| 14 | **Run benchmark** | Table and bars: RAID 1 writes slower than single disk | "RAID 1 writes to two disks, so writes cost more; reads can use either copy." |
| 15 | **Run 5 disaster scenarios** | Table of recovery time, data lost, RTO and RPO | "Scenario 5 deliberately fails RPO: data created after the last sync and backup cannot be recovered." |
| 16 | **Generate report files** | Message listing saved files | "Reports and CSVs are in storage_sim/reports." |

Tip: always use **Recover all** or **Reset system** before moving on, so the next step starts from a healthy state.

## Console fallback (if asked to show the terminal)
1. `python3 main.py` (Windows: `py main.py`)
2. Menu 2 (health) -> 7 (inject corruption) -> 3 (integrity check) -> 8 (auto recovery)
3. Menu 4 (RAID) -> fail a disk -> replace and rebuild
4. Menu 5 (replication) -> fail over -> fail back
5. Menu 9 (benchmark), 10 (DR analysis), 11 (reports)

## Likely questions
- **Is this a real SAN?** No. It simulates SAN data-protection concepts in software, and the code is labelled that way.
- **Why isn't RAID enough?** It protects against disk failure, not deletion, corruption written to both disks, or site loss.
- **Why check checksums before replicating?** So corrupted data is not copied over a good replica.
- **What are RTO and RPO?** RTO is how fast you recover; RPO is how much data you can afford to lose.
