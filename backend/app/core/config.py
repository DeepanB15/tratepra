from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"  # development | production
    auto_create_tables: bool = True  # set False in production and use `alembic upgrade head`

    database_url: str = "postgresql+psycopg2://tratepra:tratepra@localhost:5432/tratepra"

    db_pool_size: int = 5
    db_max_overflow: int = 5

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:4b"
    ollama_timeout_seconds: float = 120.0

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    youtube_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "tratepra/1.0"
    google_trends_api_key: str = ""
    # No public endpoint is documented for the alpha; set the one given with your access.
    google_trends_api_endpoint: str = ""
    google_trends_allow_fallback: bool = False

    internal_api_token: str = "change-me"
    cors_origins: str = "http://localhost:5173"

    # Connector behaviour
    http_timeout_seconds: float = 15.0
    http_max_retries: int = 2

    # Research ranking weights R = 0.45S + 0.25K + 0.20F + 0.10Q
    rank_normalize_semantic: bool = True
    rank_w_semantic: float = 0.45
    rank_w_keyword: float = 0.25
    rank_w_freshness: float = 0.20
    rank_w_quality: float = 0.10

    # Trend score weights T = 0.30G + 0.20M + 0.15E + 0.15N + 0.10S + 0.10C
    trend_w_growth: float = 0.30
    trend_w_momentum: float = 0.20
    trend_w_engagement: float = 0.15
    trend_w_novelty: float = 0.15
    trend_w_search: float = 0.10
    trend_w_cross_source: float = 0.10
    trend_min_coverage: float = 0.50  # minimum fraction of total weight available
    trend_window_days: int = 7
    trend_topic_match_threshold: float = 0.80  # centroid cosine needed to keep a topic's identity
    lifecycle_min_abs_increase: int = 3  # spike guard: a jump smaller than this many documents is not "emerging"
    trend_formula_version: str = "v1.0"
    trend_n_windows: int = 6  # number of consecutive windows analysed (lookback = window_days * n_windows)

    # Topic identity across runs. Pairs at/above `trend_topic_match_threshold` can be matched (one-to-one).
    # Pairs between the floor and the threshold are never silently matched: they are reported as an
    # uncertain identity, or as a potential split / merge when another topic competes for the same stored one.
    trend_identity_floor: float = 0.65

    # Operational activity state (distinct from the analytical lifecycle). Measured in COMPLETED runs and
    # relative to the latest completed run, so failed runs or a collection outage never age a topic.
    trend_stale_after_missed_runs: int = 1  # absent from this many latest completed runs -> stale
    trend_inactive_after_missed_runs: int = 4  # absent from this many -> inactive
    trend_stale_after_days: float = 14.0  # last observation this long before the latest completed run -> stale
    trend_inactive_after_days: float = 45.0
    trend_analysis_overdue_days: float = 3.0  # data-freshness warning when the latest completed run is older than this
    trend_running_timeout_minutes: int = 60  # a 'running' row older than this is treated as a crashed run
    trend_new_topic_days: float = 14.0  # a topic first seen within this window is "newly discovered"

    # Topic-model quality guards (diagnostic flags only; documents are never forced into topics)
    topic_broad_share: float = 0.40  # a topic holding more than this share of clustered docs is flagged broad
    topic_name_min_coverage: float = 0.50  # share of member docs that must contain a name term
    topic_high_noise_share: float = 0.60

    # Lifecycle thresholds (configurable)
    lifecycle_emerging_min_growth: float = 25.0
    lifecycle_growing_min_growth: float = 10.0
    lifecycle_declining_max_growth: float = -10.0
    lifecycle_min_documents: int = 5

    # Phase 2: research dossiers
    dossier_inline_execution: bool = False  # tests/dev: run generation in the request instead of a worker thread
    dossier_workers: int = 2
    dossier_running_timeout_minutes: int = 30  # a 'running' dossier older than this is treated as crashed
    dossier_max_evidence: int = 12
    dossier_retrieval_limit: int = 80
    dossier_article_refresh_max: int = 5  # bounded article re-extraction per generation
    dossier_support_overlap: float = 0.6  # claim token coverage for 'supported'; MIN_SUPPORT_OVERLAP..this = partial

    # Phase 3: monitoring. Thresholds are used only through MonitoringConfig (monitoring/config.py).
    monitoring_scheduler_enabled: bool = False  # opt-in: nothing runs in the background unless enabled
    monitoring_interval_minutes: int = 360
    monitoring_tick_seconds: int = 30
    monitoring_inline_execution: bool = False  # tests/dev: run manual triggers in the request
    monitoring_job_max_attempts: int = 2
    monitoring_job_retry_delay_seconds: float = 5.0
    monitoring_running_timeout_minutes: int = 120  # a 'running' job row older than this is treated as interrupted
    monitoring_collection_queries: str = ""  # comma-separated extra queries; watched trend names are always added
    monitoring_collection_max_queries: int = 8
    monitoring_collection_time_range: str = "7d"
    monitoring_min_observations: int = 2  # comparable completed-run observations needed before comparing
    monitoring_min_documents: int = 8  # topic volume below this never raises growth/decline/spike events
    monitoring_min_sources: int = 2  # distinct sources required for growth/spike/new-emerging events
    monitoring_min_growth_change_pp: float = 15.0  # growth_pct must change by this many points
    monitoring_min_volume_change: int = 5  # and document volume by at least this many documents
    monitoring_decline_pct: float = 30.0  # relative volume drop to call a decline
    monitoring_spike_baseline_window: int = 5  # prior comparable observations used as the baseline
    monitoring_spike_z: float = 3.0  # deviation (in baseline standard deviations) for a spike
    monitoring_spike_min_ratio: float = 1.5
    monitoring_critical_spike_ratio: float = 3.0
    monitoring_new_documents_min: int = 3  # new member documents needed for a 'new supporting evidence' event
    monitoring_related_similarity: float = 0.75  # topic-embedding cosine for 'new related topic'
    monitoring_emerging_min_score: float = 0.0
    monitoring_emerging_important_score: float = 70.0
    monitoring_cooldown_hours: float = 24.0  # same event type for same topic within this window is suppressed unless severity rises
    monitoring_window_tolerance_days: float = 1.0  # snapshot windows must match within this to be compared
    monitoring_llm_explanations: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() != "development"

    def security_problems(self) -> list[str]:
        """Configuration issues that must block startup outside development."""
        problems = []
        if self.internal_api_token in ("", "change-me") or len(self.internal_api_token) < 16:
            problems.append("INTERNAL_API_TOKEN must be set to a random value of at least 16 characters")
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS must not contain '*'")
        return problems

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
