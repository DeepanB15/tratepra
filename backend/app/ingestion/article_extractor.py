
"""Optional, bounded article-text extraction.

RSS remains the discovery source. Extraction failures never discard RSS records.
"""
from dataclasses import dataclass
import logging

import trafilatura

log = logging.getLogger(__name__)

MAX_ARTICLE_CHARS = 20_000
MIN_ARTICLE_CHARS = 300


@dataclass
class ExtractionResult:
    text: str | None
    status: str
    method: str


def extract_article(html: bytes | str) -> ExtractionResult:
    """Extract readable article text from already-fetched HTML."""
    try:
        text = trafilatura.extract(
            html,
            output_format="txt",
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
        if not text:
            return ExtractionResult(None, "unavailable", "trafilatura")

        text = " ".join(text.split())[:MAX_ARTICLE_CHARS]

        if len(text) < MIN_ARTICLE_CHARS:
            return ExtractionResult(None, "insufficient_content", "trafilatura")

        return ExtractionResult(text, "extracted", "trafilatura")

    except Exception:
        log.exception("Article text extraction failed")
        return ExtractionResult(None, "error", "trafilatura")
