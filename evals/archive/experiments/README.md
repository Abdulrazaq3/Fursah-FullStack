![SAAI — Learn AI by building](../docs/assets/saai-header.png)

**English** | [العربية](README.ar.md)

# Experiments — local semantic retrieval

**Previous:** [Data](../data/README.md) · **Overview:** [FURSAH](../README.md) · **Next:** [Backend](../backend/README.md)

This experiment verifies one part of FURSAH: converting opportunity and query text into vectors, storing them and retrieving the closest opportunities. It does not run the application's recommendation workflow.

## What the experiment uses

| Component | Choice | Purpose |
|---|---|---|
| Embedding model | BAAI/bge-m3, pinned revision | Generate dense 1024-dimensional vectors locally |
| Model runtime | SentenceTransformers on CPU | Encode documents and queries using the same model |
| Storage | PostgreSQL with pgvector | Keep opportunities, source evidence and vectors together |
| Search | Exact cosine search, Top-2 | Establish a small reproducible retrieval baseline |
| Corpus | Four manually prepared opportunities | Inspect relationships and results before expanding |
| Evaluation | Eight manually labelled queries | Six in-scope queries and two without a relevant sample record |

The [experiment design](../docs/first-retrieval-experiment.md) explains these choices. The current PostgreSQL instance runs on `127.0.0.1:55432`, separately from the existing system service.

## Prepare and run

Run from the project root. First-time setup needs Python 3.11, a PostgreSQL 18 installation with development headers and Visual Studio C++ build tools. The database setup script uses those existing Windows installations; it does not install them.

```powershell
.\scripts\setup-python.ps1
.\scripts\run-retrieval-experiment.ps1
```

The second command performs four stages:

| Stage | What happens | Output |
|---|---|---|
| 1. Prepare | Check the database and verify or download the checkpoint | SHA256-verified local model |
| 2. Index | Prepare four source-backed documents and encode them | Vectors stored with opportunity IDs and evidence versions |
| 3. Evaluate | Run the eight queries and compare SQL rankings with a local calculation | Rankings, scores and measured timings |
| 4. Review | Generate an Arabic review from the actual report | `results/retrieval-review.md` |

The model weights are about 2.27 GB. A first download requires internet; inference uses the local snapshot offline. Cached weights are checked by size and SHA256, and a stale snapshot can be repaired from a verified cached copy.

## Read the results

| File | Contents |
|---|---|
| [Human-readable review](../results/retrieval-review.md) | Findings, timings, limitations and next decisions |
| [Numeric report](../results/retrieval-report.json) | Model revision, versions, hashes and per-query results |
| [Indexed documents](../results/indexed-documents.json) | Exact search text and its source-backed parts |
| [Prepared sample](../examples/linked-data.sample.json) | Four opportunities, six announcements and 24 evidence items |
| [Evaluation queries](../examples/retrieval-eval.sample.json) | The original manual labels; completed-run status lives in the report |

The completed run reached **Recall@2 = 100% on the six in-scope queries**. Requests about cooking and first aid still returned nearest neighbours despite having no relevant sample opportunity. These neighbours are not recommendations; relevance and abstention handling remain application work.

## Expanded relevance evaluation

We measured 48 distinct queries against the same four opportunities, separating calibration from evaluation. The full-document cutoff removed unrelated additions but lost every result for one relevant query. Title verification preserved relevant queries but accepted unrelated candidates. **Neither cutoff is enabled in the application.** See the [relevance decision](../docs/relevance-gate.md) for measurements and limitations.

With the model, database and indexed data from the original experiment ready, run from the project root:

```powershell
.\scripts\setup-postgres.ps1
.\.venv\Scripts\python.exe .\experiments\evaluate_relevance.py
.\.venv\Scripts\python.exe .\experiments\evaluate_title_relevance.py
```

Each experiment runs independently of the other's report, reads the database without changing data and regenerates its own reports: [full-document review](../results/relevance-review.md), [title review](../results/title-relevance-review.md). Neither re-downloads weights or re-indexes opportunities.

## Joint request/activity verification

A local CrossEncoder now reads each request together with source-backed opportunity title and activity excerpts. Across 70 distinct queries, 16 calibrate the policy, 32 are previously viewed diagnostics and 22 are fresh tests against eight candidates. The fresh test retained 15/16 relevant candidates with no false additions, but missed every result for one positive query. It is not enabled in the API. See [measurements, latency and decision](../docs/joint-relevance.md).

```powershell
.\scripts\download-reranker.ps1
.\.venv\Scripts\python.exe .\experiments\evaluate_joint_relevance.py --check-inputs
.\.venv\Scripts\python.exe .\experiments\evaluate_joint_relevance.py
```

The separate checkpoint download is about 2.3 GB; subsequent inference is offline using existing dependencies. This experiment reads source files directly and needs no running PostgreSQL instance. Outputs: [review](../results/joint-relevance-review.md), [full measurements](../results/joint-relevance-report.json).

## Expanded calibration and separate evaluation

The expanded round defines 45 calibration queries across 12 candidates and 11 topics, followed by 42 held-out queries across 16 candidates and 15 topics. Four topics are excluded from calibration inference. Previous queries remain diagnostic; old and new policies use the same fresh scores. See the [protocol and limits](../docs/expanded-calibration.md).

The completed round retained 30/32 relevant candidates under both policies, but the new one accepted two false additions versus one previously. It was rejected for activation. [Measured review](../results/relevance-expanded-v1-review.md).

```powershell
.\.venv\Scripts\python.exe .\experiments\evaluate_expanded_relevance.py --phase check-inputs
.\.venv\Scripts\python.exe .\experiments\evaluate_expanded_relevance.py --phase calibrate
.\.venv\Scripts\python.exe .\experiments\evaluate_expanded_relevance.py --phase evaluate
```

Calibration freezes the policy and input fingerprints before evaluation. Evaluation rejects changed policies or inputs. Existing artifacts are preserved; a `--run-id` identifies a round but does not make a previously viewed test fresh. No model download or database modification is needed.

## Explicit tool/activity checks

A bounded rule layer preserves tool names, explicit activities and supported AND/OR scope, then checks source excerpts. It vetoes unsupported matches and never promotes low scores based on keywords. See [coverage and design](../docs/request-requirements.md).

```powershell
.\.venv\Scripts\python.exe .\experiments\evaluate_request_requirements.py --phase diagnostic
.\.venv\Scripts\python.exe .\experiments\evaluate_request_requirements.py --phase check-inputs
.\.venv\Scripts\python.exe .\experiments\evaluate_request_requirements.py --phase evaluate
```

Diagnostics reuse prior scores without model inference. Evaluation freezes rules and cases before comparing both decisions on identical scores. Ambiguous request cases are measured separately from search precision/recall. No new model download or recalibration is required.

The first 32-case round is complete and preserved: 28 search cases retained 20/24 true candidates and removed the single false addition; four review cases abstained. Parser defects led to a failed 11/12 component confirmation, then a fresh 8/8 confirmation for rules v1.2. Rules v1.3 additionally passed six fresh cases after enforcing negation word boundaries. These 26 component cases do not add neural evaluations. Current replay over 185 previously scored search requests retains 130/141 true candidates and removes three false additions, with no accepted true candidate lost. Semantic misses remain unresolved; the guard is outside the API.

See the [first held-out review](../results/request-requirements-review.md), [failed v1.1 confirmation](../results/request-requirements-confirmation-review.md) [v1.2 confirmation](../results/request-requirements-confirmation-v12-review.md) and [current v1.3 confirmation](../results/request-requirements-confirmation-v13-review.md). Completed runs reject overwrites. The component runner is `confirm_request_requirements.py --version v13` with `PYTHONPATH=backend;experiments`; prior test requests are diagnostics after fixes.

## Structured constraint cases

The [structured-constraint policy](../docs/constraint-policy.md) is checked against 25 prewritten cases: four on the prepared sample and 21 explicitly synthetic cases. All passed; no model inference, database write or public contract change occurred. [Decisions and evidence](../results/constraint-check-v1-review.md) preserve unknown and conflicting source facts. Eligibility, request-plan resolution and live registration remain outside this component.

`evaluate_constraints.py` creates a sealed report and refuses to overwrite a completed round. Repeat verification without touching reports using the experiment unit-test command below. The existing CI command includes `test_constraint_cases.py`; eight experiment tests pass locally, including 25 labelled subcases. Remote CI was not run for these changes.

## Eligibility and question impact

[Bounded eligibility checks](../docs/eligibility-policy.md) passed 28 labelled cases (four source-sample, 24 synthetic), and question selection passed 10 scenarios with simulated upstream gates. This measures deterministic rules, not general requirement interpretation or an integrated recommendation journey. The four source records remain uncertain because their eligibility facts are incomplete. No model, database or HTTP call occurred.

[Review and limitations](../results/eligibility-check-v1-review.md) preserve the results. `evaluate_eligibility.py` refuses to replace a completed round; `test_eligibility_cases.py` repeats verification without writing reports. The existing CI test discovery now covers 10 experiment tests locally, including both eligibility and question groups. Remote CI was not run.

## Request plan and conflicts

The [bounded request-plan reader and resolver](../docs/request-plan.md) passed 30 prewritten cases. A later composition test exposed removal of tool OR from the semantic query; the original report was preserved and v1.1 fixes the transfer. The [current report](../results/request-plan-v1.1-review.md) replays the same 30 known cases, not a fresh benchmark or new model inference.

The runner `evaluate_request_plan.py --run-id request-plan-v1.1` preserves completed reports. `test_request_plan_cases.py` repeats verification without report writes; 11 experiment tests now pass locally. General model interpretation, retrieval/API integration and production readiness remain open.

## Inspect individual parts

| File | Responsibility |
|---|---|
| [local_retrieval.py](local_retrieval.py) | Validate excerpts, encode, store, search and measure |
| [model_integrity.py](model_integrity.py) | Verify checkpoint identity and recover a valid cached file |
| [check_database.py](check_database.py) | Exercise vector SQL and evidence relationships using synthetic vectors, then roll back |
| [test_model_integrity.py](test_model_integrity.py) | Cover stale pointers and reject corrupt cached weights |
| [review_results.py](review_results.py) | Turn the completed numeric report into a readable review |
| [evaluate_relevance.py](evaluate_relevance.py) | Calibrate a full-document cutoff, then evaluate separate queries |
| [evaluate_title_relevance.py](evaluate_title_relevance.py) | Measure title verification with a fresh confirmation set |
| [evaluate_joint_relevance.py](evaluate_joint_relevance.py) | Calibrate the joint verifier and evaluate fresh queries and candidates |
| [local_reranker.py](local_reranker.py) | Run a local CrossEncoder with verified weights and a token limit |
| [evaluate_expanded_relevance.py](evaluate_expanded_relevance.py) | Separate policy freezing from held-out comparison and diagnostic replay |
| [calibration_protocol.py](calibration_protocol.py) | Check query overlap, candidate scope and frozen-policy bindings |
| [test_calibration_protocol.py](test_calibration_protocol.py) | Cover leakage and changed policy or evaluation inputs |
| [evaluate_request_requirements.py](evaluate_request_requirements.py) | Measure requirement extraction, match vetoes and complex-request review |

Run a topic-only query after the environment and checkpoint are ready:

```powershell
.\.venv\Scripts\python.exe .\experiments\local_retrieval.py --query "ورشة ترجمة المحتوى التعليمي"
```

Check the database independently of the model:

```powershell
.\.venv\Scripts\python.exe .\experiments\check_database.py
```

That check uses synthetic vectors and reverses its writes. It tests storage behaviour, not Arabic understanding or embedding quality.

Stop the project database when needed:

```powershell
.\scripts\stop-postgres.ps1
```

---

**Next: [connect retrieval to the backend workflow](../backend/README.md).**
