"""Trend pipeline orchestration: documents -> BERTopic -> temporal signals -> Trend Score.

Each run appends new TrendObservation rows; old observations are never overwritten.
Topics are matched to the previous run by centroid similarity so a topic keeps its id
(and therefore its history) across runs.
"""
import logging
import uuid
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.connectors import all_connectors
from app.core.config import get_settings
from app.ingestion.collector import NON_TEXT_SOURCES
from app.intelligence import engagement as eng
from app.intelligence import growth as gr
from app.intelligence import lifecycle as lc
from app.intelligence import momentum as mo
from app.intelligence import novelty as nv
from app.intelligence import temporal_analysis as ta
from app.intelligence.preprocessor import prepare
from app.intelligence.explain import explain
from app.intelligence.topic_representations import centroid, match_topics, nearest_topics, topic_name
from app.intelligence.trend_score import trend_score
from app.models import (
    Document,
    DocumentEmbedding,
    Source,
    Topic,
    TopicDocument,
    TrendObservation,
)

log = logging.getLogger(__name__)

N_WINDOWS = 6


def _load_eligible(db: Session, lookback_days: int):
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    rows = db.execute(
        select(Document, Source.key, DocumentEmbedding.embedding)
        .join(Source, Source.id == Document.source_id)
        .join(DocumentEmbedding, DocumentEmbedding.document_id == Document.id)
        .where(Source.key.notin_(NON_TEXT_SOURCES), Document.published_at.is_not(None), Document.published_at >= cutoff)
    ).all()
    return rows


def _trends_points(db: Session) -> dict[str, list[tuple[datetime, float]]]:
    """Search-interest time series grouped by the originating query."""
    rows = db.execute(
        select(Document)
        .join(Source, Source.id == Document.source_id)
        .where(Source.key == "google_trends", Document.published_at.is_not(None))
    ).scalars()
    out: dict[str, list[tuple[datetime, float]]] = {}
    for d in rows:
        val = (d.engagement or {}).get("search_interest")
        q = (d.metadata_ or {}).get("query")
        if val is None or not q:
            continue
        out.setdefault(q, []).append((d.published_at, float(val)))
    return out


def recompute(db: Session) -> dict:
    s = get_settings()
    from app.intelligence.embeddings import model_name
    from app.intelligence.topic_model import fit_topics

    now = datetime.now(timezone.utc)
    rows = _load_eligible(db, s.trend_window_days * N_WINDOWS)
    if not rows:
        return {"status": "no_documents", "topics": 0}

    raw = [
        {"id": d.id, "text": d.normalized_text, "doc": d, "source": key, "vec": np.asarray(vec, dtype=np.float32)}
        for d, key, vec in rows
    ]
    kept, prep_stats = prepare(raw)
    if len(kept) < 20:
        return {"status": "insufficient_documents", "topics": 0, "prep": prep_stats}

    vecs = np.vstack([k["vec"] for k in kept])
    result = fit_topics([k["text"] for k in kept], vecs)

    # --- group docs by topic ---
    groups: dict[int, list[int]] = {}
    for idx, t in enumerate(result.assignments):
        if t != -1:
            groups.setdefault(t, []).append(idx)
    if not groups:
        return {"status": "no_topics_found", "topics": 0, "noise": result.n_noise, "prep": prep_stats}

    # --- history for novelty & continuity ---
    prior = db.scalars(select(Topic).where(Topic.embedding.is_not(None))).all()
    prior_vecs = {str(t.id): np.asarray(t.embedding, dtype=np.float32) for t in prior}

    edges = ta.window_edges(now, s.trend_window_days, N_WINDOWS)
    available = [c for c in all_connectors() if c.is_configured()]
    text_available = [c.key for c in available if c.key not in NON_TEXT_SOURCES]
    trends_series = _trends_points(db)
    run_id = uuid.uuid4().hex

    topic_info = {}
    eng_raw: dict[str, float | None] = {}
    for t_idx, members in groups.items():
        c = centroid(vecs[members])
        nov = nv.novelty_score(c, list(prior_vecs.values())) if prior_vecs else None
        topic_info[t_idx] = {"centroid": c, "novelty": nov, "match": None, "members": members}
        key = f"t{t_idx}"
        eng_raw[key] = eng.topic_engagement_raw(
            [eng.doc_engagement(kept[i]["source"], kept[i]["doc"].engagement) for i in members]
        )
    eng_norm = eng.percentile_normalize(eng_raw)

    # Continuity: one-to-one global matching so two new topics never claim the same stored topic.
    matches = match_topics({k: v["centroid"] for k, v in topic_info.items()}, prior_vecs, s.trend_topic_match_threshold)
    for t_idx, (pid, _sim) in matches.items():
        topic_info[t_idx]["match"] = pid

    # --- reset assignments for the documents we reassign ---
    doc_ids = [k["id"] for k in kept]
    db.execute(delete(TopicDocument).where(TopicDocument.document_id.in_(doc_ids)))

    used_ids: set[str] = set()
    created = 0
    for t_idx, info in topic_info.items():
        members = info["members"]
        terms = result.topic_terms.get(t_idx, [])
        name = topic_name(terms)
        topic = None
        if info["match"] and info["match"] not in used_ids:
            topic = db.get(Topic, uuid.UUID(info["match"]))
        if topic is None:
            topic = Topic(name=name)
            db.add(topic)
            created += 1
        topic.name, topic.terms = name, terms
        topic.embedding = info["centroid"].tolist()
        topic.model_version = f"bertopic+{model_name()}"
        topic.run_id = run_id
        db.flush()
        used_ids.add(str(topic.id))
        info["topic"] = topic

        for i in members:
            db.add(TopicDocument(topic_id=topic.id, document_id=kept[i]["id"], probability=result.probabilities[i]))

        # --- temporal signals ---
        ts = [kept[i]["doc"].published_at for i in members]
        volumes = ta.window_counts(ts, edges)
        g = gr.growth_pct(volumes[-1], volumes[-2]) if len(volumes) >= 2 else gr.GrowthResult(None, "insufficient_history")
        m = mo.momentum(volumes)
        sources_obs = sorted({kept[i]["source"] for i in members})
        cross = (
            100.0 * len(sources_obs) / len(text_available)
            if len(text_available) >= 2
            else None  # a single configured text source cannot show cross-source activity
        )
        search = None
        matched_query = None
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
            "novelty": info["novelty"],
            "search_interest": search,
            "cross_source_activity": cross,
        }
        sc = trend_score(signals)
        life = lc.classify(volumes)
        observed = set(sources_obs) | ({"google_trends"} if search is not None else set())
        db.add(
            TrendObservation(
                topic_id=topic.id,
                window_start=edges[-1][0],
                window_end=edges[-1][1],
                document_volume=volumes[-1],
                growth=signals["growth"],
                momentum=signals["momentum"],
                engagement=signals["engagement"],
                novelty=signals["novelty"],
                search_interest=signals["search_interest"],
                cross_source_activity=signals["cross_source_activity"],
                trend_score=sc.score,
                lifecycle=life,
                coverage={
                    "sources_available": len(available),
                    "sources_observed": len(observed),
                    "observed_sources": sorted(observed),
                    "signal_weight_coverage": round(sc.coverage_weight, 3),
                    "available_signals": sc.available,
                    "missing_signals": sc.missing,
                    "score_withheld": sc.withheld,
                    "min_coverage": s.trend_min_coverage,
                },
                raw_signals={
                    "volumes": volumes,
                    "growth_pct": g.value,
                    "growth_flag": g.flag,
                    "momentum_pp": m.value,
                    "momentum_direction": m.direction,
                    "trends_query": matched_query,
                    "topic_size": len(members),
                    "source_counts": {k: sum(1 for i in members if kept[i]["source"] == k) for k in sources_obs},
                },
                formula_version=s.trend_formula_version,
                model_version=f"bertopic+{model_name()}",
            )
        )
    db.commit()
    return {
        "status": "ok",
        "topics": len(topic_info),
        "new_topics": created,
        "noise_documents": result.n_noise,
        "documents": len(kept),
        "prep": prep_stats,
        "run_id": run_id,
    }


# ---------------- read side ----------------

def _latest_observation(db: Session, topic_id) -> TrendObservation | None:
    return db.scalar(
        select(TrendObservation).where(TrendObservation.topic_id == topic_id).order_by(TrendObservation.created_at.desc()).limit(1)
    )


def list_trends(db: Session, lifecycle: str | None = None, q: str | None = None, min_sources: int | None = None, limit: int = 50) -> list[dict]:
    out = []
    for t in db.scalars(select(Topic)).all():
        o = _latest_observation(db, t.id)
        if o is None:
            continue
        if lifecycle and o.lifecycle != lifecycle:
            continue
        if q and q.lower() not in t.name.lower() and not any(q.lower() in x.lower() for x in t.terms):
            continue
        if min_sources and (o.coverage or {}).get("sources_observed", 0) < min_sources:
            continue
        growth_pct = (o.raw_signals or {}).get("growth_pct")
        out.append(
            {
                "topic_id": str(t.id),
                "topic_name": t.name,
                "trend_score": o.trend_score,
                "lifecycle": o.lifecycle,
                "growth": growth_pct,
                "coverage": o.coverage,
                "sparkline": (o.raw_signals or {}).get("volumes", []),
                "last_updated": o.created_at,
            }
        )
    out.sort(key=lambda r: (r["trend_score"] is not None, r["trend_score"] or 0), reverse=True)
    return out[:limit]


def trend_detail(db: Session, topic_id: str) -> dict:
    try:
        tid = uuid.UUID(topic_id)
    except ValueError:
        raise LookupError("Topic not found")
    t = db.get(Topic, tid)
    if t is None:
        raise LookupError("Topic not found")
    obs = db.scalars(
        select(TrendObservation).where(TrendObservation.topic_id == t.id).order_by(TrendObservation.created_at.desc()).limit(2)
    ).all()
    o = obs[0] if obs else None
    prev = obs[1] if len(obs) > 1 else None
    related = []
    if t.embedding is not None:
        others = {str(x.id): np.asarray(x.embedding, dtype=np.float32) for x in db.scalars(select(Topic).where(Topic.id != t.id, Topic.embedding.is_not(None)))}
        names = {str(x.id): x.name for x in db.scalars(select(Topic))}
        related = [names[k] for k, _ in nearest_topics(np.asarray(t.embedding, dtype=np.float32), others, k=3)]

    docs = db.execute(
        select(Document, Source.key)
        .join(TopicDocument, TopicDocument.document_id == Document.id)
        .join(Source, Source.id == Document.source_id)
        .where(TopicDocument.topic_id == t.id)
        .order_by(Document.published_at.desc())
        .limit(8)
    ).all()
    signals = {
        "growth": o.growth if o else None,
        "momentum": o.momentum if o else None,
        "engagement": o.engagement if o else None,
        "novelty": o.novelty if o else None,
        "search_interest": o.search_interest if o else None,
        "cross_source_activity": o.cross_source_activity if o else None,
    }
    raw = (o.raw_signals or {}) if o else {}
    explanation = (
        explain(signals, o.trend_score, o.lifecycle, o.coverage or {}, raw.get("volumes", []), prev.trend_score if prev else None)
        if o
        else {"summary": "This topic has no trend observation yet.", "contributions": [], "missing": []}
    )
    return {
        "topic_id": str(t.id),
        "topic_name": t.name,
        "trend_score": o.trend_score if o else None,
        "lifecycle": o.lifecycle if o else None,
        "signals": signals,
        "coverage": o.coverage if o else {},
        "explanation": explanation,
        "source_distribution": raw.get("source_counts", {}),
        "weekly_volumes": raw.get("volumes", []),
        "previous_score": prev.trend_score if prev else None,
        "topic_size": raw.get("topic_size"),
        "related_topics": related,
        "representative_documents": [
            {"id": str(d.id), "title": d.title, "url": d.url, "source": key, "published_at": d.published_at}
            for d, key in docs
        ],
        "terms": t.terms,
        "last_updated": o.created_at if o else None,
    }


def trend_history(db: Session, topic_id: str) -> list[dict]:
    rows = db.scalars(
        select(TrendObservation).where(TrendObservation.topic_id == uuid.UUID(topic_id)).order_by(TrendObservation.created_at)
    ).all()
    return [
        {
            "window_start": r.window_start,
            "window_end": r.window_end,
            "document_volume": r.document_volume,
            "growth": (r.raw_signals or {}).get("growth_pct"),
            "trend_score": r.trend_score,
            "lifecycle": r.lifecycle,
            "created_at": r.created_at,
            "volumes": (r.raw_signals or {}).get("volumes", []),
        }
        for r in rows
    ]
