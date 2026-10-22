![SAAI — Learn AI by building](../../docs/assets/saai-header.png)

# Fursah system evals

The original Day 4 cases and graders remain available. The expanded local-catalog suite adds per-stage OpenTelemetry traces, source/ID graders and an independent raw-source availability audit.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-evals.txt
.\scripts\run-catalog-evals.ps1 -Label baseline-check
```

Uses the real Gemini API, local BGE models and the complete PostgreSQL catalog. Phoenix is optional. Development labels and source inputs are pinned by `catalog_cases_manifest.json`; the six holdout cases have not been run. Labels are AI source reviewed, not human-approved production gold.

[Arabic guide and metric definitions](../../docs/system-evals.md) · [Baseline findings](../../results/catalog-eval-baseline-v1-review.md)
