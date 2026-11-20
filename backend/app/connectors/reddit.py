"""Reddit connector (OAuth, application-only).

Reddit requires app registration and permission for commercial use. Verify approval
before using this in a monetized product. Without credentials the connector reports
"unavailable" and returns nothing.
"""
from datetime import datetime, timezone
import time

from app.connectors.base import BaseConnector, make_record, parse_time_range
from app.core.exceptions import ConnectorError

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
SEARCH_URL = "https://oauth.reddit.com/search"


class RedditConnector(BaseConnector):
    key = "reddit"
    name = "Reddit"

    _token: str | None = None
    _token_expiry: float = 0.0

    def is_configured(self) -> bool:
        return bool(self.settings.reddit_client_id and self.settings.reddit_client_secret)

    def unavailable_reason(self) -> str:
        return "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set (app registration and approval required)"

    def _get_token(self) -> str:
        cls = RedditConnector
        if cls._token and time.time() < cls._token_expiry - 30:
            return cls._token
        resp = self._request(
            "POST",
            TOKEN_URL,
            auth=(self.settings.reddit_client_id, self.settings.reddit_client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self.settings.reddit_user_agent},
        )
        data = resp.json()
        cls._token = data["access_token"]
        cls._token_expiry = time.time() + int(data.get("expires_in", 3600))
        return cls._token

    @staticmethod
    def _t_param(time_range: str) -> str:
        days = parse_time_range(time_range).days
        return "day" if days <= 1 else "week" if days <= 7 else "month" if days <= 31 else "year"

    def search(self, query: str, time_range: str = "30d", limit: int = 50) -> list[dict]:
        if not self.is_configured():
            raise ConnectorError(self.key, self.unavailable_reason(), kind="unavailable")
        token = self._get_token()
        resp = self._request(
            "GET",
            SEARCH_URL,
            params={"q": query, "sort": "relevance", "t": self._t_param(time_range), "limit": limit, "type": "link"},
            headers={"Authorization": f"bearer {token}", "User-Agent": self.settings.reddit_user_agent},
        )
        records = []
        for child in resp.json().get("data", {}).get("children", []):
            d = child.get("data", {})
            if not d.get("id") or not d.get("title"):
                continue
            created = d.get("created_utc")
            records.append(
                make_record(
                    self.key,
                    d["id"],
                    d["title"],
                    f"https://www.reddit.com{d.get('permalink', '')}",
                    description=(d.get("selftext") or None),
                    published_at=datetime.fromtimestamp(created, tz=timezone.utc) if created else None,
                    engagement={
                        "score": d.get("score"),
                        "num_comments": d.get("num_comments"),
                        "upvote_ratio": d.get("upvote_ratio"),
                    },
                    metadata={"subreddit": d.get("subreddit"), "author_hidden": True},
                )
            )
        return records
