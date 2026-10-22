![SAAI](https://i.imgur.com/YHRhgqv.png)

**English** | [العربية](README.ar.md)

# Frontend — profile, search and evidence

[Overview](../README.md) · [Previous: backend](../backend/README.md) · [Next: evaluation](../evals/README.md)

We retained the starter's **React + TypeScript + Vite** interface and connected it to the implemented API. The browser collects input and displays the backend's answers; it does not run the models or hold their keys.

## What the user sees

Profile → query → loading → recommendations, clarification, no matches or error → opportunity details and evidence.

For example, if a supported eligibility requirement depends on an unanswered profile field, `needs_info` asks the user to complete it. It should not display confirmed eligibility without evidence.

| File | What to read |
|---|---|
| [src/App.tsx](src/App.tsx) | Profile and search state |
| [src/api/client.ts](src/api/client.ts) | HTTP requests and response validation |
| [src/types.ts](src/types.ts) | Shared API shapes |
| [src/profile/](src/profile/) | Profile editor, choices and browser-local persistence |
| [src/opportunities/](src/opportunities/) | Search, recommendation cards and evidence details |
| [src/labels.ts](src/labels.ts) | Arabic labels and formatting |

## Run the interface

From the repository root, install dependencies once and start Vite:

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev
```

Create `frontend/.env.local` from [.env.example](.env.example) if missing. The backend uses port 8000 by default:

```dotenv
FURSAH_DEV_API_TARGET=http://127.0.0.1:8000
VITE_API_BASE_URL=
```

If you choose a different backend port, update `FURSAH_DEV_API_TARGET` to match and restart the frontend. An unreachable proxy target can appear in the browser as HTTP 500.

Open [127.0.0.1:5173](http://127.0.0.1:5173). A blank `VITE_API_BASE_URL` uses Vite's local proxy; for a separately hosted API, set its origin without `/api`.

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

The UI validates input for usability; the [backend contract](../backend/app/schemas.py) still validates incoming requests. A successful build does not establish recommendation quality—use the [evaluation guide](../evals/README.md).
