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


def acceleration_assessment(volumes: list[int], momentum_direction: str | None = None, growth_flag: str | None = None) -> dict:
    """Is the topic accelerating over several windows, or did it just spike in the latest one?

    Uses only the stored per-window document volumes (and the stored momentum direction); no narrative is added.
      sustained_acceleration  the last two window-over-window changes are both increases and the latest is larger
      single_window_spike     only the latest window is elevated (>= 2x the mean of earlier windows) after flat/low
                              earlier activity, and the increase is not preceded by a rise
      rising                  latest window is above the previous one, evidence short of the two above
      flat_or_falling         latest window is not above the previous one
      insufficient_history    fewer than 3 windows or a very small total volume
    """
    v = [int(x) for x in (volumes or [])]
    if len(v) < 3 or sum(v) < 5:
        return {"label": "insufficient_history", "text": "Not enough weekly history to tell a sustained rise from a spike."}
    cur, prev, prev2 = v[-1], v[-2], v[-3]
    earlier = v[:-1]
    earlier_mean = sum(earlier) / len(earlier)
    if cur <= prev:
        return {"label": "flat_or_falling", "text": f"Latest window ({cur}) is not above the previous one ({prev})."}
    two_rises = prev > prev2 and cur > prev
    if two_rises and momentum_direction in (None, "accelerating", "steady"):
        return {"label": "sustained_acceleration", "text": f"Volume rose in consecutive windows ({prev2} → {prev} → {cur}), so this is not a one-window spike."}
    if earlier_mean > 0 and cur >= 2 * earlier_mean and prev <= prev2 + 1:
        return {"label": "single_window_spike", "text": f"Only the latest window is elevated ({cur} vs an earlier average of {earlier_mean:.1f}); treat as a possible temporary spike until it persists."}
    if earlier_mean == 0:
        return {"label": "single_window_spike", "text": f"No earlier activity and {cur} documents in the latest window: new, but not yet shown to persist."}
    return {"label": "rising", "text": f"Latest window ({cur}) is above the previous one ({prev}); the rise is not yet sustained across consecutive windows."}


def short_summary(
    score: float | None,
    lifecycle: str | None,
    growth_pct: float | None,
    momentum_direction: str | None,
    volumes: list[int],
    coverage: dict,
    source_count: int,
    top_signal: str | None = None,
) -> str:
    """One evidence-grounded line for list rows. Built only from stored values."""
    bits: list[str] = []
    if score is None:
        cov = round(100 * (coverage or {}).get("signal_weight_coverage", 0))
        bits.append(f"Score withheld ({cov}% signal coverage)")
    elif top_signal:
        bits.append(f"Score {score:.0f}, led by {top_signal.lower()}")
    else:
        bits.append(f"Score {score:.0f}")
    if growth_pct is not None and len(volumes) >= 2:
        bits.append(f"{volumes[-2]}→{volumes[-1]} docs ({growth_pct:+.0f}%)")
    elif volumes:
        bits.append(f"{volumes[-1]} docs this window")
    if momentum_direction and momentum_direction != "unknown":
        bits.append(momentum_direction)
    bits.append(f"{source_count} source{'s' if source_count != 1 else ''}")
    return "; ".join(bits)
