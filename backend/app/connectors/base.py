from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any
import re

import httpx

from app.core.config import get_settings
from app.ingestion.resilience import request_with_retry


def parse_time_range(time_range: str) -> timedelta:
    """'7d' -> 7 days, '12h' -> 12 hours, '2w' -> 2 weeks. Defaults to 30 days."""
    m = re.fullmatch(r"(\d+)([dhw])", time_range or "")
    if not m:
        return timedelta(days=30)
    n, unit = int(m.group(1)), m.group(2)
    return {"d": timedelta(days=n), "h": timedelta(hours=n), "w": timedelta(weeks=n)}[unit]


def make_record(
    source: str,
    external_id: str,
    title: str,
    url: str | None,
    description: str | None = None,
    published_at: datetime | None = None,
    engagement: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Unified connector record. Missing fields stay None; nothing is invented."""
    return {
        "source": source,
        "external_id": external_id,
        "title": title,
        "description": description,
        "url": url,
        "published_at": published_at,
        "collected_at": datetime.now(timezone.utc),
        "engagement": engagement or {},
        "metadata": metadata or {},
    }


class BaseConnector(ABC):
    key: str = ""
    name: str = ""

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return True

    def availability(self) -> dict[str, Any]:
        configured = self.is_configured()
        return {
            "key": self.key,
            "name": self.name,
            "available": configured,
            "reason": None if configured else self.unavailable_reason(),
        }

    def unavailable_reason(self) -> str:
        return "Not configured"

    @abstractmethod
    def search(self, query: str, time_range: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    # --- shared HTTP helper: timeouts, backoff retries, quota/rate-limit mapping (see ingestion/resilience.py) ---
    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        s = self.settings
        return request_with_retry(
            method,
            url,
            source=self.key,
            timeout=s.http_timeout_seconds,
            max_retries=s.http_max_retries,
            **kwargs,
        )
