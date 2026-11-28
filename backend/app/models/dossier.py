"""Phase 2 research dossier models. Documents are referenced by id; article content is never copied."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import Document


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchDossier(Base):
    """One dossier per (subject, time range, source filter) - `dossier_key` makes creation idempotent.

    `status` is the state of the latest generation attempt. Content columns (sections, evidence_quality, ...)
    are only replaced when a generation COMPLETES, so a failed refresh never loses the previous result.
    """

    __tablename__ = "research_dossiers"
    __table_args__ = (
        UniqueConstraint("dossier_key", name="uq_research_dossiers_key"),
        CheckConstraint("status IN ('pending','running','completed','failed')", name="ck_research_dossiers_status"),
        Index("ix_research_dossiers_topic", "topic_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    dossier_key: Mapped[str] = mapped_column(String(64))
    topic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(Text, default="")
    query_text: Mapped[str] = mapped_column(Text)
    time_range: Mapped[str] = mapped_column(String(20), default="30d")
    source_filters: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    generation: Mapped[int] = mapped_column(Integer, default=0)  # completed generations
    sections: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_quality: Mapped[dict] = mapped_column(JSON, default=dict)
    diagnostics: Mapped[dict] = mapped_column(JSON, default=dict)
    versions: Mapped[dict] = mapped_column(JSON, default=dict)  # engine/model/formula versions for reproducibility
    model: Mapped[str] = mapped_column(String(100), default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    evidence: Mapped[list["DossierEvidence"]] = relationship(back_populates="dossier", cascade="all, delete-orphan")
    claims: Mapped[list["DossierClaim"]] = relationship(back_populates="dossier", cascade="all, delete-orphan")


class DossierEvidence(Base):
    __tablename__ = "dossier_evidence"
    __table_args__ = (
        UniqueConstraint("dossier_id", "document_id", name="uq_dossier_evidence_doc"),
        CheckConstraint("role IN ('supporting','contradictory','context')", name="ck_dossier_evidence_role"),
        Index("ix_dossier_evidence_dossier_rank", "dossier_id", "rank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    dossier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_dossiers.id", ondelete="CASCADE"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20), default="supporting")
    role_reason: Mapped[str] = mapped_column(Text, default="")
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    publisher: Mapped[str] = mapped_column(String(255), default="", index=True)  # snapshot, for filtering
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    excerpt: Mapped[str] = mapped_column(Text, default="")  # the text shown to the model / used for verification
    excerpt_basis: Mapped[str] = mapped_column(String(20), default="rss")  # article | rss
    article_status: Mapped[str] = mapped_column(String(20), default="rss_only")
    diagnostics: Mapped[dict] = mapped_column(JSON, default=dict)

    dossier: Mapped[ResearchDossier] = relationship(back_populates="evidence")
    document: Mapped[Document] = relationship()


class DossierClaim(Base):
    __tablename__ = "dossier_claims"
    __table_args__ = (
        UniqueConstraint("dossier_id", "claim_no", name="uq_dossier_claims_no"),
        CheckConstraint(
            "status IN ('supported','partially_supported','contradicted','unverified','insufficient_evidence')",
            name="ck_dossier_claims_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    dossier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_dossiers.id", ondelete="CASCADE"), index=True)
    claim_no: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(40), default="overview")
    text: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(20), default="factual")  # factual | quantitative | temporal | opinion
    status: Mapped[str] = mapped_column(String(30), default="unverified")
    explanation: Mapped[str] = mapped_column(Text, default="")
    overlap: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_coverage: Mapped[int] = mapped_column(Integer, default=0)  # distinct publishers backing the claim

    dossier: Mapped[ResearchDossier] = relationship(back_populates="claims")
    links: Mapped[list["ClaimEvidence"]] = relationship(back_populates="claim", cascade="all, delete-orphan")


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        UniqueConstraint("claim_id", "dossier_evidence_id", "relation", name="uq_claim_evidence"),
        CheckConstraint("relation IN ('supports','contradicts')", name="ck_claim_evidence_relation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dossier_claims.id", ondelete="CASCADE"), index=True)
    dossier_evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dossier_evidence.id", ondelete="CASCADE"), index=True
    )
    relation: Mapped[str] = mapped_column(String(20), default="supports")
    overlap: Mapped[float | None] = mapped_column(Float, nullable=True)

    claim: Mapped[DossierClaim] = relationship(back_populates="links")
    evidence: Mapped[DossierEvidence] = relationship()
