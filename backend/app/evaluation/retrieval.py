"""Ranked-retrieval metrics. `ranked` is a list of document keys (URLs/ids), best first; `relevant` a set of keys
(binary) or a dict key -> graded relevance (for nDCG)."""
import math


def precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    return sum(1 for r in ranked[:k] if r in relevant) / k


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float | None:
    """None when there are no relevant documents (recall is undefined, not zero)."""
    if not relevant:
        return None
    return sum(1 for r in ranked[:k] if r in relevant) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float:
    for i, r in enumerate(ranked, start=1):
        if r in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list[str], grades: dict[str, float], k: int) -> float | None:
    if not grades or max(grades.values()) <= 0:
        return None
    dcg = sum(grades.get(r, 0.0) / math.log2(i + 1) for i, r in enumerate(ranked[:k], start=1))
    ideal = sorted(grades.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 1) for i, g in enumerate(ideal, start=1))
    return dcg / idcg if idcg else None


def evaluate_query(ranked: list[str], relevant: set[str], k: int = 5) -> dict:
    return {
        f"precision@{k}": precision_at_k(ranked, relevant, k),
        f"recall@{k}": recall_at_k(ranked, relevant, k),
        "mrr": reciprocal_rank(ranked, relevant),
        f"ndcg@{k}": ndcg_at_k(ranked, {r: 1.0 for r in relevant}, k),
    }


def aggregate(rows: list[dict]) -> dict:
    """Mean of each metric over queries where it is defined."""
    out: dict[str, float | None] = {}
    for key in rows[0] if rows else []:
        vals = [r[key] for r in rows if r.get(key) is not None]
        out[key] = round(sum(vals) / len(vals), 4) if vals else None
    out["queries"] = len(rows)
    return out
