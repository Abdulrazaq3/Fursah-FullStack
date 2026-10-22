"""Optional background observation; cannot replace inputs to the checked workflow."""
from __future__ import annotations

import asyncio
import logging
import time

from .infrastructure.openrouter_understanding import (
    BASE_URL, MODEL_ID, UnderstandingError, understand_query,
)
from .request_plan import build_request_plan
from .request_requirements import TOOLS, normalized
from .schemas import SearchConstraints

_tasks: set[asyncio.Task] = set()
MAX_IN_FLIGHT = 2
TOOL_KEYS = {normalized(alias)[0]: key for key, aliases in TOOLS.items() for alias in (key, *aliases)}


def compare_with_reference(proposal, plan):
    # The LLM result is only compared; it never enters build_request_plan or _run.
    if plan["status"] == "requires_interpretation":
        return "reference_requires_review"
    extracted = {}
    for claim in plan["query_claims"]:
        field, value = claim["field"], claim["value"]
        if isinstance(value, list):
            extracted[field] = list(dict.fromkeys(extracted.get(field, []) + value))
        else:
            extracted[field] = value
    required = extracted.pop("required_locations", [])
    expected = SearchConstraints(**extracted).model_dump(mode="json")
    actual = proposal.constraints.model_dump(mode="json")

    def comparable(value):
        return {key: sorted(item or []) if isinstance(item, list) or key == "location_preference"
                else item for key, item in value.items()}

    same = (comparable(expected) == comparable(actual)
            and sorted(required) == sorted(proposal.required_locations)
            and proposal.tool_mode == plan["requirements"]["tool_mode"]
            and sorted(t["tool"] for t in plan["requirements"]["tools"]) ==
                sorted(TOOL_KEYS.get(normalized(tool)[0], normalized(tool)[0]) for tool in proposal.tools)
            and not proposal.needs_review)
    return "matches_reference" if same else "differs_from_reference"


def _emit(deps, request_id, outcome, started):
    try:
        # Separate trace identity prevents late observations from reopening the
        # main request's sequence after its HTTP response has been finalized.
        deps.tracer.emit(request_id=request_id + ":understanding", step="response_ready",
                         component="understanding_shadow", outcome=outcome,
                         elapsed_ms=(time.monotonic() - started) * 1000)
    except Exception:
        logging.getLogger(__name__).warning("Understanding observation trace unavailable")


async def _observe(request, deps):
    started = time.monotonic()
    outcome = "cancelled"
    try:
        result = await understand_query(request.query, deps.model_config,
            timeout=deps.settings.understanding_shadow_timeout_seconds,
            max_output_tokens=deps.settings.understanding_max_output_tokens)
        comparison = compare_with_reference(result.proposal, build_request_plan(request))
        outcome = (f"{comparison};model={result.model_id};"
                   f"input_tokens={result.prompt_tokens};output_tokens={result.completion_tokens}")
    except UnderstandingError as exc:
        outcome = exc.category
    except asyncio.CancelledError:
        raise
    except Exception:
        # No raw exception text: it could contain the query, output or credentials.
        outcome = "observation_error"
    finally:
        _emit(deps, request.request_id, outcome, started)


def schedule_understanding_shadow(request, deps):
    if deps.settings.understanding_mode != "shadow":
        return False
    config = deps.model_config
    if (not config or config.provider != "openrouter" or not config.api_key
            or config.base_url.rstrip("/") != BASE_URL or config.model_name != MODEL_ID):
        _emit(deps, request.request_id, "not_configured", time.monotonic())
        return False
    if len(_tasks) >= MAX_IN_FLIGHT:
        _emit(deps, request.request_id, "skipped_capacity", time.monotonic())
        return False
    task = asyncio.create_task(_observe(request.model_copy(deep=True), deps))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


async def stop_understanding_shadow():
    tasks = tuple(_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _tasks.difference_update(tasks)
