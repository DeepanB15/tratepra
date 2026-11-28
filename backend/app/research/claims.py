"""Claim-level verification for dossiers (deterministic; no LLM call per claim).

Each claim is a sentence of the generated overview or a key finding. For every claim we record the evidence it
cites, whether that citation exists and has an openable URL, how much of the claim's content vocabulary appears
in the cited excerpt, any evidence that *contradicts* it, and a status:

  supported              valid citation and token coverage >= support threshold (default 0.6)
  partially_supported    valid citation and coverage between the minimum (0.2) and the support threshold
  contradicted           evidence with opposite polarity about the same content (see detect_contradiction)
  unverified             no citation, an invalid citation, or coverage below the minimum
  insufficient_evidence  nothing to verify against (no evidence) or the cited excerpt is too short to judge

LIMITATION (kept visible in the product): coverage is lexical overlap, not entailment. A claim can reuse the right
words with the wrong meaning and still pass; a correct paraphrase can fail. Contradiction detection is likewise
a conservative polarity-cue heuristic and misses most contradictions that are not phrased with an explicit cue.
"""
import re
from dataclasses import dataclass, field

from app.research.citation_validator import (
    MIN_SUPPORT_OVERLAP,
    _CITE,
    _content_tokens,
    split_claims,
    valid_url,
)

ENGINE_VERSION = "claims-1"
MIN_EXCERPT_CHARS = 40

_NEG = re.compile(
    r"\b(no|not|never|none|without|denies|denied|deny|disputes?|disputed|debunk\w*|refutes?|refuted|false|untrue|"
    r"fails?|failed|fell|drops?|dropped|declin\w+|decreas\w+|shrink\w*|rejects?|rejected|contradict\w*)\b",
    re.I,
)
_QUANT = re.compile(r"\d")
_TEMPORAL = re.compile(r"\b(since|until|before|after|in (?:19|20)\d\d|last (?:week|month|year)|yesterday|today|20\d\d)\b", re.I)
_OPINION = re.compile(r"\b(should|best|worst|likely|expected to|may|might|could|probably|believe|think)\b", re.I)


def claim_type(text: str) -> str:
    if _OPINION.search(text):
        return "opinion"
    if _QUANT.search(text):
        return "quantitative"
    if _TEMPORAL.search(text):
        return "temporal"
    return "factual"


@dataclass
class EvidenceView:
    """What claim verification may see of one piece of evidence (the excerpt shown to the model)."""

    index: int  # 1-based citation number
    key: str  # stable id (document id)
    url: str | None
    text: str  # title + excerpt
    publisher: str


@dataclass
class ClaimLink:
    evidence_key: str
    relation: str  # supports | contradicts
    overlap: float


@dataclass
class VerifiedClaim:
    text: str
    section: str
    claim_type: str
    status: str
    explanation: str
    overlap: float | None
    links: list[ClaimLink] = field(default_factory=list)
    source_coverage: int = 0
    cited: list[int] = field(default_factory=list)


def polarity(text: str) -> bool:
    """True when the text carries an explicit negation / refutation / decline cue."""
    return bool(_NEG.search(text))


def detect_contradiction(claim_tokens: set[str], evidence_text: str, claim_text: str) -> float | None:
    """Overlap score when some sentence of the evidence discusses the same content as the claim (>= 50% of the
    claim's content tokens) but has the OPPOSITE polarity cue state. Otherwise None."""
    if len(claim_tokens) < 3:
        return None
    claim_neg = polarity(_CITE.sub("", claim_text))
    for sentence in split_claims(evidence_text):
        toks = _content_tokens(sentence)
        if not toks:
            continue
        ov = len(claim_tokens & toks) / len(claim_tokens)
        if ov >= 0.5 and polarity(sentence) != claim_neg:
            return round(ov, 3)
    return None


def verify_claim(text: str, section: str, evidence: list[EvidenceView], support_threshold: float = 0.6) -> VerifiedClaim:
    ctype = claim_type(text)
    refs = sorted({int(n) for n in _CITE.findall(text)})
    clean = re.sub(r"\s{2,}", " ", _CITE.sub("", text)).replace(" .", ".").replace(" ,", ",").strip()
    tokens = _content_tokens(clean)

    if not evidence:
        return VerifiedClaim(clean, section, ctype, "insufficient_evidence", "No evidence was retrieved to check this claim against.", None)

    valid = [n for n in refs if 1 <= n <= len(evidence) and valid_url(evidence[n - 1].url)]
    invalid = [n for n in refs if n not in valid]
    links: list[ClaimLink] = []
    overlap = None
    status, why = "unverified", ""

    # Contradiction search runs over ALL retrieved evidence, cited or not.
    contradicted_by = []
    for ev in evidence:
        c = detect_contradiction(tokens, ev.text, clean)
        if c is not None:
            contradicted_by.append((ev, c))
            links.append(ClaimLink(ev.key, "contradicts", c))

    if not refs:
        why = "The claim has no citation."
    elif not valid:
        why = "Every cited reference is missing or has no openable source URL" + (f" (invalid: {invalid})." if invalid else ".")
    else:
        per = []
        for n in valid:
            ev = evidence[n - 1]
            ov = (len(tokens & _content_tokens(ev.text)) / len(tokens)) if tokens else 1.0
            per.append((n, ev, ov))
        best_n, best_ev, overlap = max(per, key=lambda x: x[2])
        overlap = round(overlap, 3)
        for n, ev, ov in per:
            if ov >= MIN_SUPPORT_OVERLAP:
                links.append(ClaimLink(ev.key, "supports", round(ov, 3)))
        if all(len(e.text) < MIN_EXCERPT_CHARS for _, e, _ in per):
            status, why = "insufficient_evidence", "The cited excerpt is too short to judge the claim."
        elif overlap >= support_threshold:
            status, why = "supported", f"Cited evidence [{best_n}] covers {round(overlap * 100)}% of the claim's content words (lexical check)."
        elif overlap >= MIN_SUPPORT_OVERLAP:
            status, why = "partially_supported", f"Cited evidence [{best_n}] covers only {round(overlap * 100)}% of the claim's content words (lexical check)."
        else:
            why = f"Cited evidence shares too little vocabulary with the claim ({round(overlap * 100)}% of content words)."

    if contradicted_by:
        ev, c = max(contradicted_by, key=lambda x: x[1])
        status = "contradicted"
        why = (why + " " if why else "") + f"Evidence [{ev.index}] discusses the same content with opposite polarity cues (overlap {round(c * 100)}%); review it."
    supporters = {evidence_by_key.publisher for evidence_by_key in evidence if any(l.evidence_key == evidence_by_key.key and l.relation == "supports" for l in links)}
    return VerifiedClaim(clean, section, ctype, status, why.strip(), overlap, links, len(supporters), valid)


def extract_claims(overview: str, key_findings: list[str]) -> list[tuple[str, str]]:
    """(text, section) for every sentence of the overview and every key finding, de-duplicated."""
    out, seen = [], set()
    for section, texts in (("overview", split_claims(overview or "")), ("key_findings", key_findings or [])):
        for t in texts:
            norm = re.sub(r"\W+", " ", _CITE.sub("", t).lower()).strip()
            if norm and norm not in seen and len(norm) > 3:
                seen.add(norm)
                out.append((t, section))
    return out
