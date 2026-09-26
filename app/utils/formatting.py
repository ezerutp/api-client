from datetime import datetime


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "—"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def format_duration(ms: float | None) -> str:
    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms:.0f} ms"
    if ms < 60_000:
        return f"{ms / 1000:.2f} s"
    return f"{ms / 60_000:.1f} min"


def format_relative_time(moment: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now(moment.tzinfo)
    seconds = int((now - moment).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86_400:
        return f"{seconds // 3600} h ago"
    if seconds < 7 * 86_400:
        days = seconds // 86_400
        return "yesterday" if days == 1 else f"{days} days ago"
    return moment.strftime("%b %d, %Y")
