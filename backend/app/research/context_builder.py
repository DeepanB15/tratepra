from dataclasses import dataclass

from app.ingestion.deduplicator import jaccard_similarity, token_set
from app.research.claims import polarity
from app.research.excerpts import build_excerpt

MAX_SNIPPET_CHARS = 500
SIMILAR_TITLE_THRESHOLD = 0.7  # skip evidence whose title is this similar to something already selected
MIN_SCORE_FRACTION_FOR_QUOTA = 0.5  # a source gets a guaranteed slot only if its best item is this close to the top score


@dataclass
class EvidenceContext:
    selected: list  # RankedItem list, index i -> citation [i+1]
    text: str
    excerpts: list = None  # Excerpt per selected item: the exact text shown to the model, reused for verification


def _doc_key(item):
    d = item.candidate.document
    return getattr(d, "id", None) or id(d)


def select_evidence(ranked: list, max_items: int = 10, max_per_source: int = 5) -> list:
    """Top-ranked, non-repetitive evidence with balanced source coverage (see select_evidence_explained)."""
    return select_evidence_explained(ranked, max_items, max_per_source)[0]


def select_evidence_explained(ranked: list, max_items: int = 10, max_per_source: int = 5) -> tuple[list, dict]:
    """Returns (selected, rejections) where rejections maps document id -> reason it was not selected.

    1. Guarantee one slot to the best item of every source whose best item scores within
       half of the overall top score (prevents one connector crowding out the rest).
    2. Fill remaining slots by score, with a per-source cap.
    Items whose titles are near-identical to an already selected item, or that share a canonical URL or
    content hash with one, are skipped as duplicates. The result is ordered by score; position i becomes
    citation [i+1].
    """
    if not ranked:
        return [], {}
    top = ranked[0].score
    chosen: list = []
    titles: list[tuple[frozenset[str], bool]] = []
    seen_keys: set[str] = set()
    counts: dict[str, int] = {}
    rejections: dict = {}

    def dup_keys(item) -> set[str]:
        d = item.candidate.document
        return {k for k in (getattr(d, "canonical_url", None), getattr(d, "content_hash", None)) if k}

    def reject(item, reason: str) -> bool:
        rejections.setdefault(_doc_key(item), reason)
        return False

    def take(item) -> bool:
        key = item.candidate.source_key
        if item in chosen:
            return False
        if dup_keys(item) & seen_keys:
            return reject(item, "duplicate_url_or_content")
        title = item.candidate.document.title
        t, pol = token_set(title), polarity(title)
        # A near-identical title with OPPOSITE polarity ("X works" vs "X does not work") is a potential
        # contradiction, not a repeat, so it is kept.
        if len(t) >= 3 and any(jaccard_similarity(t, p) >= SIMILAR_TITLE_THRESHOLD and pol == pp for p, pp in titles):
            return reject(item, "near_duplicate_title")
        if counts.get(key, 0) >= max_per_source:
            return reject(item, "source_cap")
        chosen.append(item)
        titles.append((t, pol))
        seen_keys.update(dup_keys(item))
        counts[key] = counts.get(key, 0) + 1
        rejections.pop(_doc_key(item), None)
        return True

    best_per_source: dict[str, object] = {}
    for item in ranked:
        best_per_source.setdefault(item.candidate.source_key, item)
    for item in sorted(best_per_source.values(), key=lambda i: i.score, reverse=True):
        if len(chosen) < max_items and item.score >= MIN_SCORE_FRACTION_FOR_QUOTA * top:
            take(item)
    for item in ranked:
        if len(chosen) >= max_items:
            reject(item, "below_selection_limit")
            continue
        take(item)
    chosen.sort(key=lambda i: i.score, reverse=True)
    for item in chosen:
        rejections.pop(_doc_key(item), None)
    return chosen, rejections


def build_context(selected: list, terms: list[str] | None = None) -> EvidenceContext:
    """Numbered evidence for the model. Article excerpts are used when real article text exists, otherwise the
    RSS description (never labelled as an article)."""
    lines, excerpts = [], []
    for i, item in enumerate(selected, start=1):
        d = item.candidate.document
        ex = build_excerpt(d, terms)
        excerpts.append(ex)
        pub = d.published_at.date().isoformat() if d.published_at else "unknown date"
        basis = "article excerpt" if ex.basis == "article" else "RSS summary"
        lines.append(f"[{i}] ({item.candidate.source_key}, {pub}, {basis}) {d.title}\n{ex.text}".strip())
    return EvidenceContext(selected=selected, text="\n\n".join(lines), excerpts=excerpts)
