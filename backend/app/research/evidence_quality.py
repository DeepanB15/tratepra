"""Evidence quality: separate, rule-based dimensions. There is deliberately NO single confidence percentage.

Each dimension gets a descriptive label from the explicit thresholds below. The labels describe how much and
how varied the *retrieved* evidence is; they do not say a claim is true. Duplicate or repeated items are
collapsed before counting, so republished copies cannot raise a label.
"""
from collections import Counter
from dataclasses import dataclass

STRONG, MODERATE, LIMITED, INSUFFICIENT = "strong", "moderate", "limited", "insufficient"
LABEL_TEXT = {
    STRONG: "Strong evidence coverage",
    MODERATE: "Moderate evidence coverage",
    LIMITED: "Limited evidence coverage",
    INSUFFICIENT: "Insufficient evidence coverage",
}
_ORDER = [INSUFFICIENT, LIMITED, MODERATE, STRONG]

RULES_VERSION = "eq-1"
RULES = {
    "coverage": "unique documents after duplicate removal: strong >=8, moderate 4-7, limited 2-3, insufficient <=1",
    "source_diversity": "distinct publishers and largest publisher share: strong >=4 publishers and top share <=40%; "
    "moderate >=3 and <=60%; limited >=2; insufficient 1 or none",
    "temporal": "distinct publication days and fraction of the requested window spanned: strong >=5 days and >=50%; "
    "moderate >=3 days and >=25%; limited >=2 days; insufficient <=1 day or undated",
    "claim_support": "share of claims supported or partially supported, with none contradicted: strong >=80% supported; "
    "moderate >=50% supported or partial; limited >0%; insufficient: no claims or none supported",
}


@dataclass
class EvidenceItem:
    key: str  # duplicate key (canonical URL / content hash)
    title: str
    publisher: str
    day: str | None  # ISO date or None
    article_status: str


def _dedupe(items: list[EvidenceItem]) -> tuple[list[EvidenceItem], int]:
    seen, out = set(), []
    for it in items:
        k = it.key or f"{it.publisher}|{it.title.lower().strip()}"
        if k in seen or f"{it.publisher}|{it.title.lower().strip()}" in seen:
            continue
        seen.add(k)
        seen.add(f"{it.publisher}|{it.title.lower().strip()}")
        out.append(it)
    return out, len(items) - len(out)


def _dim(label: str, detail: dict, explanation: str) -> dict:
    return {"label": label, "text": LABEL_TEXT[label], "explanation": explanation, **detail}


def assess(items: list[EvidenceItem], claims: list[dict], window_days: float) -> dict:
    unique, dup = _dedupe(items)
    n = len(unique)

    cov_label = STRONG if n >= 8 else MODERATE if n >= 4 else LIMITED if n >= 2 else INSUFFICIENT
    article = sum(1 for i in unique if i.article_status in ("full", "partial"))
    coverage = _dim(
        cov_label,
        {"unique_documents": n, "duplicates_ignored": dup, "with_article_text": article, "rss_only_or_unavailable": n - article},
        f"{n} unique document(s); {article} with article text, {n - article} limited to the feed summary."
        + (f" {dup} duplicate(s) were not counted." if dup else ""),
    )

    pubs = Counter(i.publisher for i in unique)
    top_share = (max(pubs.values()) / n) if n else 0.0
    if len(pubs) >= 4 and top_share <= 0.4:
        div = STRONG
    elif len(pubs) >= 3 and top_share <= 0.6:
        div = MODERATE
    elif len(pubs) >= 2:
        div = LIMITED
    else:
        div = INSUFFICIENT
    top_name = pubs.most_common(1)[0][0] if pubs else None
    diversity = _dim(
        div,
        {"publishers": len(pubs), "top_publisher": top_name, "top_publisher_share": round(top_share, 2),
         "publisher_counts": dict(pubs.most_common(8))},
        f"{len(pubs)} publisher(s)" + (f"; the largest ({top_name}) accounts for {round(top_share * 100)}% of the evidence." if n else "."),
    )

    days = sorted({i.day for i in unique if i.day})
    span = 0.0
    if len(days) >= 2:
        from datetime import date

        span = (date.fromisoformat(days[-1]) - date.fromisoformat(days[0])).days + 1
    frac = min(1.0, span / max(window_days, 1.0)) if span else 0.0
    if len(days) >= 5 and frac >= 0.5:
        tl = STRONG
    elif len(days) >= 3 and frac >= 0.25:
        tl = MODERATE
    elif len(days) >= 2:
        tl = LIMITED
    else:
        tl = INSUFFICIENT
    undated = sum(1 for i in unique if not i.day)
    temporal = _dim(
        tl,
        {"distinct_days": len(days), "span_days": span, "window_days": round(window_days, 1), "window_fraction": round(frac, 2),
         "undated": undated, "earliest": days[0] if days else None, "latest": days[-1] if days else None},
        f"{len(days)} distinct publication day(s) spanning {int(span)} of {round(window_days)} day(s)"
        + (f"; {undated} undated." if undated else "."),
    )

    total = len(claims)
    by = Counter(c["status"] for c in claims)
    sup, part, con = by.get("supported", 0), by.get("partially_supported", 0), by.get("contradicted", 0)
    if total and sup / total >= 0.8 and con == 0:
        cs = STRONG
    elif total and (sup + part) / total >= 0.5:
        cs = MODERATE
    elif total and sup + part > 0:
        cs = LIMITED
    else:
        cs = INSUFFICIENT
    claim_support = _dim(
        cs,
        {"claims": total, "by_status": dict(by)},
        f"{sup} supported, {part} partially supported, {con} contradicted, "
        f"{by.get('unverified', 0) + by.get('insufficient_evidence', 0)} unverified of {total} claim(s). "
        "Support is a lexical-overlap check against the cited excerpt, not proof of accuracy.",
    )

    dims = {"coverage": coverage, "source_diversity": diversity, "temporal": temporal, "claim_support": claim_support}
    weakest = min(dims, key=lambda k: _ORDER.index(dims[k]["label"]))
    return {
        "rules_version": RULES_VERSION,
        "dimensions": dims,
        "limiting_dimension": weakest,
        "summary": f"Weakest dimension: {weakest.replace('_', ' ')} ({LABEL_TEXT[dims[weakest]['label']].lower()}).",
        "rules": RULES,
        "note": "These labels describe the amount and variety of retrieved evidence. They are not a probability that the dossier is correct.",
    }
