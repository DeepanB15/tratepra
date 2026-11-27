"""Topic naming from evidence (pure; no LLM).

A name is built only from c-TF-IDF terms that BERTopic extracted from the topic's own documents. Quality is
*measured*: `coverage` is the share of member documents that actually contain at least one of the name terms.
Weak, generic or poorly covered names are flagged for human review rather than silently accepted.
"""
import re
from dataclasses import dataclass, field

# Terms that carry no topical information on their own. A name made only of these is flagged, never trusted.
GENERIC_TERMS = frozenset(
    """news latest new update updates report reports says said announces announced today week year years
    time first next one two three top best technology tech business industry company companies market
    development developments world people use using used like make made get also according amid
    artificial intelligence ai video watch live review""".split()
)
GENERIC_NAMES = frozenset(
    {
        "artificial intelligence", "technology news", "business updates", "latest developments", "ai news",
        "tech news", "latest news", "breaking news", "business news", "ai", "technology", "news",
    }
)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9\+\#\.\-']*")


@dataclass
class TopicName:
    name: str
    terms_used: list[str]
    coverage: float | None  # share of member docs containing >=1 name term; None if no docs supplied
    confidence: float  # 0-1, from coverage and distinctiveness (documented in PHASE_1_ARCHITECTURE.md)
    needs_review: bool
    reasons: list[str] = field(default_factory=list)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall((text or "").lower()))


def _is_generic(term: str) -> bool:
    words = term.lower().split()
    return term.lower() in GENERIC_NAMES or all(w in GENERIC_TERMS for w in words)


def _overlaps(term: str, picked: list[str]) -> bool:
    tw = set(term.lower().split())
    return any(tw <= set(p.lower().split()) or set(p.lower().split()) <= tw for p in picked)


def _pretty(term: str) -> str:
    out = []
    for w in term.split():
        out.append(w if (w.isupper() or any(c.isdigit() for c in w)) else w.capitalize())
    return " ".join(out)


def name_topic(
    terms: list[str],
    member_texts: list[str] | None = None,
    min_coverage: float = 0.5,
    max_terms: int = 3,
) -> TopicName:
    specific = [t for t in terms if t and not _is_generic(t)]
    picked: list[str] = []
    # Prefer distinctive bigrams first when they are among the strongest terms, otherwise follow c-TF-IDF rank.
    for t in specific:
        if _overlaps(t, picked):
            continue
        picked.append(t)
        if len(picked) >= (2 if " " in picked[0] else max_terms):
            break

    reasons: list[str] = []
    if not picked:
        generic_only = [t for t in terms if t][:max_terms]
        name = " / ".join(_pretty(t) for t in generic_only) or "Unnamed Topic"
        reasons.append("only generic terms available" if generic_only else "no terms extracted")
        return TopicName(name, generic_only, None, 0.0, True, reasons)

    name = " / ".join(_pretty(t) for t in picked)
    if name.lower() in GENERIC_NAMES:
        reasons.append("generic topic name")

    coverage = None
    if member_texts:
        toks = [_tokens(t) for t in member_texts]
        lowered = [(t or "").lower() for t in member_texts]
        hit = 0
        for tk, low in zip(toks, lowered):
            if any((term.lower() in low) if " " in term else (term.lower() in tk) for term in picked):
                hit += 1
        coverage = hit / len(member_texts)
        if coverage < min_coverage:
            reasons.append(f"name terms appear in only {round(100 * coverage)}% of member documents")

    dropped = len(specific) < min(len(terms), 3)
    if dropped and len(picked) < 2:
        reasons.append("few distinctive terms (most top terms were generic)")

    cov_part = coverage if coverage is not None else 0.5
    distinct_part = min(len(picked), max_terms) / max_terms
    confidence = round(0.7 * cov_part + 0.3 * distinct_part, 3)
    return TopicName(name, picked, None if coverage is None else round(coverage, 3), confidence, bool(reasons), reasons)
