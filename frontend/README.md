![SAAI](readme-header.png)

**English** | [العربية](README.ar.md)

# Frontend

React, TypeScript and Vite collect the profile, constraints and query, call the backend and display recommendations, missing information, conflicts and opportunity details.

```powershell
# From the project root
npm --prefix frontend run dev
```

Open [127.0.0.1:5173](http://127.0.0.1:5173). Configure the backend origin in local `frontend/.env` using [.env.example](.env.example). Its port must match `backend/run.ps1 -Port ...`. Keep API keys in the backend only.

| File | Responsibility |
|---|---|
| `src/App.tsx` | Coordinates profile and search state |
| `src/api/client.ts` | Requests and response validation |
| `src/types.ts` | API contract types |
| `src/profile/` | Profile editor, allowed choices and browser-local persistence |
| `src/opportunities/` | Search, recommendations and evidence-backed details |
| `src/labels.ts` | Arabic labels and formatting |
| `vite.config.ts` | Local server and API proxy |

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

The interface presents the backend's real answers. Its contracts are paired with [backend schemas](../backend/app/schemas.py). End-to-end quality and traces are in [evals](../evals/README.md).
