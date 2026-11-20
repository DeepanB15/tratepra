"""Deduplication, layered cheapest-first:
1. exact (source, external_id)
2. canonical URL
3. content hash
4. lightweight near-duplicate detection (token Jaccard) within the same source

Near-duplicate checks stay within one source on purpose: the same story appearing in news and
on YouTube is genuine cross-source activity and must not be collapsed.
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, Source

NEAR_DUP_THRESHOLD = 0.8
MIN_TOKENS_FOR_NEAR_DUP = 4
RECENT_STORED_LIMIT = 1000

_TOKEN = re.compile(r"[a-z0-9]+")


def token_set(text: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN.findall((text or "").lower()) if len(t) > 2)


def jaccard_similarity(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_near_duplicate(tokens: frozenset[str], pool: list[frozenset[str]], threshold: float) -> bool:
    if len(tokens) < MIN_TOKENS_FOR_NEAR_DUP:
        return False
    return any(len(p) >= MIN_TOKENS_FOR_NEAR_DUP and jaccard_similarity(tokens, p) >= threshold for p in pool)


def _sim_text(d: dict) -> str:
    return (d.get("title") or "") + " " + (d.get("description") or "")[:200]


def dedupe_batch(docs: list[dict], near_threshold: float = NEAR_DUP_THRESHOLD) -> list[dict]:
    seen_ids, seen_urls, seen_hashes = set(), set(), set()
    pools: dict[str, list[frozenset[str]]] = {}
    out = []
    for d in docs:
        id_key = (d["source"], d["external_id"])
        url_key = d.get("canonical_url")
        h = d["content_hash"]
        if id_key in seen_ids or (url_key and url_key in seen_urls) or h in seen_hashes:
            continue
        tokens = token_set(_sim_text(d))
        pool = pools.setdefault(d["source"], [])
        if _is_near_duplicate(tokens, pool, near_threshold):
            continue
        seen_ids.add(id_key)
        if url_key:
            seen_urls.add(url_key)
        seen_hashes.add(h)
        pool.append(tokens)
        out.append(d)
    return out


def filter_existing(db: Session, docs: list[dict], near_threshold: float = NEAR_DUP_THRESHOLD) -> tuple[list[dict], int]:
    """Drop docs already stored (exact or near-duplicate). Returns (new_docs, duplicate_count)."""
    if not docs:
        return [], 0
    hashes = [d["content_hash"] for d in docs]
    urls = [d["canonical_url"] for d in docs if d.get("canonical_url")]
    existing_hashes = set(db.scalars(select(Document.content_hash).where(Document.content_hash.in_(hashes))))
    existing_urls = set(db.scalars(select(Document.canonical_url).where(Document.canonical_url.in_(urls)))) if urls else set()

    sources = {s.key: s.id for s in db.scalars(select(Source))}
    ext_pairs = set()
    recent_pools: dict[str, list[frozenset[str]]] = {}
    for key, sid in sources.items():
        ids = [d["external_id"] for d in docs if d["source"] == key]
        if not ids:
            continue
        ext_pairs |= {
            (key, e)
            for e in db.scalars(select(Document.external_id).where(Document.source_id == sid, Document.external_id.in_(ids)))
        }
        recent = db.scalars(
            select(Document.normalized_text).where(Document.source_id == sid).order_by(Document.collected_at.desc()).limit(RECENT_STORED_LIMIT)
        )
        recent_pools[key] = [token_set(t[:300]) for t in recent]

    new = []
    for d in docs:
        if (
            d["content_hash"] in existing_hashes
            or (d.get("canonical_url") and d["canonical_url"] in existing_urls)
            or (d["source"], d["external_id"]) in ext_pairs
            or _is_near_duplicate(token_set(_sim_text(d)), recent_pools.get(d["source"], []), near_threshold)
        ):
            continue
        new.append(d)
    return new, len(docs) - len(new)
