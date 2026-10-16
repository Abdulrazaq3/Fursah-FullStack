![SAAI — Learn AI by building](../docs/assets/saai-header.png)

**English** | [العربية](README.ar.md)

# Scripts — setup and execution

**Previous:** [Frontend](../frontend/README.md) · **Overview:** [FURSAH](../README.md) · **Next:** [Current milestone](../README.md#status)

Run the commands below from `fursah-fullstack/`. Choose application startup or the independent retrieval experiment; they prepare different dependencies and resources.

## Application commands

| Command | What it does |
|---|---|
| `.\scripts\setup-fullstack.ps1` | Prepare the root Python environment, install API dependencies and run frontend npm ci |
| `.\scripts\start-backend.ps1` | Start FastAPI on 127.0.0.1:8000 |
| `.\scripts\start-backend.ps1 -Reload` | Start with development reload enabled |
| `.\scripts\start-frontend.ps1` | Start Vite on 127.0.0.1:5173 |

Use separate terminals for the API and interface. Stop each server with Ctrl+C. Startup alone does not implement discovery, details or AI orchestration.

## Retrieval commands

| Command | What it does |
|---|---|
| `.\scripts\setup-python.ps1` | Install CPU PyTorch and the verified retrieval dependencies |
| `.\scripts\setup-postgres.ps1` | Prepare and start the isolated PostgreSQL/pgvector runtime on 55432 |
| `.\.venv\Scripts\python.exe .\scripts\download-model.py` | Validate or download the pinned model and record its manifest |
| `.\.venv\Scripts\python.exe .\scripts\download-model.py --check-only` | Validate or recover the local checkpoint without a download |
| `.\scripts\run-retrieval-experiment.ps1` | Prepare, index, evaluate and write the review |
| `.\scripts\stop-postgres.ps1` | Stop only the project database instance |

The database script needs existing PostgreSQL 18 and Visual Studio C++ build tools. See [experiment setup](../experiments/README.md) before using it on another device.

## Checks and builds

Build the frontend:

```powershell
npm --prefix frontend run build
```

Run API boundary checks:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'backend'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

The optional [browser smoke script](smoke-fullstack.cjs) checks frontend-to-API transport and the expected unfinished response. Setup and evidence are in [fullstack verification](../docs/fullstack-verification.md).

## Container definitions

```powershell
docker compose up --build -d
docker compose down
```

Docker is required. The default frontend address is `http://127.0.0.1:8080`; nginx forwards API requests to the backend container. These definitions have not been built on this device. They currently package the frontend and API shell, not the local embedding model or experiment database.

For configuration, use the templates at the [root](../.env.example), [backend](../backend/.env.example) and [frontend](../frontend/.env.example). Do not overwrite an existing local configuration. Container and CI boundaries are explained in [project structure](../docs/project-structure.md).

---

**Next: [review the milestone and choose the next implementation task](../README.md#status).**
