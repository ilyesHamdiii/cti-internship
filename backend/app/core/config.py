from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CTI_", extra="ignore")

    app_name: str = "CTI Detection Engineering Platform"
    environment: Literal["local", "test", "production"] = "local"
    database_url: str = "postgresql+psycopg://cti:cti@postgres:5432/cti"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: SecretStr = Field(default=SecretStr("change-me-local-development-secret"))
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_minutes: int = 60 * 24
    seeded_admin_email: str = "admin@example.local"
    seeded_admin_password: SecretStr = Field(default=SecretStr("ChangeMe123!"))

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: AnyUrl = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_prompt_token_cost: float = 0.00000014
    deepseek_completion_token_cost: float = 0.00000028
    ai_fixture_mode: bool = True

    misp_url: str = "https://misp"
    misp_api_key: SecretStr | None = None
    misp_verify_tls: bool = False
    misp_poll_interval_seconds: int = 300

    sigma_target: str = "splunk"
    max_repair_attempts: int = 3
    quality_threshold: float = 75.0
    reasoning_max_revisions: int = 3
    reasoning_min_improvement_delta: float = 0.03
    reasoning_confidence_target: float = 0.82
    reasoning_trust_target: float = 0.88


@lru_cache
def get_settings() -> Settings:
    return Settings()
