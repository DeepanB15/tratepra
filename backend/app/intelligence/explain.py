"""Plain-language, auditable explanation of a Trend Score (pure functions, no I/O).

Contributions are exact: with available signals A and weights w, score = sum(w_k * v_k) / sum(w_A),
so each signal contributes w_k * v_k / sum(w_A) points and the contributions add up to the score.
"""
from app.intelligence.trend_score import SIGNAL_NAMES, weights

LABELS = {
    "growth": "Growth",
    "momentum": "Momentum",
    "engagement": "Engagement",
    "novelty": "Novelty",
    "search_interest": "Search interest",
    "cross_source_activity": "Cross-source activity",
}
_MISSING_WHY = {
    "growth": "needs at least two time windows of history",
    "momentum": "needs at least three time windows of history",
    "engagement": "no engagement metrics were available for this topic's documents",
    "novelty": "no earlier topics exist yet to compare against",
    "search_interest": "no Google Trends time series matched this topic (connector unavailable or no matching query)",
    "cross_source_activity": "fewer than two text sources are configured, so it cannot be measured",
}
LIFECYCLE_TEXT = {
    "emerging": "little prior activity, now rising",
    "growing": "sustained increase in activity",
    "peaking": "at its highest activity and no longer accelerating",
    "declining": "activity is falling",
    None: "no label: activity is stable or there is not enough evidence",
}


def contributions(signals: dict[str, float | None], w: dict[str, float] | None = None) -> list[dict]:
    w = w or weights()
    avail = [k for k in SIGNAL_NAMES if signals.get(k) is not None]
    total = sum(w[k] for k in avail)
    rows = []
    for k in SIGNAL_NAMES:
        v = signals.get(k)
        if v is None:
            rows.append({"signal": k, "label": LABELS[k], "value": None, "weight": w[k], "points": None, "reason_missing": _MISSING_WHY[k]})
        else:
            rows.append(
                {
                    "signal": k,
                    "label": LABELS[k],
                    "value": round(float(v), 1),
                    "weight": w[k],
                    "points": round(w[k] * float(v) / total, 2) if total else 0.0,
                    "reason_missing": None,
                }
            )
    return rows


def explain(
    signals: dict[str, float | None],
    score: float | None,
    lifecycle: str | None,
    coverage: dict,
    volumes: list[int],
    previous_score: float | None = None,
) -> dict:
    rows = contributions(signals)
    present = sorted((r for r in rows if r["points"] is not None), key=lambda r: r["points"], reverse=True)
    parts: list[str] = []
    if score is None:
        cov = round(100 * (coverage or {}).get("signal_weight_coverage", 0))
        parts.append(
            f"No Trend Score is shown: only {cov}% of the scoring weight has data (minimum "
            f"{round(100 * (coverage or {}).get('min_coverage', 0.5))}%). Missing signals are never counted as zero."
        )
    else:
        top = ", ".join(f"{r['label'].lower()} ({r['points']:.1f} pts)" for r in present[:2])
        parts.append(f"Score {score:.0f}/100, driven mainly by {top}." if top else f"Score {score:.0f}/100.")
    if volumes:
        parts.append(f"Documents per weekly window (oldest to newest): {', '.join(map(str, volumes))}.")
    parts.append(f"Lifecycle: {lifecycle or 'unlabelled'} - {LIFECYCLE_TEXT.get(lifecycle, LIFECYCLE_TEXT[None])}.")
    if previous_score is not None and score is not None:
        delta = round(score - previous_score, 1)
        parts.append(f"Score changed {delta:+.1f} since the previous computation.")
    missing = [r for r in rows if r["points"] is None]
    return {
        "summary": " ".join(parts),
        "contributions": rows,
        "missing": [{"signal": r["signal"], "label": r["label"], "reason": r["reason_missing"]} for r in missing],
    }
