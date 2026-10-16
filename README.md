![SAAI — Learn AI by building](docs/assets/saai-header.png)

**English** | [العربية](README.ar.md)

# FURSAH — فرصة

An opportunity recommendation application that connects a person's profile, interests and constraints with source-supported opportunities. This workspace brings together the frontend, API, data, experiments and the decisions behind the system.

**Current milestone:** local semantic retrieval works on a small documented sample. The frontend reaches the API; the recommendation workflow and details implementation are still pending.

[Start locally](#start) · [Guides](#guides) · [Project map](#map) · [Current status](#status)

---

<a id="start"></a>
## Start locally

Run these commands from `fursah-fullstack/`. The supplied scripts use Windows PowerShell, Python 3.11 and Node.js 22 with npm.

**1. Prepare the frontend and API dependencies**

```powershell
.\scripts\setup-fullstack.ps1
```

**2. Start the API in one terminal**

```powershell
.\scripts\start-backend.ps1
```

**3. Start the interface in a second terminal**

```powershell
.\scripts\start-frontend.ps1
```

| Open | Address | What to expect |
|---|---|---|
| Interface | [127.0.0.1:5173](http://127.0.0.1:5173) | Profile, constraints and search form |
| API documentation | [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | Request and response contracts |
| Liveness | [127.0.0.1:8000/health](http://127.0.0.1:8000/health) | HTTP 200 |
| Application readiness | [127.0.0.1:8000/ready](http://127.0.0.1:8000/ready) | HTTP 503 until storage and workflow integration are complete |

Stop either server with **Ctrl+C**. This setup does not download a model or start the retrieval database. A search currently returns `FURSAH_NOT_IMPLEMENTED`; the frontend displays that state.

<a id="guides"></a>
## Follow the project

| Step | Guide | What it explains |
|---|---|---|
| 1. Understand the design | [Design and decisions](docs/README.md) | Responsibilities, data contracts and build notes |
| 2. Understand the evidence | [Data](data/README.md) | Raw announcements, original sources and preparation |
| 3. Inspect retrieval | [Experiments](experiments/README.md) | Local embeddings, vector search and measured results |
| 4. Connect the application | [Backend](backend/README.md) | API contracts, storage access and the pending workflow |
| 5. Use the interface | [Frontend](frontend/README.md) | User input, HTTP requests and displayed states |
| 6. Operate the workspace | [Scripts](scripts/README.md) | Setup, execution, checks and container commands |

<a id="map"></a>
## Project map

```text
fursah-fullstack/
├── README.md / README.ar.md
├── frontend/                 # React interface and HTTP client
├── backend/                  # FastAPI service, contracts and tests
├── data/                     # Raw announcements and preparation notebooks
├── experiments/              # Independent retrieval experiment
├── examples/                 # Hand-prepared records and evaluation queries
├── results/                  # Measured reports and verification evidence
├── docs/                     # Design, decisions and documentation assets
├── scripts/                  # Setup and execution commands
├── .github/workflows/        # CI definitions
├── compose.yaml              # Frontend and API containers
└── .local/                   # Local models and database files; excluded from Git
```

See [project structure](docs/project-structure.md) for boundaries and deployment preparation. Experiments remain separate from the API until their logic is integrated into the application.

<a id="status"></a>
## Current status

Last reviewed: **16 October 2026**.

| Area | Status | Evidence or next task |
|---|---|---|
| Frontend and API transport | Verified locally | [Fullstack verification](docs/fullstack-verification.md) |
| Raw evidence | 1,000 fictional announcements available | [Data guide](data/README.md) |
| Local retrieval | Completed on four opportunities and eight queries | [Measured review](results/retrieval-review.md) |
| Requests outside sample topics | Nearest neighbours still returned | Expand evaluation and implement relevance/abstention handling |
| Constraints and eligibility | Designed; application integration pending | [Data model](docs/data-model.md) and [tool design](docs/agent-tools.md) |
| Discovery and details API | Contract available; implementation pending | [Backend guide](backend/README.md) |
| Container deployment | Definitions prepared; not tested on this device | Docker is not installed locally; CI includes container checks |

The first retrieval experiment reached **Recall@2 = 100% on six in-scope development queries**. The other two queries have no relevant opportunity in the sample. This does not establish full-corpus quality or production readiness.

## Main components

| Responsibility | Current choice |
|---|---|
| Interface | React, TypeScript and Vite |
| HTTP API and validation | FastAPI and Pydantic |
| Local embeddings experiment | BGE-M3 through SentenceTransformers; dense, 1024 dimensions |
| Experiment storage and search | PostgreSQL with pgvector; exact cosine search |
| Deployment definitions | Separate frontend/API images, nginx and Docker Compose |

The reasoning model and orchestration framework remain decisions for application implementation.

## Continue building

We are in **stage 8: build, evaluate and improve** of the [build notes](fursah-ai-build-notes.md). Next, expand relevance evaluation, address unrelated results and connect constraints, evidence, registration and eligibility checks to the API workflow.

**Next: [design and decisions](docs/README.md).**
