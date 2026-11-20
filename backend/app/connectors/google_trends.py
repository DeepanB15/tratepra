"""Google Trends provider.

Google's official Trends API is an alpha restricted to selected testers, so this
connector is an isolated provider interface:
  1. Official API (only if GOOGLE_TRENDS_API_KEY is set and access is confirmed).
  2. Optional experimental fallback via pytrends (GOOGLE_TRENDS_ALLOW_FALLBACK=true),
     clearly labelled in record metadata. The scoring system never assumes either works.
If neither is available the connector reports "unavailable" rather than simulating data.
"""
from datetime import datetime, timezone
from typing import Any

from app.connectors.base import BaseConnector, make_record, parse_time_range
from app.core.exceptions import ConnectorError, ConnectorUnavailable

# Google documents the Trends API as an alpha for selected testers and publishes no public endpoint
# or schema. The endpoint therefore comes from configuration (GOOGLE_TRENDS_API_ENDPOINT) and
# the response parser is deliberately strict: an unrecognised response is reported as an error,
# never guessed at.


class GoogleTrendsConnector(BaseConnector):
    key = "google_trends"
    name = "Google Trends"

    def _has_official(self) -> bool:
        # A key alone is not enough: without the endpoint granted with your access we cannot call anything.
        return bool(self.settings.google_trends_api_key and self.settings.google_trends_api_endpoint)

    def _has_fallback(self) -> bool:
        if not self.settings.google_trends_allow_fallback:
            return False
        try:
            import pytrends  # noqa: F401
        except ImportError:
            return False
        return True

    def is_configured(self) -> bool:
        return self._has_official() or self._has_fallback()

    def unavailable_reason(self) -> str:
        s = self.settings
        if s.google_trends_api_key and not s.google_trends_api_endpoint:
            return "GOOGLE_TRENDS_API_KEY is set but GOOGLE_TRENDS_API_ENDPOINT is not (use the endpoint from your alpha access)"
        return (
            "No official Google Trends API access (alpha, selected testers) and the "
            "experimental fallback is disabled or pytrends is not installed"
        )

    def search(self, query: str, time_range: str = "30d") -> list[dict[str, Any]]:
        if self._has_official():
            return self._official(query, time_range)
        if self._has_fallback():
            return self._fallback(query, time_range)
        raise ConnectorUnavailable(self.key, self.unavailable_reason())

    def _official(self, query: str, time_range: str) -> list[dict[str, Any]]:
        end = datetime.now(timezone.utc)
        start = end - parse_time_range(time_range)
        resp = self._request(
            "GET",
            self.settings.google_trends_api_endpoint,
            params={
                "terms": query,
                "timeline_resolution": "DAY",
                "time_restriction.start_date": start.date().isoformat(),
                "time_restriction.end_date": end.date().isoformat(),
                "key": self.settings.google_trends_api_key,
            },
        )
        try:
            lines = resp.json()["lines"]
            points = lines[0]["points"] if lines else []
        except (KeyError, IndexError, TypeError, ValueError):
            raise ConnectorError(self.key, "Unrecognised Google Trends response format; the parser needs adjusting to your API version")
        return self._to_records(query, points, provider="official_api", experimental=False)

    def _fallback(self, query: str, time_range: str) -> list[dict[str, Any]]:
        from pytrends.request import TrendReq  # experimental, unofficial

        days = max(1, int(parse_time_range(time_range).days or 1))
        timeframe = "today 1-m" if days <= 30 else "today 3-m" if days <= 90 else "today 12-m"
        try:
            py = TrendReq(hl="en-US", tz=0, timeout=(5, 15))
            py.build_payload([query], timeframe=timeframe)
            df = py.interest_over_time()
        except Exception as exc:  # unofficial API fails unpredictably
            raise ConnectorError(self.key, f"Experimental fallback failed: {exc}")
        if df.empty:
            return []
        points = [
            {"date": idx.date().isoformat(), "value": int(row[query])} for idx, row in df.iterrows()
        ]
        return self._to_records(query, points, provider="pytrends_experimental", experimental=True)

    def _to_records(self, query: str, points: list[dict], provider: str, experimental: bool) -> list[dict]:
        records = []
        for p in points:
            date_s = p.get("date") or p.get("time")
            value = p.get("value")
            if date_s is None or value is None:
                continue
            published = datetime.fromisoformat(str(date_s)).replace(tzinfo=timezone.utc)
            records.append(
                make_record(
                    self.key,
                    f"{query.lower()}|{date_s}",
                    f"Search interest for '{query}' on {date_s}",
                    None,
                    description=None,
                    published_at=published,
                    engagement={"search_interest": float(value)},
                    metadata={
                        "provider": provider,
                        "experimental": experimental,
                        "query": query,
                        "scale": "0-100 relative",
                    },
                )
            )
        return records
