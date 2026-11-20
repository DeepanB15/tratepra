"""WS4: language detection, one-to-one topic matching, lifecycle spike guard, score explanation."""
import numpy as np

from app.intelligence.explain import contributions, explain
from app.intelligence.lifecycle import classify
from app.intelligence.preprocessor import is_probably_english
from app.intelligence.topic_representations import match_topics
from app.intelligence.trend_score import trend_score

EN = "Developers are adopting terminal coding agents because they can run tests and the results are reviewed by the team"
ES = "Los desarrolladores estan adoptando agentes de programacion en la terminal porque pueden ejecutar pruebas y revisar los resultados"


def test_language_detection():
    assert is_probably_english(EN)
    assert not is_probably_english(ES)                      # Latin script, passes the old ASCII-only test
    assert not is_probably_english("これは日本語の文章です。" * 3)
    assert is_probably_english("Rust 1.80 released")        # short title: ASCII fallback
    assert not is_probably_english("")


def test_match_topics_is_one_to_one_and_threshold_bound():
    prior = {"p1": np.array([1.0, 0.0, 0.0]), "p2": np.array([0.0, 1.0, 0.0])}
    new = {0: np.array([1.0, 0.05, 0.0]), 1: np.array([1.0, 0.2, 0.0]), 2: np.array([0.0, 0.0, 1.0])}
    m = match_topics(new, prior, 0.8)
    assert m[0][0] == "p1"             # closest claims p1
    assert 1 not in m or m[1][0] != "p1"  # the other candidate cannot steal it
    assert 2 not in m                  # unrelated topic stays new
    assert len({v[0] for v in m.values()}) == len(m)
    assert match_topics(new, {}, 0.8) == {}


def test_lifecycle_spike_guard():
    # +100% on a tiny base (3 -> 6 would be a real jump; 1 -> 2 must not label)
    assert classify([2, 2, 2, 2, 1, 2]) not in ("emerging", "growing")
    assert classify([2, 3, 4, 6, 9, 14]) in ("emerging", "growing")


def test_contributions_sum_to_score_and_missing_are_explained():
    sig = {"growth": 80, "momentum": 60, "engagement": None, "novelty": 40, "search_interest": None, "cross_source_activity": 100}
    sc = trend_score(sig)
    rows = contributions(sig)
    assert abs(sum(r["points"] for r in rows if r["points"] is not None) - sc.score) < 0.05
    ex = explain(sig, sc.score, "growing", {"signal_weight_coverage": sc.coverage_weight}, [1, 2, 4], previous_score=50.0)
    assert {m["signal"] for m in ex["missing"]} == {"engagement", "search_interest"}
    assert all(m["reason"] for m in ex["missing"])
    assert "since the previous computation" in ex["summary"]


def test_withheld_score_is_explained_not_zeroed():
    sig = {k: None for k in ("growth", "momentum", "engagement", "novelty", "search_interest", "cross_source_activity")}
    sig["growth"] = 70
    sc = trend_score(sig)
    assert sc.score is None
    ex = explain(sig, None, None, {"signal_weight_coverage": sc.coverage_weight, "min_coverage": 0.5}, [])
    assert "No Trend Score" in ex["summary"]
