![SAAI — Learn AI by building](../docs/assets/saai-header.png)

**English** | [العربية](README.ar.md)

# Frontend — interface and API connection

**Previous:** [Backend](../backend/README.md) · **Overview:** [FURSAH](../README.md) · **Next:** [Scripts](../scripts/README.md)

The React and TypeScript interface collects profile information, constraints and a free-text request, then displays the API response. Its connection to the local API has been verified; the recommendation workflow remains pending in the backend.

## 1. Start the interface

Keep the backend running. Open a second terminal in `fursah-fullstack/frontend/`:

```bash
npm ci
cp .env.example .env
npm run dev
```

On Windows PowerShell, use `Copy-Item .env.example .env`. Copy the template only when first creating your local settings.

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The server uses this fixed port; stop a conflicting process or deliberately update the port and backend allowed origins.

Your `.env` should contain:

```dotenv
VITE_API_BASE_URL=
FURSAH_DEV_API_TARGET=http://127.0.0.1:8000
```

Blank `VITE_API_BASE_URL` uses the frontend origin. Vite proxies API requests during development; nginx does so in the container build. For a separately hosted backend, set its absolute origin only, without `/api`, and configure backend CORS. Restart Vite after changing `.env`.

## 2. Understand what the interface does

1. The user selects profile information and constraints.
2. The frontend validates choices and saves the profile in this browser's local storage.
3. The user enters a free-text search.
4. `api/client.ts` sends the request to the backend.
5. The interface displays loading, results, missing information, no matches or an error.
6. Opening a card requests that opportunity's details from the backend.

There is no mock-data fallback. `FURSAH_NOT_IMPLEMENTED` is expected until the backend exercise is implemented.

Editing the query or saving the profile invalidates old results and pending searches. A conflict-resolution button from an earlier search therefore cannot act on a new query. With inputs unchanged, resolving a conflict resubmits the same query, profile and constraints with the selected resolution.

## 3. Find the relevant files

| File | Responsibility |
|---|---|
| `src/main.tsx` | Mounts React and loads styles. |
| `src/App.tsx` | Coordinates profiles, searches, results and panels; aborts obsolete browser searches. |
| `src/types.ts` | TypeScript request and response structures matching the backend contract. |
| `src/api/client.ts` | HTTP requests, timeouts, input checks and response validation. |
| `src/labels.ts` | Arabic labels and formatting for dates, deadlines, costs and errors. |
| `src/styles.css` | Layout, colours, spacing and responsive styling. |
| `src/profile/choices.ts` | Frontend-only city, major, interest and skill lists. Displayed values are submitted unchanged. |
| `src/profile/profile.ts` | Profile loading, recovery, saving, draft conversion and validation. |
| `src/profile/ProfileChoices.tsx` | Dropdowns and searchable single/multiple selections. |
| `src/profile/ProfilePanel.tsx` | Profile summary and editor. |
| `src/opportunities/SearchForm.tsx` | Query input and search submission. |
| `src/opportunities/SearchResults.tsx` | Renders the current search outcome. |
| `src/opportunities/OpportunityCard.tsx` | One recommendation summary and eligibility badge. |
| `src/opportunities/OpportunityDetails.tsx` | Loads and displays details, requirements and sources. |
| `src/components/Header.tsx` | Branding and the profile button. |
| `src/components/Drawer.tsx` | Shared side panel, keyboard focus handling and closing behaviour. |
| `src/vite-env.d.ts` | TypeScript declarations for Vite environment settings. |

Supporting files:

| File | Purpose |
|---|---|
| `package.json` | Dependencies and development/build commands. |
| `package-lock.json` | Exact dependency resolution for repeatable installation; keep it. |
| `tsconfig.json` | TypeScript checking configuration. |
| `vite.config.ts` | React plugin and local server settings. |
| `index.html` | Browser entry page and font links. |
| `.env.example` | Safe template for the backend origin. |

`node_modules/` is installed dependencies and `dist/` is generated build output. Neither is a source folder to edit or commit. Fonts and branding may use external assets; API data still comes only from your configured backend.

## 4. Follow the form rules

- Cities, majors, interests and skills are selected from `choices.ts`. Typing searches the choices; it does not create new values.
- Descriptions remain free text. Do not send model credentials from the browser.
- Preferred cities are an array or `null`, not one string.
- Unknown skills, explicitly no skills and listed skills are separate states. The summary shows “لم تُحدّد بعد” for unknown and “لا توجد — حسب اختيارك” for explicitly none.
- Missing-field paths, including indexed skill names/levels, use readable Arabic labels. Unknown paths receive a generic prompt rather than raw technical text.
- Duration limits must be positive whole days. Budget limits may contain decimals but cannot be negative.
- Invalid saved fields are corrected independently where possible, retaining valid information and showing a notice. Old single-city preferences are converted into arrays.

These list restrictions belong to the frontend. Direct API callers can submit other string values; backend learner code must handle unmatched values sensibly instead of crashing or inventing a substitute.

## 5. Keep both sides compatible

Read [backend/app/schemas.py](../backend/app/schemas.py) alongside [src/types.ts](src/types.ts). These are the supplied integration contract; keep them compatible while changing your internal implementation. Public contract changes require organizer coordination.

The response must distinguish:

- Search outcome: `ok`, `needs_info`, `no_match`, `error`.
- Registration status: what the source says about applications.
- Eligibility: `confirmed` or `uncertain`, supported by the available facts.

Details expect a positive integer-or-null duration and eligibility statements grouped under `mandatory` and `preferred`. Recommendations and details require source IDs. Date-only deadlines are shown without inventing a cutoff time; fully specified instants are displayed in Asia/Riyadh.

If current details cannot be loaded, the interface marks the earlier recommendation information as unverified. The backend remains responsible for keeping recommendation facts and detail facts consistent.

### What each search state means

| State | What the user sees | Backend responsibility |
|---|---|---|
| Loading | A search is in progress. | Finish within your configured budget or return a controlled error. |
| `ok` | One to three recommendation cards. | Supply real IDs, supporting source IDs and honest eligibility. |
| `needs_info` | A request to clarify editable profile fields or a constraint conflict. | Name relevant fields; do not request fields the form does not collect. |
| `no_match` | A clear message without cards. | Use when no supported result meets the request. |
| `error` | An error message. | Include the error code; unfinished backend is not an empty successful search. |

Copy an example from the [backend contract guide](../backend/README.md#public-contract-examples) into `/docs` to understand the format. Then connect real data; do not return the example as a fake recommendation.

### Registration-status display values

`application_status` is an optional string, not an enum prescribing your internal storage schema. These known values have Arabic frontend labels:

| API value | Display |
|---|---|
| `open` | مفتوح |
| `closed` | مغلق |
| `cancelled` | ملغى |
| `not_yet_open` | لم يبدأ التسجيل |
| `requires_verification` | يتطلب تحققًا |
| `unknown` or `null` | غير معروف |

The frontend also accepts `not_open_yet` as an alias with the same label. Other values display as supplied, with underscores replaced by spaces; map your internal states deliberately at the API boundary. These are distinct from search outcomes `ok`, `needs_info`, `no_match` and `error`.

A published “not yet open” statement does not establish current status after its opening date passes. Preserve the source statement and add an explanation, or return `requires_verification` when current status is unknown. Do not assume registration is now open. Keep recommendation and detail facts consistent.

### Evidence versions and attendance

Recommendation and details responses accept `evidence_version`, an optional nonblank string. Generate a deterministic fingerprint from the actual source facts, including requirements and attendance, with stable ordering. Capture the recommendation version from the evidence that was evaluated; never replace it with a later details version. The same source ID can contain changed facts.

The details UI keeps a previous eligibility confirmation only when source IDs and nonempty versions match and displayed facts are unchanged. Missing or changed versions require rechecking; the old reason and next action are withheld. This field is optional so unfinished integrations can run, but cannot preserve confirmation without it.

Location, delivery mode and attendance are separate sourced facts. Online mode alone does not prove attendance is unnecessary. Contradictory flags produce a warning and uncertain eligibility.

## 6. Walk through your connected application

Save a profile, enter a relevant query, inspect the response, then open a recommendation's details. Explain which sources support it and what is still unknown. Missing-information requests should identify fields the user can actually edit.

Useful commands:

```bash
npm run typecheck
npm run build
```

These commands check types and build the interface. The [local transport verification](../docs/fullstack-verification.md) covers the browser/API connection; recommendation quality requires its own end-to-end evaluation after implementation.

| Problem | First check |
|---|---|
| Cannot contact backend | Backend terminal, origin in `.env`, and backend CORS settings. |
| Search is unfinished | Implement the learner backend files; do not add fake frontend results. |
| Invalid response | Compare the returned JSON with the agreed schemas. |
| Slow search | Inspect model/tool execution and backend time limits. |
| A choice is missing | Update `choices.ts` intentionally and document any data mapping implications. |

**Review the [current milestone](../README.md#status) before continuing application integration.**

---

**Next: [Scripts](../scripts/README.md).**
