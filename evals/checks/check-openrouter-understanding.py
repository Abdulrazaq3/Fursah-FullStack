"""One bounded live understanding check, independent of the BGE/DB pilot."""
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.infrastructure.config import get_settings
from app.infrastructure.dependencies import build_model_config
from app.infrastructure.openrouter_understanding import UnderstandingError, understand_query
from app.request_plan import build_request_plan
from app.schemas import DiscoveryRequest
from app.understanding_shadow import compare_with_reference


async def main():
    settings = get_settings()
    request = DiscoveryRequest(request_id="openrouter-check",
        query="أبحث عن ورشة مجانية لتعلم Excel عن بعد", profile={}, constraints={})
    try:
        result = await understand_query(request.query, build_model_config(settings),
            timeout=settings.understanding_shadow_timeout_seconds,
            max_output_tokens=settings.understanding_max_output_tokens)
    except UnderstandingError as exc:
        next_step = {
            "not_configured": "Configure OpenRouter in backend/.env and rerun this check.",
            "timeout": "The configured deadline expired; check connectivity and the bounded timeout setting.",
            "authentication": "Check the OpenRouter key and its permissions locally.",
            "rate_limited": "Wait for the provider rate limit to recover before retrying.",
            "invalid_output": "Inspect the schema, model support and output-token budget before retrying.",
        }.get(exc.category, "Inspect the reported failure category before retrying.")
        print(json.dumps({"status": "not_verified", "category": exc.category,
            "next": next_step}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "api_verified", "model": result.model_id,
        "comparison": compare_with_reference(result.proposal, build_request_plan(request)),
        "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
        "recommendation_policy_changed": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
