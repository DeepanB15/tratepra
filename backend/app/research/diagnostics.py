"""Retrieval diagnostics. Scores describe ranking similarity, NOT factual confidence."""
from collections import Counter
from datetime import datetime, timezone

from app.research.excerpts import publisher_of


def _day(d):
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.date().isoformat()


def retrieval_diagnostics(candidates: list, ranked: list, selected: list, rejections: dict, entities: list[str]) -> dict:
    method = Counter(c.match for c in candidates)
    chosen_ids = {i.candidate.document.id for i in selected}
    dates = sorted(d for d in (_day(i.candidate.document.published_at) for i in selected) if d)
    publishers = Counter(publisher_of(i.candidate.document) for i in selected)
    sources = Counter(i.candidate.source_key for i in selected)
    reasons = Counter(rejections.values())
    items = []
    for rank, i in enumerate(selected, start=1):
        d = i.candidate.document
        text = (d.normalized_text or "").lower()
        items.append(
            {
                "document_id": str(d.id),
                "rank": rank,
                "match_method": i.candidate.match,
                "scores": {  # ranking components 0-100 (similarity/relevance, not truth)
                    "semantic": round(i.semantic, 1),
                    "keyword": round(i.keyword, 1),
                    "freshness": round(i.freshness, 1),
                    "quality": round(i.quality, 1),
                    "combined": round(i.score, 1),
                },
                "matched_entities": [e for e in entities if e in text],
                "article_status": getattr(d, "article_status", "rss_only"),
            }
        )
    return {
        "candidates_retrieved": len(candidates),
        "candidates_ranked": len(ranked),
        "selected": len(selected),
        "rejected": len(candidates) - len(chosen_ids),
        "by_match_method": dict(method),
        "rejection_reasons": dict(reasons),
        "source_distribution": dict(sources),
        "publisher_distribution": dict(publishers),
        "date_coverage": {"earliest": dates[0] if dates else None, "latest": dates[-1] if dates else None, "distinct_days": len(set(dates))},
        "undated_selected": sum(1 for i in selected if i.candidate.document.published_at is None),
        "items": items,
        "note": "Scores rank similarity to the question. They are not a measure of factual accuracy.",
    }
