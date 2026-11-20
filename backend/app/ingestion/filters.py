"""Date-window filtering applied consistently across all connectors.

- Documents with a publication time outside the requested window are dropped.
- Documents without a publication time are reported separately (never given an invented date).
  They are kept by default, because research retrieval falls back to collection time, while
  trend analysis excludes them from temporal windows.
- All comparisons are timezone-aware UTC; original timestamps are preserved.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.connectors.base import parse_time_range


def as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


@dataclass
class DateFilterResult:
    kept: list[dict] = field(default_factory=list)
    out_of_window: int = 0
    undated: int = 0


def filter_by_date(docs: list[dict], time_range: str, now: datetime | None = None, keep_undated: bool = True) -> DateFilterResult:
    now = as_utc(now) if now else datetime.now(timezone.utc)
    cutoff = now - parse_time_range(time_range)
    result = DateFilterResult()
    for d in docs:
        published = d.get("published_at")
        if published is None:
            result.undated += 1
            if keep_undated:
                result.kept.append(d)
            continue
        if as_utc(published) < cutoff:
            result.out_of_window += 1
            continue
        result.kept.append(d)
    return result
