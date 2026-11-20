
"""Track the source text used to generate each document embedding.

Revision ID: 002
Revises: 001
"""
import hashlib

from alembic import op
import sqlalchemy as sa


revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_embeddings",
        sa.Column("text_hash", sa.String(length=64), nullable=True),
    )

    connection = op.get_bind()

    rows = connection.execute(
        sa.text("""
            SELECT e.document_id, d.normalized_text
            FROM document_embeddings AS e
            JOIN documents AS d ON d.id = e.document_id
        """)
    ).fetchall()

    for document_id, normalized_text in rows:
        fingerprint = hashlib.sha256(
            (normalized_text or "").encode("utf-8")
        ).hexdigest()

        connection.execute(
            sa.text("""
                UPDATE document_embeddings
                SET text_hash = :fingerprint
                WHERE document_id = :document_id
            """),
            {
                "fingerprint": fingerprint,
                "document_id": document_id,
            },
        )

    op.alter_column(
        "document_embeddings",
        "text_hash",
        existing_type=sa.String(length=64),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("document_embeddings", "text_hash")
