![SAAI — Learn AI by building](../docs/assets/saai-header.png)

**English** | [العربية](README.ar.md)

# Backend — API and workflow

**Previous:** [Experiments](../experiments/README.md) · **Overview:** [FURSAH](../README.md) · **Next:** [Frontend](../frontend/README.md)

FastAPI defines FURSAH's HTTP boundary: request validation, response contracts and controlled errors. The frontend reaches this service, while discovery, details and the connection to the local retrieval experiment remain pending.

## Start from the workspace

From the project root, use the shared Python environment and setup scripts:

```powershell
.\scripts\setup-fullstack.ps1
.\scripts\start-backend.ps1
```

The [main guide](../README.md#start) shows how to start the frontend in a second terminal.

## Alternative standalone setup

Use Python 3.11+ from `fursah-fullstack/backend/`:

First check that `python3` is version 3.11 or newer. If it is older, select a suitable interpreter such as `python3.12` and use it to create the environment. On Windows, use `py -3.12 --version` then `py -3.12 -m venv .venv` if that version is installed.

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

On Windows use `py -m venv .venv`, `.venv\Scripts\Activate.ps1`, and `Copy-Item .env.example .env`. Copy the environment template only if `.env` does not already exist. Open [API docs](http://localhost:8000/docs).

Base dependencies are sufficient to start the shell. Add only the SDK/framework dependencies your design needs; LangChain, LangGraph, PydanticAI and other choices are all optional. No framework whitelist is enforced. No provider connection is made during startup.

## What should happen before implementation?

| Endpoint | Expected starter state |
|---|---|
| `GET /health` | 200: the API process is running. |
| `GET /ready` | 503: storage/application readiness is unfinished. |
| `POST /api/v1/discover` with a valid request | 503 with `FURSAH_NOT_IMPLEMENTED`. |
| `GET /api/v1/opportunities/{id}` | 503 with `FURSAH_NOT_IMPLEMENTED`. |
| Invalid discovery request | 422 with `FURSAH_REQUEST_VALIDATION_ERROR`. |

These errors are intentional until you connect your implementation. Begin with one path from raw evidence to an API response, then expand it.

## What is fixed?

`app/schemas.py` defines the public request/response models used by the frontend. `main.py` and `routes.py` provide HTTP plumbing. Keep endpoint URLs, response meanings and types compatible. `internal.py` contains optional type examples, not a required database schema or agent state.

| Optional starting point | Input and responsibility | Output |
|---|---|---|
| `repository.py` | Your storage, search criteria or opportunity ID | Internal evidence or public details |
| `agent.py` | Your context, client configuration and prompts | Your internal result |
| `tools.py` | Your tool arguments and application dependencies | Your observations/evidence |
| `validation.py` | Proposed results and evidence | Your checked outcome |
| `workflow.py:discover` | Public request and dependencies | `DiscoveryResponse` |
| `internal.py` | Your schema design | Replaceable internal models |
| `../data/data_exploration_and_preparation.ipynb` | Raw announcements | Your preparation process and storage |

You may combine, split, rename or replace learner modules. These are suggested locations, **not a mandatory pipeline**. Reconnect `routes.py` and dependency wiring if your entry points move. Do not fill unfinished endpoints with fake successful recommendations.

## First working integration

1. Finish the notebook sample and extend its source observations with the application facts you need.
2. Read your chosen storage in `repository.py`. Implement `get_details(id)` to return `OpportunityDetailsResponse` for a real record, or `None` when the ID is absent.
3. Try that ID through `/docs`. Use actual source evidence; the illustrative examples below are not records to serve.
4. Connect `discover(request, deps)` to your retrieval and decision logic. An LLM does not automatically gain access to your dataset: your code must supply retrieved evidence or tools that access it.
5. Map the result to `DiscoveryResponse`, then try the same request through the frontend. Make readiness reflect the components you have implemented.

Your internal records do not need to look like the response JSON. The repository/workflow boundary is where you adapt them. You may choose ordinary retrieval followed by model selection, an agent with tools, or another design.

### Constraints and evidence: two examples

- Saved city is Riyadh; the query says “Jeddah this time.” After resolving that request, pass the **same resolved constraints to filtering and ranking**. Preserve the saved preferences. An unresolved city disagreement should return `needs_info` with `constraint_conflict: true` and `constraints.location_preference`.
- A source says “Python knowledge required.” Keep that requirement visible; do not add an age or study-year condition. Ask for missing skills only when needed for the decision. Request a skill level only if a sourced requirement actually needs it. Unsupported eligibility remains uncertain.

## Storage and readiness

`DatasetLoader` is an optional CSV/JSON helper. `data/prepared/opportunities.json` is only an example for teams choosing JSON; it is not required by startup or readiness. Other stores can bypass that helper entirely.

Implement these replaceable hooks:

- `repository.is_ready()`: check that your actual store is accessible and contains the information your implementation needs.
- `workflow.application_is_ready(deps)`: check that your application components and configuration are usable, including your model client if required.

Both return actual booleans. `/ready` returns 200 only when both return `True`; unfinished, failed or false checks return 503 with safe explanations. Do not return `True` unconditionally. Readiness is operational, not proof that your recommendations are correct. Keep probes bounded and avoid billable model calls on every health request.

### Startup and cleanup

Your application may open stores and reusable asynchronous clients during startup/lifespan and close them during shutdown. Handle requests within the lifecycle those resources support. Avoid unnecessary connections for every step, and do not use closed resources.

## Configuration and model initialization

`.env.example` provides optional model fields and runtime settings. Initialize your chosen client wherever your design requires; `agent.py` is a suggested location. `deps.model_config` is an optional convenience for API-key providers or explicitly enabled loopback clients. Replace it for other authentication methods. It does not gate shell startup or readiness. Never put credentials in frontend code, source records or logs.

`FURSAH_FRAMEWORK_TRACK` is an optional descriptive label, not a switch that implements a framework. `FURSAH_DATA_DIR` locates raw files and optional JSON helpers, relative to `fursah-fullstack/`. `FURSAH_ALLOWED_ORIGINS` controls frontend origins. Model/workflow budgets are settings for learner code to enforce, not automatic orchestration.

## Evaluation-time policy

Leave `FURSAH_EVALUATION_TIME` blank for actual request time. For this classroom, the organizer selected **18 October 2026**. The setting below retains noon in Asia/Riyadh:

```dotenv
FURSAH_EVALUATION_TIME=2026-10-18T12:00:00+03:00
```

Set this value in your local or deployed exercise environment only; the blank default remains actual time. Restart after changing settings. The route captures one `deps.evaluation_time` per discovery request; reuse that value across your tools and decisions. Naive dates/times without an offset are rejected. Dataset timestamps stay unchanged. Only compare exact deadlines when the source supplies sufficient date/time/timezone information; reaching the exact cutoff means expired. Incomplete facts remain uncertain.

See the [data exercise](../data/README.md) for expired deadlines and uncertain cases. Keep source dates unchanged.

## Public contract examples

These illustrate shapes only; they are not dataset answers or ranking/eligibility solutions. Full defaults and required fields are shown in `/docs` and `app/schemas.py`.

**Discovery request:** `POST /api/v1/discover`

```json
{"request_id":"example-1","query":"أبحث عن ورشة","profile":{"interests":[],"skills":null},"constraints":{}}
```

**Example HTTP 200 missing-information response:**

```json
{"request_id":"example-1","status":"needs_info","message":"هل لديك معرفة Python المطلوبة في الإعلان؟","recommendations":[],"missing_fields":["profile.skills"]}
```

**Example HTTP 200 result shape:** the content below is illustrative only.

```json
{"request_id":"example-1","status":"ok","message":"مثال لتنسيق الاستجابة فقط","recommendations":[{"opportunity_id":"EXAMPLE","title":"عنوان توضيحي","eligibility_status":"uncertain","reason":"نص توضيحي وليس قرار أهلية","source_ids":["EXAMPLE-SOURCE"]}],"missing_fields":[]}
```

**Example HTTP 200 with no supported match:**

```json
{"request_id":"example-1","status":"no_match","message":"لم نجد فرصة تدعم الأدلة مطابقتها لطلبك","recommendations":[],"missing_fields":[]}
```

`needs_info` is appropriate when an answer from the user can resolve a relevant missing fact; it is not a substitute for provider failures or every unknown source fact. The example above asks about skills because a hypothetical source requires Python, not because all searches require skills.

**Details request:** `GET /api/v1/opportunities/EXAMPLE` (no body).

**Example HTTP 200 details shape:**

```json
{"opportunity_id":"EXAMPLE","title":"عنوان توضيحي","source_ids":["EXAMPLE-SOURCE"],"topics":[],"required_skills":null,"eligibility_requirements":{"mandatory":null,"preferred":null},"data_warnings":[]}
```

Until implemented, discovery returns HTTP 503:

```json
{"request_id":"example-1","status":"error","message":"The FURSAH discovery workflow is intentionally unfinished in the starter.","recommendations":[],"missing_fields":[],"error_code":"FURSAH_NOT_IMPLEMENTED"}
```

Details use the generic error shape, also HTTP 503 while unfinished:

```json
{"request_id":"example-1","error_code":"FURSAH_NOT_IMPLEMENTED","message":"The details implementation is unfinished.","details":[]}
```

Messages and generated request IDs may differ. Invalid request bodies return HTTP 422 with `FURSAH_REQUEST_VALIDATION_ERROR`. A completed repository returns 404 for a missing opportunity.

## Validate meaning as well as model output

Schema-valid JSON does not prove that the model understood the query. If the user requests Jeddah and the model omits it, a response can be structurally valid but semantically wrong. Check explicit constraints before filtering and ranking, and return readable interpreted filters. Account for negation and alternatives; do not apply a substring rule as a universal Arabic parser.

Verify selected IDs belong to the candidates, evidence belongs to those records, and quoted text matches its source. On failure, you may give targeted feedback and retry within a defined limit; after that, return a controlled error. Never accept unsupported output merely to avoid an error. When asking about missing skills, explain which skills are required and why, without requesting fields the form does not collect.

Match client code to the installed SDK and pin dependencies you have verified in your implementation. Quote package extras in shell commands, such as `'package[extra]'`. Measure retrieval and model time separately, with bounded retries and a total execution timeout.

## Important contract meanings

Skills `null` means unanswered; `[]` means explicitly none. Do not request profile fields the interface does not collect. Eligibility is distinct from registration status. Mandatory and preferred requirements are nullable lists of source-supported statements. Duration is a positive whole number of days or null; hours and sessions are separate facts.

`evidence_version` optionally identifies the source facts behind a recommendation or details response. Your implementation must change it when relevant evidence changes. The frontend retains an earlier eligibility confirmation only when source IDs, nonempty evidence versions and displayed facts agree. Missing versions remain API-valid but cannot preserve confirmation in the details panel. Delivery mode and physical attendance are distinct facts; conflicting facts produce uncertainty.

## Troubleshooting

| Symptom | Check next |
|---|---|
| `/health` cannot be reached | Start uvicorn from `backend/`; check the port and selected Python environment. |
| `FURSAH_NOT_IMPLEMENTED` | Follow the named learner entry point; this is expected before implementation. |
| Details cannot find your prepared records | Check your export/store path and repository mapping. Saving notebook outputs does not connect storage. |
| Provider authentication fails | Check your chosen provider, base URL, model name and authentication method in backend settings. Never expose credentials in the browser. |
| Model output fails validation | Compare it with your internal output type, then map to the public response contract. |
| Search takes too long | Measure retrieval and model stages separately; reuse suitable clients and enforce bounded retries and timeouts. |

Consult the [registration-status display values](../frontend/README.md#registration-status-display-values) when mapping internal states. A past opening date alone does not prove registration is open now.

## Try your implementation

Use the examples above and `/docs` to understand the API contract. Existing transport and boundary checks are recorded in [fullstack verification](../docs/fullstack-verification.md); complete recommendation behaviour still needs implementation and evaluation.

---

**Next: [Frontend](../frontend/README.md).**
