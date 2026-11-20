import numpy as np
import pytest

from app.intelligence import engagement as eng
from app.intelligence import growth as gr
from app.intelligence import lifecycle as lc
from app.intelligence import momentum as mo
from app.intelligence import novelty as nv
from app.intelligence import temporal_analysis as ta
from app.intelligence.trend_score import trend_score, weights


def test_growth_matches_spec_example():
    # Week 3 -> Week 4 in the blueprint: 85 -> 130
    g = gr.growth_pct(130, 85)
    assert g.flag == "ok"
    assert g.value == pytest.approx((130 - 85) / 85 * 100)


def test_zero_baseline_is_not_infinite_growth():
    g = gr.growth_pct(50, 0)
    assert g.value is None
    assert g.flag == "zero_baseline"


def test_sparse_baseline_flagged():
    g = gr.growth_pct(10, 2)
    assert g.flag == "sparse_baseline"
    assert g.value == pytest.approx(400.0)


def test_normalize_growth_bounds():
    assert gr.normalize_growth(-100) == 0
    assert gr.normalize_growth(0) == 50
    assert gr.normalize_growth(500) == 100
    assert gr.normalize_growth(None) is None


def test_momentum_accelerating():
    # 40 -> 55 (+37.5%), 55 -> 85 (+54.5%), 85 -> 130 (+52.9%) : latest vs previous
    m = mo.momentum([40, 55, 85, 130])
    assert m.value == pytest.approx(((130 - 85) / 85 - (85 - 55) / 55) * 100)
    assert m.direction == "steady"  # +/- within 5pp band
    m2 = mo.momentum([10, 11, 12, 20])
    assert m2.direction == "accelerating"


def test_momentum_needs_three_windows_and_valid_baselines():
    assert mo.momentum([5, 10]).direction == "unknown"
    assert mo.momentum([0, 5, 10]).value is None  # zero baseline in the earlier growth


def test_novelty_none_without_history_and_inverse_similarity():
    v = np.array([1.0, 0.0])
    assert nv.novelty_score(v, []) is None
    assert nv.novelty_score(v, [np.array([1.0, 0.0])]) == pytest.approx(0.0)
    assert nv.novelty_score(v, [np.array([0.0, 1.0])]) == pytest.approx(100.0)


def test_engagement_unknown_source_is_none_not_zero():
    assert eng.doc_engagement("google_news", {}) is None
    assert eng.topic_engagement_raw([None, None]) is None
    out = eng.percentile_normalize({"a": 1.0, "b": 5.0, "c": None})
    assert out["c"] is None and out["a"] == 0.0 and out["b"] == 100.0


def test_trend_score_all_signals_matches_formula():
    sig = {"growth": 90, "momentum": 80, "engagement": 70, "novelty": 60, "search_interest": 50, "cross_source_activity": 40}
    r = trend_score(sig)
    expected = 0.30 * 90 + 0.20 * 80 + 0.15 * 70 + 0.15 * 60 + 0.10 * 50 + 0.10 * 40
    assert r.score == pytest.approx(expected, abs=0.01)
    assert r.coverage_weight == pytest.approx(1.0)


def test_trend_score_renormalizes_missing_signals_not_zero():
    sig = {"growth": 80, "momentum": 80, "engagement": None, "novelty": 80, "search_interest": None, "cross_source_activity": None}
    r = trend_score(sig)
    assert r.score == pytest.approx(80.0)  # not dragged toward zero by missing signals
    assert set(r.missing) == {"engagement", "search_interest", "cross_source_activity"}


def test_trend_score_withheld_below_min_coverage():
    sig = {"growth": 90, "momentum": None, "engagement": None, "novelty": None, "search_interest": None, "cross_source_activity": None}
    r = trend_score(sig)  # only 30% of weight available < 50% default minimum
    assert r.withheld and r.score is None


def test_weights_sum_to_one():
    assert sum(weights().values()) == pytest.approx(1.0)


def test_lifecycle_thresholds():
    assert lc.classify([1, 1]) is None  # insufficient evidence
    assert lc.classify([0, 0, 1, 12]) == lc.EMERGING  # new topic with enough evidence
    assert lc.classify([40, 55, 85, 130]) == lc.GROWING or lc.classify([40, 55, 85, 130]) == lc.EMERGING
    assert lc.classify([20, 60, 100, 100]) == lc.PEAKING
    assert lc.classify([100, 90, 60, 40]) == lc.DECLINING


def test_window_counts_and_edges():
    from datetime import datetime, timedelta, timezone

    end = datetime(2026, 11, 11, tzinfo=timezone.utc)
    edges = ta.window_edges(end, 7, 3)
    assert edges[-1][1] == end and edges[0][1] == end - timedelta(days=14)
    stamps = [end - timedelta(days=1), end - timedelta(days=2), end - timedelta(days=9), None]
    assert ta.window_counts(stamps, edges) == [0, 1, 2]


def test_search_interest_signal():
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rising = [(base + timedelta(days=i), float(10 + i * 5)) for i in range(12)]
    assert ta.search_interest_signal(rising) > 60
    assert ta.search_interest_signal(rising[:3]) is None
