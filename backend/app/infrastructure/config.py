from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit
import ipaddress

from datetime import datetime, timezone

from pydantic import AwareDatetime, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FURSAH_",
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    framework_track: str = ""  # Optional descriptive label; no framework whitelist.
    evaluation_time: AwareDatetime | None = None
    model_provider: str = ""
    model_name: str = ""
    model_api_key: str = Field(default="", repr=False)
    model_base_url: str = ""
    # Explicit opt-in, restricted to loopback OpenAI-compatible servers.
    allow_keyless_local_model: bool = False

    model_timeout_seconds: int = Field(default=40, gt=0)
    workflow_timeout_seconds: int = Field(default=90, gt=0)
    model_max_retries: int = Field(default=1, ge=0)
    model_output_retries: int = Field(default=1, ge=0)
    max_workflow_steps: int = Field(default=8, gt=0)

    data_dir: Path = PROJECT_ROOT / "data"
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    trace_jsonl_path: str = ""

    # Phoenix tracing (Day 4). See infrastructure/observability.py.
    phoenix_enabled: bool = False
    phoenix_endpoint: str = "http://localhost:6006/v1/traces"
    phoenix_project: str = "fursah"
    phoenix_instrument: str = "auto"  # auto | langchain | pydantic_ai | openai | none

    @field_validator("evaluation_time", mode="before")
    @classmethod
    def empty_time_means_live(cls, value):
        return None if value == "" else value

    def resolve_evaluation_time(self) -> datetime:
        """Capture once per discovery request; preserve timezone-aware instants."""
        return self.evaluation_time or datetime.now(timezone.utc)

    @field_validator("data_dir")
    @classmethod
    def resolve_data_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value

    @property
    def allowed_origin_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def keyless_local_model(self) -> bool:
        try:
            url = urlsplit(self.model_base_url)
            local = url.hostname == "localhost" or ipaddress.ip_address(url.hostname or "").is_loopback
            return bool(self.allow_keyless_local_model and self.model_provider == "openai"
                        and url.scheme in {"http", "https"} and local
                        and not url.username and not url.password)
        except ValueError:
            return False

    @property
    def live_model_configured(self) -> bool:
        return bool(self.model_provider.strip() and self.model_name.strip() and (self.model_api_key.strip() or self.keyless_local_model))


def get_settings() -> Settings:
    return Settings()
