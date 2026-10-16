"""Organizer-provided Phoenix tracing (Day 4).

You do two things with this module:
1. Call setup_observability() once when the app starts, before the first request.
2. Wrap code your framework cannot see in start_span(...).

Set FURSAH_PHOENIX_INSTRUMENT to what your code calls: langchain, pydantic_ai, openai, or
none (no automatic spans: record your model and tool calls yourself with start_span).
auto guesses from what is INSTALLED:
- LangChain / LangGraph -> LangChain instrumentor
- PydanticAI            -> PydanticAI instrumentor
- neither, but openai   -> OpenAI SDK instrumentor
LangChain and PydanticAI call the OpenAI SDK internally, so it is only instrumented
on its own; instrumenting both would record every model call twice.
"""
from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace

from .config import get_settings

_tracer = trace.get_tracer("fursah")
_instrumented: list[str] = []


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _choose_instrumentors(mode: str) -> list[str]:
    if mode == "none":
        return []
    if mode != "auto":
        return [mode]
    chosen = [name for name, module in (("langchain", "langchain_core"), ("pydantic_ai", "pydantic_ai"))
              if _installed(module)]
    if not chosen and _installed("openai"):
        chosen = ["openai"]
    return chosen


def setup_observability(export: bool = True) -> list[str]:
    """Send framework spans and custom spans to Phoenix.

    No-op unless FURSAH_PHOENIX_ENABLED=true. Returns the instrumentors switched on.
    export=False instruments without sending anything (evals/run_eval.py uses it when
    Phoenix is not running, and keeps the spans in memory for the graders).
    """
    settings = get_settings()
    if not settings.phoenix_enabled or _instrumented:
        return list(_instrumented)

    try:
        from phoenix.otel import HTTPSpanExporter, SimpleSpanProcessor, register
    except ImportError as exc:
        raise RuntimeError(
            "FURSAH_PHOENIX_ENABLED=true but the tracing packages are not installed: run "
            "`pip install -r requirements-observability.txt`, or set FURSAH_PHOENIX_ENABLED=false "
            "(for example in a deployed container)."
        ) from exc

    # Tracer provider: where spans are exported.
    if export:
        provider = register(project_name=settings.phoenix_project, endpoint=settings.phoenix_endpoint)
    else:
        from opentelemetry.sdk.trace import TracerProvider
        provider = TracerProvider()
        trace.set_tracer_provider(provider)

    for name in _choose_instrumentors(settings.phoenix_instrument):
        if name == "langchain":
            from openinference.instrumentation.langchain import LangChainInstrumentor
            LangChainInstrumentor().instrument(tracer_provider=provider)
        elif name == "openai":
            from openinference.instrumentation.openai import OpenAIInstrumentor
            OpenAIInstrumentor().instrument(tracer_provider=provider)
        elif name == "pydantic_ai":
            from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor
            from pydantic_ai import Agent
            from pydantic_ai.models.instrumented import InstrumentationSettings
            # Order matters: convert PydanticAI spans to OpenInference first, then export.
            # The first add_span_processor() replaces register()'s default exporter,
            # so the exporter is added again after the converter.
            provider.add_span_processor(OpenInferenceSpanProcessor())
            if export:
                provider.add_span_processor(SimpleSpanProcessor(HTTPSpanExporter(endpoint=settings.phoenix_endpoint)))
            Agent.instrument_all(InstrumentationSettings(version=5))
        else:
            raise ValueError(f"Unknown FURSAH_PHOENIX_INSTRUMENT value: {name}")
        _instrumented.append(name)

    target = settings.phoenix_endpoint if export else "memory only, not exported"
    print(f"Phoenix tracing -> {target} "
          f"(project: {settings.phoenix_project}, instrumentors: {_instrumented or 'none, custom spans only'})")
    if settings.phoenix_instrument == "auto":
        # auto sees what is INSTALLED, not what your code calls.
        print("  FURSAH_PHOENIX_INSTRUMENT=auto chose these from the installed packages. If your code calls "
              "the OpenAI SDK directly, set FURSAH_PHOENIX_INSTRUMENT=openai; then check that each model "
              "call appears as an LLM span.")
    return list(_instrumented)


@contextmanager
def start_span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    """Open a custom span nested under the framework span that is currently running.

    LangGraph runs nodes and tools in worker threads where the instrumentor's span is
    not "current", so the parent is taken from the instrumentor explicitly.
    Attribute values must be str, bool, int, float, or lists of those.
    """
    parent = None
    # Only look for a LangChain parent if the app has actually loaded LangChain: an
    # installed-but-unused LangChain cannot be running, and get_current_span() fails then.
    if "langchain" in _instrumented and "langchain_core.runnables.config" in sys.modules:
        from openinference.instrumentation.langchain import get_current_span

        framework_span = get_current_span()
        if framework_span is not None:
            parent = trace.set_span_in_context(framework_span)

    with _tracer.start_as_current_span(name, context=parent) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        yield span
