# Data sources

| Source | Access | Auth | Notes |
| --- | --- | --- | --- |
| Google News | RSS search feed | none | Titles/descriptions/dates only; no engagement. Descriptions are short snippets |
| YouTube | Data API v3 `search.list` + `videos.list` | API key | `search.list` costs 100 quota units; searches are cached 6h and quota use is tracked in-process |
| Google Trends | Official API (alpha, selected testers) else optional `pytrends` fallback | access-dependent | Fallback is unofficial, may break, and is labelled `experimental` in record metadata. Scoring never depends on it |
| Reddit | Reddit Data API, app-only OAuth | client id/secret | Commercial use needs Reddit's permission. Check current developer terms and rate limits before production use |

The Google Trends endpoint path in `connectors/google_trends.py` is a placeholder; replace it with the endpoint and parameters from your granted access.

Common record: `source, external_id, title, description, url, published_at, collected_at, engagement, metadata`. Missing fields are `None`.
