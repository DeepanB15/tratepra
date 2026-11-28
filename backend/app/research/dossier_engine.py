"""Pure dossier builder: evidence + (optional) synthesized draft -> sections A-G, claims, evidence quality.

No database and no network here, so every rule is unit-testable. Nothing in a dossier is invented: sections
B, C, D, E, F and G are derived deterministically from the retrieved documents, claim checks and detected gaps;
only the overview prose (section A) can come from the LLM, and every sentence of it is claim-checked.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.research import evidence_quality
from app.research.claims import (
    ENGINE_VERSION as CLAIMS_VERSION,
    EvidenceView,
    VerifiedClaim,
    extract_claims,
    verify_claim,
)
from app.research.evidence_quality import EvidenceItem
from app.research.excerpts import publisher_of
from app.research.query_processor import extract_phrases

ENGINE_VERSION = "dossier-1"
NO_CONTRADICTION_TEXT = "No contradictory evidence was identified in the available dataset."
NO_EVIDENCE_TEXT = (
    "Insufficient evidence: no relevant documents were found in the available dataset for this subject and time range."
)
MAX_DEVELOPMENTS = 8
MAX_ENTITIES = 12
MAX_QUESTIONS = 8


@dataclass
class DossierContent:
    sections: dict
    evidence: list[dict]  # rows for dossier_evidence
    claims: list[VerifiedClaim]
    evidence_quality: dict
    versions: dict = field(default_factory=dict)


def _day(d: datetime | None) -> str | None:
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.date().isoformat()


def _first_sentence(text: str, limit: int = 220) -> str:
    s = (text or "").strip().split(". ")[0]
    return (s if len(s) <= limit else s[: limit - 1] + "…").strip()


def build_dossier(
    *,
    subject: str,
    selected: list,  # RankedItem, citation i+1
    excerpts: list,  # Excerpt per selected item (same order)
    overview: str,
    key_findings: list[str],
    model: str,
    degraded: bool,
    window_days: float,
    requested_sources: list[str],
    entity_seeds: list[tuple[str, str]] | None = None,  # (name, origin) from query/topic terms
    support_threshold: float = 0.6,
    now: datetime | None = None,
) -> DossierContent:
    now = now or datetime.now(timezone.utc)
    docs = [i.candidate.document for i in selected]
    views = [
        EvidenceView(
            index=n,
            key=str(d.id),
            url=d.url,
            text=f"{d.title}. {ex.text}",
            publisher=publisher_of(d),
        )
        for n, (d, ex) in enumerate(zip(docs, excerpts), start=1)
    ]

    # ---- claims (A / key findings), verified deterministically ---------------------------------
    claims = [verify_claim(t, section, views, support_threshold) for t, section in extract_claims(overview, key_findings)]
    for n, c in enumerate(claims, start=1):
        c.explanation = c.explanation or "No additional detail."

    # ---- evidence rows with roles ----------------------------------------------------------------
    role: dict[str, tuple[str, str]] = {}
    for n, c in enumerate(claims, start=1):
        for link in c.links:
            if link.relation == "contradicts":
                role[link.evidence_key] = ("contradictory", f"Opposite-polarity statement about claim {n}: \"{c.text[:120]}\"")
    for n, c in enumerate(claims, start=1):
        for link in c.links:
            if link.relation == "supports" and link.evidence_key not in role:
                role[link.evidence_key] = ("supporting", f"Covers {round(link.overlap * 100)}% of the content words of claim {n}.")
    evidence_rows = []
    for rank, (item, d, ex, v) in enumerate(zip(selected, docs, excerpts, views), start=1):
        r, why = role.get(v.key, ("context", "Retrieved as relevant to the subject; not linked to a specific claim."))
        evidence_rows.append(
            {
                "document_id": d.id,
                "key": v.key,
                "rank": rank,
                "role": r,
                "role_reason": why,
                "relevance": round(item.score, 2),
                "excerpt": ex.text,
                "excerpt_basis": ex.basis,
                "article_status": getattr(d, "article_status", "rss_only"),
                "title": d.title,
                "url": d.url,
                "publisher": v.publisher,
                "source": item.candidate.source_key,
                "published": _day(d.published_at),
            }
        )

    # ---- quality -------------------------------------------------------------------------------
    quality = evidence_quality.assess(
        [
            EvidenceItem(
                key=d.canonical_url or d.content_hash or "",
                title=d.title,
                publisher=v.publisher,
                day=_day(d.published_at),
                article_status=getattr(d, "article_status", "rss_only"),
            )
            for d, v in zip(docs, views)
        ],
        [{"status": c.status} for c in claims],
        window_days,
    )

    # ---- sections ------------------------------------------------------------------------------
    kept = [c for c in claims if c.status in ("supported", "partially_supported")]
    overview_text = " ".join(c.text for c in kept if c.section == "overview") or (
        NO_EVIDENCE_TEXT if not docs else "No statement in the generated overview could be verified against the retrieved evidence; see the claim list and evidence."
    )
    sec_a = {
        "text": overview_text,
        "model": model,
        "degraded": degraded,
        "claims_total": len(claims),
        "claims_flagged": len([c for c in claims if c.status not in ("supported", "partially_supported")]),
        "note": "Statements are checked by lexical overlap with the cited excerpt; this is not proof of accuracy.",
    }

    dated = sorted((r for r in evidence_rows if r["published"]), key=lambda r: r["published"])
    undated = [r for r in evidence_rows if not r["published"]]
    developments = [
        {
            "date": r["published"], "title": r["title"], "publisher": r["publisher"], "document_id": str(r["document_id"]),
            "citation": r["rank"], "summary": _first_sentence(r["excerpt"]), "article_status": r["article_status"],
        }
        for r in (dated + undated)[:MAX_DEVELOPMENTS]
    ]
    sec_b = {"items": developments, "ordering": "chronological; undated items last"}

    def ev_out(r):
        return {k: (str(v) if k == "document_id" else v) for k, v in r.items() if k != "key"}

    sec_c = {"items": [ev_out(r) for r in evidence_rows if r["role"] == "supporting"]}
    contra = [ev_out(r) for r in evidence_rows if r["role"] == "contradictory"]
    sec_d = {
        "items": contra,
        "text": None if contra else NO_CONTRADICTION_TEXT,
        "method": "Polarity-cue heuristic: a sentence about the same content words as a claim, with opposite negation/decline cues. It cannot find contradictions that lack such cues.",
    }

    # entities: only names that actually occur in the retrieved documents
    seeds = list(entity_seeds or [])
    seeds += [(p, "evidence_titles") for p in _title_phrases(docs)]
    entities = {}
    for name, origin in seeds:
        n = name.lower().strip()
        if not n or n in entities:
            continue
        hits = [d for d in docs if n in (d.normalized_text or "").lower() or n in d.title.lower()]
        if hits:
            entities[n] = {
                "name": name, "origin": origin, "documents": len(hits),
                "publishers": len({publisher_of(d) for d in hits}), "document_ids": [str(d.id) for d in hits[:5]],
            }
    sec_e = {"items": sorted(entities.values(), key=lambda e: (-e["documents"], e["name"]))[:MAX_ENTITIES],
             "method": "Names are taken from the question, trend terms and capitalised phrases repeated in evidence titles, and kept only when found in the retrieved documents."}

    gaps = _gaps(evidence_rows, quality, claims, requested_sources, window_days, now, degraded)
    sec_f = {"items": gaps}
    sec_g = {"items": _questions(subject, gaps, claims, sec_e["items"]),
             "note": "Suggested follow-ups generated from the detected gaps and claim checks. They are not findings."}

    sections = {
        "overview": sec_a, "key_developments": sec_b, "supporting_evidence": sec_c,
        "contradictory_evidence": sec_d, "key_entities": sec_e, "evidence_gaps": sec_f, "research_questions": sec_g,
    }
    return DossierContent(
        sections=sections, evidence=evidence_rows, claims=claims, evidence_quality=quality,
        versions={"dossier_engine": ENGINE_VERSION, "claims": CLAIMS_VERSION, "evidence_quality": evidence_quality.RULES_VERSION},
    )


def _title_phrases(docs: list) -> list[str]:
    """Multi-word capitalised phrases that appear in at least two evidence titles."""
    from collections import Counter

    c = Counter()
    for d in docs:
        c.update(set(extract_phrases(d.title)))
    return [p for p, n in c.items() if n >= 2]


def _gaps(rows, quality, claims, requested_sources, window_days, now, degraded) -> list[dict]:
    gaps = []

    def add(code, text, severity="info"):
        gaps.append({"code": code, "text": text, "severity": severity})

    dims = quality["dimensions"]
    n = dims["coverage"]["unique_documents"]
    if n == 0:
        add("no_evidence", "No relevant documents were found.", "high")
        return gaps
    if n < 4:
        add("few_documents", f"Only {n} unique document(s) were found.", "high" if n < 2 else "medium")
    limited = dims["coverage"]["rss_only_or_unavailable"]
    if limited and limited / n >= 0.5:
        add("feed_summaries_only", f"{limited} of {n} documents are limited to feed summaries; full article text was unavailable.", "medium")
    div = dims["source_diversity"]
    if div["publishers"] < 2:
        add("single_publisher", "All evidence comes from a single publisher.", "high")
    elif div["top_publisher_share"] > 0.6:
        add("publisher_concentration", f"{round(div['top_publisher_share'] * 100)}% of the evidence comes from {div['top_publisher']}.", "medium")
    t = dims["temporal"]
    if t["distinct_days"] < 3 and window_days > 7:
        add("narrow_time_coverage", f"Evidence covers only {t['distinct_days']} distinct day(s) of a {round(window_days)}-day window.", "medium")
    if t["latest"]:
        age = (now.date() - datetime.fromisoformat(t["latest"]).date()).days
        if age > max(3, 0.25 * window_days):
            add("no_recent_evidence", f"The most recent evidence is {age} days old.", "medium")
    if t["undated"]:
        add("undated_evidence", f"{t['undated']} document(s) have no publication date.", "low")
    present = {r["source"] for r in rows}
    missing = [s for s in requested_sources if s not in present]
    if missing:
        add("sources_without_evidence", "No evidence from: " + ", ".join(missing) + ".", "low")
    weak = [c for c in claims if c.status in ("unverified", "insufficient_evidence")]
    if weak:
        add("unverified_claims", f"{len(weak)} generated statement(s) could not be verified against the evidence.", "medium")
    single = [c for c in claims if c.status == "supported" and c.source_coverage <= 1]
    if single:
        add("single_source_support", f"{len(single)} supported statement(s) rest on a single publisher.", "low")
    if degraded:
        add("llm_unavailable", "The language model was unavailable; the overview is an extractive summary.", "medium")
    return gaps


def _questions(subject: str, gaps: list[dict], claims: list[VerifiedClaim], entities: list[dict]) -> list[str]:
    qs: list[str] = []
    for c in [c for c in claims if c.status == "contradicted"][:2]:
        qs.append(f"Why does the available evidence disagree about: \"{c.text[:140]}\"?")
    for c in [c for c in claims if c.status in ("partially_supported", "unverified")][:3]:
        qs.append(f"What additional reporting confirms or refutes: \"{c.text[:140]}\"?")
    codes = {g["code"] for g in gaps}
    if codes & {"single_publisher", "publisher_concentration"}:
        qs.append(f"Which other publishers have covered {subject}?")
    if codes & {"narrow_time_coverage", "no_recent_evidence"}:
        qs.append(f"What has changed about {subject} in the most recent days?")
    if "feed_summaries_only" in codes:
        qs.append("What do the full articles behind the feed summaries say?")
    if "no_evidence" in codes:
        qs.append(f"Which sources or keywords would surface evidence about {subject}?")
    for e in entities[:2]:
        qs.append(f"How is {e['name']} involved in {subject}?")
    return list(dict.fromkeys(qs))[:MAX_QUESTIONS]
