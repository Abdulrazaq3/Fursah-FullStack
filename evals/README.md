![SAAI](https://i.imgur.com/YHRhgqv.png)

**English** | [العربية](README.ar.md)

# Evaluation — how we checked our implementation

[Overview](../README.md) · [Previous: frontend](../frontend/README.md)

We evaluate the real discovery workflow, not a mocked recommendation. Cases exercise request understanding, retrieval, constraints and source evidence. Phoenix shows what happened; code graders decide whether the checks passed.

## Run and inspect

After [backend setup](../backend/README.md#setup) and catalog publication, run from the repository root in PowerShell:

```powershell
.\evals\run.ps1 -Demo -Open          # Three development cases
.\evals\run.ps1 -Label full-dev -Open # All twelve development cases
```

These calls use the configured Gemini API, local models and database. The runner starts the application inside its process; a separate API server is unnecessary. Each case uses a fixed evaluation time without changing `.env`.

Open [Phoenix](http://127.0.0.1:6006), choose **fursah-eval**, then an `eval.case` trace. Its child spans show stage durations and outputs; annotations show scores and failure reasons. A span is one measured operation, such as retrieval or reranking.

## Where the evaluation lives

| Location | Purpose |
|---|---|
| [cases/](cases/) | Development cases, a separate holdout and fingerprints |
| [run.py](run.py) | Execute the application and export traces/scores |
| [catalog_graders.py](catalog_graders.py) | Full-workflow checks |
| [grading.py](grading.py) | Metric name, value and reason |
| [source_audit.py](source_audit.py) | Independently inspect original source evidence |
| [../backend/app/instrumentation/](../backend/app/instrumentation/README.md) | Instrumented stages and Phoenix connection |
| [runs/](runs/README.md) | Each run's results, traces and summary |
| [tests/](tests/) | Regression checks without model calls |
| [archive/](archive/README.md) | Previous experiments and recorded measurements |

## What we found

The [22 October baseline](archive/reports/catalog-eval-baseline-v1-review.md) initially passed 9/12 checks. An independent audit found closed opportunities in the raw source text; rescoring the same responses reduced this to **7/12**. This shows why checking only extracted fields is insufficient.

Open issues include missed closures, unrelated recommendations and latency (30.1 seconds on average in that run). The demo intentionally includes a known closure failure. These are recorded results, not a new run performed for these README files. The six-case holdout is reserved for independent evaluation; do not use it to tune fixes. Expectations still need human review before being treated as a gold standard.

## Useful commands

```powershell
.\evals\phoenix.ps1 -Open            # Inspect saved traces
.\evals\test.ps1                     # Regression checks
.\evals\run.ps1 -Demo -OfflineTraces  # Save traces without Phoenix
```

Exit code `2` means evaluation completed with quality failures; `1` or `3` indicates an execution/measurement problem. New outputs go to `runs/`; Phoenix state goes to `.local/phoenix/`. Historical reports are evidence of previous runs, not current readiness approval.

Historical browser/pilot checks and the Day 4 example live in `archive/checks/`, `archive/starter/` and `archive/cases/`. The current demo uses `cases/dev.jsonl` and `catalog_graders.py`.
