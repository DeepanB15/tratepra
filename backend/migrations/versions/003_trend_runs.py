"""Phase 1: trend run tracking, observation->run link, topic freshness and review fields.

Additive only. No existing row is deleted or rewritten except a read-derived backfill of
topics.last_observed_at (max of the topic's existing observation timestamps). Legacy observations keep
run_id = NULL; they are preserved as-is and reported as legacy in the history endpoint.

Revision ID: 003
Revises: 002
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, col: str) -> bool:
    return any(c["name"] == col for c in sa.inspect(op.get_bind()).get_columns(table))


def _has_index(table: str, name: str) -> bool:
    return any(i["name"] == name for i in sa.inspect(op.get_bind()).get_indexes(table))


def _has_fk(table: str, name: str) -> bool:
    return any(f["name"] == name for f in sa.inspect(op.get_bind()).get_foreign_keys(table))


def upgrade() -> None:
    """Idempotent: with AUTO_CREATE_TABLES=true the app may already have created trend_runs (create_all creates
    missing tables but never adds columns), so every step first checks what exists."""
    if not _has_table("trend_runs"):
        _create_trend_runs()
    _upgrade_dependents()


def _create_trend_runs() -> None:
    op.create_table(
        "trend_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("documents_available", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("noise_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("topics_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("topics_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("topics_matched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_version", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("formula_version", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("configuration", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("diagnostics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key", name="uq_trend_runs_run_key"),
        sa.CheckConstraint("status IN ('pending','running','completed','failed')", name="ck_trend_runs_status"),
    )
    op.create_index("ix_trend_runs_status_completed", "trend_runs", ["status", "completed_at"])


def _upgrade_dependents() -> None:
    # --- observations -> runs ---
    if not _has_column("trend_observations", "run_id"):
        op.add_column("trend_observations", sa.Column("run_id", sa.UUID(), nullable=True))
    if not _has_fk("trend_observations", "fk_trend_obs_run"):
        op.create_foreign_key("fk_trend_obs_run", "trend_observations", "trend_runs", ["run_id"], ["id"], ondelete="SET NULL")
    if not _has_index("trend_observations", "ix_trend_observations_run_id"):
        op.create_index("ix_trend_observations_run_id", "trend_observations", ["run_id"])
    if not _has_index("trend_observations", "uq_trend_obs_topic_run"):
        op.create_index(
            "uq_trend_obs_topic_run", "trend_observations", ["topic_id", "run_id"], unique=True,
            postgresql_where=sa.text("run_id IS NOT NULL"),
        )

    # --- topics: freshness + naming review ---
    if not _has_column("topics", "last_run_id"):
        op.add_column("topics", sa.Column("last_run_id", sa.UUID(), nullable=True))
    if not _has_fk("topics", "fk_topics_last_run"):
        op.create_foreign_key("fk_topics_last_run", "topics", "trend_runs", ["last_run_id"], ["id"], ondelete="SET NULL")
    if not _has_column("topics", "last_observed_at"):
        op.add_column("topics", sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_index("topics", "ix_topics_last_observed_at"):
        op.create_index("ix_topics_last_observed_at", "topics", ["last_observed_at"])
    if not _has_column("topics", "name_confidence"):
        op.add_column("topics", sa.Column("name_confidence", sa.Float(), nullable=True))
    if not _has_column("topics", "needs_review"):
        op.add_column("topics", sa.Column("needs_review", sa.Boolean(), nullable=False, server_default="false"))
    if not _has_column("topics", "review_reasons"):
        op.add_column("topics", sa.Column("review_reasons", sa.JSON(), nullable=False, server_default="[]"))

    # Backfill from existing history (read-derived; nothing is deleted or reset).
    op.execute(
        """
        UPDATE topics t
        SET last_observed_at = o.last_seen
        FROM (SELECT topic_id, MAX(created_at) AS last_seen FROM trend_observations GROUP BY topic_id) o
        WHERE o.topic_id = t.id AND t.last_observed_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("topics", "review_reasons")
    op.drop_column("topics", "needs_review")
    op.drop_column("topics", "name_confidence")
    op.drop_index("ix_topics_last_observed_at", table_name="topics")
    op.drop_column("topics", "last_observed_at")
    op.drop_constraint("fk_topics_last_run", "topics", type_="foreignkey")
    op.drop_column("topics", "last_run_id")

    op.drop_index("uq_trend_obs_topic_run", table_name="trend_observations")
    op.drop_index("ix_trend_observations_run_id", table_name="trend_observations")
    op.drop_constraint("fk_trend_obs_run", "trend_observations", type_="foreignkey")
    op.drop_column("trend_observations", "run_id")

    op.drop_index("ix_trend_runs_status_completed", table_name="trend_runs")
    op.drop_table("trend_runs")
