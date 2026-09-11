from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Bot
    bot_token: str = Field(..., validation_alias="BOT_TOKEN")

    # Database
    database_url: str = Field(..., validation_alias="DATABASE_URL")
    db_pool_min: int = Field(10, validation_alias="DB_POOL_MIN")
    db_pool_max: int = Field(20, validation_alias="DB_POOL_MAX")

    # Dig settings
    dig_cooldown_seconds: int = Field(3600, validation_alias="DIG_COOLDOWN_SECONDS")
    dig_min_kg: float = Field(1.0, validation_alias="DIG_MIN_KG")
    dig_max_kg: float = Field(7.0, validation_alias="DIG_MAX_KG")
    dig_precision: int = Field(1, validation_alias="DIG_PRECISION")

    # History
    history_retention_hours: int = Field(48, validation_alias="HISTORY_RETENTION_HOURS")
    cleanup_interval_seconds: int = Field(3600, validation_alias="CLEANUP_INTERVAL_SECONDS")

    # Cache
    leaderboard_cache_ttl: int = Field(30, validation_alias="LEADERBOARD_CACHE_TTL")

    # Rate limiting
    rate_limit_requests: int = Field(30, validation_alias="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(60, validation_alias="RATE_LIMIT_WINDOW")

    # Web server
    web_host: str = Field("0.0.0.0", validation_alias="WEB_HOST")
    web_port: int = Field(8080, validation_alias="WEB_PORT")

    # Logging
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")
    log_format: str = Field("json", validation_alias="LOG_FORMAT")

    @field_validator("bot_token")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        if not v or v.count(":") != 1:
            raise ValueError("Invalid bot token format")
        return v

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL must be postgresql://...")
        if "sslmode=" not in v:
            return v + ("&" if "?" in v else "?") + "sslmode=require"
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()