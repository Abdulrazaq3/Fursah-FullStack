"""Day 4 · 2.3: code graders, one per component from your 2.1 audit.

Every grader has the same signature:

    grader(case, response, spans) -> Grade | None

case      one line of dev_cases.jsonl. Its "expected" block holds:
            status                 "ok" or "no_match"
            acceptable_source_ids  recommending ANY source of these opportunities is correct
            excluded_source_ids    {source_id: reason}: recommending these is wrong, even
                                   next to an acceptable source in the same recommendation
            uncertain_source_ids   {source_id: reason}: availability unknown; a recommendation
                                   made only of these is not graded (always empty in no_match cases)
response  the DiscoveryResponse your workflow.discover() returned
spans     {span name: attributes} for this case's trace; the last span wins when a name
          repeats. spans.all(name) returns every span with that name, in order.

Return None when the case has nothing to check for this metric (e.g. no acceptable IDs).
Put the expected and the actual value in `reason`: it is printed under every failing case.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class Grade:
    metric: str
    score: float  # 0..1
    reason: str = ""  # "expected X, got Y"


def tool_inputs(spans, tool_name: str) -> list[dict]:
    """Arguments of every call to `tool_name`, for any framework that records tool spans.

    LangChain, LangGraph and PydanticAI all record `tool.name` and the arguments as JSON in
    `input.value`. Without a framework, record them yourself on a custom span with the same keys.
    Exception: LangChain records a tool with ONE argument as the bare value, not JSON; that
    call comes back as {"raw": value}. Print tool_inputs(...) once to see what yours returns.
    """
    calls = []
    for attributes in spans.all_spans():
        if attributes.get("tool.name") == tool_name:
            value = attributes.get("input.value") or "{}"
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
            calls.append(parsed if isinstance(parsed, dict) else {"raw": value})
    return calls


# --- Example (given) ---------------------------------------------------------------

def grade_status(case, response, spans):
    expected = case["expected"]["status"]
    got = response.status.value
    return Grade("e2e.status", float(got == expected), f"expected {expected!r}, got {got!r}")


# --- Your graders: one per deterministic or verifiable component in your 2.1 table ---


GRADERS = [
    grade_status,
]
