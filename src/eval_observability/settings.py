"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVAL_OBS_", env_file=".env", extra="ignore")

    database_url: str = Field(
        default="sqlite:///./evalobs.db",
        description="SQLAlchemy database URL. Use postgresql+psycopg://... in production.",
    )
    otel_exporter: str = Field(
        default="memory",
        description=(
            "One of: memory, console, otlp. ('stdout' is an alias for 'console'.) "
            "The 'memory' exporter is for tests; 'otlp' is the production wire-in."
        ),
    )
    otel_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP gRPC endpoint when otel_exporter=otlp.",
    )
    service_name: str = Field(default="eval-observability")
    suites_root: Path = Field(default=Path("eval/suites"))
    reports_dir: Path = Field(default=Path("reports"))
    baselines_dir: Path = Field(default=Path("eval/baselines"))
    regression_delta_threshold: float = Field(
        default=0.02, description="Minimum mean drop (in absolute fraction) to flag as regression."
    )
    regression_p_threshold: float = Field(
        default=0.05, description="p-value upper bound for Welch's t-test to flag as regression."
    )


def get_settings() -> Settings:
    return Settings()
