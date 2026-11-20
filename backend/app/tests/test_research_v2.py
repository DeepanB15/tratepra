"""Unit tests for query processing, evidence selection and claim-level verification (pure logic)."""
from types import SimpleNamespace

import pytest

from app.research.citation_validator import EvidenceRef, verify_answer
from app.research.context_builder import select_evidence
from app.research.query_processor import InvalidQuery, extract_phrases, process_query
from app.research.ranker import normalize_semantic
from app.research.retriever import build_tsquery


def test_phrases_quoted_and_entities():
    assert "claude code" in extract_phrases("What is Claude Code doing")
    assert extract_phrases('news about "open weight models"') == ["open weight models"]


@pytest.mark.parametrize("q", ["", "  ", "ab", "the a of"])
def test_invalid_queries(q):
    with pytest.raises(InvalidQuery):
        process_query(q)


def test_tsquery_is_sanitised():
    q = build_tsquery(["rust", "c++;drop"], ["claude code"])
    assert q == "rust | cdrop | (claude <-> code)"
    assert build_tsquery([], []) is None


def test_normalize_semantic_spread_and_small_pool():
    assert normalize_semantic([10, 20]) == [10, 20]
    out = normalize_semantic([20, 30, 40, 50, 60])
    assert out[0] == 0 and out[-1] == 100


def _item(key, title, score):
    doc = SimpleNamespace(title=title, description="", published_at=None)
    return SimpleNamespace(candidate=SimpleNamespace(source_key=key, document=doc), score=score)


def test_select_evidence_source_quota_and_diversity():
    ranked = [_item("google_news", f"Distinct headline number {i} about topic {i}", 90 - i) for i in range(8)]
    ranked.insert(2, _item("google_news", "Distinct headline number 0 about topic 0", 87))  # near-duplicate title
    ranked.append(_item("reddit", "Reddit thread on a different angle entirely", 60))
    sel = select_evidence(ranked, max_items=6, max_per_source=5)
    assert any(i.candidate.source_key == "reddit" for i in sel)  # quota slot
    assert sum(i.candidate.source_key == "google_news" for i in sel) <= 5
    titles = [i.candidate.document.title for i in sel]
    assert len(titles) == len(set(titles))
    assert [i.score for i in sel] == sorted((i.score for i in sel), reverse=True)


EVIDENCE = [
    EvidenceRef("Terminal coding agents gain adoption among developers", "https://a.example/1"),
    EvidenceRef("Some doc without a link about pricing", None),
]


def test_verify_answer_flags_uncited_weak_and_invalid():
    v = verify_answer(
        "Terminal coding agents are gaining adoption among developers [1]. "
        "Quantum computers will replace GPUs [1]. A fact with nothing cited. Pricing doubled [2]. "
        "The evidence is insufficient on pricing.",
        ["Developers adopt coding agents [1]", "Made up [9]"],
        EVIDENCE,
    )
    reasons = {u["text"]: u["reason"] for u in v.unverified}
    assert "Quantum computers will replace GPUs [1]." in reasons          # weak overlap
    assert "A fact with nothing cited." in reasons                         # no citation
    assert any("openable" in r for r in reasons.values())                  # evidence has no URL / ref 9
    assert "Made up" in " ".join(u["text"] for u in v.unverified)          # invalid-only ref is not "meta"
    assert v.cited == {1}
    assert "insufficient" in v.answer                                      # honest meta sentence kept
    assert v.stats["claims_unverified"] == len(v.unverified)


def test_verify_answer_nothing_verifiable_is_explicit():
    v = verify_answer("Totally unsupported statement here.", [], EVIDENCE)
    assert "No claim" in v.answer and v.unverified
