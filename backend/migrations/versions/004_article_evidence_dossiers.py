"""Phase 2: article evidence state on documents; research dossiers, evidence, claims.

Additive and idempotent (AUTO_CREATE_TABLES=true may already have created the new tables; create_all never
adds columns, so every step checks what exists). Existing documents are never rewritten except a read-derived
backfill that marks documents whose metadata already records a successful extraction as status 'full'
(article_text stays NULL for those legacy rows: the text is still inside normalized_text).

Revision ID: 004
Revises: 003
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

DOC_COLUMNS = [
    ("article_status", sa.Column("article_status", sa.String(20), nullable=False, server_default="rss_only")),
    ("article_text", sa.Column("article_text", sa.Text(), nullable=True)),
    ("article_method", sa.Column("article_method", sa.String(40), nullable=True)),
    ("article_extracted_at", sa.Column("article_extracted_at", sa.DateTime(timezone=True), nullable=True)),
    ("article_text_hash", sa.Column("article_text_hash", sa.String(64), nullable=True)),
    ("article_failure_reason", sa.Column("article_failure_reason", sa.String(80), nullable=True)),
]


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _insp().has_table(name)


def _has_column(table: str, col: str) -> bool:
    return any(c["name"] == col for c in _insp().get_columns(table))


def upgrade() -> None:
    for name, col in DOC_COLUMNS:
        if not _has_column("documents", name):
            op.add_column("documents", col)
    op.execute(
        """
        UPDATE documents SET article_status = 'full', article_method = COALESCE(metadata->'article_extraction'->>'method','trafilatura')
        WHERE article_status = 'rss_only' AND metadata->'article_extraction'->>'status' = 'extracted'
        """
    )

    if not _has_table("research_dossiers"):
        op.create_table(
            "research_dossiers",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("dossier_key", sa.String(64), nullable=False),
            sa.Column("topic_id", sa.UUID(), sa.ForeignKey("topics.id", ondelete="SET NULL"), nullable=True),
            sa.Column("title", sa.Text(), nullable=False, server_default=""),
            sa.Column("query_text", sa.Text(), nullable=False),
            sa.Column("time_range", sa.String(20), nullable=False, server_default="30d"),
            sa.Column("source_filters", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sections", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("evidence_quality", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("diagnostics", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("versions", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("model", sa.String(100), nullable=False, server_default=""),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("dossier_key", name="uq_research_dossiers_key"),
            sa.CheckConstraint("status IN ('pending','running','completed','failed')", name="ck_research_dossiers_status"),
        )
        op.create_index("ix_research_dossiers_topic", "research_dossiers", ["topic_id"])

    if not _has_table("dossier_evidence"):
        op.create_table(
            "dossier_evidence",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("dossier_id", sa.UUID(), sa.ForeignKey("research_dossiers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("rank", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(20), nullable=False, server_default="supporting"),
            sa.Column("role_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("relevance", sa.Float(), nullable=False, server_default="0"),
            sa.Column("publisher", sa.String(255), nullable=False, server_default=""),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("excerpt", sa.Text(), nullable=False, server_default=""),
            sa.Column("excerpt_basis", sa.String(20), nullable=False, server_default="rss"),
            sa.Column("article_status", sa.String(20), nullable=False, server_default="rss_only"),
            sa.Column("diagnostics", sa.JSON(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("dossier_id", "document_id", name="uq_dossier_evidence_doc"),
            sa.CheckConstraint("role IN ('supporting','contradictory','context')", name="ck_dossier_evidence_role"),
        )
        op.create_index("ix_dossier_evidence_dossier_rank", "dossier_evidence", ["dossier_id", "rank"])
        op.create_index("ix_dossier_evidence_document_id", "dossier_evidence", ["document_id"])
        op.create_index("ix_dossier_evidence_publisher", "dossier_evidence", ["publisher"])

    if not _has_table("dossier_claims"):
        op.create_table(
            "dossier_claims",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("dossier_id", sa.UUID(), sa.ForeignKey("research_dossiers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("claim_no", sa.Integer(), nullable=False),
            sa.Column("section", sa.String(40), nullable=False, server_default="overview"),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("claim_type", sa.String(20), nullable=False, server_default="factual"),
            sa.Column("status", sa.String(30), nullable=False, server_default="unverified"),
            sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
            sa.Column("overlap", sa.Float(), nullable=True),
            sa.Column("source_coverage", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("dossier_id", "claim_no", name="uq_dossier_claims_no"),
            sa.CheckConstraint(
                "status IN ('supported','partially_supported','contradicted','unverified','insufficient_evidence')",
                name="ck_dossier_claims_status",
            ),
        )
        op.create_index("ix_dossier_claims_dossier_id", "dossier_claims", ["dossier_id"])

    if not _has_table("claim_evidence"):
        op.create_table(
            "claim_evidence",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("claim_id", sa.UUID(), sa.ForeignKey("dossier_claims.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "dossier_evidence_id", sa.UUID(), sa.ForeignKey("dossier_evidence.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("relation", sa.String(20), nullable=False, server_default="supports"),
            sa.Column("overlap", sa.Float(), nullable=True),
            sa.UniqueConstraint("claim_id", "dossier_evidence_id", "relation", name="uq_claim_evidence"),
            sa.CheckConstraint("relation IN ('supports','contradicts')", name="ck_claim_evidence_relation"),
        )
        op.create_index("ix_claim_evidence_claim_id", "claim_evidence", ["claim_id"])
        op.create_index("ix_claim_evidence_dossier_evidence_id", "claim_evidence", ["dossier_evidence_id"])


def downgrade() -> None:
    op.drop_table("claim_evidence")
    op.drop_table("dossier_claims")
    op.drop_table("dossier_evidence")
    op.drop_table("research_dossiers")
    for name, _ in reversed(DOC_COLUMNS):
        op.drop_column("documents", name)
