![SAAI — Learn AI by building](../docs/assets/saai-header.png)

**English** | [العربية](README.ar.md)

# Data — evidence and preparation

**Previous:** [Docs](../docs/README.md) · **Overview:** [FURSAH](../README.md) · **Next:** [Experiments](../experiments/README.md)

Raw announcements are the source of facts and evidence. This folder contains the original training corpus and a [guided notebook](data_exploration_and_preparation.ipynb). Our four-opportunity manual sample lives in [examples](../examples/linked-data.sample.json); full-corpus automated preparation remains ahead.

## Input

`raw/raw_opportunities.csv` contains **1,000 fictional announcements**. Organizations and application destinations are educational examples. Use a CSV parser with `utf-8-sig`; quoted cells can contain commas and newlines.

| Column | Meaning |
|---|---|
| `source_id` | Stable announcement identifier; preserve it. |
| `source_type` | Social post, email, brochure, group message or noticeboard. |
| `source_name` | Publishing source. |
| `published_at` | Publication timestamp with timezone offset; not verification time. |
| `content` | Original announcement text. |

Keep the raw CSV unchanged. Multiple announcements may describe one opportunity; source IDs and opportunity IDs have different meanings.

## Begin with the notebook

Use Python 3.11+ in VS Code with Jupyter support, or install JupyterLab in your virtual environment:

```bash
python -m pip install jupyterlab
jupyter lab
```

Open `data_exploration_and_preparation.ipynb` from `fursah-fullstack/data/` and select the intended Python environment. Adjust `DATA_PATH` if your working directory differs. The core lesson uses **pandas and IPython**; the notebook includes an optional `%pip install pandas ipython` cell with `clear_output()`. These are notebook dependencies, not API requirements.

The guided notebook follows the same ten real announcements through reading, exploration, cleaning, extraction, unknown values, related-source review, deadlines, scaling and saving. **Nine exercises** ask for 1–3 expressions, following explained examples. Replace each `...` before continuing.

The supplied [preparation_helpers.py](preparation_helpers.py) handles repetitive extraction, date processing, batch preparation and JSON saving. Keep it beside the notebook. Students do not need to edit it to complete this lesson: the learning goal is to understand, configure and inspect the supplied workflow. The notebook explains every helper before use, including its limitations. The helpers do not implement discovery, eligibility decisions, automatic source merging or the full learner backend.

Running the completed lesson writes `prepared/lesson_sample.json` and `prepared/source_preparation.json`. These retain source-level rows and original text; they are not a complete opportunity store or API response. Your team still extends fields, reviews source conflicts/updates and connects its chosen storage. No model or API key is needed for the lesson.

Start with about 10 announcements. Demonstrate one path from raw evidence through your storage to the public API. Then prepare the entire corpus; a small sample does not satisfy the final requirement.

## Decide your representation

Your internal schema may differ from the API. Choose how to retain identity, provenance, exact supporting excerpts, dates, locations, requirements, costs, missing facts and unresolved conflicts. Document your choices before scaling.

You may choose JSON, SQLite, a document store, a search index or another suitable design. The notebook demonstrates JSON saving and reloading through supplied helpers; your application may use another storage implementation. `DatasetLoader.load_prepared_opportunities()` supports a nonempty JSON array at `data/prepared/opportunities.json` only if you choose that helper. Your application readiness must check your actual store, not an unused export file.

## From announcements to opportunities

An **announcement** is one source row. An **opportunity** is the activity your application presents; several announcements may describe it. Grouping retains the evidence rather than deleting it.

| Illustrative sources | Interpretation |
|---|---|
| A post and a repost both advertise the same workshop. | Review them as related evidence; retain both source IDs. |
| Original: 20–22 October. Update: “The start moved to 25 October.” | Only the start changed explicitly. The new end and duration are unknown. |
| One source says 100 SAR; another says 150 SAR with no correction explanation. | Preserve both claims and flag the conflict. Do not choose the cheaper one. |
| The same URL appears under different publishers. | The link alone does not establish identity or update authority. Review before merging. |

Embeddings can suggest related text, but similarity does not prove a duplicate or authorize a correction. No embedding model is required for this notebook.

## Connect your export to the application

The lesson exports **source-level observations**, not finished API records. For example, a row can retain `source_id`, `content`, `fee_evidence` and `cost_sar: null`. That null means the helper did not establish a fee; it is not a free opportunity.

Your next milestone is to read your chosen store in `repository.py`, select one real opportunity and map it to the public details response. Keep source IDs and evidence available. The backend does not read notebook cell outputs or execute the notebook. JSON is an example; a database or index is equally valid. See the [backend integration steps](../backend/README.md#first-working-integration).

<a id="mapping"></a>
## Field-mapping worksheet

Complete this for one activity before scaling. Your internal representation is a team decision; these prompts are not a mandatory storage schema or reference answers.

| Original evidence | Your internal decision | At the API boundary |
|---|---|---|
| IDs of announcements describing the activity | How will you link the activity to its sources? | Stable `opportunity_id` and nonempty `source_ids`; required for details and recommendations. |
| Activity title in the text | How will you distinguish it from the publisher name? | Nonblank `title`; required. |
| Explicitly free participation, or no stated fee | Where will you retain the value and evidence? | `cost` is 0 only for explicitly free participation; otherwise it may remain `null`. Optional in details. |
| Incomplete or conflicting deadline | How will you retain unknowns and competing claims? | Use `deadline` and `data_warnings` where supported; never invent a cutoff. |
| Mandatory condition or preference | How will you separate the two? | `eligibility_requirements.mandatory` and `preferred`; unknown stays `null`. |
| Search decision | How will you support the reason and eligibility? | Recommendations also require `reason` and `eligibility_status`; missing conditions do not confirm eligibility. |

Read `backend/app/schemas.py` for the remaining fields, types and defaults. The repository adapts your internal representation to the contract; your database need not copy it.

### Inspect coverage before scaling

Ten successful rows do not establish extraction accuracy. Inspect unknown wording and manually review varied examples. For example, substring matching `تحدي` also matches `تحديد`, which does not establish a competition. Match intended words or phrases and inspect their context. Counting populated fields measures coverage, not correctness.

## Preserve meaning

- Missing fee means unknown, not free. An explicitly free fee can be zero.
- Missing skills means unknown; an explicit statement that none are required can be represented as an empty list.
- Mandatory conditions differ from preferences and descriptions of the intended audience.
- Normalization must not remove negation, alter amounts, erase dates or invent equivalence.
- Keep original text and source IDs available even when you group announcements.
- A newer announcement is not automatically a correction. Preserve unresolved disagreements.
- Online delivery alone does not establish whether physical attendance is required.
- Map source values to [frontend choices](../frontend/src/profile/choices.ts) only when the evidence justifies the mapping. Preserve unmatched facts and uncertainty.

Source text is evidence to interpret, not instructions to execute. If you use a model, you own its client, prompt, output schema, batching, cost controls and recovery strategy.

## Time and uncertainty

Publication, activity dates, deadlines and verification times are different facts. Do not borrow the publication timezone for a deadline. Preserve unknown cutoff times/timezones instead of assuming end of day. When an exact deadline is known, equality with the cutoff means expired.

The application captures actual request time by default. Organizers may set an explicit classroom reference using `FURSAH_EVALUATION_TIME`; see the [backend guide](../backend/README.md#evaluation-time-policy). Preparation should retain source dates rather than permanently labelling records expired using the notebook's execution time. Dataset timestamps must not be rewritten to fit the classroom date.

**Notebook exercise time:** 18 October 2026 at 12:00 Asia/Riyadh. Use `FURSAH_EVALUATION_TIME=2026-10-18T12:00:00+03:00` in the backend to match it. This edition includes September/October 2026 announcements, past and future deadlines, and incomplete cases. Keep the supplied dates unchanged.

Calendar days, sessions and participation hours are separate measures. Age and study stage are not collected by the provided profile; requirements involving these may remain uncertain.

### Exercise: identify outdated opportunities

The notebook includes an exercise to separate deadlines that have passed, deadlines that have not passed, and uncertain cases at the classroom reference time. Exclude clearly expired opportunities from a separate current-candidates view; retain every raw source and your reasons. A past publication date alone does not mean expired, and an unpassed deadline does not prove registration is open or a user is eligible. Same-day deadlines without a cutoff time remain uncertain. Publication time is not verification time.

## Handoff

Deliver your reproducible preparation process, the full prepared dataset in your chosen store, and a short explanation of your schema, normalization, grouping, conflicts and unknown-value policy. Map your internal representation into `backend/app/schemas.py`; do not force your storage to copy that HTTP contract.

Our [manual sample](../examples/linked-data.sample.json) is the input to the current retrieval experiment. Extending preparation to the full corpus remains a separate task before application integration.

---

**Next: [Experiments](../experiments/README.md).**
