from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Drivee NL2SQL Backend"
    app_env: str = "local"
    debug: bool = True
    api_prefix: str = "/api"
    backend_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    database_url: str = "postgresql+psycopg2://drivee:drivee@localhost:5432/drivee"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = Field(default="change-me-super-secret-key-at-least-32-chars", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    first_superuser_email: str = "admin@example.com"
    first_superuser_password: str = "admin123"

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_seconds: int = 300

    # New datasets. Put these files into ./data before docker compose up.
    incity_csv_path: str = "/data/incity.csv"
    pass_detail_csv_path: str = "/data/pass_detail.csv"
    driver_detail_csv_path: str = "/data/driver_detail.csv"
    dataset_notes_path: str = "/data/notes.md"

    # Backward-compatible old names. They are no longer the primary source.
    train_csv_path: str = "/data/train.csv"
    train_notes_path: str = "/data/notes.md"

    good_prompts_path: str = "/data/goodprompts.txt"
    semantic_layer_path: str = "/app/src/semantic/semantic_layer.json"
    import_datasets_on_startup: bool = True
    import_train_on_startup: bool = True

    sql_default_limit: int = 100
    sql_max_limit: int = 500
    # Per-session SET LOCAL statement_timeout for user SQL (ms). Large incity aggregates need more than a few seconds.
    sql_statement_timeout_ms: int = 180_000
    sql_max_offset: int = 1_000
    sql_max_table_references: int = 3
    sql_max_train_references: int = 3  # kept for compatibility with older code/env
    sql_max_explain_total_cost: float = 2_000_000
    sql_max_explain_plan_rows: int = 2_000_000
    sql_block_select_star: bool = True
    sql_block_cross_join: bool = True
    sql_readonly_transaction: bool = True

    templates_cache_ttl_seconds: int = 60 * 60 * 24
    template_result_cache_ttl_seconds: int = 60 * 10
    template_match_threshold: float = 0.88

    report_scheduler_enabled: bool = True
    report_scheduler_interval_seconds: int = 300
    report_scheduler_batch_size: int = 10
    default_report_schedule_timezone: str = "UTC"

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @field_validator(
        "sql_default_limit",
        "sql_max_limit",
        "sql_statement_timeout_ms",
        "sql_max_offset",
        "sql_max_table_references",
        "sql_max_train_references",
        "sql_max_explain_plan_rows",
        "report_scheduler_interval_seconds",
        "report_scheduler_batch_size",
    )
    @classmethod
    def positive_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("limit must be positive")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
