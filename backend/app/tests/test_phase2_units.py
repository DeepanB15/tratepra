from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.ingestion import article_state as st
from app.ingestion.article_enrichment import enrich_records
from app.ingestion.article_extractor import MAX_ARTICLE_CHARS
from app.ingestion.article_fetcher import fetch_article_outcome
from app.research import evidence_quality as eq
from app.research.claims import EvidenceView, claim_type, detect_contradiction, extract_claims, verify_claim
from app.research.citation_validator import _content_tokens
from app.research.context_builder import build_context, select_evidence_explained
from app.research.dossier_engine import NO_CONTRADICTION_TEXT, build_dossier
from app.research.excerpts import build_excerpt, publisher_of
from app.research.query_processor import process_query

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)


def doc(title="T", desc="d", status="rss_only", article=None, url="https://a.com/x", pub=None, **kw):
    return SimpleNamespace(
        id=kw.get("id", title), title=title, description=desc, normalized_text=f"{title}. {desc}" + (f"\n\n{article}" if article else ""),
        article_status=status, article_text=article, url=url, canonical_url=url, content_hash=str(kw.get("id", title)), published_at=pub or NOW,
        metadata_={}, source=SimpleNamespace(key="google_news"),
    )


def ranked(d, score=80, src="google_news"):
    return SimpleNamespace(candidate=SimpleNamespace(document=d, source_key=src, match="semantic"), score=score, semantic=50, keyword=50, freshness=50, quality=70)


# ---- article states -------------------------------------------------------------------------
def test_article_states_are_distinct_and_rss_is_never_full():
    long = "x" * 1500
    assert st.classify(long, None) == st.FULL
    assert st.classify("y" * 400, None) == st.PARTIAL
    assert st.classify("z" * MAX_ARTICLE_CHARS, None) == st.PARTIAL  # truncated at the cap
    assert st.classify(None, "insufficient_content") == st.TOO_SHORT
    assert st.classify(None, "http_403") == st.FAILED and st.classify(None, "timeout") == st.FAILED
    assert st.classify(None, "blocked_unsafe_url") == st.FAILED
    assert st.classify(None, "unavailable") == st.UNAVAILABLE and st.classify(None, "no_url") == st.UNAVAILABLE
    assert st.classify(None, "not_attempted_limit") == st.RSS_ONLY
    s = st.build_state(None, "http_500")
    assert s["article_text"] is None and s["article_text_hash"] is None and s["article_failure_reason"] == "http_500"
    s = st.build_state(long, None)
    assert s["article_text_hash"] == st.text_hash(long) and s["article_extracted_at"] is not None


def test_normalized_text_composition_matches_indexed_text():
    assert st.compose_normalized_text("Title. desc", "Body.") == "Title. desc\n\nBody."
    assert st.compose_normalized_text("Title. desc", None) == "Title. desc"


def test_enrichment_records_failure_reason_and_limit():
    recs = [{"source": "google_news", "url": f"https://a.com/{i}", "description": "d", "metadata": {}} for i in range(7)]
    from app.ingestion.article_fetcher import FetchOutcome

    with patch("app.ingestion.article_enrichment.fetch_article_outcome", return_value=FetchOutcome(None, "http_404")):
        out = enrich_records(recs)
    assert out[0]["_article"]["article_status"] == "failed" and out[0]["_article"]["article_failure_reason"] == "http_404"
    assert out[6]["_article"]["article_status"] == "rss_only"  # beyond the per-run limit: not attempted


def test_fetch_outcome_reports_reasons_and_keeps_ssrf_protection():
    assert fetch_article_outcome("http://127.0.0.1/a").reason == "blocked_unsafe_url"
    with patch("app.ingestion.article_fetcher._public_http_url", side_effect=[True, False]):
        with patch("app.ingestion.article_fetcher.httpx.Client") as cc:
            resp = cc.return_value.__enter__.return_value.stream.return_value.__enter__.return_value
            resp.status_code, resp.headers = 302, {"location": "http://10.0.0.1/"}
            assert fetch_article_outcome("https://e.com/a").reason == "blocked_unsafe_redirect"


# ---- excerpts / context ---------------------------------------------------------------------
def test_excerpt_uses_relevant_article_sentences_and_is_bounded():
    art = "Filler opening sentence about nothing relevant at all. " * 20 + "Banks adopted autonomous refactoring pipelines widely. " + "More filler text appears afterwards in bulk. " * 20
    ex = build_excerpt(doc(status="full", article=art), ["banks", "refactoring"])
    assert ex.basis == "article" and "autonomous refactoring" in ex.text and len(ex.text) <= 700


def test_rss_only_failed_and_short_documents_use_rss_description():
    for status in ("rss_only", "failed", "too_short", "unavailable"):
        ex = build_excerpt(doc(desc="feed text", status=status, article="should be ignored " * 30), ["feed"])
        assert ex.basis == "rss" and ex.text == "feed text"


def test_context_shows_basis_and_returns_matching_excerpts():
    ctx = build_context([ranked(doc(status="full", article="Some long article sentence about agents here. " * 5)), ranked(doc(title="Other", desc="blurb"))], ["agents"])
    assert "article excerpt" in ctx.text and "RSS summary" in ctx.text and [e.basis for e in ctx.excerpts] == ["article", "rss"]


def test_selection_reports_rejection_reasons_and_keeps_opposite_polarity():
    a = ranked(doc(title="Developers use coding agents in terminals", id=1, url="https://a.com/1"), 90)
    dup = ranked(doc(title="Developers use coding agents in terminals", id=2, url="https://b.com/2"), 80)
    opp = ranked(doc(title="Developers do not use coding agents in terminals", id=3, url="https://c.com/3"), 70)
    same_url = ranked(doc(title="Completely different words here today", id=4, url="https://a.com/1"), 60)
    chosen, rej = select_evidence_explained([a, dup, opp, same_url], max_items=10)
    assert [c.candidate.document.id for c in chosen] == [1, 3]
    assert rej[2] == "near_duplicate_title" and rej[4] == "duplicate_url_or_content"
    _, rej2 = select_evidence_explained([a, opp], max_items=1)
    assert rej2[3] == "below_selection_limit"


# ---- query processing -----------------------------------------------------------------------
def test_query_processing_keeps_original_and_extracts_entities():
    pq = process_query("How is OpenAI using GPT-5 for Claude Code in the last 2 weeks?", topic_ids=["t1"])
    assert pq.original.startswith("How is OpenAI") and pq.time_range == "14d" and pq.topic_ids == ["t1"]
    assert {"openai", "gpt-5", "claude code"} <= set(pq.entities)
    assert "how" not in pq.entities


# ---- claims ---------------------------------------------------------------------------------
def views(*texts):
    return [EvidenceView(i, f"k{i}", "https://a.com/x", t, f"p{i}") for i, t in enumerate(texts, start=1)]


def test_claim_statuses():
    ev = views("Developers adopt coding agents quickly in terminals across many teams. Sentence two here.")
    assert verify_claim("Developers adopt coding agents quickly [1].", "overview", ev).status == "supported"
    assert verify_claim("Gardening robots love sunshine [1].", "overview", ev).status == "unverified"
    assert verify_claim("Developers adopt coding agents quickly.", "overview", ev).status == "unverified"  # uncited
    assert verify_claim("Developers adopt coding agents [7].", "overview", ev).status == "unverified"  # invalid reference
    assert verify_claim("Anything [1].", "overview", []).status == "insufficient_evidence"
    part = verify_claim("Developers adopt coding agents quickly while regulators publish unrelated bulletins monthly [1].", "overview", ev)
    assert part.status in ("partially_supported", "unverified")
    assert verify_claim("Developers adopt coding agents quickly [1].", "overview", views("Too short")).status == "insufficient_evidence"


def test_claim_without_valid_url_cannot_be_supported():
    bad = [EvidenceView(1, "k", None, "Developers adopt coding agents quickly in terminals everywhere.", "p")]
    assert verify_claim("Developers adopt coding agents quickly [1].", "overview", bad).status == "unverified"


def test_contradiction_needs_same_content_and_opposite_polarity():
    claim = "Developers use coding agents in terminals"
    toks = _content_tokens(claim)
    assert detect_contradiction(toks, "Developers do not use coding agents in terminals.", claim) is not None
    assert detect_contradiction(toks, "Developers use coding agents in terminals daily.", claim) is None  # agreement
    assert detect_contradiction(toks, "The weather did not improve in the city today.", claim) is None  # unrelated negation
    c = verify_claim(claim + " [1].", "overview", views("Developers use coding agents in terminals daily at work.", "Developers do not use coding agents in terminals."))
    assert c.status == "contradicted" and any(l.relation == "contradicts" for l in c.links)


def test_claim_type_and_extraction_dedup():
    assert claim_type("Usage grew 40% in March") == "quantitative" and claim_type("Teams may adopt it") == "opinion"
    assert claim_type("It launched last month") == "temporal" and claim_type("The tool is open source") == "factual"
    got = extract_claims("A is true [1]. B is true [2].", ["A is true [1]", "C holds [3]"])
    assert [t for t, _ in got] == ["A is true [1].", "B is true [2].", "C holds [3]"]


# ---- evidence quality -----------------------------------------------------------------------
def item(i, pub, day, status="rss_only", key=None):
    return eq.EvidenceItem(key=key if key is not None else f"u{i}", title=f"t{i}", publisher=pub, day=day, article_status=status)


def test_quality_dimensions_are_separate_with_transparent_labels():
    many = [item(i, f"p{i % 4}", f"2026-11-{10 + i:02d}", "full") for i in range(8)]
    q = eq.assess(many, [{"status": "supported"}] * 5, 14)
    d = q["dimensions"]
    assert d["coverage"]["label"] == "strong" and d["source_diversity"]["label"] == "strong"
    assert d["temporal"]["label"] == "strong" and d["claim_support"]["label"] == "strong"
    assert "confidence" not in q and all(k in q["rules"] for k in d)
    one = eq.assess([item(1, "a", "2026-11-10")], [], 30)
    assert {v["label"] for v in one["dimensions"].values()} == {"insufficient"}
    assert one["dimensions"]["coverage"]["text"] == "Insufficient evidence coverage"


def test_duplicate_repeats_do_not_raise_quality():
    same = [item(i, "a", "2026-11-10", key="same-url") for i in range(10)]
    q = eq.assess(same, [], 30)
    assert q["dimensions"]["coverage"]["unique_documents"] == 1 and q["dimensions"]["coverage"]["duplicates_ignored"] == 9
    assert q["dimensions"]["coverage"]["label"] == "insufficient"
    syndicated = [item(i, "a", "2026-11-10", key=f"u{i}") for i in range(6)]
    for it in syndicated:
        it.title = "Same headline"  # same publisher+title with different URLs is also a repeat
    assert eq.assess(syndicated, [], 30)["dimensions"]["coverage"]["unique_documents"] == 1


def test_publisher_concentration_limits_diversity():
    items = [item(i, "a" if i < 7 else "b", f"2026-11-{i + 1:02d}") for i in range(8)]
    d = eq.assess(items, [], 30)["dimensions"]["source_diversity"]
    assert d["label"] == "limited" and d["top_publisher"] == "a" and d["top_publisher_share"] > 0.8


def test_contradicted_claims_prevent_strong_claim_support():
    q = eq.assess([item(1, "a", "2026-11-10")], [{"status": "supported"}] * 4 + [{"status": "contradicted"}], 30)
    assert q["dimensions"]["claim_support"]["label"] == "moderate"


# ---- dossier engine -------------------------------------------------------------------------
def test_engine_sections_have_no_invented_items_and_default_contradiction_text():
    d1 = doc(title="Coding agents gain adoption", desc="developers adopt coding agents quickly", id="1", url="https://a.com/1")
    d2 = doc(title="Coding agents gain traction", desc="developers adopt coding agents widely", id="2", url="https://b.com/2", pub=NOW - timedelta(days=3))
    sel = [ranked(d1), ranked(d2)]
    ctx = build_context(sel, ["coding", "agents"])
    out = build_dossier(
        subject="coding agents", selected=sel, excerpts=ctx.excerpts, overview="Developers adopt coding agents quickly [1].",
        key_findings=["Developers adopt coding agents widely [2]"], model="m", degraded=False, window_days=30,
        requested_sources=["google_news", "reddit"], entity_seeds=[("coding agents", "query"), ("nonexistent thing", "query")], now=NOW,
    )
    s = out.sections
    assert s["contradictory_evidence"]["text"] == NO_CONTRADICTION_TEXT and s["contradictory_evidence"]["items"] == []
    assert {e["name"] for e in s["key_entities"]["items"]} == {"coding agents"}  # only entities present in the documents
    assert [i["citation"] for i in s["key_developments"]["items"]] == [2, 1]  # chronological
    codes = {g["code"] for g in s["evidence_gaps"]["items"]}
    assert {"few_documents", "feed_summaries_only", "sources_without_evidence"} <= codes
    assert any("Which other publishers" in q or "full articles" in q for q in s["research_questions"]["items"])
    assert {e["document_id"] for e in out.evidence} == {"1", "2"}
    assert all(c.status in ("supported", "partially_supported") for c in out.claims)


def test_engine_empty_evidence():
    out = build_dossier(subject="x", selected=[], excerpts=[], overview="Insufficient evidence", key_findings=[], model="none",
                        degraded=False, window_days=30, requested_sources=["reddit"], now=NOW)
    assert out.sections["overview"]["text"].startswith("Insufficient evidence") and out.evidence == []
    assert out.sections["evidence_gaps"]["items"][0]["code"] == "no_evidence"


def test_publisher_prefers_metadata_then_host():
    d = doc(url="https://www.example.org/a")
    assert publisher_of(d) == "example.org"
    d.metadata_ = {"publisher": "Example Times"}
    assert publisher_of(d) == "Example Times"
