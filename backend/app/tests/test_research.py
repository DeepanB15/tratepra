from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.research.citation_validator import validate_all, validate_text
from app.research.context_builder import build_context, select_evidence
from app.research.query_processor import process_query
from app.research.ranker import combine, freshness, keyword_relevance, rank


def test_query_processor_keywords_intent_and_time():
    pq = process_query("What are the emerging trends in AI agents over the past 2 weeks?")
    assert "ai" in pq.keywords and "agents" in pq.keywords
    assert "what" not in pq.keywords
    assert pq.intent == "trend"
    assert pq.time_range == "14d"


def test_query_default_time_range():
    assert process_query("rust async runtimes", "30d").time_range == "30d"


def test_citation_validator_strips_unsupported():
    r = validate_text("Agents grow fast [1][2]. Another claim [7].", n_evidence=3)
    assert r.cited == {1, 2}
    assert r.removed == {7}
    assert "[7]" not in r.text


def test_validate_all_drops_empty_findings():
    ans, findings, cited, removed = validate_all("A [1].", ["B [9]", "C [2]"], 2)
    assert cited == {1, 2} and removed == {9}
    assert "B" in findings[0] and "[9]" not in findings[0]


def test_ranker_formula_and_ordering():
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)

    def cand(title, sem, days_old, q=80.0, src="google_news"):
        doc = SimpleNamespace(
            normalized_text=title,
            title=title,
            description="",
            published_at=now - timedelta(days=days_old),
        )
        return SimpleNamespace(document=doc, source_key=src, semantic=sem, quality=q)

    items = rank([cand("ai agents rising", 60, 20), cand("ai agents coding", 90, 1)], ["ai", "agents"], 30, now)
    assert items[0].candidate.document.title == "ai agents coding"
    s = items[0]
    assert s.score == pytest.approx(0.45 * s.semantic + 0.25 * s.keyword + 0.20 * s.freshness + 0.10 * s.quality)


def test_freshness_unknown_date_not_invented():
    assert freshness(None, 30) == 0.0
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)
    assert freshness(now, 30, now) == 100.0
    assert freshness(now - timedelta(days=30), 30, now) == 0.0


def test_keyword_relevance():
    # token overlap 2/3 (weight .8) + adjacent phrase "ai agents" 1 of 2 bigrams (weight .2)
    assert keyword_relevance("Ai agents ship", ["ai", "agents", "robots"]) == pytest.approx(0.8 * 200 / 3 + 0.2 * 50)


def test_evidence_cap_per_source_and_numbering():
    def item(src, i):
        doc = SimpleNamespace(title=f"t{i}", description="d", published_at=None)
        return SimpleNamespace(candidate=SimpleNamespace(document=doc, source_key=src), score=100 - i)

    ranked = [item("youtube", i) for i in range(8)] + [item("reddit", 9)]
    sel = select_evidence(ranked, max_items=10, max_per_source=3)
    assert sum(1 for s in sel if s.candidate.source_key == "youtube") == 3
    ctx = build_context(sel)
    assert ctx.text.startswith("[1]")
