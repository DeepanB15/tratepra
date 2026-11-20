from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    sources: list[str] = Field(
        default_factory=lambda: ["google_news", "youtube", "reddit", "google_trends"], max_length=4
    )
    time_range: str = Field(default="30d", pattern=r"^\d+[dhw]$")
    refresh: bool = True  # call live connectors before retrieval


class EvidenceItem(BaseModel):
    document_id: str
    title: str
    url: str | None
    source: str
    published_at: datetime | None
    relevance: float | None = None
    cited: bool = False


class ResearchResponse(BaseModel):
    research_id: str
    query: str
    answer: str
    key_findings: list[str]
    sources_used: list[str]
    source_status: dict[str, Any]
    source_distribution: dict[str, int]
    evidence: list[EvidenceItem]
    related_topics: list[str]
    model: str
    degraded: bool = False  # True when the LLM was unavailable and an extractive fallback was used
    transparency: dict[str, Any] = Field(default_factory=dict)
    unverified_claims: list[dict[str, Any]] = Field(default_factory=list)
    execution_ms: int
    created_at: datetime


class HistoryItem(BaseModel):
    research_id: str
    query: str
    sources: list[str]
    created_at: datetime


class SavedCreate(BaseModel):
    item_type: str = Field(pattern=r"^(research|trend)$")
    item_id: str
    title: str = ""


class SavedOut(BaseModel):
    id: str
    item_type: str
    item_id: str
    title: str
    created_at: datetime


class TrendSummary(BaseModel):
    topic_id: str
    topic_name: str
    trend_score: float | None
    lifecycle: str | None
    growth: float | None
    coverage: dict[str, Any]
    sparkline: list[int]
    last_updated: datetime | None


class TrendDetail(BaseModel):
    topic_id: str
    topic_name: str
    trend_score: float | None
    lifecycle: str | None
    signals: dict[str, float | None]
    coverage: dict[str, Any]
    explanation: dict[str, Any] = Field(default_factory=dict)
    source_distribution: dict[str, int] = Field(default_factory=dict)
    weekly_volumes: list[int] = Field(default_factory=list)
    previous_score: float | None = None
    topic_size: int | None = None
    related_topics: list[str]
    representative_documents: list[dict[str, Any]]
    terms: list[str]
    last_updated: datetime | None


class TrendHistoryPoint(BaseModel):
    window_start: datetime
    window_end: datetime
    document_volume: int
    growth: float | None
    trend_score: float | None
    lifecycle: str | None
    created_at: datetime
    volumes: list[int] = []
