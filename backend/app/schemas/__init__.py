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
    score_withheld: bool = False
    score_coverage: float | None = None
    lifecycle: str | None
    activity_state: str = "active"
    growth: float | None
    momentum_direction: str | None = None
    momentum_pp: float | None = None
    document_volume: int | None = None
    supporting_documents: int | None = None
    source_count: int = 0
    source_distribution: dict[str, int] = Field(default_factory=dict)
    coverage: dict[str, Any]
    sparkline: list[int]
    is_new: bool = False
    needs_review: bool = False
    explanation: str = ""
    last_updated: datetime | None
    last_observed_at: datetime | None = None
    first_seen_at: datetime | None = None


class RelatedTopic(BaseModel):
    topic_id: str
    name: str
    similarity: float


class RunInfo(BaseModel):
    run_id: str
    status: str
    completed_at: datetime | None
    model_version: str
    formula_version: str
    documents_processed: int


class TrendDetail(BaseModel):
    topic_id: str
    topic_name: str
    terms: list[str]
    trend_score: float | None
    score_withheld: bool = False
    lifecycle: str | None
    activity_state: str = "active"
    signals: dict[str, float | None]
    coverage: dict[str, Any]
    explanation: dict[str, Any] = Field(default_factory=dict)
    growth_pct: float | None = None
    growth_flag: str | None = None
    momentum_direction: str | None = None
    momentum_pp: float | None = None
    document_volume: int | None = None
    source_distribution: dict[str, int] = Field(default_factory=dict)
    weekly_volumes: list[int] = Field(default_factory=list)
    previous_score: float | None = None
    topic_size: int | None = None
    related_topics: list[str]
    related_topic_details: list[RelatedTopic] = Field(default_factory=list)
    representative_documents: list[dict[str, Any]]
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    name_confidence: float | None = None
    first_seen_at: datetime | None = None
    last_observed_at: datetime | None = None
    last_updated: datetime | None
    model_version: str | None = None
    formula_version: str | None = None
    last_run: RunInfo | None = None
    identity: dict[str, Any] | None = None


class TrendHistoryPoint(BaseModel):
    window_start: datetime
    window_end: datetime
    observed_at: datetime | None = None
    document_volume: int
    growth: float | None
    momentum: float | None = None
    momentum_direction: str | None = None
    trend_score: float | None
    score_withheld: bool = False
    lifecycle: str | None
    run_id: str | None = None
    run_completed_at: datetime | None = None
    legacy: bool = False
    created_at: datetime
    volumes: list[int] = []


class RunSummary(BaseModel):
    run_id: str
    run_key: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    window_end: datetime | None
    documents_available: int
    documents_processed: int
    documents_rejected: int
    noise_documents: int
    noise_percentage: float | None = None
    topics_discovered: int
    topics_created: int
    topics_matched: int
    model_version: str
    formula_version: str
    error_message: str | None = None
    attempts: int | None = None
    topic_quality: dict[str, Any] | None = None


class RunDetail(RunSummary):
    configuration: dict[str, Any] = Field(default_factory=dict)
    rejection: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] | None = None
    identity: dict[str, Any] | None = None


class DataFreshness(BaseModel):
    latest_successful_analysis_at: datetime | None
    age_hours: float | None
    overdue: bool
    overdue_after_days: float


class DiscoveryOverview(BaseModel):
    total_active_trends: int
    emerging_trends: int
    rising_trends: int
    peaking_trends: int
    declining_trends: int
    accelerating_trends: int
    new_trends: int
    withheld_score_trends: int
    needs_review_trends: int
    stale_trends: int
    inactive_trends: int
    activity_state_counts: dict[str, int]
    latest_successful_run: RunDetail | None
    latest_run: RunSummary | None
    latest_run_status: str | None
    documents_analyzed: int | None
    topic_model_diagnostics: dict[str, Any] | None
    data_freshness: DataFreshness
    generated_at: datetime
