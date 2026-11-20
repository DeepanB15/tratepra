import json
from pathlib import Path

from app.evaluation.benchmark import time_it
from app.evaluation.citations import citation_metrics
from app.evaluation.retrieval import aggregate, evaluate_query, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
from app.evaluation.trend_quality import lifecycle_accuracy, noise_rate, topic_coherence_proxy, topic_stability
from app.research.citation_validator import EvidenceRef


def test_retrieval_metrics_hand_computed():
    ranked = ["a", "b", "c", "d"]
    rel = {"b", "d", "z"}
    assert precision_at_k(ranked, rel, 2) == 0.5
    assert recall_at_k(ranked, rel, 4) == 2 / 3
    assert reciprocal_rank(ranked, rel) == 0.5
    assert recall_at_k(ranked, set(), 3) is None
    # grades b=1,d=1,z=1 -> DCG = 1/log2(3)+1/log2(5); IDCG = 1 + 1/log2(3) + 1/log2(4)
    expected = (1 / 1.5849625 + 1 / 2.3219281) / (1 + 1 / 1.5849625 + 0.5)
    assert abs(ndcg_at_k(ranked, {r: 1.0 for r in rel}, 4) - expected) < 1e-4


def test_aggregate_skips_undefined():
    rows = [evaluate_query(["a"], {"a"}, 1), evaluate_query(["x"], set(), 1)]
    agg = aggregate(rows)
    assert agg["queries"] == 2 and agg["recall@1"] == 1.0


def test_citation_metrics():
    m = citation_metrics("Agents adopted widely by developers [1]. Unsupported claim here.", [], [EvidenceRef("agents adopted by developers", "https://x.test/1")])
    assert m["claims_total"] == 2 and m["verified_rate"] == 0.5 and m["evidence_coverage"] == 1.0


def test_trend_quality_metrics():
    assert noise_rate([0, -1, -1, 1]) == 0.5
    assert topic_stability({"a": {"1", "2"}}, {"x": {"1", "2"}}) == 1.0
    assert topic_stability({"a": {"1"}}, {"x": {"2"}}) == 0.0
    assert topic_coherence_proxy(["rust"], ["Rust news", "cooking"]) == 0.5


def test_lifecycle_synthetic_cases_pass():
    path = Path(__file__).resolve().parents[3] / "data" / "evaluation" / "trend_cases.json"
    result = lifecycle_accuracy(json.loads(path.read_text())["cases"])
    assert result["wrong"] == [], result["wrong"]


def test_time_it_shape():
    assert set(time_it(lambda: None, 3)) == {"runs", "min_ms", "median_ms", "max_ms"}
