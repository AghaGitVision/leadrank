from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Every external dependency degrades to a local equivalent so the project runs
    with `uvicorn app.main:app` and no infrastructure. The production targets are
    documented in docs/ARCHITECTURE.md and selected purely by these env vars.
    """

    app_name: str = "LeadRank"
    env: str = "local"

    # sqlite for the demo, postgres+psycopg://... in production
    database_url: str = "sqlite:///./leadrank.db"

    # empty string => in-process LRU cache instead of Redis
    redis_url: str = ""
    scan_cache_ttl_days: int = 7

    # live  = fetch real sites (respects robots.txt, rate limited)
    # offline = replay bundled scan fixtures, for demos and CI without egress
    scan_mode: str = "offline"
    scan_concurrency: int = 8
    scan_timeout_seconds: float = 5.0
    scan_user_agent: str = "LeadRankBot/1.0 (+https://github.com/leadrank; contact: support@example.com)"

    # optional: narrative sentence generation. Never affects the score.
    anthropic_api_key: str = ""
    narrative_model: str = "claude-sonnet-4-6"

    # learned weights are only applied once this many decisions exist in a run
    learning_min_decisions: int = 15
    learning_max_shift: float = 0.35

    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="LEADRANK_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
