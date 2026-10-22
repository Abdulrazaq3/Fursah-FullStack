![SAAI](../frontend/readme-header.png)

**English** | [العربية](README.ar.md)

# Data

`raw/raw_opportunities.csv` retains all 1,000 original announcements unchanged. `preparation_helpers.py` provides the original cleaning helpers; `backend/app/dataset_preparation.py` links observations to opportunity identities, facts and source evidence.

`prepared/catalog.json` contains **913 opportunities and 1,013 source records**: 900 grouped opportunities from the supplied CSV, plus 13 saved additions from `prepared/real-catalog.json`. The API searches this catalog in PostgreSQL/pgvector.

```powershell
# From the project root; prepare, embed missing documents and publish
.\.venv\Scripts\python.exe backend/scripts/prepare-catalog.py --publish

# Publish the reviewed existing prepared package
.\.venv\Scripts\python.exe backend/scripts/prepare-catalog.py --reuse-prepared --publish
```

Preparation keeps original text, source IDs, missing values, contradictory claims and explicit updates. Unknown prices stay unknown. Original dates remain unchanged and availability is evaluated at request time. The process uses saved sources; it does not fetch external opportunities.

Outputs are `prepared/source_preparation.json`, `prepared/catalog.json` and `prepared/preparation-report.json`. Local vectors are cached under `.local/`. Published releases live in the `fursah_catalog` schema; withdrawal and rollback preserve earlier releases. Use `--help` for their arguments.

`requirements.txt` contains offline preparation dependencies. Run [backend/setup.ps1](../backend/setup.ps1) with `-Models` to install them along with local inference dependencies. [Evaluation](../evals/README.md) owns quality checks and frozen dataset fingerprints.
