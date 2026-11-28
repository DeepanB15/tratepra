"""Phase 1 pure-logic tests: run key, freshness, identity, naming, diagnostics, validation, explanations."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.intelligence import topic_identity as ti
from app.intelligence.explain import acceleration_assessment, short_summary
from app.intelligence.freshness import ACTIVE, INACTIVE, STALE, FreshnessConfig, activity_state
from app.intelligence.preprocessor import prepare, validate_embedding
from app.intelligence.run_key import analysis_anchor, compute_run_key, document_fingerprint
from app.intelligence.topic_diagnostics import run_diagnostics, topic_cohesion
from app.intelligence.topic_naming import name_topic
from app.services.trend_run_service import sanitize_error

UTC = timezone.utc


# ------------------------------------------------------------------ run key
def test_run_key_is_deterministic_and_order_independent():
    docs = [("b", "h2", "t2", "2026-01-02"), ("a", "h1", "t1", "2026-01-01")]
    fp1, fp2 = document_fingerprint(docs), document_fingerprint(list(reversed(docs)))
    assert fp1 == fp2
    end = datetime(2026, 1, 3, tzinfo=UTC)
    cfg = {"x": 1, "nested": {"b": 2, "a": 1}}
    k1 = compute_run_key(documents_fingerprint=fp1, window_end=end, configuration=cfg)
    k2 = compute_run_key(documents_fingerprint=fp2, window_end=end, configuration={"nested": {"a": 1, "b": 2}, "x": 1})
    assert k1 == k2 and len(k1) == 64


@pytest.mark.parametrize("change", ["docs", "window", "config"])
def test_run_key_changes_when_anything_that_matters_changes(change):
    end = datetime(2026, 1, 3, tzinfo=UTC)
    base = dict(documents_fingerprint=document_fingerprint([("a", "h", "t", "p")]), window_end=end, configuration={"v": 1})
    changed = dict(base)
    if change == "docs":
        changed["documents_fingerprint"] = document_fingerprint([("a", "h-edited", "t", "p")])
    elif change == "window":
        changed["window_end"] = end + timedelta(days=1)
    else:
        changed["configuration"] = {"v": 2}
    assert compute_run_key(**base) != compute_run_key(**changed)


def test_anchor_is_next_utc_midnight_and_timezone_safe():
    assert analysis_anchor(datetime(2026, 11, 26, 3, 0, tzinfo=UTC)) == datetime(2026, 11, 27, tzinfo=UTC)
    assert analysis_anchor(datetime(2026, 11, 26, 23, 59, tzinfo=UTC)) == datetime(2026, 11, 27, tzinfo=UTC)
    ist = timezone(timedelta(hours=5, minutes=30))
    # 2026-11-27 01:00 IST == 2026-11-26 19:30 UTC -> same UTC day as the two above
    assert analysis_anchor(datetime(2026, 11, 27, 1, 0, tzinfo=ist)) == datetime(2026, 11, 27, tzinfo=UTC)
    assert analysis_anchor(datetime(2026, 11, 26, 12, 0)).tzinfo is not None  # naive treated as UTC


# ------------------------------------------------------------------ freshness
T0 = datetime(2026, 11, 1, tzinfo=UTC)


def test_activity_state_by_missed_runs():
    cfg = FreshnessConfig(stale_after_missed_runs=1, inactive_after_missed_runs=4)
    assert activity_state(T0, T0, 0, cfg) == ACTIVE
    assert activity_state(T0, T0, 1, cfg) == STALE
    assert activity_state(T0, T0, 3, cfg) == STALE
    assert activity_state(T0, T0, 4, cfg) == INACTIVE


def test_activity_state_by_age_relative_to_latest_completed_run_not_wall_clock():
    cfg = FreshnessConfig(stale_after_days=14, inactive_after_days=45)
    ref = T0 + timedelta(days=20)
    assert activity_state(T0, ref, 0, cfg) == STALE
    assert activity_state(T0, T0 + timedelta(days=60), 0, cfg) == INACTIVE
    # a long outage (no completed runs since) leaves a topic observed in the latest run ACTIVE
    assert activity_state(T0, T0, 0, cfg) == ACTIVE


def test_never_observed_is_inactive_and_naive_datetimes_are_handled():
    assert activity_state(None, T0, 0) == INACTIVE
    assert activity_state(datetime(2026, 11, 1), datetime(2026, 11, 1, tzinfo=UTC), 0) == ACTIVE


# ------------------------------------------------------------------ identity
def _v(*xs):
    return np.array(xs, dtype=np.float32)


def test_identity_new_when_no_history_or_nothing_similar():
    assert ti.resolve_identities({0: _v(1, 0, 0)}, {}, 0.8, 0.65)[0].outcome == ti.NEW
    d = ti.resolve_identities({0: _v(0, 0, 1)}, {"p": _v(1, 0, 0)}, 0.8, 0.65)[0]
    assert d.outcome == ti.NEW and d.matched_topic_id is None


def test_identity_matched_is_one_to_one():
    prior = {"p1": _v(1, 0, 0), "p2": _v(0, 1, 0)}
    new = {0: _v(1, 0.05, 0), 1: _v(0.02, 1, 0)}
    d = ti.resolve_identities(new, prior, 0.8, 0.65)
    assert d[0].outcome == ti.MATCHED and d[0].matched_topic_id == "p1"
    assert d[1].outcome == ti.MATCHED and d[1].matched_topic_id == "p2"
    assert len({x.matched_topic_id for x in d.values()}) == 2


def test_identity_potential_split_gets_new_id_and_names_its_parent():
    prior = {"p1": _v(1, 0, 0)}
    # A is very close to p1 and claims it. B is ~0.7 similar (between floor and threshold) -> split candidate.
    new = {0: _v(1, 0.05, 0), 1: _v(0.7, 0.714, 0)}
    d = ti.resolve_identities(new, prior, 0.8, 0.65)
    assert d[0].outcome == ti.MATCHED and d[0].matched_topic_id == "p1"
    assert d[1].outcome == ti.SPLIT
    assert d[1].matched_topic_id is None, "a split must never silently inherit the parent's id"
    assert d[1].related_topic_ids == ["p1"]


def test_identity_potential_merge_keeps_one_id_and_lists_the_absorbed_topic():
    prior = {"p1": _v(1, 0, 0), "p2": _v(0.7, 0.714, 0)}
    new = {0: _v(0.95, 0.3, 0)}  # similar to both stored topics, closest to p1
    d = ti.resolve_identities(new, prior, 0.8, 0.65)[0]
    assert d.outcome == ti.MERGE and d.matched_topic_id == "p1" and d.related_topic_ids == ["p2"]


def test_identity_uncertain_when_between_floor_and_threshold_and_nobody_else_claims():
    prior = {"p1": _v(1, 0, 0)}
    d = ti.resolve_identities({0: _v(0.7, 0.714, 0)}, prior, 0.8, 0.65)[0]
    assert d.outcome == ti.UNCERTAIN and d.matched_topic_id is None and d.related_topic_ids == ["p1"]
    assert 0.65 <= d.similarity < 0.8


def test_identity_decision_is_serialisable():
    d = ti.resolve_identities({0: _v(1, 0, 0)}, {"p": _v(1, 0, 0)}, 0.8, 0.65)[0].as_dict()
    assert d["outcome"] == "matched" and isinstance(d["similarity"], float)


# ------------------------------------------------------------------ naming
def test_naming_uses_specific_terms_and_measures_coverage():
    texts = ["Kubernetes operators simplify scaling", "New kubernetes operators released", "Operator pattern for kubernetes"]
    n = name_topic(["kubernetes operators", "operators", "kubernetes", "release", "scaling"], texts)
    assert n.name == "Kubernetes Operators / Release"  # overlapping unigrams skipped; bigram lead caps name at 2 terms
    assert n.coverage == pytest.approx(2 / 3, abs=1e-3) and not n.needs_review  # measured: phrase absent from 1 of 3 docs


def test_naming_flags_generic_terms_instead_of_trusting_them():
    n = name_topic(["artificial intelligence", "news", "latest", "technology"], ["AI news today"] * 3)
    assert n.needs_review and "only generic terms available" in n.reasons
    n2 = name_topic([], None)
    assert n2.name == "Unnamed Topic" and n2.needs_review and n2.confidence == 0.0


def test_naming_flags_names_that_most_documents_do_not_contain():
    texts = ["completely different words here"] * 4 + ["rust compiler release"]
    n = name_topic(["rust compiler"], texts, min_coverage=0.5)
    assert n.coverage == pytest.approx(0.2) and n.needs_review
    assert any("only 20%" in r for r in n.reasons)


def test_naming_generic_name_detection_by_exact_phrase():
    n = name_topic(["quantum", "ai"], ["quantum computing news"] * 3)
    assert n.name == "Quantum"  # 'ai' is generic and dropped; the specific term is kept


# ------------------------------------------------------------------ diagnostics
def test_run_diagnostics_counts_noise_sizes_sources_and_flags():
    assign = [0] * 30 + [1] * 5 + [-1] * 15
    sources = ["news"] * 35 + ["reddit"] * 15
    d = run_diagnostics(assign, sources, {0: ["a"], 1: []}, {0: 0.8, 1: 0.6}, broad_share=0.4, high_noise_share=0.6)
    assert d["eligible_documents"] == 50 and d["documents_in_topics"] == 35 and d["noise_documents"] == 15
    assert d["noise_percentage"] == 30.0 and d["topics_discovered"] == 2
    assert d["topic_size"]["min"] == 5 and d["topic_size"]["max"] == 30 and d["topic_size"]["mean"] == 17.5
    assert d["source_distribution"] == {"news": 35, "reddit": 15}
    assert d["per_source"]["reddit"] == {"documents": 15, "in_topics": 0, "noise": 15}
    flags = {(f["topic_index"], f["flag"]) for f in d["topic_flags"]}
    assert (0, "overly_broad") in flags and (1, "no_representation") in flags
    assert "not semantic coherence" in d["cohesion"]["metric"]


def test_run_diagnostics_high_noise_flag_and_empty_run():
    d = run_diagnostics([-1] * 8 + [0] * 2, ["s"] * 10, {0: ["a"]}, {0: 0.7})
    assert any(f.startswith("high_noise") for f in d["run_flags"])
    e = run_diagnostics([], [], {}, {})
    assert e["topics_discovered"] == 0 and e["topic_size"]["min"] is None


def test_cohesion_is_one_for_identical_vectors():
    v = np.tile(np.array([[1.0, 0, 0]], dtype=np.float32), (4, 1))
    assert topic_cohesion(v, np.array([1.0, 0, 0])) == pytest.approx(1.0)


# ------------------------------------------------------------------ input validation
EN = "Teams adopt terminal coding agents for reviewing code changes"


def _doc(i, text=EN, vec=None, model="m"):
    return {"id": f"d{i}", "text": text, "vec": np.ones(4, dtype=np.float32) if vec is None else vec, "embedding_model": model}


def test_prepare_rejects_with_reasons_and_never_drops_silently():
    docs = [
        _doc(1, f"{EN} one"),
        _doc(2, f"{EN} one"),  # duplicate content
        _doc(3, ""),  # empty
        _doc(4, "tiny"),  # too short
        _doc(5, "これは日本語の文章です。" * 4),  # non-English
        _doc(6, f"{EN} two", vec=np.array([np.nan, 1, 1, 1], dtype=np.float32)),
        _doc(7, f"{EN} three", vec=np.ones(3, dtype=np.float32)),  # wrong dimension
        _doc(8, f"{EN} four", model="other-model"),
        _doc(9, f"{EN} five"),
    ]
    kept, st = prepare(docs, expected_dim=4, expected_model="m")
    assert [k["id"] for k in kept] == ["d1", "d9"]
    r = st["reasons"]
    assert r["duplicate_content"] == 1 and r["empty_text"] == 1 and r["too_short"] == 1 and r["non_english"] == 1
    assert r["invalid_embedding"] == 1 and r["embedding_dimension_mismatch"] == 1 and r["embedding_model_mismatch"] == 1
    assert st["input"] == len(kept) + st["rejected"], "every input document is either kept or counted as rejected"
    assert st["rejected_samples"]["duplicate_content"] == ["d2"]


def test_validate_embedding_cases():
    assert validate_embedding(np.ones(4), 4) is None
    assert validate_embedding(np.zeros(4), 4) == "invalid_embedding"
    assert validate_embedding(np.ones(5), 4) == "embedding_dimension_mismatch"
    assert validate_embedding([[1, 2]], None) == "invalid_embedding"
    assert validate_embedding("abc", 3) == "invalid_embedding"


# ------------------------------------------------------------------ explanations
def test_acceleration_distinguishes_sustained_rise_from_spike():
    assert acceleration_assessment([1, 2, 3, 5, 8, 13], "accelerating")["label"] == "sustained_acceleration"
    assert acceleration_assessment([2, 2, 3, 2, 2, 12], "unknown")["label"] == "single_window_spike"
    assert acceleration_assessment([0, 0, 0, 0, 0, 9])["label"] == "single_window_spike"
    assert acceleration_assessment([5, 6, 7, 8, 7, 6])["label"] == "flat_or_falling"
    assert acceleration_assessment([1, 2])["label"] == "insufficient_history"
    assert acceleration_assessment([3, 4, 4, 5, 5, 6])["label"] == "rising"


def test_short_summary_only_uses_stored_values():
    s = short_summary(61.4, "growing", 40.0, "accelerating", [3, 5, 7], {"signal_weight_coverage": 0.8}, 2, "Growth")
    assert "Score 61, led by growth" in s and "5→7 docs (+40%)" in s and "accelerating" in s and "2 sources" in s
    w = short_summary(None, None, None, "unknown", [4], {"signal_weight_coverage": 0.4}, 1)
    assert "Score withheld (40% signal coverage)" in w and "unknown" not in w and "1 source" in w and "source;" not in w


# ------------------------------------------------------------------ error hygiene
def test_sanitize_error_removes_credentials():
    msg = 'could not connect: postgresql://user:s3cret@db.example.com:5432/postgres password=hunter2 api_key: abc123'
    out = sanitize_error(RuntimeError(msg))
    assert "s3cret" not in out and "hunter2" not in out and "abc123" not in out
    assert out.startswith("RuntimeError:") and len(sanitize_error("x" * 2000)) == 500


# ------------------------------------------------------------------ BERTopic reproducibility (real model, synthetic data)
def test_bertopic_pipeline_is_reproducible_and_keeps_noise_separate():
    pytest.importorskip("bertopic")
    pytest.importorskip("hdbscan")
    from app.intelligence.topic_model import fit_topics, model_parameters

    rng = np.random.default_rng(0)
    centers = np.eye(3, 16, dtype=np.float32) * 5
    vocab = {
        0: ["kubernetes", "operator", "cluster", "pods", "helm", "scheduler"],
        1: ["rust", "compiler", "borrow", "checker", "cargo", "crates"],
        2: ["solar", "battery", "grid", "storage", "inverter", "panels"],
    }
    texts, vecs = [], []
    for c in range(3):
        for i in range(25):
            words = [vocab[c][(i + k) % 6] for k in range(3)]
            texts.append(" ".join(words))
            vecs.append(centers[c] + rng.normal(0, 0.15, 16))
    for i in range(3):  # a few scattered stray points
        texts.append(f"outlier{i} stray{i} misc{i}")
        vecs.append(rng.normal(0, 8.0, 16))
    X = np.vstack(vecs).astype(np.float32)
    a, b = fit_topics(texts, X), fit_topics(texts, X)
    assert a.assignments == b.assignments, "seeded pipeline must be reproducible"
    found = {t for t in a.assignments if t != -1}
    assert len(found) == 3
    # noise is reported, never hidden: n_noise equals the number of -1 assignments (HDBSCAN decides which docs
    # are noise; this test does not assume the 3 stray points are, because cosine-UMAP may attach them)
    assert a.n_noise == sum(1 for t in a.assignments if t == -1)
    assert a.notes and "min_df" in a.notes[0]  # disjoint synthetic vocabulary exercises the recorded fallback
    assert model_parameters(len(texts))["random_state"] == 42
    for t in found:
        top_terms = " ".join(a.topic_terms[t])
        assert any(w in top_terms for w in ("kubernetes", "rust", "solar"))
