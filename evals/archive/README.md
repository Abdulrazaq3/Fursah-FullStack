# Evaluation archive

Historical experiments, fixtures and measured reports are kept here. Start current work from [the eval guide](../README.md).

| Former location | Current location |
|---|---|
| `results/` | `reports/` |
| `examples/` | `fixtures/` |
| `experiments/` | `experiments/` |
| `backend/evals/results/` | `runs/` |

`layout-map.json` records original paths and hashes before reorganization. Historical reports retain their original text and paths; frozen approvals resolve those references through `backend/app/infrastructure/reference_paths.py`. The model runtime lives in `backend/app/infrastructure/models/`; its measured reranker source is preserved.

These are records of previous measurements, not current commands to run during the classroom demonstration.
