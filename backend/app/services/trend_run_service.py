"""Trend pipeline orchestration with persisted, idempotent runs.

documents -> validation -> BERTopic -> identity resolution -> temporal signals -> Trend Score -> persist.

Guarantees
- Every execution is a TrendRun. The run key fingerprints (eligible documents, analysis window, model
  configuration, embedding model, formula version); a COMPLETED run with the same key is returned as-is and
  nothing is appended, so repeating an identical analysis cannot create duplicate observations.
- All topic / observation / membership writes happen in ONE transaction that also marks the run completed.
  Any failure rolls that back and only then records the failure on the run, so a failed run cannot corrupt
  earlier observations or make topics look stale (last_observed_at moves only on a completed run).
- Nothing is deleted from history. Observations are append-only.
"""
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors import all_connectors
from app.core.config import Settings, get_settings
from app.ingestion.collector import NON_TEXT_SOURCES
from app.intelligence import engagement as eng
from app.intelligence import growth as gr
from app.intelligence import lifecycle as lc
from app.intelligence import momentum as mo
from app.intelligence import novelty as nv
from app.intelligence import temporal_analysis as ta
from app.intelligence import topic_identity as ti
from app.intelligence.preprocessor import prepare
from app.intelligence.run_key import analysis_anchor, compute_run_key, document_fingerprint
from app.intelligence.topic_diagnostics import run_diagnostics, topic_cohesion
from app.intelligence.topic_model import MIN_DOCS, model_parameters
from app.intelligence.topic_naming import name_topic
from app.intelligence.topic_representations import centroid
from app.intelligence.trend_score import trend_score, weights
from app.models import Document, DocumentEmbedding, Source, Topic, TopicDocument, TrendObservation, TrendRun

log = logging.getLogger(__name__)

FitFn = Callable[..., object]


# ---------------------------------------------------------------- helpers
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_error(exc: BaseException | str, limit: int = 500) -> str:
    """Error text safe to persist and expose: no credentials, no connection strings."""
    text = f"{type(exc).__name__}: {exc}" if isinstance(exc, BaseException) else str(exc)
    text = re.sub(r"([a-z][a-z0-9+.\-]*://)[^@\s/]+@", r"\1***@", text, flags=re.I)
    text = re.sub(r"(password|passwd|pwd|token|api[_-]?key|secret)\s*[=:]\s*\S+", r"\1=***", text, flags=re.I)
    return text[:limit]


def build_configuration(s: Settings, n_docs: int) -> dict:
    """Everything that can change the result of a run. Hashed into the run key; stored on the run.
    Contains no secrets (numeric/enum model parameters only)."""
    return {
        "topic_model": model_parameters(max(n_docs, MIN_DOCS)),
        "embedding_model": s.embedding_model,
        "embedding_dim": s.embedding_dim,
        "window_days": s.trend_window_days,
        "n_windows": s.trend_n_windows,
        "topic_match_threshold": s.trend_topic_match_threshold,
        "identity_floor": s.trend_identity_floor,
        "signal_weights": weights(s),
        "min_coverage": s.trend_min_coverage,
        "lifecycle": {
            "emerging_min_growth": s.lifecycle_emerging_min_growth,
            "growing_min_growth": s.lifecycle_growing_min_growth,
            "declining_max_growth": s.lifecycle_declining_max_growth,
            "min_documents": s.lifecycle_min_documents,
            "min_abs_increase": s.lifecycle_min_abs_increase,
        },
        "formula_version": s.trend_formula_version,
    }


def _load_candidates(db: Session, anchor: datetime, lookback_days: int):
    cutoff = anchor - timedelta(days=lookback_days)
    text_filter = (
        Source.key.notin_(NON_TEXT_SOURCES), Document.published_at.is_not(None),
        Document.published_at >= cutoff, Document.published_at <= anchor,
    )
    rows = db.execute(
        select(Document, Source.key, DocumentEmbedding.embedding, DocumentEmbedding.model, DocumentEmbedding.text_hash)
        .join(Source, Source.id == Document.source_id)
        .join(DocumentEmbedding, DocumentEmbedding.document_id == Document.id)
        .where(*text_filter)
        .order_by(Document.id)
    ).all()
    base = select(func.count(Document.id)).join(Source, Source.id == Document.source_id)
    counts = {
        "text_documents_in_window": db.scalar(base.where(*text_filter)) or 0,
        "future_dated": db.scalar(base.where(Source.key.notin_(NON_TEXT_SOURCES), Document.published_at > anchor)) or 0,
        "undated_text_documents": db.scalar(base.where(Source.key.notin_(NON_TEXT_SOURCES), Document.published_at.is_(None))) or 0,
        "non_text_documents_in_window": db.scalar(base.where(Source.key.in_(NON_TEXT_SOURCES), Document.published_at >= cutoff, Document.published_at <= anchor)) or 0,
    }
    counts["with_embedding"] = len(rows)
    counts["without_embedding"] = max(0, counts["text_documents_in_window"] - len(rows))
    return rows, counts


def _trends_points(db: Session) -> dict[str, list[tuple[datetime, float]]]:
    """Search-interest time series grouped by the originating query."""
    rows = db.execute(
        select(Document).join(Source, Source.id == Document.source_id).where(Source.key == "google_trends", Document.published_at.is_not(None))
    ).scalars()
    out: dict[str, list[tuple[datetime, float]]] = {}
    for d in rows:
        val = (d.engagement or {}).get("search_interest")
        q = (d.metadata_ or {}).get("query")
        if val is None or not q:
            continue
        out.setdefault(q, []).append((d.published_at, float(val)))
    return out


def run_summary(run: TrendRun, status: str | None = None) -> dict:
    d = run.diagnostics or {}
    return {
        "status": status or run.status,
        "run_id": str(run.id),
        "run_key": run.run_key,
        "topics": run.topics_discovered,
        "new_topics": run.topics_created,
        "matched_topics": run.topics_matched,
        "noise_documents": run.noise_documents,
        "documents": run.documents_processed,
        "documents_rejected": run.documents_rejected,
        "completed_at": run.completed_at,
        "error": run.error_message,
        "prep": d.get("prep"),
    }


# ---------------------------------------------------------------- analysis (no writes)
def _analyse(db: Session, s: Settings, kept: list[dict], vecs: np.ndarray, result, anchor: datetime) -> dict:
    groups: dict[int, list[int]] = {}
    for idx, t in enumerate(result.assignments):
        if t != -1:
            groups.setdefault(t, []).append(idx)

    prior = db.scalars(select(Topic).where(Topic.embedding.is_not(None))).all()
    prior_vecs = {str(t.id): np.asarray(t.embedding, dtype=np.float32) for t in prior}
    prior_versions = {str(t.id): t.model_version for t in prior}

    edges = ta.window_edges(anchor, s.trend_window_days, s.trend_n_windows)
    available = [c for c in all_connectors() if c.is_configured()]
    text_available = [c.key for c in available if c.key not in NON_TEXT_SOURCES]
    trends_series = _trends_points(db)

    info: dict[int, dict] = {}
    eng_raw: dict[str, float | None] = {}
    for t_idx, members in groups.items():
        c = centroid(vecs[members])
        nov = nv.novelty_score(c, list(prior_vecs.values())) if prior_vecs else None
        info[t_idx] = {"centroid": c, "novelty": nov, "members": members, "cohesion": topic_cohesion(vecs[members], c)}
        eng_raw[f"t{t_idx}"] = eng.topic_engagement_raw([eng.doc_engagement(kept[i]["source"], kept[i]["doc"].engagement) for i in members])
    eng_norm = eng.percentile_normalize(eng_raw)

    decisions = ti.resolve_identities({k: v["centroid"] for k, v in info.items()}, prior_vecs, s.trend_topic_match_threshold, s.trend_identity_floor)

    for t_idx, e in info.items():
        members = e["members"]
        terms = result.topic_terms.get(t_idx, [])
        nm = name_topic(terms, [kept[i]["text"] for i in members], s.topic_name_min_coverage)
        e.update(terms=terms, naming=nm, decision=decisions[t_idx])

        ts = [kept[i]["doc"].published_at for i in members]
        volumes = ta.window_counts(ts, edges)
        g = gr.growth_pct(volumes[-1], volumes[-2]) if len(volumes) >= 2 else gr.GrowthResult(None, "insufficient_history")
        m = mo.momentum(volumes)
        sources_obs = sorted({kept[i]["source"] for i in members})
        cross = 100.0 * len(sources_obs) / len(text_available) if len(text_available) >= 2 else None
        search, matched_query = None, None
        for q, pts in trends_series.items():
            if ta.terms_overlap(q, terms):
                search = ta.search_interest_signal(pts)
                matched_query = q
                if search is not None:
                    break
        signals = {
            "growth": gr.normalize_growth(g.value),
            "momentum": mo.normalize_momentum(m.value),
            "engagement": eng_norm.get(f"t{t_idx}"),
            "novelty": e["novelty"],
            "search_interest": search,
            "cross_source_activity": cross,
        }
        sc = trend_score(signals)
        observed = set(sources_obs) | ({"google_trends"} if search is not None else set())
        e.update(
            volumes=volumes, growth=g, momentum=m, signals=signals, score=sc, lifecycle=lc.classify(volumes),
            sources_obs=sources_obs, observed=observed, available_n=len(available), matched_query=matched_query,
        )
    versions_changed = sorted({prior_versions[d.matched_topic_id] for d in decisions.values() if d.matched_topic_id and prior_versions.get(d.matched_topic_id)})
    return {"info": info, "edges": edges, "prior_count": len(prior_vecs), "prior_versions": versions_changed}


def _identity_diagnostics(info: dict[int, dict], model_version: str, prior_versions: list[str], prior_count: int) -> dict:
    counts = {o: 0 for o in ti.OUTCOMES}
    rows = []
    for t_idx, e in info.items():
        d: ti.IdentityDecision = e["decision"]
        counts[d.outcome] += 1
        rows.append({"topic_index": t_idx, "name": e["naming"].name, **d.as_dict()})
    return {
        "stored_topics_considered": prior_count,
        "outcomes": counts,
        "model_version": model_version,
        "model_version_changed": any(v != model_version for v in prior_versions),
        "previous_model_versions": prior_versions,
        "decisions": rows,
    }


# ---------------------------------------------------------------- run lifecycle
def _claim_run(db: Session, s: Settings, key: str, anchor: datetime, configuration: dict, model_version: str, now: datetime):
    """Return (run, early_result). early_result is set when the caller must not execute."""
    existing = db.scalar(select(TrendRun).where(TrendRun.run_key == key))
    if existing is not None:
        if existing.status == "completed":
            return existing, run_summary(existing, "unchanged")
        timed_out = existing.started_at is None or (now - existing.started_at) > timedelta(minutes=s.trend_running_timeout_minutes)
        if existing.status in ("running", "pending") and not timed_out:
            return existing, run_summary(existing, "already_running")
        attempts = int((existing.diagnostics or {}).get("attempts", 1)) + 1  # retry of a failed / crashed run
        existing.status, existing.started_at, existing.error_message = "running", now, None
        existing.diagnostics = {"attempts": attempts}
        db.commit()
        return existing, None
    run = TrendRun(
        run_key=key, status="running", started_at=now, window_end=anchor, configuration=configuration,
        model_version=model_version, formula_version=s.trend_formula_version, diagnostics={"attempts": 1},
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:  # another process claimed the same key between our SELECT and INSERT
        db.rollback()
        other = db.scalar(select(TrendRun).where(TrendRun.run_key == key))
        return other, run_summary(other, "unchanged" if other.status == "completed" else "already_running")
    return run, None


def _mark_failed(db: Session, run: TrendRun, message: str, diagnostics: dict | None = None) -> None:
    db.rollback()
    run = db.get(TrendRun, run.id)
    run.status, run.error_message, run.completed_at = "failed", sanitize_error(message), None
    if diagnostics:
        run.diagnostics = {**(run.diagnostics or {}), **diagnostics}
    db.commit()


def _persist(db: Session, s: Settings, run: TrendRun, kept: list[dict], result, analysis: dict, model_version: str, done_at: datetime) -> tuple[int, int]:
    """Write topics, memberships and observations. Caller commits (single transaction)."""
    info, edges = analysis["info"], analysis["edges"]
    db.execute(delete(TopicDocument).where(TopicDocument.document_id.in_([k["id"] for k in kept])))

    created = matched = 0
    used: set[str] = set()
    for t_idx, e in info.items():
        d: ti.IdentityDecision = e["decision"]
        nm = e["naming"]
        topic = None
        if d.matched_topic_id and d.matched_topic_id not in used:
            topic = db.get(Topic, uuid.UUID(d.matched_topic_id))
        if topic is None:
            topic = Topic(name=nm.name)
            db.add(topic)
            created += 1
        else:
            matched += 1
        reasons = list(nm.reasons)
        if d.outcome in (ti.SPLIT, ti.MERGE, ti.UNCERTAIN):
            reasons.append(f"identity: {d.outcome.replace('_', ' ')}")
        topic.name, topic.terms = nm.name, e["terms"]
        topic.embedding = e["centroid"].tolist()
        topic.model_version, topic.run_id = model_version, str(run.id)
        topic.last_run_id, topic.last_observed_at = run.id, done_at
        topic.name_confidence, topic.needs_review, topic.review_reasons = nm.confidence, bool(reasons), reasons
        db.flush()
        used.add(str(topic.id))
        e["topic_id"] = str(topic.id)

        for i in e["members"]:
            db.add(TopicDocument(topic_id=topic.id, document_id=kept[i]["id"], probability=result.probabilities[i]))

        sc, g, m, sig = e["score"], e["growth"], e["momentum"], e["signals"]
        members = e["members"]
        db.add(
            TrendObservation(
                topic_id=topic.id, run_id=run.id, window_start=edges[-1][0], window_end=edges[-1][1],
                document_volume=e["volumes"][-1],
                growth=sig["growth"], momentum=sig["momentum"], engagement=sig["engagement"], novelty=sig["novelty"],
                search_interest=sig["search_interest"], cross_source_activity=sig["cross_source_activity"],
                trend_score=sc.score, lifecycle=e["lifecycle"],
                coverage={
                    "sources_available": e["available_n"],
                    "sources_observed": len(e["observed"]),
                    "observed_sources": sorted(e["observed"]),
                    "signal_weight_coverage": round(sc.coverage_weight, 3),
                    "available_signals": sc.available,
                    "missing_signals": sc.missing,
                    "score_withheld": sc.withheld,
                    "min_coverage": s.trend_min_coverage,
                    "identity": d.as_dict(),
                },
                raw_signals={
                    "volumes": e["volumes"],
                    "growth_pct": g.value,
                    "growth_flag": g.flag,
                    "momentum_pp": m.value,
                    "momentum_direction": m.direction,
                    "trends_query": e["matched_query"],
                    "topic_size": len(members),
                    "source_counts": {k: sum(1 for i in members if kept[i]["source"] == k) for k in e["sources_obs"]},
                    "cohesion": round(float(e["cohesion"]), 4),
                    "name_coverage": nm.coverage,
                },
                formula_version=s.trend_formula_version, model_version=model_version,
            )
        )
    return created, matched


# ---------------------------------------------------------------- public entry point
def recompute(db: Session, as_of: datetime | None = None, dry_run: bool = False, fit: FitFn | None = None) -> dict:
    """Run (or recognise) one trend analysis.

    as_of    analysis time (default: now). The window ends at the start of the next UTC day.
    dry_run  perform the full analysis and return diagnostics but write NOTHING (safe on a live database).
    fit      topic-model function (default: BERTopic pipeline); injectable for tests.
    """
    s = get_settings()
    from app.intelligence.embeddings import model_name

    if fit is None:
        from app.intelligence.topic_model import fit_topics as fit

    now = as_of or _utcnow()
    anchor = analysis_anchor(now)
    model_version = f"bertopic+{model_name()}"

    rows, counts = _load_candidates(db, anchor, s.trend_window_days * s.trend_n_windows)
    raw = [
        {"id": d.id, "text": d.normalized_text, "doc": d, "source": key, "vec": np.asarray(vec, dtype=np.float32) if vec is not None else None,
         "embedding_model": emodel, "content_hash": d.content_hash, "text_hash": thash}
        for d, key, vec, emodel, thash in rows
    ]
    kept, prep = prepare(raw, expected_dim=s.embedding_dim, expected_model=s.embedding_model)
    input_diag = {**counts, "documents_available": len(rows)}

    configuration = build_configuration(s, len(kept))
    fingerprint = document_fingerprint([(str(k["id"]), k["content_hash"] or "", k["text_hash"] or "", k["doc"].published_at.isoformat()) for k in kept])
    key = compute_run_key(documents_fingerprint=fingerprint, window_end=anchor, configuration=configuration)

    base_diag = {"input": input_diag, "prep": prep, "documents_fingerprint": fingerprint}

    if dry_run:
        return _dry_run(db, s, kept, anchor, base_diag, key, fit, model_version)

    run, early = _claim_run(db, s, key, anchor, configuration, model_version, _utcnow())  # wall clock, not as_of
    if early is not None:
        return early
    run.documents_available, run.documents_processed, run.documents_rejected = len(rows), len(kept), prep["rejected"]
    try:
        if not rows:
            _mark_failed(db, run, "no_documents: no eligible text documents with embeddings in the analysis window", base_diag)
            return {**run_summary(db.get(TrendRun, run.id)), "status": "no_documents", "topics": 0}
        if len(kept) < MIN_DOCS:
            _mark_failed(db, run, f"insufficient_documents: {len(kept)} usable documents, topic modeling needs {MIN_DOCS}", base_diag)
            return {**run_summary(db.get(TrendRun, run.id)), "status": "insufficient_documents", "topics": 0, "prep": prep}

        vecs = np.vstack([k["vec"] for k in kept])
        result = fit([k["text"] for k in kept], vecs)
        if not any(t != -1 for t in result.assignments):
            _mark_failed(db, run, "no_topics_found: every document was classified as noise", {**base_diag, "noise_documents": result.n_noise})
            return {**run_summary(db.get(TrendRun, run.id)), "status": "no_topics_found", "topics": 0, "noise_documents": result.n_noise, "prep": prep}

        analysis = _analyse(db, s, kept, vecs, result, anchor)
        base_diag["model_notes"] = getattr(result, "notes", None) or []
        done_at = _utcnow()
        created, matched = _persist(db, s, run, kept, result, analysis, model_version, done_at)

        info = analysis["info"]
        diag = run_diagnostics(
            result.assignments, [k["source"] for k in kept],
            result.topic_terms, {t: e["cohesion"] for t, e in info.items()},
            languages={"en": len(kept), "rejected_non_english": prep["non_english"]},
            broad_share=s.topic_broad_share, high_noise_share=s.topic_high_noise_share,
        )
        diag["topics"] = [
            {
                "topic_id": e["topic_id"], "name": e["naming"].name, "size": len(e["members"]), "terms": e["terms"][:5],
                "name_confidence": e["naming"].confidence, "name_coverage": e["naming"].coverage, "needs_review": e["naming"].needs_review,
                "review_reasons": e["naming"].reasons, "cohesion": round(float(e["cohesion"]), 4), "identity": e["decision"].outcome,
                "score_withheld": e["score"].withheld,
            }
            for e in info.values()
        ]
        run.status, run.completed_at, run.error_message = "completed", done_at, None
        run.noise_documents, run.topics_discovered = result.n_noise, len(info)
        run.topics_created, run.topics_matched = created, matched
        run.diagnostics = {
            **(run.diagnostics or {}), **base_diag, "topic_quality": diag,
            "identity": _identity_diagnostics(info, model_version, analysis["prior_versions"], analysis["prior_count"]),
        }
        db.commit()  # topics + observations + run completion: one atomic commit
        return {**run_summary(run), "status": "ok", "run_id": str(run.id)}
    except Exception as exc:
        log.exception("trend run %s failed", run.id)
        _mark_failed(db, run, exc, base_diag)
        raise


def _dry_run(db, s, kept, anchor, base_diag, key, fit, model_version) -> dict:
    out = {"status": "dry_run", "run_key": key, "documents": len(kept), "prep": base_diag["prep"], "input": base_diag["input"], "topics": 0}
    if len(kept) < MIN_DOCS:
        return {**out, "status": "insufficient_documents"}
    vecs = np.vstack([k["vec"] for k in kept])
    result = fit([k["text"] for k in kept], vecs)
    if not any(t != -1 for t in result.assignments):
        return {**out, "status": "no_topics_found", "noise_documents": result.n_noise}
    analysis = _analyse(db, s, kept, vecs, result, anchor)
    info = analysis["info"]
    diag = run_diagnostics(
        result.assignments, [k["source"] for k in kept], result.topic_terms, {t: e["cohesion"] for t, e in info.items()},
        languages={"en": len(kept), "rejected_non_english": base_diag["prep"]["non_english"]},
        broad_share=s.topic_broad_share, high_noise_share=s.topic_high_noise_share,
    )
    topics = []
    for t_idx, e in info.items():
        sc, nm = e["score"], e["naming"]
        top = sorted(e["members"], key=lambda i: -float(np.dot(kept[i]["vec"], e["centroid"]) / (np.linalg.norm(kept[i]["vec"]) or 1.0)))[:5]
        topics.append(
            {
                "name": nm.name, "size": len(e["members"]), "terms": e["terms"][:8], "name_confidence": nm.confidence,
                "name_coverage": nm.coverage, "needs_review": nm.needs_review, "review_reasons": nm.reasons,
                "cohesion": round(float(e["cohesion"]), 4), "volumes": e["volumes"], "lifecycle": e["lifecycle"],
                "score": sc.score, "score_withheld": sc.withheld, "score_coverage": round(sc.coverage_weight, 3),
                "available_signals": sc.available, "missing_signals": sc.missing, "sources": e["sources_obs"],
                "identity": e["decision"].as_dict(),
                "representative_titles": [kept[i]["doc"].title for i in top],
            }
        )
    return {
        **out, "status": "dry_run", "topics": len(info), "noise_documents": result.n_noise, "topic_quality": diag, "topic_details": topics,
        "identity": _identity_diagnostics(info, model_version, analysis["prior_versions"], analysis["prior_count"]),
    }
