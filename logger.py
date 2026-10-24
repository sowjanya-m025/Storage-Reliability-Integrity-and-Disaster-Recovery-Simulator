"""Operation log (history of everything the simulator does)."""
from datetime import datetime
import config


def log(msg, level="INFO"):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = "%s [%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), level, msg)
    with open(config.LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def tail(n=15):
    if not config.LOG_FILE.exists():
        return []
    with open(config.LOG_FILE, "r", encoding="utf-8") as f:
        return [l.rstrip("\n") for l in f.readlines()[-n:]]
