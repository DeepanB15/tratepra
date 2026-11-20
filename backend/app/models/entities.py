
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    literal_column,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.core.database import Base

EMBED_DIM = get_settings().embedding_dim


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    quality_weight: Mapped[float] = mapped_column(Float, default=70.0)
    last_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    documents: Mapped[list["Document"]] = relationship(back_populates="source")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_doc_source_external"),
        Index("ix_documents_source_published", "source_id", "published_at"),
        Index(
            "ix_documents_fts",
            func.to_tsvector(literal_column("'english'"), literal_column("normalized_text")),
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_text: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(1024), index=True, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    engagement: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    source: Mapped[Source] = relationship(back_populates="documents")
    embedding: Mapped["DocumentEmbedding | None"] = relationship(
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )


class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"
    __table_args__ = (
        Index(
            "ix_document_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding = mapped_column(Vector(EMBED_DIM))
    model: Mapped[str] = mapped_column(String(200))
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
    )

    document: Mapped[Document] = relationship(back_populates="embedding")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms: Mapped[list] = mapped_column(JSON, default=list)
    embedding = mapped_column(Vector(EMBED_DIM), nullable=True)
    model_version: Mapped[str] = mapped_column(String(100), default="")
    run_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    documents: Mapped[list["TopicDocument"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    observations: Mapped[list["TrendObservation"]] = relationship(back_populates="topic", cascade="all, delete-orphan")


class TopicDocument(Base):
    __tablename__ = "topic_documents"

    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)

    topic: Mapped[Topic] = relationship(back_populates="documents")


class TrendObservation(Base):
    """Append-only history. Never overwritten."""

    __tablename__ = "trend_observations"
    __table_args__ = (Index("ix_trend_obs_topic_created", "topic_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    document_volume: Mapped[int] = mapped_column(Integer, default=0)
    growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum: Mapped[float | None] = mapped_column(Float, nullable=True)
    engagement: Mapped[float | None] = mapped_column(Float, nullable=True)
    novelty: Mapped[float | None] = mapped_column(Float, nullable=True)
    search_interest: Mapped[float | None] = mapped_column(Float, nullable=True)
    cross_source_activity: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    lifecycle: Mapped[str | None] = mapped_column(String(20), nullable=True)
    coverage: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_signals: Mapped[dict] = mapped_column(JSON, default=dict)
    formula_version: Mapped[str] = mapped_column(String(20), default="v1.0")
    model_version: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    topic: Mapped[Topic] = relationship(back_populates="observations")


class ResearchQuery(Base):
    __tablename__ = "research_queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    query: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    time_range: Mapped[str] = mapped_column(String(20), default="30d")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    result: Mapped["ResearchResult | None"] = relationship(
        back_populates="query",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ResearchResult(Base):
    __tablename__ = "research_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    query_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_queries.id", ondelete="CASCADE"), unique=True)
    answer: Mapped[str] = mapped_column(Text)
    key_findings: Mapped[list] = mapped_column(JSON, default=list)
    related_topics: Mapped[list] = mapped_column(JSON, default=list)
    source_status: Mapped[dict] = mapped_column(JSON, default=dict)
    source_distribution: Mapped[dict] = mapped_column(JSON, default=dict)
    model: Mapped[str] = mapped_column(String(100), default="")
    execution_ms: Mapped[int] = mapped_column(Integer, default=0)
    retrieval_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    query: Mapped[ResearchQuery] = relationship(back_populates="result")
    evidence: Mapped[list["ResearchEvidence"]] = relationship(
        back_populates="result",
        cascade="all, delete-orphan",
    )


class ResearchEvidence(Base):
    __tablename__ = "research_evidence"
    __table_args__ = (UniqueConstraint("result_id", "document_id", name="uq_evidence_result_document"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_results.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(Integer)
    relevance: Mapped[float] = mapped_column(Float)
    cited: Mapped[int] = mapped_column(Integer, default=0)

    result: Mapped[ResearchResult] = relationship(back_populates="evidence")
    document: Mapped[Document] = relationship()


class SavedItem(Base):
    __tablename__ = "saved_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    item_type: Mapped[str] = mapped_column(String(20))
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("item_type", "item_id", name="uq_saved_item"),)


class CollectionLog(Base):
    """One row per source per collection run."""

    __tablename__ = "collection_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), index=True, default="")
    source_key: Mapped[str] = mapped_column(String(50), index=True)
    query: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    out_of_window: Mapped[int] = mapped_column(Integer, default=0)
    undated: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
