"""Fault injection: simulate real-world storage problems."""
import config
from logger import log


def corrupt(disk, rel):
    if not disk.online() or not disk.exists(rel):
        return False
    p = disk.path / rel
    data = bytearray(p.read_bytes()) or bytearray(b"X")
    for i in range(min(8, len(data))):
        data[i] ^= 0xFF                      # flip bits = silent data corruption
    p.write_bytes(bytes(data))
    log("FAULT: silent corruption injected into %s on %s" % (rel, disk.name), "WARN")
    return True


def delete(disk, rel):
    if not disk.online() or not disk.exists(rel):
        return False
    disk.delete(rel)
    log("FAULT: %s deleted from %s" % (rel, disk.name), "WARN")
    return True


def fill(disk, target_pct=92):
    """Add an untracked filler file so the disk reaches target_pct usage."""
    need = int(disk.capacity * target_pct / 100.0) - disk.used()
    if need <= 0:
        return 0
    disk.write("_filler.bin", bytes(need))
    log("FAULT: filler of %.1f MB added to %s (low-space simulation)" % (need / config.MB, disk.name), "WARN")
    return need


def remove_filler(disk):
    if disk.online() and disk.exists("_filler.bin"):
        disk.delete("_filler.bin")
        log("Filler removed from %s" % disk.name)
        return True
    return False
