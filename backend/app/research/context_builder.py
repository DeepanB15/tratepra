from dataclasses import dataclass

from app.ingestion.deduplicator import jaccard_similarity, token_set

MAX_SNIPPET_CHARS = 500
SIMILAR_TITLE_THRESHOLD = 0.7  # skip evidence whose title is this similar to something already selected
MIN_SCORE_FRACTION_FOR_QUOTA = 0.5  # a source gets a guaranteed slot only if its best item is this close to the top score


@dataclass
class EvidenceContext:
    selected: list  # RankedItem list, index i -> citation [i+1]
    text: str


def select_evidence(ranked: list, max_items: int = 10, max_per_source: int = 5) -> list:
    """Top-ranked, non-repetitive evidence with balanced source coverage.

    1. Guarantee one slot to the best item of every source whose best item scores within
       half of the overall top score (prevents one connector crowding out the rest).
    2. Fill remaining slots by score, with a per-source cap.
    Items whose titles are near-identical to an already selected item are skipped.
    The result is ordered by score; position i becomes citation [i+1].
    """
    if not ranked:
        return []
    top = ranked[0].score
    chosen: list = []
    titles: list[frozenset[str]] = []
    counts: dict[str, int] = {}

    def repetitive(item) -> bool:
        t = token_set(item.candidate.document.title)
        return len(t) >= 3 and any(jaccard_similarity(t, p) >= SIMILAR_TITLE_THRESHOLD for p in titles)

    def take(item) -> bool:
        key = item.candidate.source_key
        if item in chosen or counts.get(key, 0) >= max_per_source or repetitive(item):
            return False
        chosen.append(item)
        titles.append(token_set(item.candidate.document.title))
        counts[key] = counts.get(key, 0) + 1
        return True

    best_per_source: dict[str, object] = {}
    for item in ranked:
        best_per_source.setdefault(item.candidate.source_key, item)
    for item in sorted(best_per_source.values(), key=lambda i: i.score, reverse=True):
        if len(chosen) < max_items and item.score >= MIN_SCORE_FRACTION_FOR_QUOTA * top:
            take(item)
    for item in ranked:
        if len(chosen) >= max_items:
            break
        take(item)
    chosen.sort(key=lambda i: i.score, reverse=True)
    return chosen


def build_context(selected: list) -> EvidenceContext:
    lines = []
    for i, item in enumerate(selected, start=1):
        d = item.candidate.document
        pub = d.published_at.date().isoformat() if d.published_at else "unknown date"
        body = (d.description or "")[:MAX_SNIPPET_CHARS]
        lines.append(f"[{i}] ({item.candidate.source_key}, {pub}) {d.title}\n{body}".strip())
    return EvidenceContext(selected=selected, text="\n\n".join(lines))
