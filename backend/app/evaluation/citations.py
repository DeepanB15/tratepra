"""Citation-quality metrics computed from a VerifiedAnswer (see research/citation_validator.py)."""
from app.research.citation_validator import EvidenceRef, verify_answer


def citation_metrics(answer: str, findings: list[str], evidence: list[EvidenceRef]) -> dict:
    v = verify_answer(answer, findings, evidence)
    total = v.stats["claims_total"]
    return {
        "claims_total": total,
        "claims_verified": v.stats["claims_verified"],
        "verified_rate": round(v.stats["claims_verified"] / total, 3) if total else None,
        "invalid_references": len(v.removed_refs),
        "evidence_cited": len(v.cited),
        "evidence_available": len(evidence),
        "evidence_coverage": round(len(v.cited) / len(evidence), 3) if evidence else None,
        "unverified": v.unverified,
    }
