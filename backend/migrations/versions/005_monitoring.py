"""Phase 3: monitoring - watchlist, trend events, notifications, preferences, job runs.

Additive and idempotent (AUTO_CREATE_TABLES may already have created the tables). No existing table or row is
modified; trend_observations is reused as the snapshot history.

Revision ID: 005
Revises: 004
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

EVENT_TYPES = ("growth_acceleration", "growth_slowdown", "activity_decline", "lifecycle_transition", "new_supporting_evidence",
               "contradictory_evidence", "new_related_topic", "activity_disappearance", "activity_spike", "new_emerging_trend", "monitoring_failure")
SEVERITIES = ("informational", "important", "critical")
EVENT_STATES = ("new", "read", "dismissed", "archived")
JOB_TYPES = ("collection", "recompute", "detection", "evidence", "notifications", "cycle")


def _in(values) -> str:
    return ",".join(f"'{v}'" for v in values)


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _ts(name, nullable=True, default_now=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=sa.text("now()") if default_now else None)


def upgrade() -> None:
    if not _has_table("trend_watchlist"):
        op.create_table(
            "trend_watchlist",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("user_id", sa.UUID(), nullable=True),
            sa.Column("topic_id", sa.UUID(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
            _ts("added_at", False, True),
            sa.Column("monitoring_enabled", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
            sa.Column("user_note", sa.Text(), nullable=False, server_default=""),
            _ts("last_viewed_at"),
            _ts("created_at", False, True),
            _ts("updated_at", False, True),
            sa.CheckConstraint("priority IN ('low','normal','high')", name="ck_watchlist_priority"),
        )
        op.create_index("ix_trend_watchlist_topic_id", "trend_watchlist", ["topic_id"])
        op.create_index("uq_watchlist_topic_global", "trend_watchlist", ["topic_id"], unique=True, postgresql_where=sa.text("user_id IS NULL"))
        op.create_index("uq_watchlist_user_topic", "trend_watchlist", ["user_id", "topic_id"], unique=True, postgresql_where=sa.text("user_id IS NOT NULL"))

    if not _has_table("trend_events"):
        op.create_table(
            "trend_events",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("topic_id", sa.UUID(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=True),
            sa.Column("event_type", sa.String(40), nullable=False),
            sa.Column("severity", sa.String(15), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("previous_value", sa.Float(), nullable=True),
            sa.Column("current_value", sa.Float(), nullable=True),
            sa.Column("change_percentage", sa.Float(), nullable=True),
            sa.Column("previous_observation_id", sa.UUID(), sa.ForeignKey("trend_observations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("current_observation_id", sa.UUID(), sa.ForeignKey("trend_observations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("evidence_document_ids", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
            sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("detection_version", sa.String(20), nullable=False),
            sa.Column("deduplication_key", sa.String(200), nullable=False),
            sa.Column("state", sa.String(10), nullable=False, server_default="new"),
            _ts("state_changed_at"),
            _ts("detected_at", False, True),
            _ts("created_at", False, True),
            sa.UniqueConstraint("deduplication_key", name="uq_trend_events_dedup"),
            sa.CheckConstraint(f"event_type IN ({_in(EVENT_TYPES)})", name="ck_trend_events_type"),
            sa.CheckConstraint(f"severity IN ({_in(SEVERITIES)})", name="ck_trend_events_severity"),
            sa.CheckConstraint(f"state IN ({_in(EVENT_STATES)})", name="ck_trend_events_state"),
        )
        op.create_index("ix_trend_events_topic_detected", "trend_events", ["topic_id", "detected_at"])
        op.create_index("ix_trend_events_detected", "trend_events", ["detected_at"])
        op.create_index("ix_trend_events_type_topic", "trend_events", ["event_type", "topic_id"])

    if not _has_table("notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("user_id", sa.UUID(), nullable=True),
            sa.Column("event_id", sa.UUID(), sa.ForeignKey("trend_events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("severity", sa.String(15), nullable=False),
            _ts("read_at"),
            _ts("dismissed_at"),
            _ts("created_at", False, True),
            sa.CheckConstraint(f"severity IN ({_in(SEVERITIES)})", name="ck_notifications_severity"),
        )
        op.create_index("uq_notifications_event_global", "notifications", ["event_id"], unique=True, postgresql_where=sa.text("user_id IS NULL"))
        op.create_index("uq_notifications_user_event", "notifications", ["user_id", "event_id"], unique=True, postgresql_where=sa.text("user_id IS NOT NULL"))
        op.create_index("ix_notifications_unread", "notifications", ["read_at", "dismissed_at", "created_at"])

    if not _has_table("monitoring_preferences"):
        op.create_table(
            "monitoring_preferences",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("scope_key", sa.String(64), nullable=False, server_default="global"),
            sa.Column("min_notification_severity", sa.String(15), nullable=False, server_default="informational"),
            sa.Column("muted_event_types", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("notify_watchlist_only", sa.Boolean(), nullable=False, server_default="false"),
            _ts("updated_at", False, True),
            sa.UniqueConstraint("scope_key", name="uq_monitoring_preferences_scope"),
            sa.CheckConstraint(f"min_notification_severity IN ({_in(SEVERITIES)})", name="ck_prefs_severity"),
        )

    if not _has_table("monitoring_job_runs"):
        op.create_table(
            "monitoring_job_runs",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("cycle_id", sa.UUID(), nullable=True),
            sa.Column("job_type", sa.String(20), nullable=False),
            sa.Column("status", sa.String(10), nullable=False, server_default="running"),
            sa.Column("trigger", sa.String(10), nullable=False, server_default="scheduled"),
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
            _ts("started_at", False, True),
            _ts("completed_at"),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.CheckConstraint(f"job_type IN ({_in(JOB_TYPES)})", name="ck_job_runs_type"),
            sa.CheckConstraint("status IN ('running','completed','failed','skipped')", name="ck_job_runs_status"),
        )
        op.create_index("ix_job_runs_type_started", "monitoring_job_runs", ["job_type", "started_at"])
        op.create_index("ix_monitoring_job_runs_cycle_id", "monitoring_job_runs", ["cycle_id"])


def downgrade() -> None:
    # Drops only the tables this migration created. No Phase 1/2 data is touched.
    for t in ("monitoring_job_runs", "monitoring_preferences", "notifications", "trend_events", "trend_watchlist"):
        op.drop_table(t)
