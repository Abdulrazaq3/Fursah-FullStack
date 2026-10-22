![SAAI](../frontend/readme-header.png)

**English** | [العربية](README.ar.md)

# Backend

FastAPI and Pydantic expose discovery and opportunity details. `app/catalog_workflow.py` runs Gemini understanding, local vector retrieval, BGE reranking and deterministic evidence, constraint and eligibility checks.

```powershell
# From the project root
.\backend\run.ps1 -Port 8019
```

| Location | Responsibility |
|---|---|
| `app/routes.py`, `app/schemas.py` | Routes and contracts |
| `app/catalog_workflow.py` | Full-catalog request journey |
| `app/active_understanding.py` | Checked Gemini request proposal |
| `app/catalog_store.py`, `migrations/` | Catalog storage and vector retrieval |
| `app/infrastructure/config.py` | Runtime settings loaded from `backend/.env` |
| `app/infrastructure/models/` | Local BGE model adapters |
| [app/instrumentation/](app/instrumentation/README.md) | Spans and Phoenix export |
| `scripts/` | Model downloads, database setup/stop and catalog preparation |
| [../evals/](../evals/README.md) | All evaluation and regression checks |

## Setup and maintenance

`setup.ps1` installs base API dependencies. Optional `-Models`, `-Evals` and `-Frontend` also prepare model/data dependencies, Phoenix tooling and frontend dependencies. See the [root setup order](../README.md).

```powershell
.\backend\setup.ps1 -Models -Evals -Frontend
.\backend\scripts\setup-postgres.ps1
.\.venv\Scripts\python.exe backend/scripts/download-model.py --check-only
```

The five operational scripts are required to reproduce the local workspace: two model downloaders, database setup/stop and `prepare-catalog.py`. Preparation supports `--publish`, `--reuse-prepared`, `--withdraw` and `--rollback`; see [data](../data/README.md).

Use [.env.example](.env.example) to create local settings only if missing. Store the OpenRouter key in `.env`. `/health` checks liveness; `/ready` preserves the quality/deployment approval gate.
