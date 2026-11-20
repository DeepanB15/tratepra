from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
import re
from html import unescape

import feedparser

from app.connectors.base import BaseConnector, make_record, parse_time_range
from app.core.exceptions import ConnectorError

_TAG = re.compile(r"<[^>]+>")


class GoogleNewsConnector(BaseConnector):
    key = "google_news"
    name = "Google News"

    def build_url(self, query: str, time_range: str) -> str:
        days = max(1, int(parse_time_range(time_range).total_seconds() // 86400))
        q = quote_plus(f"{query} when:{days}d")
        return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

    @staticmethod
    def _parse_date(entry) -> datetime | None:
        raw = entry.get("published")
        if not raw:
            return None
        try:
            dt = parsedate_to_datetime(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None

    def search(self, query: str, time_range: str = "30d") -> list[dict]:
        url = self.build_url(query, time_range)
        resp = self._request("GET", url, headers={"User-Agent": "Tratepra/1.0"})
        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            raise ConnectorError(self.key, f"Invalid feed: {feed.get('bozo_exception')}")

        records = []
        for e in feed.entries:
            link = e.get("link")
            ext_id = e.get("id") or link
            if not ext_id or not e.get("title"):
                continue
            desc = unescape(_TAG.sub(" ", e.get("summary", ""))).strip() or None
            publisher = (e.get("source") or {}).get("title") if isinstance(e.get("source"), dict) else None
            records.append(
                make_record(
                    self.key,
                    ext_id,
                    e["title"],
                    link,
                    description=desc,
                    published_at=self._parse_date(e),
                    metadata={"publisher": publisher, "feed_url": url},
                )
            )
        return records
