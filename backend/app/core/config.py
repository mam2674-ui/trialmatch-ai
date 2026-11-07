"""Application settings. Every secret comes from the environment; nothing is hardcoded."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TrialMatch AI"
    environment: str = Field("development", description="development | test | production")

    # Database (PostgreSQL + pgvector)
    database_url: str = "postgresql+psycopg://trialmatch@localhost:5433/trialmatch"

    # ClinicalTrials.gov API v2
    ctgov_base_url: str = "https://clinicaltrials.gov/api/v2"
    ctgov_timeout_seconds: float = 30.0
    # The public API documents a limit of roughly 50 requests/minute per IP; stay under it.
    ctgov_requests_per_minute: int = 40
    ctgov_max_retries: int = 3
    trial_cache_ttl_hours: int = 24
    search_cache_ttl_hours: int = 6
    max_candidates: int = 60

    # Anthropic Claude (optional: the app degrades gracefully without it)
    # auth: "auto" uses ANTHROPIC_API_KEY if set, otherwise an `ant auth login` profile if one exists.
    anthropic_auth: str = Field("auto", description="auto | api_key | profile | none")
    anthropic_api_key: SecretStr | None = None
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "medium"
    claude_timeout_seconds: float = 120.0
    llm_max_trials_per_match: int = 8
    llm_concurrency: int = 4

    # Embeddings
    embeddings_enabled: bool = True
    embedding_model: str = "pritamdeka/S-PubMedBert-MS-MARCO"
    embedding_dim: int = 768

    # Geocoding (patient location only; trial sites use ClinicalTrials.gov geoPoints)
    geocoder: str = Field("nominatim", description="nominatim | none")
    geocoder_user_agent: str = "TrialMatchAI/0.1 (portfolio project)"

    # Privacy / sessions
    session_ttl_minutes: int = 60

    # API hardening
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3010"]
    rate_limit_per_minute: int = 30
    max_narrative_chars: int = 4000

    @property
    def llm_auth_mode(self) -> str | None:
        """'api_key', 'profile', or None (Claude disabled)."""
        has_key = bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value())
        if self.anthropic_auth == "none":
            return None
        if self.anthropic_auth == "api_key":
            return "api_key" if has_key else None
        if self.anthropic_auth == "profile":
            return "profile"
        if has_key:
            return "api_key"
        return "profile" if _ant_profile_available() else None

    @property
    def llm_enabled(self) -> bool:
        return self.llm_auth_mode is not None


def _ant_profile_available() -> bool:
    """True if `ant auth login` stored credentials (or an auth token is exported) that the SDK can use."""
    if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    config_dir = Path(os.environ.get("ANTHROPIC_CONFIG_DIR", Path.home() / ".config" / "anthropic"))
    creds = config_dir / "credentials"
    return creds.is_dir() and any(creds.glob("*.json"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
