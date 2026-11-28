"""Deterministic explanations built only from stored event values. An optional LLM rewrite is accepted only if it
introduces no number that the deterministic text does not contain; the deterministic text stays authoritative."""
import re
from typing import Callable

from app.monitoring.detection import EventCandidate


def n(x: float | int | None, digits: int = 1) -> str:
    if x is None:
        return "n/a"
    return str(int(x)) if float(x) == int(x) else f"{x:.{digits}f}"


def _reliability(d: dict) -> str:
    cov = d.get("score_coverage")
    bits = [f"{d.get('comparable_observations', 0) + 1} comparable observation(s)", f"{d.get('sources', 0)} source(s)"]
    if cov is not None:
        bits.append(f"{round(cov * 100)}% score signal coverage")
    bits.append(f"scoring formula {d.get('formula_version', '?')}")
    return "Reliability: " + ", ".join(bits) + "."


def _evidence(c: EventCandidate, titles: list[str] | None) -> str:
    if c.evidence_document_ids:
        k = len(c.evidence_document_ids)
        head = f"Evidence: {k} document(s) attached"
        return head + (": " + "; ".join(titles[:3]) + "." if titles else ".")
    return "Evidence: none attached; this event is based on aggregate observations only."


def _compare(d: dict) -> str:
    return f"compared with the previous observation window ending {str(d.get('previous_window_end', ''))[:10]}" if d.get("previous_window_end") else "compared with the previous observation"


def explain(c: EventCandidate, evidence_titles: list[str] | None = None) -> str:
    d, name = c.details, d_topic(c)
    t = c.event_type
    if t == "growth_acceleration":
        what = (f"{name} is growing faster than in the previous window: growth moved from {n(c.previous_value)}% to {n(c.current_value)}% "
                f"(+{n(d.get('change_points'))} points), while document volume went from {n(d.get('previous_volume'))} to {n(d.get('current_volume'))}.")
    elif t == "growth_slowdown":
        what = (f"{name} is still growing but more slowly: growth moved from {n(c.previous_value)}% to {n(c.current_value)}% "
                f"({n(d.get('change_points'))} points), with document volume {n(d.get('previous_volume'))} → {n(d.get('current_volume'))}.")
    elif t == "activity_decline":
        what = f"Activity for {name} fell from {n(c.previous_value)} to {n(c.current_value)} documents ({n(c.change_percentage)}%)."
    elif t == "lifecycle_transition":
        what = f"{name} moved from {d.get('from')} to {d.get('to')} in the lifecycle classification" + (" (the expected forward progression)." if d.get("forward") else " (not the usual forward progression).")
    elif t == "activity_spike":
        z = d.get("z")
        what = (f"Document volume for {name} reached {n(c.current_value)}, against a recent baseline average of {n(d.get('baseline_mean'))} "
                f"over {n(d.get('baseline_n'))} earlier observations (ratio {n(d.get('ratio'))}x" + (f", {n(z)} baseline standard deviations above the mean" if z is not None else ", flat baseline") + "). "
                "This measures deviation from the recent baseline; it is not a statistical significance test.")
    elif t == "activity_disappearance":
        what = (f"{name} is now classified {d.get('state')}: it was absent from {n(d.get('missed_runs'))} completed analysis run(s) since it was last observed. "
                "Failed runs and failed collections are not counted.")
    elif t == "new_emerging_trend":
        what = f"{name} appeared for the first time as an emerging trend with {n(c.current_value)} documents" + (f" and a trend score of {n(d.get('trend_score'))}." if d.get("trend_score") is not None else " (score withheld for low signal coverage).")
    elif t == "new_supporting_evidence":
        what = f"{n(c.current_value)} new document(s) were associated with {name} since the last check" + (f" from {n(d.get('publishers'))} publisher(s)." if d.get("publishers") else ".")
    elif t == "contradictory_evidence":
        what = f"A newly collected document uses opposite-polarity wording about a statement in the latest {name} dossier: \"{str(d.get('claim', ''))[:140]}\". This is a wording heuristic; review the document."
    elif t == "new_related_topic":
        what = f"A newly discovered topic, \"{d.get('related_name')}\", is related to {name} (topic similarity {n(d.get('similarity'), 2)}). The topics remain separate."
    else:
        what = c.title
    parts = [what]
    if t in ("growth_acceleration", "growth_slowdown", "activity_decline", "lifecycle_transition", "activity_spike"):
        parts.append(f"Comparison: {_compare(d)}.")
    parts += [_reliability(d), _evidence(c, evidence_titles)]
    return " ".join(parts)


def d_topic(c: EventCandidate) -> str:
    return c.details.get("topic") or "This trend"


_NUM = re.compile(r"\d+(?:\.\d+)?")


def guard_rewrite(original: str, rewritten: str) -> bool:
    """A rewrite is acceptable only if every number in it already appears in the deterministic text."""
    allowed = set(_NUM.findall(original))
    return bool(rewritten.strip()) and set(_NUM.findall(rewritten)) <= allowed and len(rewritten) <= 2 * len(original)


def finalize(text: str, rewrite: Callable[[str], str] | None = None) -> tuple[str, bool]:
    """(explanation, rewritten?). A failed or rejected LLM rewrite silently keeps the deterministic text."""
    if rewrite is None:
        return text, False
    try:
        out = rewrite(text)
    except Exception:
        return text, False
    return (out.strip(), True) if guard_rewrite(text, out) else (text, False)
