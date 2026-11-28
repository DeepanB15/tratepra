"""Research/dossier quality metrics. Pure functions; every number is computed from supplied data, never defaulted."""
from collections import Counter

SECTION_KEYS = ["overview", "key_developments", "supporting_evidence", "contradictory_evidence", "key_entities", "evidence_gaps", "research_questions"]


def diversity(publishers: list[str]) -> dict:
    """Distinct publishers and the share held by the largest one (None when there is no evidence)."""
    if not publishers:
        return {"distinct_publishers": 0, "top_share": None}
    c = Counter(publishers)
    return {"distinct_publishers": len(c), "top_share": round(max(c.values()) / len(publishers), 3)}


def duplicate_rate(keys: list[str]) -> float | None:
    """Share of retrieved items that repeat an earlier item's duplicate key (url/content hash)."""
    if not keys:
        return None
    return round(1 - len(set(keys)) / len(keys), 3)


def dossier_metrics(dossier: dict, claims: list[dict], expected_gaps: set[str] | None = None) -> dict:
    """Claim- and structure-level metrics for one generated dossier."""
    n = len(claims)
    by = Counter(c["status"] for c in claims)
    cited = sum(1 for c in claims if c["supporting_evidence_ids"] or c["contradictory_evidence_ids"] or c["status"] in ("supported", "partially_supported"))
    out = {
        "claims": n,
        "citation_coverage": round(cited / n, 3) if n else None,  # claims tied to at least one evidence item
        "claim_support_rate": round((by.get("supported", 0) + by.get("partially_supported", 0)) / n, 3) if n else None,
        "unsupported_claim_rate": round((by.get("unverified", 0) + by.get("insufficient_evidence", 0) + by.get("contradicted", 0)) / n, 3) if n else None,
        "completeness": round(sum(1 for k in SECTION_KEYS if k in dossier["sections"]) / len(SECTION_KEYS), 3),
    }
    found = {g["code"] for g in dossier["sections"].get("evidence_gaps", {}).get("items", [])}
    if expected_gaps is not None:
        out["gap_recall"] = round(len(found & expected_gaps) / len(expected_gaps), 3) if expected_gaps else None
        out["gap_precision"] = round(len(found & expected_gaps) / len(found), 3) if found else None
    return out


def mean_of(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(vals) / len(vals), 3) if vals else None
