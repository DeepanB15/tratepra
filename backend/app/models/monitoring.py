"""Phase 3 monitoring models. Snapshots are NOT stored separately: trend_observations (tied to completed
TrendRuns) are the snapshot history. user_id is nullable everywhere: the app is single-user today and these
tables are shaped so per-user scoping can be added later."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    literal_column,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import Topic, TrendObservation


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


EVENT_TYPES = (
    "growth_acceleration", "growth_slowdown", "activity_decline", "lifecycle_transition", "new_supporting_evidence",
    "contradictory_evidence", "new_related_topic", "activity_disappearance", "activity_spike", "new_emerging_trend",
    "monitoring_failure",
)
SEVERITIES = ("informational", "important", "critical")
EVENT_STATES = ("new", "read", "dismissed", "archived")
JOB_TYPES = ("collection", "recompute", "detection", "evidence", "notifications", "cycle")


def _in(values) -> str:
    return ",".join(f"'{v}'" for v in values)


class TrendWatchlist(Base):
    __tablename__ = "trend_watchlist"
    __table_args__ = (
        # One entry per topic per scope: separate partial uniques because NULL user_id values never collide.
        Index("uq_watchlist_topic_global", "topic_id", unique=True, postgresql_where=literal_column("user_id IS NULL")),
        Index("uq_watchlist_user_topic", "user_id", "topic_id", unique=True, postgresql_where=literal_column("user_id IS NOT NULL")),
        CheckConstraint("priority IN ('low','normal','high')", name="ck_watchlist_priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    priority: Mapped[str] = mapped_column(String(10), default="normal", server_default="normal")
    user_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    topic: Mapped[Topic] = relationship()


class TrendEvent(Base):
    """Immutable detection result. Only `state` (the activity-feed read/dismiss/archive flag) ever changes;
    it is independent of notification state."""

    __tablename__ = "trend_events"
    __table_args__ = (
        UniqueConstraint("deduplication_key", name="uq_trend_events_dedup"),
        CheckConstraint(f"event_type IN ({_in(EVENT_TYPES)})", name="ck_trend_events_type"),
        CheckConstraint(f"severity IN ({_in(SEVERITIES)})", name="ck_trend_events_severity"),
        CheckConstraint(f"state IN ({_in(EVENT_STATES)})", name="ck_trend_events_state"),
        Index("ix_trend_events_topic_detected", "topic_id", "detected_at"),
        Index("ix_trend_events_detected", "detected_at"),
        Index("ix_trend_events_type_topic", "event_type", "topic_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(15))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    previous_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_observation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trend_observations.id", ondelete="SET NULL"), nullable=True)
    current_observation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trend_observations.id", ondelete="SET NULL"), nullable=True)
    evidence_document_ids: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)  # metric name, inputs, thresholds, comparability, reliability
    detection_version: Mapped[str] = mapped_column(String(20))
    deduplication_key: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(10), default="new", server_default="new")
    state_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topic: Mapped[Topic | None] = relationship()
    current_observation: Mapped[TrendObservation | None] = relationship(foreign_keys=[current_observation_id])


class Notification(Base):
    """In-app notification for an event. Read/dismissed state lives here, never on the event."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("uq_notifications_event_global", "event_id", unique=True, postgresql_where=literal_column("user_id IS NULL")),
        Index("uq_notifications_user_event", "user_id", "event_id", unique=True, postgresql_where=literal_column("user_id IS NOT NULL")),
        Index("ix_notifications_unread", "read_at", "dismissed_at", "created_at"),
        CheckConstraint(f"severity IN ({_in(SEVERITIES)})", name="ck_notifications_severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trend_events.id", ondelete="CASCADE"))
    severity: Mapped[str] = mapped_column(String(15))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    event: Mapped[TrendEvent] = relationship()


class MonitoringPreference(Base):
    """Notification preferences. `scope_key` is 'global' today; a per-user key can replace it later."""

    __tablename__ = "monitoring_preferences"
    __table_args__ = (
        UniqueConstraint("scope_key", name="uq_monitoring_preferences_scope"),
        CheckConstraint(f"min_notification_severity IN ({_in(SEVERITIES)})", name="ck_prefs_severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    scope_key: Mapped[str] = mapped_column(String(64), default="global")
    min_notification_severity: Mapped[str] = mapped_column(String(15), default="informational", server_default="informational")
    muted_event_types: Mapped[list] = mapped_column(JSON, default=list)
    notify_watchlist_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class MonitoringJobRun(Base):
    __tablename__ = "monitoring_job_runs"
    __table_args__ = (
        CheckConstraint(f"job_type IN ({_in(JOB_TYPES)})", name="ck_job_runs_type"),
        CheckConstraint("status IN ('running','completed','failed','skipped')", name="ck_job_runs_status"),
        Index("ix_job_runs_type_started", "job_type", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10), default="running")
    trigger: Mapped[str] = mapped_column(String(10), default="scheduled")  # scheduled | manual
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
