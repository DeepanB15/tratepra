from datetime import datetime, timezone
from threading import Lock
import time

from app.connectors.base import BaseConnector, make_record, parse_time_range
from app.core.exceptions import ConnectorError

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
SEARCH_QUOTA_COST = 100  # units per search.list call
VIDEOS_QUOTA_COST = 1
CACHE_TTL_SECONDS = 6 * 3600

_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_cache_lock = Lock()
_quota_used = 0


def quota_used() -> int:
    return _quota_used


class YouTubeConnector(BaseConnector):
    key = "youtube"
    name = "YouTube"

    def is_configured(self) -> bool:
        return bool(self.settings.youtube_api_key)

    def unavailable_reason(self) -> str:
        return "YOUTUBE_API_KEY is not set"

    def search(self, query: str, time_range: str = "30d", max_results: int = 25) -> list[dict]:
        global _quota_used
        if not self.is_configured():
            raise ConnectorError(self.key, self.unavailable_reason(), kind="unavailable")

        ck = (query.lower().strip(), time_range)
        with _cache_lock:
            hit = _cache.get(ck)
            if hit and time.time() - hit[0] < CACHE_TTL_SECONDS:
                return hit[1]

        published_after = (datetime.now(timezone.utc) - parse_time_range(time_range)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "relevance",
            "maxResults": min(max_results, 50),
            "publishedAfter": published_after,
            "key": self.settings.youtube_api_key,
        }
        resp = self._request("GET", SEARCH_URL, params=params)
        _quota_used += SEARCH_QUOTA_COST
        items = resp.json().get("items", [])
        ids = [i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId")]

        stats: dict[str, dict] = {}
        if ids:
            vresp = self._request(
                "GET",
                VIDEOS_URL,
                params={"part": "statistics", "id": ",".join(ids), "key": self.settings.youtube_api_key},
            )
            _quota_used += VIDEOS_QUOTA_COST
            stats = {v["id"]: v.get("statistics", {}) for v in vresp.json().get("items", [])}

        records = []
        for i in items:
            vid = i.get("id", {}).get("videoId")
            if not vid:
                continue
            sn = i.get("snippet", {})
            st = stats.get(vid, {})
            engagement = {k: int(st[k]) for k in ("viewCount", "likeCount", "commentCount") if k in st}
            pub = sn.get("publishedAt")
            records.append(
                make_record(
                    self.key,
                    vid,
                    sn.get("title", ""),
                    f"https://www.youtube.com/watch?v={vid}",
                    description=sn.get("description") or None,
                    published_at=datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else None,
                    engagement=engagement,
                    metadata={"channel": sn.get("channelTitle"), "quota_used_total": _quota_used},
                )
            )
        with _cache_lock:
            _cache[ck] = (time.time(), records)
        return records
