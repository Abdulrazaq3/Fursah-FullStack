from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from datetime import datetime

from .config import Settings, get_settings
from ..repository import OpportunityRepository
from .data_package import DatasetLoader
from .tracing import Tracer


@dataclass
class ModelClientConfig:
    provider: str
    model_name: str
    api_key: str = field(repr=False)
    base_url: str
    timeout_seconds: int
    max_retries: int


@dataclass
class AppDependencies:
    settings: Settings
    bridge: DatasetLoader
    repository: OpportunityRepository
    model_config: ModelClientConfig | None
    tracer: Tracer

    evaluation_time: datetime | None = None

    def readiness(self) -> tuple[dict[str, bool], dict[str, str]]:
        # These are extension points, not proof of recommendation correctness.
        from ..workflow import application_is_ready
        checks, details = {}, {}
        for name, check in (("storage", self.repository.is_ready),
                            ("application", lambda: application_is_ready(self))):
            try:
                result = check()
                checks[name] = result is True
                if result is not True:
                    details[name] = "Not ready: inspect the team's implementation and configuration."
            except NotImplementedError:
                checks[name] = False
                details[name] = "Intentionally unfinished: implement this readiness hook."
            except Exception:
                checks[name] = False
                details[name] = "Readiness check failed; inspect configuration locally."
        return checks, details


def build_model_config(settings: Settings) -> ModelClientConfig | None:
    """Optional configuration helper for an API-key or loopback provider.

    Students may replace this factory for other authentication/client designs.
    The shell and readiness hooks do not depend on these optional settings.
    """
    if not settings.live_model_configured:
        return None
    return ModelClientConfig(
        provider=settings.model_provider,
        model_name=settings.model_name,
        api_key=settings.model_api_key,
        base_url=settings.model_base_url,
        timeout_seconds=settings.model_timeout_seconds,
        max_retries=settings.model_max_retries,
    )


@lru_cache(maxsize=1)
def get_app_dependencies() -> AppDependencies:
    settings = get_settings()
    bridge = DatasetLoader(settings)
    tracer = Tracer(settings.trace_jsonl_path)
    repository = OpportunityRepository(bridge)
    return AppDependencies(
        settings=settings,
        bridge=bridge,
        repository=repository,
        model_config=build_model_config(settings),
        tracer=tracer,
    )
