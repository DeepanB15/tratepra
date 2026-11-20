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

    # Lifecycle thresholds (configurable)
    lifecycle_emerging_min_growth: float = 25.0
    lifecycle_growing_min_growth: float = 10.0
    lifecycle_declining_max_growth: float = -10.0
    lifecycle_min_documents: int = 5

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
