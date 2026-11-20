"""Trend-engine quality metrics (pure)."""
from app.intelligence.lifecycle import classify


def noise_rate(assignments: list[int]) -> float | None:
    """Share of documents BERTopic left unassigned (-1)."""
    return round(sum(1 for a in assignments if a == -1) / len(assignments), 4) if assignments else None


def topic_stability(prev: dict[str, set[str]], curr: dict[str, set[str]]) -> float | None:
    """Mean best-Jaccard of each previous topic's document set against the current run (1.0 = identical)."""
    if not prev or not curr:
        return None
    scores = []
    for a in prev.values():
        best = max((len(a & b) / len(a | b) for b in curr.values() if a | b), default=0.0)
        scores.append(best)
    return round(sum(scores) / len(scores), 4)


def topic_coherence_proxy(topic_terms: list[str], texts: list[str]) -> float | None:
    """Share of a topic's documents containing at least one of its top terms (a cheap proxy, NOT NPMI)."""
    if not texts or not topic_terms:
        return None
    terms = [t.lower() for t in topic_terms]
    return round(sum(1 for x in texts if any(t in x.lower() for t in terms)) / len(texts), 4)


def lifecycle_accuracy(cases: list[dict]) -> dict:
    """cases: {"volumes": [...], "expected": label|None}. Returns accuracy and the disagreeing cases."""
    wrong = []
    for c in cases:
        got = classify(c["volumes"])
        if got != c["expected"]:
            wrong.append({**c, "got": got})
    n = len(cases)
    return {"cases": n, "correct": n - len(wrong), "accuracy": round((n - len(wrong)) / n, 3) if n else None, "wrong": wrong}
