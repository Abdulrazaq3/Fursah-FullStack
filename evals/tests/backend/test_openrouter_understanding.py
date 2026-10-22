import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from app.infrastructure.config import Settings
from app.infrastructure.dependencies import ModelClientConfig
from app.infrastructure.openrouter_understanding import (
    BASE_URL, MODEL_ID, QueryUnderstanding, UnderstandingError, UnderstandingResult,
    output_schema, understand_query,
)
from app.request_plan import build_request_plan
from app.schemas import DiscoveryRequest, SearchConstraints
from app.understanding_shadow import (
    compare_with_reference, schedule_understanding_shadow, stop_understanding_shadow,
)


def config():
    return ModelClientConfig("openrouter", MODEL_ID, "test-secret", BASE_URL, 5, 0)


def proposal():
    return {"constraints": SearchConstraints(max_budget_sar=0,
        opportunity_types=["workshop"], delivery_modes=["online"]).model_dump(mode="json"),
        "required_locations": [], "tools": ["Excel"], "tool_mode": "all", "needs_review": False}


def response(value=None, **updates):
    body = {"model": MODEL_ID, "choices": [{"finish_reason": "stop",
        "message": {"content": json.dumps(proposal() if value is None else value)}}],
        "usage": {"prompt_tokens": 123, "completion_tokens": 80}}
    body.update(updates)
    return body


class OpenRouterClientTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, body=None, status=200, handler=None, **kwargs):
        transport = httpx.MockTransport(handler or (lambda request:
            httpx.Response(status, json=response() if body is None else body)))
        return await understand_query("ورشة مجانية لتعلم Excel عن بعد", config(), transport=transport, **kwargs)

    async def test_one_structured_request_sends_query_only_and_requires_supported_parameters(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=response())

        result = await self.call(handler=handler)
        self.assertEqual(len(calls), 1)
        sent = json.loads(calls[0].content)
        self.assertEqual(str(calls[0].url), BASE_URL + "/chat/completions")
        self.assertEqual(sent["model"], MODEL_ID)
        self.assertEqual(sent["provider"], {"require_parameters": True})
        self.assertEqual(sent["max_tokens"], 768)
        self.assertEqual(sent["reasoning"], {"effort": "low", "exclude": True})
        self.assertTrue(sent["response_format"]["json_schema"]["strict"])
        self.assertNotIn("tools", sent)
        self.assertNotIn("test-secret", calls[0].content.decode())
        self.assertEqual(result.prompt_tokens, 123)
        self.assertEqual(result.proposal.constraints.max_budget_sar, 0)

    async def test_complete_schema_and_dates_are_validated(self):
        value = proposal()
        value["constraints"].update(available_from="2026-12-01", available_to="2026-12-02")
        result = await self.call(response(value))
        self.assertEqual(result.proposal.constraints.available_from.isoformat(), "2026-12-01")
        schema = output_schema()["$defs"]["QueryConstraints"]
        self.assertEqual(set(schema["required"]), set(SearchConstraints.model_fields))
        self.assertFalse(schema["additionalProperties"])

    async def test_no_key_unapproved_target_or_model_never_calls_network(self):
        for changed in (replace(config(), api_key=""), replace(config(), provider="other"),
                        replace(config(), base_url="https://untrusted.example"),
                        replace(config(), model_name="other/model")):
            handler = Mock()
            with self.subTest(config=repr(changed)), self.assertRaisesRegex(UnderstandingError, "not_configured"):
                await understand_query("ورشة", changed, transport=httpx.MockTransport(handler))
            handler.assert_not_called()

    async def test_http_errors_are_categorized_without_retries_or_remote_details(self):
        for code, category in [(429, "rate_limited"), (401, "authentication"),
                               (403, "authentication"), (500, "upstream_error"), (302, "upstream_error")]:
            handler = Mock(return_value=httpx.Response(code, text="test-secret private query"))
            with self.subTest(code=code), self.assertRaisesRegex(UnderstandingError, category) as caught:
                await self.call(handler=handler)
            self.assertNotIn("test-secret", str(caught.exception))
            self.assertEqual(handler.call_count, 1)

    async def test_malformed_refused_truncated_and_wrong_model_outputs_are_rejected(self):
        invalid = [[], {"choices": []}, response(model="other/model")]
        for reason in ["length", "tool_calls", "content_filter"]:
            bad = response()
            bad["choices"][0]["finish_reason"] = reason
            invalid.append(bad)
        for content in ["not json", "{}", json.dumps({**proposal(), "invented": True})]:
            bad = response()
            bad["choices"][0]["message"]["content"] = content
            invalid.append(bad)
        bad = response()
        bad["choices"][0]["message"]["refusal"] = "Cannot comply"
        invalid.append(bad)
        for body in invalid:
            with self.subTest(body=body), self.assertRaisesRegex(UnderstandingError, "invalid_output"):
                await self.call(body)

    async def test_missing_nested_fields_negative_budget_reversed_dates_and_string_boolean_rejected(self):
        invalid = []
        value = proposal()
        value["constraints"].pop("max_budget_sar")
        invalid.append(value)
        for changes in ({"max_budget_sar": -1}, {"max_budget_sar": "0"},
                        {"available_from": "2026-12-02", "available_to": "2026-12-01"}):
            value = proposal()
            value["constraints"].update(changes)
            invalid.append(value)
        invalid.append({**proposal(), "needs_review": "false"})
        for value in invalid:
            with self.subTest(value=value), self.assertRaisesRegex(UnderstandingError, "invalid_output"):
                await self.call(response(value))

    async def test_timeout_and_connection_errors_are_bounded(self):
        async def slow(request):
            await asyncio.sleep(10)
        with self.assertRaisesRegex(UnderstandingError, "timeout"):
            await self.call(handler=slow, timeout=.01)

        def disconnected(request):
            raise httpx.ConnectError("test-secret", request=request)
        with self.assertRaisesRegex(UnderstandingError, "connection_error"):
            await self.call(handler=disconnected)

    async def test_oversized_responses_and_invalid_usage_are_rejected(self):
        with self.assertRaisesRegex(UnderstandingError, "invalid_output"):
            await self.call(handler=lambda request: httpx.Response(200, content=b"x" * 65_537))
        with self.assertRaisesRegex(UnderstandingError, "invalid_output"):
            await self.call(response(usage={"prompt_tokens": True}))


class UnderstandingShadowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.request = DiscoveryRequest(request_id="shadow-test",
            query="ورشة مجانية لتعلم Excel عن بعد", profile={"city": "جدة", "user_id": "private-user"},
            constraints={"max_budget_sar": 100})
        self.deps = SimpleNamespace(settings=Settings(_env_file=None, understanding_mode="shadow"),
                                    model_config=config(), tracer=Mock())
        self.addAsyncCleanup(stop_understanding_shadow)

    def result(self, **updates):
        value = proposal()
        value.update(updates)
        return UnderstandingResult(QueryUnderstanding.model_validate_json(json.dumps(value)), MODEL_ID, 123, 80)

    async def finish(self):
        from app.understanding_shadow import _tasks
        await asyncio.gather(*tuple(_tasks))

    async def test_off_mode_and_missing_credentials_make_zero_calls(self):
        with patch("app.understanding_shadow.understand_query", new_callable=AsyncMock) as client:
            self.deps.settings.understanding_mode = "off"
            self.assertFalse(schedule_understanding_shadow(self.request, self.deps))
            self.deps.settings.understanding_mode = "shadow"
            self.deps.model_config = None
            self.assertFalse(schedule_understanding_shadow(self.request, self.deps))
            client.assert_not_awaited()

    async def test_background_result_never_mutates_request_or_plan_and_trace_is_redacted(self):
        original = self.request.model_dump()
        plan = build_request_plan(self.request)
        frozen = deepcopy(plan)
        malicious = self.result(tools=["Invented tool"], required_locations=["مدينة مختلقة"])
        with patch("app.understanding_shadow.understand_query", new_callable=AsyncMock, return_value=malicious) as client:
            self.assertTrue(schedule_understanding_shadow(self.request, self.deps))
            await self.finish()
        self.assertEqual(self.request.model_dump(), original)
        self.assertEqual(plan, frozen)
        self.assertEqual(client.await_args.args[0], self.request.query)
        trace = self.deps.tracer.emit.call_args.kwargs
        self.assertIn("differs_from_reference", trace["outcome"])
        self.assertNotIn(self.request.query, repr(trace))
        self.assertNotIn("private-user", repr(trace))
        self.assertNotIn("test-secret", repr(trace))
        self.assertEqual(trace["request_id"], "shadow-test:understanding")

    async def test_comparison_preserves_zero_soft_cities_tools_and_alternatives(self):
        self.assertEqual(compare_with_reference(self.result().proposal, build_request_plan(self.request)),
                         "matches_reference")
        request = self.request.model_copy(update={"query": "ورشة مجانية عن بعد Excel أو SQL أفضل الرياض"})
        value = proposal()
        value["constraints"]["location_preference"] = ["الرياض"]
        value.update(tools=["sql", "Microsoft Excel"], tool_mode="any")
        parsed = QueryUnderstanding.model_validate_json(json.dumps(value))
        self.assertEqual(compare_with_reference(parsed, build_request_plan(request)), "matches_reference")
        self.assertEqual(compare_with_reference(self.result().proposal,
            build_request_plan(self.request.model_copy(update={"query": "ورشة Excel مو مجانية"}))),
            "reference_requires_review")

    async def test_at_most_two_background_calls_and_shutdown_cancels_pending_work(self):
        entered = asyncio.Event()
        async def pending(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
        with patch("app.understanding_shadow.understand_query", side_effect=pending) as client:
            self.assertTrue(schedule_understanding_shadow(self.request, self.deps))
            self.assertTrue(schedule_understanding_shadow(self.request, self.deps))
            self.assertFalse(schedule_understanding_shadow(self.request, self.deps))
            await entered.wait()
            self.assertEqual(client.call_count, 2)
            await stop_understanding_shadow()
        self.assertEqual(self.deps.tracer.emit.call_args.kwargs["outcome"], "cancelled")

    async def test_upstream_failure_and_logging_failure_do_not_escape_to_discovery(self):
        self.deps.tracer.emit.side_effect = OSError("local log unavailable")
        with patch("app.understanding_shadow.understand_query", new_callable=AsyncMock,
                   side_effect=UnderstandingError("rate_limited")):
            self.assertTrue(schedule_understanding_shadow(self.request, self.deps))
            await self.finish()

    async def test_api_response_is_unchanged_and_does_not_wait_for_the_observer(self):
        from datetime import datetime, timezone
        from app.main import app
        from app.infrastructure.dependencies import get_app_dependencies
        from test_discovery_pilot import FakeInference, sample_rows

        repo = Mock()
        repo.search.return_value = sample_rows()
        deps = replace(get_app_dependencies(), repository=repo, model_config=config(),
            settings=Settings(_env_file=None, discovery_pilot_enabled=True,
                understanding_mode="off", evaluation_time=datetime(2026, 10, 21, 12, tzinfo=timezone.utc)))
        app.dependency_overrides[get_app_dependencies] = lambda: deps
        self.addCleanup(app.dependency_overrides.clear)
        finished = asyncio.Event()

        async def pending(*args, **kwargs):
            await finished.wait()
            return self.result()

        with patch("app.workflow.get_local_inference", return_value=FakeInference()), \
             patch("app.understanding_shadow.understand_query", side_effect=pending) as observer:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                payload = self.request.model_copy(update={"query": "أبي فرص تحليل البيانات باستخدام Excel",
                    "constraints": SearchConstraints()}).model_dump(mode="json")
                baseline = await client.post("/api/v1/discover", json=payload)
                self.assertEqual(baseline.status_code, 200)
                self.assertEqual(baseline.json()["status"], "ok")
                deps.settings.understanding_mode = "shadow"
                observed = await asyncio.wait_for(client.post("/api/v1/discover", json=payload), timeout=2)
                self.assertEqual(observed.json(), baseline.json())
                self.assertFalse(finished.is_set())
                await asyncio.sleep(0)
                self.assertEqual(observer.await_count, 1)
                finished.set()
                await self.finish()


if __name__ == "__main__":
    unittest.main()
