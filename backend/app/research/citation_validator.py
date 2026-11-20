"""Validate [n] citations in generated text against the retrieved evidence."""
import re
from dataclasses import dataclass

_CITE = re.compile(r"\[(\d+)\]")


@dataclass
class ValidationResult:
    text: str
    cited: set[int]
    removed: set[int]


def validate_text(text: str, n_evidence: int) -> ValidationResult:
    """Keep citations 1..n_evidence; strip any that reference non-existent evidence."""
    cited: set[int] = set()
    removed: set[int] = set()

    def repl(m: re.Match) -> str:
        n = int(m.group(1))
        if 1 <= n <= n_evidence:
            cited.add(n)
            return m.group(0)
        removed.add(n)
        return ""

    cleaned = _CITE.sub(repl, text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).replace(" .", ".").replace(" ,", ",")
    return ValidationResult(text=cleaned.strip(), cited=cited, removed=removed)


def validate_all(answer: str, findings: list[str], n_evidence: int) -> tuple[str, list[str], set[int], set[int]]:
    a = validate_text(answer, n_evidence)
    cited, removed = set(a.cited), set(a.removed)
    clean_findings = []
    for f in findings:
        r = validate_text(f, n_evidence)
        cited |= r.cited
        removed |= r.removed
        if r.text:
            clean_findings.append(r.text)
    return a.text, clean_findings, cited, removed


# =====================================================================
# Claim-level verification
# =====================================================================
# Reference validation (above) only proves a citation number exists. This layer checks every
# claim (sentence): it needs at least one valid citation whose evidence has an openable URL, and
# the cited evidence must lexically cover the claim's content words.
#
# This is a transparent *heuristic*, not proof of factual correctness: it catches uncited claims,
# invented references and claims that share almost no content with what they cite. It cannot detect
# a claim that reuses the right words with the wrong meaning. Retrieval/answer quality still needs
# the measured evaluation in app/evaluation.
from dataclasses import dataclass, field
from urllib.parse import urlparse

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n+")
_WORD = re.compile(r"[a-z0-9][a-z0-9\-\+#]*")
_STOP = {
    "the", "and", "for", "are", "was", "were", "with", "that", "this", "from", "have", "has", "had", "into",
    "their", "they", "them", "its", "also", "such", "more", "than", "which", "while", "been", "being", "will",
    "can", "may", "about", "over", "across", "between", "these", "those", "there", "when", "where", "what",
    "not", "but", "his", "her", "our", "your", "you", "all", "any", "some", "most", "many", "other", "new",
}
_META = re.compile(r"\b(insufficient|no relevant|not enough|cannot be determined|unable to|no evidence)\b", re.I)
MIN_SUPPORT_OVERLAP = 0.2


@dataclass
class EvidenceRef:
    text: str  # title + description of the retrieved document
    url: str | None


@dataclass
class Claim:
    text: str
    cited: list[int]  # valid citations kept
    status: str  # supported | meta | uncited | weak | no_valid_citation
    overlap: float | None = None

    @property
    def verified(self) -> bool:
        return self.status in ("supported", "meta")


@dataclass
class VerifiedAnswer:
    answer: str
    key_findings: list[str]
    cited: set[int] = field(default_factory=set)
    removed_refs: set[int] = field(default_factory=set)
    unverified: list[dict] = field(default_factory=list)  # {"text", "reason", "section"}
    stats: dict = field(default_factory=dict)


def valid_url(url: str | None) -> bool:
    if not url:
        return False
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.netloc)


def _content_tokens(text: str) -> set[str]:
    out = set()
    for t in _WORD.findall(CITATION_RE.sub(" ", text).lower()):
        if len(t) > 2 and t not in _STOP:
            out.add(t[:-1] if t.endswith("s") and len(t) > 3 else t)
    return out


CITATION_RE = _CITE


def split_claims(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s and s.strip()]


def _check(sentence: str, evidence: list[EvidenceRef], min_overlap: float, removed: set[int]) -> Claim:
    refs = [int(n) for n in _CITE.findall(sentence)]
    valid = []
    for n in refs:
        if 1 <= n <= len(evidence) and valid_url(evidence[n - 1].url):
            valid.append(n)
        else:
            removed.add(n)
    clean = _CITE.sub(lambda m: m.group(0) if int(m.group(1)) in valid else "", sentence)
    clean = re.sub(r"[ \t]{2,}", " ", clean).replace(" .", ".").replace(" ,", ",").strip()
    tokens = _content_tokens(clean)

    if not valid:
        # A sentence that tried to cite something invalid is never "meta"; only uncited filler is.
        if _META.search(clean) or (not refs and len(tokens) < 3):
            return Claim(clean, [], "meta")  # not a factual claim (or an honest "insufficient evidence")
        return Claim(clean, [], "uncited" if not refs else "no_valid_citation")

    support = set().union(*(_content_tokens(evidence[n - 1].text) for n in valid))
    overlap = len(tokens & support) / len(tokens) if tokens else 1.0
    return Claim(clean, sorted(set(valid)), "supported" if overlap >= min_overlap else "weak", round(overlap, 3))


_REASONS = {
    "uncited": "no citation",
    "no_valid_citation": "cited evidence does not exist or has no openable source URL",
    "weak": "cited evidence shares too little content with the claim",
}


def verify_answer(
    answer: str,
    key_findings: list[str],
    evidence: list[EvidenceRef],
    min_overlap: float = MIN_SUPPORT_OVERLAP,
) -> VerifiedAnswer:
    """Keep only verified claims; report everything else as unverified (never silently dropped)."""
    removed: set[int] = set()
    cited: set[int] = set()
    unverified: list[dict] = []
    total = supported = 0

    kept_sentences = []
    for sentence in split_claims(answer):
        total += 1
        c = _check(sentence, evidence, min_overlap, removed)
        if c.verified:
            supported += 1
            cited.update(c.cited)
            kept_sentences.append(c.text)
        else:
            unverified.append({"text": c.text, "reason": _REASONS[c.status], "section": "answer"})

    kept_findings = []
    for finding in key_findings:
        total += 1
        c = _check(finding, evidence, min_overlap, removed)
        if c.verified and c.text:
            supported += 1
            cited.update(c.cited)
            kept_findings.append(c.text)
        else:
            unverified.append({"text": c.text, "reason": _REASONS.get(c.status, "unsupported"), "section": "key_findings"})

    text = " ".join(kept_sentences)
    if not text:
        text = (
            "No claim in the generated draft could be verified against the retrieved evidence. "
            "Review the evidence list directly."
            if total
            else "No relevant evidence was found for this query in the selected sources."
        )
    return VerifiedAnswer(
        answer=text,
        key_findings=kept_findings,
        cited=cited,
        removed_refs=removed,
        unverified=unverified,
        stats={"claims_total": total, "claims_verified": supported, "claims_unverified": len(unverified)},
    )
