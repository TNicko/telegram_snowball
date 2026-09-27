from __future__ import annotations


def format_bytes(size: int | float | None) -> str | None:
    """Human file size using 1024-based KB / MB / GB."""
    if size is None:
        return None
    try:
        value = float(size)
    except (TypeError, ValueError):
        return None
    if value < 0 or value != value:
        return None
    units = ("B", "KB", "MB", "GB", "TB")
    n = value
    unit = units[0]
    for unit in units:
        if n < 1024 or unit == units[-1]:
            break
        n /= 1024
    if unit == "B":
        return f"{int(round(n))} B"
    if n >= 10:
        return f"{n:.0f} {unit}"
    text = f"{n:.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return f"{text} {unit}"
