"""Run labelled cases through the real API workflow and show traces and grades in Phoenix.

    python -m evals.run --label baseline --trace-export phoenix

In-process evaluation: your FastAPI app (`app.main:app`, or --app module:attribute) is
started with its own lifespan, and each case is POSTed to /api/v1/discover through
httpx's ASGI transport. No network and no server process, but the same route, request
validation, dependencies and startup code as the UI. Real model API calls still use
the network. FURSAH_EVALUATION_TIME is set from
the cases, exactly as the hidden test set is graded.

Each case is wrapped in an `eval.case` span: a failing case prints its trace_id, which you
can open in Phoenix (Traces tab, filter: trace_id == "<trace_id>").
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import io
import inspect
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from statistics import mean

EVALS = Path(__file__).resolve().parent
BACKEND = EVALS.parent / 'backend'
sys.path.insert(0, str(BACKEND))


class CaseSpans(dict):
    """{span name: attributes}, last span wins; .all(name) and .all_spans() keep every span."""

    def __init__(self, spans: list[tuple[str, dict]]):
        super().__init__()
        self._spans = spans
        for name, attributes in spans:
            self[name] = attributes

    def all(self, name: str) -> list[dict]:
        return [attributes for span_name, attributes in self._spans if span_name == name]

    def all_spans(self) -> list[dict]:
        return [attributes for _, attributes in self._spans]


def load_cases(path: Path, only: set[str] | None) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len({c['case_id'] for c in cases}) != len(cases):
        raise SystemExit('Duplicate evaluation case IDs')
    if only:
        known = {c["case_id"] for c in cases}
        unknown = sorted(only - known)
        if unknown:
            raise SystemExit(f"Unknown case ID(s): {', '.join(unknown)}. Known: {', '.join(sorted(known))}")
        cases = [c for c in cases if c["case_id"] in only]
    if not cases:
        raise SystemExit(f"No cases to run in {path}")
    return cases


def grade_failures(grades, case, critical_metrics=None):
    """Ranking diagnostics need an explicit target, not an accidental 100% gate."""
    thresholds = case.get('metric_thresholds', {})
    return [g for g in grades if g.score < thresholds.get(g.metric, 1.0)
            and (critical_metrics is None or g.metric in critical_metrics or g.metric in thresholds)]


def verify_manifest(cases_path):
    path=cases_path.parent/'manifest.json'
    if cases_path.name not in {'dev.jsonl','holdout.jsonl'}:
        return None
    manifest=json.loads(path.read_text(encoding='utf-8'))
    root=BACKEND.parent.resolve()
    for relative,expected in manifest['files'].items():
        target=(root/relative).resolve()
        if not target.is_relative_to(root) or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
            raise SystemExit('Frozen evaluation input changed: '+relative)
    return hashlib.sha256(path.read_bytes()).hexdigest()


SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{6,}|Bearer\s+\S+|api[_-]?key\s*[=:]\s*\S+)", re.IGNORECASE)


def summarize(text, limit: int = 200) -> str:
    """One line, secrets redacted, truncated: safe to print and to save."""
    line = SECRET.sub("[redacted]", " ".join(str(text).split()))
    return line if len(line) <= limit else line[: limit - 1] + "…"


def run_graders(graders, case, response, spans) -> tuple[list, list[str]]:
    """Valid grades, and errors for graders that raised or returned an invalid score.
    None stays valid: that metric does not apply to this case."""
    grades, errors = [], []
    for grader in graders:
        name = getattr(grader, "__name__", repr(grader))
        try:
            grade = grader(case, response, spans)
        except Exception as exc:
            errors.append(f"{name} raised {type(exc).__name__}: {summarize(exc, 120)}")
            continue
        if grade is None:
            continue
        metric, score = getattr(grade, "metric", None), getattr(grade, "score", None)
        if not isinstance(metric, str) or not metric:
            errors.append(f"{name} returned a grade without a metric name")
        elif isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
            errors.append(f"{name} returned score {score!r} for {metric}: it must be a number from 0 to 1")
        else:
            grades.append(grade)
    return grades, errors


def load_app(spec: str):
    module, _, attribute = spec.partition(":")
    return getattr(importlib.import_module(module), attribute or "app")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(EVALS / 'cases/dev.jsonl'))
    parser.add_argument("--graders", default="evals.catalog_graders", help="module that defines GRADERS")
    parser.add_argument("--app", default="app.main:app", help="your FastAPI app, if you moved it")
    parser.add_argument("--label", default="", help="e.g. baseline or after-fix-1")
    parser.add_argument("--only", default="", help="comma-separated case IDs, e.g. DEV-03,DEV-07")
    parser.add_argument("--project", default="fursah-eval", help="Phoenix project for these traces")
    parser.add_argument('--trace-export', choices=['memory','phoenix'], default='memory',
                        help='Memory + local trace files by default; Phoenix is optional')
    parser.add_argument('--include-holdout', action='store_true',help='Explicitly select a sealed acceptance suite')
    parser.add_argument("--case-timeout", type=float, default=100,
                        help="seconds per case; 100 matches how long the UI waits")
    args = parser.parse_args()
    os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS', '1')
    if args.label and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.label):
        raise SystemExit('Label must contain only letters, digits, underscores and hyphens')
    if 'holdout' in Path(args.cases).stem and not args.include_holdout:
        raise SystemExit('Holdout is sealed. Use development cases for debugging; --include-holdout selects the later acceptance run.')
    manifest_sha=verify_manifest(Path(args.cases))

    cases = load_cases(Path(args.cases), {c.strip() for c in args.only.split(",") if c.strip()} or None)
    times = {c["evaluation_time"] for c in cases}
    if len(times) != 1:
        raise SystemExit(f"All cases must share one evaluation_time (the API reads it once per server): {times}")

    # The cases were labelled at one instant, so this run always uses it. Compare it with
    # what the app uses when started normally (environment or backend/.env), so the UI and
    # the evaluation do not silently disagree.
    case_time = times.pop()
    from app.infrastructure.config import get_settings as configured_settings
    configured = configured_settings().evaluation_time
    if configured is None:
        print(f"Normal operation uses the real clock. This evaluation alone uses {case_time}; backend/.env is unchanged.\n")
    elif configured != datetime.fromisoformat(case_time):
        print(f"Warning: your app is configured with FURSAH_EVALUATION_TIME={configured.isoformat()},\n"
              f"         but the cases were labelled at {case_time}. This run uses {case_time};\n"
              f"         the UI will disagree until you set the same value in backend/.env.\n")

    # Set before the app is imported: settings are read when the app builds its dependencies.
    os.environ["FURSAH_EVALUATION_TIME"] = case_time
    os.environ["FURSAH_PHOENIX_ENABLED"] = "true"
    os.environ["FURSAH_PHOENIX_PROJECT"] = args.project
    os.environ['FURSAH_EVAL_TELEMETRY_ENABLED'] = 'true'
    os.environ['FURSAH_PHOENIX_INSTRUMENT'] = 'none'

    import httpx
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from app.infrastructure.config import get_settings
    from app.instrumentation.phoenix import setup_observability, start_span

    # The small SDK suffices for local grading; no Phoenix service is required.
    endpoint = get_settings().phoenix_endpoint
    phoenix_up = args.trace_export == 'phoenix'
    if phoenix_up:
        from urllib.parse import urlsplit
        from phoenix.client import Client as PhoenixClient
        parsed_endpoint = urlsplit(endpoint)
        phoenix_url = f'{parsed_endpoint.scheme}://{parsed_endpoint.netloc}'
        httpx.get(phoenix_url + '/healthz', timeout=10).raise_for_status()
        phoenix_client = PhoenixClient(base_url=phoenix_url)
        with redirect_stdout(io.StringIO()):
            setup_observability(export=True)
    else:
        from opentelemetry.sdk.trace import TracerProvider
        trace.set_tracer_provider(TracerProvider())
    memory = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if phoenix_up:
        # Phoenix replaces its exporter when a processor is added unless told to keep it.
        provider.add_span_processor(SimpleSpanProcessor(memory), replace_default_processor=False)
    else:
        provider.add_span_processor(SimpleSpanProcessor(memory))

    from app.schemas import DiscoveryResponse, DiscoveryStatus
    if args.graders=='evals.catalog_graders':
        from app.catalog_store import connect_catalog,package_version
        package=json.loads((BACKEND.parent/'data/prepared/catalog.json').read_text(encoding='utf-8'))
        with connect_catalog(get_settings()) as conn:
            active=conn.execute('SELECT r.package_sha256 FROM fursah_catalog.state s JOIN '
                'fursah_catalog.releases r ON r.release_id=s.active_release').fetchone()
        if not active or active[0]!=package_version(package):
            raise SystemExit('Active database release differs from the labelled catalog package')

    app = load_app(args.app)
    # The app's own handler turns any exception into a generic 500 (right for production).
    # Record the exception first, so a crash shows its real cause here.
    app_errors: list[str] = []
    original_handler = app.exception_handlers.get(Exception)

    async def record_exception(request, exc):
        app_errors.append(f"{type(exc).__name__}: {exc}")
        if original_handler is None:
            from fastapi.responses import JSONResponse
            return JSONResponse({"message": "Internal Server Error"}, status_code=500)
        result = original_handler(request, exc)
        return await result if inspect.isawaitable(result) else result

    app.exception_handlers[Exception] = record_exception
    grader_module = importlib.import_module(args.graders)
    GRADERS = grader_module.GRADERS
    critical_metrics = getattr(grader_module, 'CRITICAL_METRICS', None)
    run = args.label or datetime.now().strftime("%Y%m%d-%H%M%S")

    run_dir = EVALS / 'runs' / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}{'-' + args.label if args.label else ''}"
    if run_dir.exists():
        raise SystemExit('Preserve existing evaluation artifacts; choose a new label')
    run_dir.mkdir(parents=True)
    out_path = run_dir / 'results.jsonl'
    traces_path = run_dir / 'traces.jsonl'
    summary_path = run_dir / 'summary.json'
    scores: dict[str, list[float]] = defaultdict(list)
    failures: dict[str, list[str]] = defaultdict(list)
    outcomes: Counter = Counter()
    timings = defaultdict(list)
    token_totals = Counter()
    case_seconds = []
    annotations = []

    def as_error(case: dict, message: str, code: str) -> DiscoveryResponse:
        """What the UI shows for a reply it cannot use: an error."""
        return DiscoveryResponse(request_id=case["case_id"], status=DiscoveryStatus.ERROR,
                                 message=message[:300], error_code=code)

    async def run_case(client: httpx.AsyncClient, case: dict) -> tuple[DiscoveryResponse, tuple | None]:
        """The reply to grade, and a problem: None, ("protocol", why) or ("execution", why).

        Protocol invariants are checked before any grader, with the same rules as the UI
        (frontend/src/api/client.ts): any non-2xx reply is an error whatever its body.
        A structured error (status "error") is a legitimate reply on any HTTP code.
        """
        payload = {"request_id": case["case_id"], "query": case["query"],
                   "profile": case["profile"], "constraints": case["constraints"]}
        if 'constraint_resolution' in case:
            payload['constraint_resolution'] = case['constraint_resolution']
        try:
            with redirect_stdout(io.StringIO()):  # the app's JSONL tracer prints every event
                reply = await client.post("/api/v1/discover", json=payload)
        except Exception as exc:  # the app could not answer at all
            return as_error(case, f"{type(exc).__name__}: {exc}", "EVAL_EXCEPTION"), ("execution", f"{type(exc).__name__}: {exc}")
        code = reply.status_code
        try:
            body = reply.json()
        except ValueError:
            why = f"HTTP {code}: the response is not valid JSON"
            return as_error(case, why, "EVAL_BAD_JSON"), ("execution", why)
        if not isinstance(body, dict) or "status" not in body:  # e.g. the generic 500/422 error shape
            why = f"HTTP {code}: {body.get('message', '') if isinstance(body, dict) else ''} {body.get('details', '') if isinstance(body, dict) else ''}"
            return as_error(case, why, "EVAL_EXCEPTION"), ("execution", why)
        try:
            response = DiscoveryResponse.model_validate(body)
        except Exception as exc:
            why = f"HTTP {code}: the body breaks the DiscoveryResponse contract: {summarize(exc, 160)}"
            return as_error(case, why, "EVAL_BAD_CONTRACT"), ("protocol", why)
        if response.request_id != case["case_id"]:
            why = f"request_id {response.request_id!r} is not the request's {case['case_id']!r}: echo request.request_id"
            return as_error(case, why, "EVAL_WRONG_REQUEST_ID"), ("protocol", why)
        if not 200 <= code < 300 and response.status != DiscoveryStatus.ERROR:
            why = (f"HTTP {code} with a {response.status.value!r} body: the UI rejects every non-2xx reply, "
                   f"so users see an error, not this answer")
            return as_error(case, why, "EVAL_HTTP_STATUS"), ("protocol", why)
        for rec in response.recommendations:
            with start_span('fursah.details') as detail_span:
                try:
                    detail_reply = await client.get('/api/v1/opportunities/' + rec.opportunity_id)
                    details = detail_reply.json()
                    detail_span.set_attribute('output.value',json.dumps({'opportunity_id':rec.opportunity_id,
                        'http_status':detail_reply.status_code,'details':details},ensure_ascii=False))
                except Exception as exc:
                    detail_span.set_attribute('output.value',json.dumps({'opportunity_id':rec.opportunity_id,
                        'http_status':0,'error_type':type(exc).__name__}))
        return response, None

    # Watchdog for code that BLOCKS the event loop (time.sleep, synchronous HTTP, heavy CPU
    # inside async code): asyncio cannot cancel it, so the process is stopped instead.
    GRACE = 10
    running: dict = {}

    def watchdog():
        while True:
            time.sleep(0.5)
            case_id, started = running.get("case"), running.get("started")
            if case_id and time.monotonic() - started > args.case_timeout + GRACE:
                why = (f"{case_id} blocked the event loop for over {args.case_timeout + GRACE:.0f}s, so its "
                       f"{args.case_timeout:.0f}s deadline could not stop it. Look for blocking calls inside "
                       f"async code (time.sleep, requests, heavy loops): use their async versions.")
                with out_path.open("a", encoding="utf-8") as out:
                    out.write(json.dumps({"case_id": case_id, "outcome": "TIMEOUT", "timeout": why},
                                         ensure_ascii=False) + "\n")
                print(f"{case_id:7} TIMEOUT   (blocking code)\n        {why}\n"
                      f"Run stopped: the remaining cases were not run. Results so far: {out_path}",
                      file=sys.__stdout__, flush=True)  # sys.stdout may be redirected while a case runs
                os._exit(3)

    threading.Thread(target=watchdog, daemon=True).start()

    # ONE event loop for the whole run, as in a server: the app starts once (lifespan),
    # and a client it reuses across requests stays bound to that loop.
    async def run_suite():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        with redirect_stdout(io.StringIO()):
            lifespan = app.router.lifespan_context(app)
            await lifespan.__aenter__()
        try:
            with out_path.open("x", encoding="utf-8") as out, traces_path.open('x',encoding='utf-8') as trace_out:
                # No network timeout: the ASGI transport has no network, so it would never fire.
                # The per-case deadline below is the real limit.
                async with httpx.AsyncClient(transport=transport, base_url="http://fursah.eval", timeout=None) as client:
                    for case in cases:
                        memory.clear()
                        app_errors.clear()
                        case_started = time.perf_counter()
                        with start_span("eval.case", **{"eval.case_id": case["case_id"], "eval.run": run,
                                                        "openinference.span.kind": "CHAIN",
                                                        "input.value": case["query"]}) as root:
                            running.update(case=case["case_id"], started=time.monotonic())
                            try:
                                response, problem = await asyncio.wait_for(run_case(client, case), args.case_timeout)
                            except asyncio.TimeoutError:
                                why = (f"no reply within {args.case_timeout:.0f}s: the UI gives up at 100s "
                                       f"(the workflow budget is 90s)")
                                response, problem = as_error(case, why, "EVAL_TIMEOUT"), ("timeout", why)
                            finally:
                                running.clear()
                            trace_id = root.get_span_context().trace_id
                            finished = sorted((s for s in memory.get_finished_spans() if s.context.trace_id == trace_id),
                                              key=lambda s: s.start_time)
                            spans = CaseSpans([(s.name, {k: list(v) if isinstance(v, tuple) else v
                                                         for k, v in s.attributes.items()}) for s in finished])
                            grades, grader_errors = run_graders(GRADERS, case, response, spans)
                            failed = grade_failures(grades, case, critical_metrics)
                            crash = app_errors[-1] if app_errors else (
                                problem[1] if problem and problem[0] == "execution" else None)
                            protocol = problem[1] if problem and problem[0] == "protocol" else None
                            timed_out = problem[1] if problem and problem[0] == "timeout" else None
                            outcome = ("GRADER ERROR" if grader_errors else "ERROR" if crash
                                       else "TIMEOUT" if timed_out else "PROTOCOL ERROR" if protocol
                                       else "NOT EVALUATED" if not grades else "FAIL" if failed else "PASS")
                            root.set_attribute("eval.outcome", outcome)
                            root.set_attribute("eval.failed_metrics", [g.metric for g in failed])
                            root.set_attribute("output.value", response.model_dump_json())
                            root.set_attribute("output.mime_type", "application/json")
                            span_id = format(root.get_span_context().span_id, '016x')
                            annotations.append({'span_id': span_id, 'name': 'case_outcome',
                                'annotator_kind': 'CODE', 'result': {'label': outcome,
                                    'score': 1.0 if outcome == 'PASS' else 0.0,
                                    'explanation': '; '.join(g.reason for g in failed) or outcome}})
                            annotations.extend({'span_id': span_id, 'name': g.metric,
                                'annotator_kind': 'CODE', 'result': {'score': g.score,
                                    'label': 'FAIL' if any(f.metric == g.metric for f in failed) else 'PASS',
                                    'explanation': g.reason}} for g in grades)

                        elapsed = time.perf_counter()-case_started
                        case_seconds.append(elapsed)
                        # Include the root after it has closed, along with all workflow stages.
                        exported_spans = sorted((s for s in memory.get_finished_spans() if s.context.trace_id == trace_id),
                                                key=lambda s: s.start_time)
                        first_span_start=min((s.start_time for s in exported_spans),default=0)
                        for s in exported_spans:
                            attrs = dict(s.attributes)
                            timings[s.name].append((s.end_time-s.start_time)/1e9)
                            for key in ('llm.input_tokens','llm.output_tokens'):
                                if isinstance(attrs.get(key),int): token_totals[key]+=attrs[key]
                            trace_out.write(json.dumps({'case_id':case['case_id'],'trace_id':format(trace_id,'032x'),
                                'span_id':format(s.context.span_id,'016x'),'parent_span_id':format(s.parent.span_id,'016x') if s.parent else None,
                                'name':s.name,'duration_ms':(s.end_time-s.start_time)/1e6,
                                'start_offset_ms':(s.start_time-first_span_start)/1e6,
                                'attributes':{k:list(v) if isinstance(v,tuple) else v for k,v in attrs.items()}},ensure_ascii=False)+'\n')
                        trace_out.flush()

                        for g in grades:
                            scores[g.metric].append(g.score)
                            if any(f.metric == g.metric for f in failed):
                                failures[g.metric].append(case["case_id"])
                        outcomes[outcome] += 1
                        out.write(json.dumps({"case_id": case["case_id"], "outcome": outcome,
                                              "query":case['query'],
                                              "trace_id": format(trace_id, "032x"),
                                              "seconds": elapsed, "response":response.model_dump(mode='json'),
                                              "status": response.status.value, "message": summarize(response.message, 300),
                                              "execution_error": summarize(crash, 300) if crash else None,
                                              "protocol_error": summarize(protocol, 300) if protocol else None,
                                              "timeout": timed_out,
                                              "grader_errors": grader_errors,
                                              "grades": [g.__dict__ for g in grades]}, ensure_ascii=False) + "\n")
                        out.flush()

                        if outcome == "PASS":
                            print(f"{case['case_id']:7} PASS")
                            continue
                        trace_note = f"trace_id={format(trace_id, '032x')}"
                        print(f"{case['case_id']:7} {outcome}   {trace_note}")
                        for g in failed:
                            print(f"        {g.metric:28} {g.reason}")
                        for error in grader_errors:
                            print(f"        grader error: {error}")
                        if crash:
                            print(f"        execution error: {summarize(crash)}")
                        elif timed_out:
                            print(f"        timeout: {timed_out}")
                        elif protocol:
                            print(f"        protocol error: {summarize(protocol, 260)}")
                        elif response.status.value == "error":
                            print(f"        your app returned an error: {summarize(response.message)}")
                        if outcome == "NOT EVALUATED":
                            print("        every grader returned None: nothing was measured for this case")
        finally:
            with redirect_stdout(io.StringIO()):
                await lifespan.__aexit__(None, None, None)

    asyncio.run(run_suite())

    trace.get_tracer_provider().force_flush()
    (run_dir / 'annotations.json').write_text(json.dumps(annotations,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary={'run':run,'cases':len(cases),'outcomes':dict(outcomes),
        'metrics':{metric:{'mean':mean(values),'n':len(values),'failing_cases':failures[metric]} for metric,values in scores.items()},
        'latency_seconds':{'mean':mean(case_seconds),'max':max(case_seconds),'samples':len(case_seconds)},
        'stage_seconds':{name:{'mean':mean(values),'total':sum(values),'samples':len(values)} for name,values in timings.items()},
        'token_totals':dict(token_totals),'trace_export':args.trace_export,'evaluation_time':case_time,
        'cases_sha256':hashlib.sha256(Path(args.cases).read_bytes()).hexdigest(),
        'graders_sha256':hashlib.sha256(Path(grader_module.__file__).read_bytes()).hexdigest(),
        'catalog_sha256':hashlib.sha256((BACKEND.parent/'data/prepared/catalog.json').read_bytes()).hexdigest()
            if (BACKEND.parent/'data/prepared/catalog.json').exists() else None,
        'absolute_rerank_score_cutoff':get_settings().catalog_min_rerank_score,
        'production_approval':False,'holdout_evaluated':'holdout' in Path(args.cases).stem,
        'manifest_sha256':manifest_sha,'results_file':str(out_path),'traces_file':str(traces_path),
        'phoenix_project':args.project if phoenix_up else None,
        'phoenix_url':phoenix_url if phoenix_up else None, 'phoenix_annotations':0}
    summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if phoenix_up:
        from .phoenix_export import publish_annotations
        publish_annotations(phoenix_client, annotations)
        summary['phoenix_annotations'] = len(annotations)
        summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (EVALS/'runs/latest.json').write_text(json.dumps({'run_dir':run_dir.name,
        'phoenix_project':summary['phoenix_project'],'phoenix_url':summary['phoenix_url']},indent=2)+'\n',encoding='utf-8')
    print(f"\n{'metric':30} {'score':>6} {'n':>3}  failing cases")
    for metric in sorted(scores):
        values = scores[metric]
        print(f"{metric:30} {mean(values):6.2f} {len(values):3}  {', '.join(failures[metric])}")
    order = ["PASS", "FAIL", "NOT EVALUATED", "PROTOCOL ERROR", "TIMEOUT", "ERROR", "GRADER ERROR"]
    print(f"\n{len(cases)} cases: " + ", ".join(f"{outcomes[o]} {o}" for o in order if outcomes[o]))
    print(f"Results: {out_path}")
    print(f"Local trace backup: {traces_path}")
    if phoenix_up:
        print(f"Phoenix: {phoenix_url} -> {args.project} ({summary['phoenix_annotations']} evaluation annotations)")
        print('Open a failing case: Phoenix -> Traces -> filter: trace_id == "<trace_id>"')
    if outcomes["GRADER ERROR"]:
        print("\nSome graders raised or returned invalid scores: fix them before reading the table.")
        sys.exit(1)
    if outcomes["NOT EVALUATED"] == len(cases):
        print("\nNo case was evaluated: every grader returned None.")
        sys.exit(1)
    if any(outcomes[k] for k in ('FAIL','ERROR','TIMEOUT','PROTOCOL ERROR')):
        sys.exit(2)


if __name__ == "__main__":
    main()
