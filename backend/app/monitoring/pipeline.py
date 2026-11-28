"""Monitoring work units: change detection, evidence association, notification preparation, event persistence.

Persistence is idempotent: events carry deterministic deduplication keys (unique in the database), so running a
step twice over the same observations creates nothing new. A cooldown suppresses repeats of the same kind of
change for the same topic unless the new event is more severe than the latest one.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.intelligence.freshness import activity_state, config_from_settings
from app.models import (
    Document,
    MonitoringPreference,
    Notification,
    ResearchDossier,
    DossierClaim,
    Topic,
    TopicDocument,
    TrendEvent,
    TrendObservation,
    TrendRun,
    TrendWatchlist,
)
from app.monitoring.config import MonitoringConfig
from app.monitoring.detection import COOLDOWN_TYPES, SEV_RANK, Detection, EventCandidate, detect
from app.monitoring.explanations import explain, finalize
from app.monitoring.snapshots import load_snapshots
from app.research.claims import detect_contradiction
from app.research.citation_validator import _content_tokens
from app.research.excerpts import build_excerpt, publisher_of

log = logging.getLogger(__name__)
SEVERITIES = ("informational", "important", "critical")


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def cosine(a, b) -> float | None:
    if a is None or b is None:
        return None
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na and nb else None


def latest_completed_run(db: Session) -> TrendRun | None:
    return db.scalar(select(TrendRun).where(TrendRun.status == "completed").order_by(TrendRun.completed_at.desc()).limit(1))


def watched_topics(db: Session, enabled_only: bool = True) -> list[Topic]:
    q = select(Topic).join(TrendWatchlist, TrendWatchlist.topic_id == Topic.id)
    if enabled_only:
        q = q.where(TrendWatchlist.monitoring_enabled.is_(True))
    return list(db.scalars(q))


# ------------------------------------------------------------------ persistence
def persist_candidates(db: Session, cands: list[EventCandidate], cfg: MonitoringConfig, now: datetime, rewrite=None) -> dict:
    """Insert events idempotently. Returns counts and the created event ids."""
    created, duplicates, cooled = [], 0, 0
    for c in cands:
        if c.event_type in COOLDOWN_TYPES and c.topic_id:
            since = now - timedelta(hours=cfg.cooldown_hours)
            last = db.execute(
                select(TrendEvent.severity).where(
                    TrendEvent.topic_id == uuid.UUID(c.topic_id), TrendEvent.event_type == c.event_type, TrendEvent.detected_at >= since,
                    TrendEvent.deduplication_key != c.dedup_key,
                ).order_by(TrendEvent.detected_at.desc()).limit(1)
            ).scalar()
            if last is not None and SEV_RANK[c.severity] <= SEV_RANK[last]:
                cooled += 1
                continue
        titles = []
        if c.evidence_document_ids:
            titles = list(db.scalars(select(Document.title).where(Document.id.in_([uuid.UUID(i) for i in c.evidence_document_ids]))))
        text = explain(c, titles)
        text, rewritten = finalize(text, rewrite)
        c.details = {**c.details, "explanation_rewritten_by_llm": rewritten}
        desc = text.split(" Comparison:")[0].split(" Reliability:")[0]
        stmt = (
            pg_insert(TrendEvent)
            .values(
                id=uuid.uuid4(), topic_id=uuid.UUID(c.topic_id) if c.topic_id else None, event_type=c.event_type, severity=c.severity, title=c.title,
                description=desc, previous_value=c.previous_value, current_value=c.current_value, change_percentage=c.change_percentage,
                previous_observation_id=uuid.UUID(c.previous_observation_id) if c.previous_observation_id else None,
                current_observation_id=uuid.UUID(c.current_observation_id) if c.current_observation_id else None,
                evidence_document_ids=c.evidence_document_ids, explanation=text, details=c.details, detection_version=c.detection_version,
                deduplication_key=c.dedup_key, detected_at=now,
            )
            .on_conflict_do_nothing(index_elements=["deduplication_key"])
            .returning(TrendEvent.id)
        )
        new_id = db.execute(stmt).scalar()
        if new_id:
            created.append(str(new_id))
        else:
            duplicates += 1
    db.commit()
    return {"created": len(created), "event_ids": created, "duplicates": duplicates, "cooled_down": cooled}


def llm_rewrite_fn():
    """Optional readability rewrite via the existing Ollama config. Numbers are protected by explanations.guard_rewrite."""
    s = get_settings()
    if not s.monitoring_llm_explanations:
        return None
    import httpx

    def rewrite(text: str) -> str:
        r = httpx.post(
            f"{s.ollama_base_url}/api/chat", timeout=s.ollama_timeout_seconds,
            json={"model": s.ollama_model, "stream": False, "options": {"temperature": 0.1}, "messages": [
                {"role": "system", "content": "Rewrite the text to read more clearly. Keep every number exactly. Do not add facts, causes or numbers."},
                {"role": "user", "content": text}]},
        )
        r.raise_for_status()
        return r.json()["message"]["content"]

    return rewrite


# ------------------------------------------------------------------ job: change detection
def run_detection(db: Session, now: datetime | None = None, collection_failed: bool = False, cfg: MonitoringConfig | None = None) -> dict:
    s = get_settings()
    cfg = cfg or MonitoringConfig.from_settings(s)
    now = now or datetime.now(timezone.utc)
    run = latest_completed_run(db)
    if run is None:
        return {"skipped": True, "reason": "no completed trend run"}
    watched = {t.id: t for t in watched_topics(db)}
    new_topics = list(db.scalars(
        select(Topic).where(Topic.last_run_id == run.id, ~Topic.id.in_(list(watched) or [uuid.uuid4()]))
    ))
    completed = sorted(_aware(t) for t in db.scalars(select(TrendRun.completed_at).where(TrendRun.status == "completed")))
    fcfg = config_from_settings(s)
    ref = _aware(run.completed_at)
    all_cands, suppressed, evaluated = [], [], 0
    import bisect

    for topic in [*watched.values(), *new_topics]:
        history = load_snapshots(db, topic.id)
        if not history:
            continue
        evaluated += 1
        last = topic.last_observed_at
        missed = len(completed) - bisect.bisect_right(completed, _aware(last)) if last else len(completed)
        act = {"state": activity_state(last, ref, missed, fcfg), "missed_runs": missed, "last_observed_at": last}
        created = _aware(topic.created_at)
        is_new = bool(created and ref and (ref - created).total_seconds() <= cfg.new_topic_days * 86400)
        d: Detection = detect(history, cfg, topic_name=topic.name, collection_failed=collection_failed, activity=act, is_new_topic=is_new)
        if topic.id in watched:
            all_cands += d.events
        else:  # not followed: only the "new emerging trend" discovery event applies
            all_cands += [e for e in d.events if e.event_type == "new_emerging_trend"]
        suppressed += [{"topic": topic.name, **x} for x in d.suppressed]
    all_cands += _related_topic_events(db, run, watched, cfg)
    res = persist_candidates(db, all_cands, cfg, now, llm_rewrite_fn())
    return {"run_id": str(run.id), "topics_evaluated": evaluated, "candidates": len(all_cands), **res,
            "suppressed": suppressed[:50], "suppressed_total": len(suppressed), "collection_failed": collection_failed}


def _related_topic_events(db: Session, run: TrendRun, watched: dict, cfg: MonitoringConfig) -> list[EventCandidate]:
    """New topics (first observed in the latest run) that are similar to a followed topic. Identities are never merged."""
    if not watched:
        return []
    obs_counts = dict(db.execute(select(TrendObservation.topic_id, func.count()).group_by(TrendObservation.topic_id)).all())
    fresh = [t for t in db.scalars(select(Topic).where(Topic.last_run_id == run.id)) if obs_counts.get(t.id, 0) == 1 and t.id not in watched]
    out = []
    for w in watched.values():
        wsnaps = load_snapshots(db, w.id, 1)
        if not wsnaps:
            continue
        for n in fresh:
            sim = cosine(w.embedding, n.embedding)
            if sim is not None and sim >= cfg.related_similarity:
                out.append(EventCandidate(
                    event_type="new_related_topic", severity="informational", title=f"New topic related to {w.name}: {n.name}", topic_id=str(w.id),
                    dedup_key=f"{w.id}:new_related_topic:{n.id}", current_observation_id=wsnaps[-1].observation_id, current_value=round(sim, 3),
                    details={"topic": w.name, "related_topic_id": str(n.id), "related_name": n.name, "similarity": round(sim, 3), "metric": "topic_similarity",
                             "comparable_observations": 0, "sources": wsnaps[-1].sources, "formula_version": wsnaps[-1].formula_version,
                             "score_coverage": wsnaps[-1].score_coverage, "thresholds": {"related_similarity": cfg.related_similarity}},
                ))
    return out


# ------------------------------------------------------------------ job: evidence association
def run_evidence_association(db: Session, now: datetime | None = None, cfg: MonitoringConfig | None = None, max_docs: int = 20) -> dict:
    """New member documents per followed topic since its previous snapshot (E), and cheap contradiction checks of those
    documents against the latest dossier's claims (F). No dossier is regenerated here."""
    cfg = cfg or MonitoringConfig.from_settings(get_settings())
    now = now or datetime.now(timezone.utc)
    cands, checked = [], 0
    for topic in watched_topics(db):
        hist = load_snapshots(db, topic.id)
        if len(hist) < 2:
            continue  # first observation: everything is "new"; no baseline to call anything new against
        cur, prev = hist[-1], hist[-2]
        docs = list(db.scalars(
            select(Document).join(TopicDocument, TopicDocument.document_id == Document.id)
            .where(TopicDocument.topic_id == topic.id, Document.collected_at > prev.observed_at)
            .order_by(Document.published_at.desc().nullslast()).limit(max_docs)
        ))
        if len(docs) >= cfg.new_documents_min:
            pubs = {publisher_of(d) for d in docs}
            cands.append(EventCandidate(
                event_type="new_supporting_evidence", severity="informational", title=f"{topic.name}: {len(docs)} new documents", topic_id=str(topic.id),
                dedup_key=f"{topic.id}:new_supporting_evidence:{cur.observation_id}", previous_observation_id=prev.observation_id,
                current_observation_id=cur.observation_id, current_value=len(docs), evidence_document_ids=[str(d.id) for d in docs[:5]],
                details={"topic": topic.name, "metric": "new_documents", "unit": "documents", "publishers": len(pubs), "comparable_observations": 1,
                         "sources": cur.sources, "formula_version": cur.formula_version, "score_coverage": cur.score_coverage, "since": str(prev.observed_at),
                         "thresholds": {"new_documents_min": cfg.new_documents_min}},
            ))
        dossier = db.scalar(select(ResearchDossier).where(ResearchDossier.topic_id == topic.id, ResearchDossier.generated_at.is_not(None))
                            .order_by(ResearchDossier.generated_at.desc()).limit(1))
        if dossier and docs:
            claims = db.scalars(select(DossierClaim).where(DossierClaim.dossier_id == dossier.id, DossierClaim.status.in_(("supported", "partially_supported")))).all()
            newer = [d for d in docs if d.collected_at and _aware(d.collected_at) > _aware(dossier.generated_at)]
            found = 0
            for d in newer:
                ex = build_excerpt(d, None)
                text = f"{d.title}. {ex.text}"
                for c in claims:
                    checked += 1
                    ov = detect_contradiction(_content_tokens(c.text), text, c.text)
                    if ov is not None and found < 3:
                        found += 1
                        cands.append(EventCandidate(
                            event_type="contradictory_evidence", severity="important" if c.status == "supported" else "informational",
                            title=f"{topic.name}: new evidence may contradict a dossier statement", topic_id=str(topic.id),
                            dedup_key=f"{topic.id}:contradictory_evidence:{d.id}:{c.id}", current_observation_id=cur.observation_id,
                            evidence_document_ids=[str(d.id)], current_value=ov,
                            details={"topic": topic.name, "metric": "claim_overlap", "claim": c.text, "claim_status": c.status, "dossier_id": str(dossier.id),
                                     "overlap": ov, "method": "same polarity-cue heuristic as the dossier contradiction check (Phase 2)",
                                     "comparable_observations": 1, "sources": cur.sources, "formula_version": cur.formula_version, "score_coverage": cur.score_coverage},
                        ))
                        break
    res = persist_candidates(db, cands, cfg, now, llm_rewrite_fn())
    return {"candidates": len(cands), "claim_checks": checked, **res}


# ------------------------------------------------------------------ job: notification preparation
def get_preferences(db: Session) -> MonitoringPreference:
    p = db.scalar(select(MonitoringPreference).where(MonitoringPreference.scope_key == "global"))
    if p is None:
        db.execute(pg_insert(MonitoringPreference).values(id=uuid.uuid4(), scope_key="global", muted_event_types=[]).on_conflict_do_nothing(index_elements=["scope_key"]))
        db.commit()
        p = db.scalar(select(MonitoringPreference).where(MonitoringPreference.scope_key == "global"))
    return p


def prepare_notifications(db: Session) -> dict:
    """Create a notification for every event that has none and passes the current preferences. Events that do not
    pass remain in the activity feed; a later preference change does not retro-notify them."""
    prefs = get_preferences(db)
    floor = SEV_RANK[prefs.min_notification_severity]
    muted = set(prefs.muted_event_types or [])
    watched_ids = {t.id for t in watched_topics(db, enabled_only=False)} if prefs.notify_watchlist_only else None
    events = db.scalars(select(TrendEvent).outerjoin(Notification, Notification.event_id == TrendEvent.id).where(Notification.id.is_(None)).order_by(TrendEvent.detected_at)).all()
    made = skipped = 0
    for e in events:
        if SEV_RANK[e.severity] < floor or e.event_type in muted or (watched_ids is not None and e.topic_id not in watched_ids and e.event_type != "monitoring_failure"):
            skipped += 1
            continue
        r = db.execute(pg_insert(Notification).values(id=uuid.uuid4(), event_id=e.id, severity=e.severity).on_conflict_do_nothing().returning(Notification.id)).scalar()
        made += 1 if r else 0
    db.commit()
    return {"created": made, "skipped_by_preferences": skipped}
