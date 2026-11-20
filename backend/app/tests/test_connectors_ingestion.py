from datetime import datetime, timezone

from app.connectors.base import make_record, parse_time_range
from app.connectors.google_news import GoogleNewsConnector
from app.connectors.google_trends import GoogleTrendsConnector
from app.connectors.reddit import RedditConnector
from app.connectors.youtube import YouTubeConnector
from app.core.exceptions import ConnectorError
from app.ingestion.deduplicator import dedupe_batch
from app.ingestion.normalizer import canonical_url, normalize_record
from app.intelligence.preprocessor import prepare

import pytest


def test_canonical_url_strips_tracking_and_www():
    assert canonical_url("https://www.Example.com/a/?utm_source=x&id=2#frag") == "https://example.com/a?id=2"
    assert canonical_url(None) is None


def test_normalize_keeps_none_for_missing_fields():
    rec = make_record("google_news", "id1", "<b>Hello</b> world", "https://x.com/a", description=None)
    doc = normalize_record(rec)
    assert doc["title"] == "Hello world"
    assert doc["published_at"] is None and doc["engagement"] == {}


def test_dedupe_batch_by_id_url_and_hash():
    def d(ext, url, title):
        return normalize_record(make_record("google_news", ext, title, url, description="same"))

    docs = [d("1", "https://a.com/x", "One"), d("1", "https://a.com/y", "Two"), d("2", "https://a.com/x?utm_source=z", "Three"), d("3", "https://b.com", "One")]
    out = dedupe_batch(docs)
    assert [x["external_id"] for x in out] == ["1"]


def test_preprocess_filters_short_non_english_duplicates():
    docs = [
        {"id": 1, "text": "AI coding agents are changing software development"},
        {"id": 2, "text": "short"},
        {"id": 3, "text": "人工智能代理正在改变软件开发的方式今天人工智能代理正在改变软件开发的方式今天"},
        {"id": 4, "text": "ai coding agents are changing software development"},
    ]
    kept, stats = prepare(docs)
    assert [k["id"] for k in kept] == [1]
    assert stats["too_short"] == 1 and stats["non_english"] == 1 and stats["duplicate"] == 1


def test_parse_time_range():
    assert parse_time_range("7d").days == 7
    assert parse_time_range("2w").days == 14
    assert parse_time_range("bogus").days == 30


def test_unconfigured_connectors_report_unavailable_not_fake_data():
    yt, rd, gt = YouTubeConnector(), RedditConnector(), GoogleTrendsConnector()
    yt.settings.youtube_api_key = ""
    rd.settings.reddit_client_id = ""
    gt.settings.google_trends_api_key = ""
    gt.settings.google_trends_allow_fallback = False
    for c in (yt, rd, gt):
        assert c.availability()["available"] is False
        with pytest.raises(ConnectorError) as e:
            c.search("ai", "7d")
        assert e.value.kind == "unavailable"


def test_google_news_parses_rss(monkeypatch):
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>AI agents surge</title><link>https://news.example.com/a</link>
    <guid>g1</guid><pubDate>Tue, 10 Nov 2026 10:00:00 GMT</pubDate>
    <description>&lt;p&gt;Body text&lt;/p&gt;</description></item>
    <item><title>No date item</title><link>https://news.example.com/b</link><guid>g2</guid></item>
    </channel></rss>"""

    class R:
        content = rss

    c = GoogleNewsConnector()
    monkeypatch.setattr(c, "_request", lambda *a, **k: R())
    recs = c.search("ai agents", "7d")
    assert len(recs) == 2
    assert recs[0]["published_at"] == datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
    assert recs[1]["published_at"] is None  # not manufactured
    assert recs[0]["description"] == "Body text"
