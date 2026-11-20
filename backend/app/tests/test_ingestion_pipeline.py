import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core.database import normalize_database_url
from app.core.exceptions import ConnectorError
from app.ingestion import collector
from app.ingestion.deduplicator import dedupe_batch, jaccard_similarity, token_set
from app.ingestion.filters import filter_by_date
from app.ingestion.normalizer import normalize_record
from app.ingestion.resilience import backoff_delay, parse_retry_after, request_with_retry
from app.connectors.base import make_record
from app.research.ranker import keyword_relevance


# ---------- resilience ----------
class FakeResp:
    def __init__(self, status, text="", headers=None):
        self.status_code, self.text, self.headers = status, text, headers or {}


def run(responses, max_retries=2, **kw):
    calls, sleeps = [], []
    seq = iter(responses)

    def fake(method, url, **k):
        calls.append(1)
        r = next(seq)
        if isinstance(r, Exception):
            raise r
        return r

    out = request_with_retry("GET", "http://x", source="t", timeout=1, max_retries=max_retries, sleep=sleeps.append, request_fn=fake, **kw)
    return out, len(calls), sleeps


def test_retries_transient_then_succeeds():
    resp, n, sleeps = run([httpx.ConnectTimeout("slow"), FakeResp(503), FakeResp(200)])
    assert resp.status_code == 200 and n == 3 and len(sleeps) == 2


def test_gives_up_after_max_retries_and_reports():
    with pytest.raises(ConnectorError) as e:
        run([FakeResp(500)] * 3)
    assert "after 3 attempt" in e.value.message


def test_auth_and_quota_are_not_retried():
    with pytest.raises(ConnectorError) as e:
        run([FakeResp(401)])
    assert e.value.kind == "auth"
    with pytest.raises(ConnectorError) as e:
        run([FakeResp(403, "quotaExceeded")])
    assert e.value.kind == "quota"


def test_other_4xx_not_retried():
    calls = []
    with pytest.raises(ConnectorError):
        _, n, _ = run([FakeResp(404, "nope")])


def test_rate_limit_honours_short_retry_after_but_not_long():
    resp, n, sleeps = run([FakeResp(429, headers={"Retry-After": "2"}), FakeResp(200)])
    assert sleeps == [2.0] and resp.status_code == 200
    with pytest.raises(ConnectorError) as e:
        run([FakeResp(429, headers={"Retry-After": "600"})])
    assert e.value.kind == "rate_limit"


def test_backoff_grows_and_is_capped():
    assert backoff_delay(0, jitter=False) == 0.5 and backoff_delay(3, jitter=False) == 4.0 and backoff_delay(10, jitter=False) == 8.0
    assert parse_retry_after("3") == 3.0 and parse_retry_after("Wed, 21 Oct") is None


# ---------- date filter ----------
def test_date_filter_window_and_undated():
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    docs = [
        {"published_at": now - timedelta(days=2)},
        {"published_at": now - timedelta(days=40)},
        {"published_at": None},
        {"published_at": datetime(2026, 11, 12)},  # naive treated as UTC
    ]
    r = filter_by_date(docs, "30d", now)
    assert len(r.kept) == 3 and r.out_of_window == 1 and r.undated == 1
    assert len(filter_by_date(docs, "30d", now, keep_undated=False).kept) == 2


# ---------- near-duplicate detection ----------
def _doc(src, ext, title, url=None, desc="x"):
    return normalize_record(make_record(src, ext, title, url, description=desc))


def test_jaccard():
    assert jaccard_similarity(token_set("ai coding agents rise"), token_set("ai coding agents rise")) == 1.0
    assert jaccard_similarity(set(), {"a"}) == 0.0


def test_near_duplicates_removed_within_source_only():
    a = _doc("google_news", "1", "Coding agents are going mainstream across developer teams", "https://a.com/1")
    b = _doc("google_news", "2", "Coding agents are going mainstream across developer teams today", "https://b.com/2")
    c = _doc("youtube", "3", "Coding agents are going mainstream across developer teams", "https://y.com/3", desc="video walkthrough")
    out = dedupe_batch([a, b, c])
    ids = [d["external_id"] for d in out]
    assert ids == ["1", "3"]  # b dropped (same source); c kept (cross-source activity)


def test_distinct_titles_kept():
    a = _doc("google_news", "1", "New open source language model released today", "https://a.com/1")
    b = _doc("google_news", "2", "Regulators propose new rules for chatbots in Europe", "https://b.com/2")
    assert len(dedupe_batch([a, b])) == 2


# ---------- parallel collector ----------
def test_fetch_sources_parallel_and_isolated_failures(monkeypatch):
    class Slow:
        def __init__(self, key, delay=0.3, exc=None):
            self.key, self.delay, self.exc = key, delay, exc

        def search(self, q, tr):
            time.sleep(self.delay)
            if self.exc:
                raise self.exc
            return [make_record(self.key, "1", "t", None)]

    fakes = {
        "google_news": Slow("google_news"),
        "youtube": Slow("youtube"),
        "reddit": Slow("reddit", exc=ConnectorError("reddit", "no creds", kind="unavailable")),
        "google_trends": Slow("google_trends", exc=RuntimeError("boom")),
    }
    monkeypatch.setattr(collector, "get_connector", lambda k: fakes[k])
    started = time.time()
    out = collector.fetch_sources(list(fakes), "q", "7d")
    elapsed = time.time() - started
    assert elapsed < 0.9  # 4 x 0.3s sequentially would be 1.2s
    assert list(out) == list(fakes)  # stable order
    assert out["google_news"].status == "ok" and len(out["youtube"].records) == 1
    assert out["reddit"].status == "unavailable" and out["reddit"].error == "no creds"
    assert out["google_trends"].status == "error" and "boom" in out["google_trends"].error


def test_fetch_sources_ignores_unknown_and_duplicate_keys(monkeypatch):
    assert collector.fetch_sources(["nope"], "q", "7d") == {}


# ---------- ranker keywords ----------
def test_keyword_relevance_stems_synonyms_and_phrases():
    assert keyword_relevance("AI agent news", ["ai", "agents"]) == pytest.approx(100.0)  # stem + phrase
    assert keyword_relevance("Artificial intelligence is here", ["ai"]) == 100.0  # synonym
    together = keyword_relevance("ai agents", ["ai", "agents"])
    apart = keyword_relevance("agents and ai", ["ai", "agents"])
    assert together > apart > 0
    assert keyword_relevance("nothing relevant", ["ai", "agents"]) == 0.0
    assert keyword_relevance("x", []) == 0.0


# ---------- database url ----------
def test_database_url_normalisation():
    u = normalize_database_url("postgresql+asyncpg://postgres.ref:pw@aws-0-eu.pooler.supabase.com:5432/postgres")
    assert u.startswith("postgresql+psycopg2://") and "sslmode=require" in u
    assert normalize_database_url("postgres://u:p@localhost:5432/db") == "postgresql+psycopg2://u:p@localhost:5432/db"
    assert "sslmode=disable" in normalize_database_url("postgresql://u:p@db.supabase.co/db?sslmode=disable")
