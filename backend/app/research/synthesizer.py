"""Grounded answer generation via Ollama (Qwen). Falls back to a clearly labelled
extractive summary if Ollama is unreachable; it never fabricates sources."""
import json
import logging
import re
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Tratepra, a research assistant. Answer ONLY using the numbered evidence provided. "
    "Cite evidence with bracketed numbers like [1] or [2][3] after each claim. "
    "Every factual sentence MUST end with at least one citation, and each citation must come from the "
    "evidence that supports that sentence. Never cite a number that is not in the evidence. Do not add "
    "facts that are not in the evidence. If the evidence is insufficient, say so. "
    'Respond as JSON: {"answer": "<2-4 paragraph summary with [n] citations>", '
    '"key_findings": ["<finding with [n] citation>", ...]} with 3-6 key findings.'
)


@dataclass
class SynthesisResult:
    answer: str
    key_findings: list[str]
    model: str
    degraded: bool = False


def _extractive_fallback(question: str, context_text: str, n_items: int, reason: str) -> SynthesisResult:
    findings = []
    for block in context_text.split("\n\n")[:5]:
        first = block.splitlines()[0] if block else ""
        m = re.match(r"\[(\d+)\]\s*\(.*?\)\s*(.*)", first)
        if m:
            findings.append(f"{m.group(2)} [{m.group(1)}]")
    if not findings:
        return SynthesisResult(
            answer="No relevant evidence was found for this query in the selected sources.",
            key_findings=[],
            model="none",
            degraded=True,
        )
    answer = (
        f"The language model was unavailable ({reason}), so this is an extractive summary of the "
        f"top {len(findings)} retrieved items rather than a synthesized answer. "
        + " ".join(findings[:3])
    )
    return SynthesisResult(answer=answer, key_findings=findings, model="extractive-fallback", degraded=True)


def synthesize(question: str, context_text: str, n_items: int) -> SynthesisResult:
    s = get_settings()
    if n_items == 0:
        return SynthesisResult(
            answer="No relevant evidence was found for this query in the selected sources.",
            key_findings=[],
            model="none",
            degraded=True,
        )
    payload = {
        "model": s.ollama_model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {question}\n\nEvidence:\n{context_text}"},
        ],
    }
    try:
        resp = httpx.post(f"{s.ollama_base_url}/api/chat", json=payload, timeout=120.0)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        data = json.loads(content)
        answer = str(data.get("answer", "")).strip()
        findings = [str(f).strip() for f in data.get("key_findings", []) if str(f).strip()]
        if not answer:
            raise ValueError("empty answer")
        return SynthesisResult(answer=answer, key_findings=findings, model=s.ollama_model)
    except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as exc:
        log.warning("Ollama synthesis failed: %s", exc)
        return _extractive_fallback(question, context_text, n_items, type(exc).__name__)
