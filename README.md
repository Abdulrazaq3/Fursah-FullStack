![SAAI — Learn AI by building](frontend/readme-header.png)

**English** | [العربية](README.ar.md)

# FURSAH — فرصة

An opportunity recommendation app over a local catalog of **913 opportunities**: the 1,000 supplied announcements grouped into 900 opportunities, plus 13 saved additions.

React → FastAPI → Gemini request understanding → BGE-M3 embeddings → PostgreSQL/pgvector → BGE reranking → source, constraint and eligibility checks. Requests search the saved catalog; they do not fetch opportunities from external sites.

## Run the existing workspace

Open **PowerShell** in this folder. Start the API and interface in separate terminals:

```powershell
.\backend\run.ps1 -Port 8019
```

```powershell
npm --prefix frontend run dev
```

Interface: [127.0.0.1:5173](http://127.0.0.1:5173). API: [127.0.0.1:8019/docs](http://127.0.0.1:8019/docs). The frontend's local API target must match the backend port. Existing `.env` files, database and model cache stay in place.

## Evaluation in Phoenix

Start at [instrumentation](backend/app/instrumentation/README.md), run the eval, then inspect **fursah-eval** in Phoenix:

```powershell
.\evals\run.ps1 -Demo -Open
```

The demo selects three cases. For all twelve development cases:

```powershell
.\evals\run.ps1 -Label full-dev -Open
```

Open saved traces without rerunning models: `.\evals\phoenix.ps1 -Open`. Regression checks: `.\evals\test.ps1`. See the [eval guide](evals/README.md).

## First setup on another machine

Windows prerequisites: Python 3.11, Node.js 22, PostgreSQL 18 and Visual Studio C++ build tools for the local pgvector build.

```powershell
.\backend\setup.ps1 -Models -Evals -Frontend
.\backend\scripts\setup-postgres.ps1
.\.venv\Scripts\python.exe backend/scripts/download-model.py
.\.venv\Scripts\python.exe backend/scripts/download-reranker.py
.\.venv\Scripts\python.exe backend/scripts/prepare-catalog.py --publish
```

Create `backend/.env` from its example if it does not already exist. Add the OpenRouter key there; use `FURSAH_CATALOG_MODE=prepared` and `FURSAH_UNDERSTANDING_MODE=active`. Never commit keys. See [backend](backend/README.md) and [data](data/README.md).

## Project map

| Folder | Purpose |
|---|---|
| [frontend/](frontend/README.md) | Interface and API client |
| [backend/](backend/README.md) | API, workflow, settings, model adapters and operational scripts |
| [data/](data/README.md) | Raw sources, preparation helpers and saved catalog |
| [evals/](evals/README.md) | Cases, graders, tests, run outputs, Phoenix and historical evaluation evidence |
| `.local/` | Ignored local database, models, Phoenix state and cleanup backup |

Settings used at runtime live in `backend/app/infrastructure/config.py` and `backend/.env`. Docker definitions remain in the root.

## Current status

Local integration is working. The original full development baseline passed **7/12** after independent source checks; the three-case demo reveals the known closed-registration failure. [Baseline report](evals/archive/reports/catalog-eval-baseline-v1-review.md).

The next work is source availability, unrelated-result abstention, broader development coverage, latency and deployment validation. The independent six-case holdout remains sealed. `/ready` remains 503 until production approval; the current demo is not production approval.
