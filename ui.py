"""Small console helpers (ASCII only so it works in Windows cmd / PowerShell)."""


def banner(title):
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def table(headers, rows):
    rows = [[str(c) for c in r] for r in rows]
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))
    line = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    print(line)
    print("| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |")
    print(line)
    for r in rows:
        print("| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(r)) + " |")
    print(line)


def bar(value, max_value, width=30):
    if max_value <= 0:
        return ""
    n = int(round(width * value / max_value))
    return "#" * n
