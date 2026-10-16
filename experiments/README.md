![SAAI — Learn AI by building](../docs/assets/saai-header.png)

**English** | [العربية](README.ar.md)

# Experiments — local semantic retrieval

**Previous:** [Data](../data/README.md) · **Overview:** [FURSAH](../README.md) · **Next:** [Backend](../backend/README.md)

This experiment verifies one part of FURSAH: converting opportunity and query text into vectors, storing them and retrieving the closest opportunities. It does not run the application's recommendation workflow.

## What the experiment uses

| Component | Choice | Purpose |
|---|---|---|
| Embedding model | BAAI/bge-m3, pinned revision | Generate dense 1024-dimensional vectors locally |
| Model runtime | SentenceTransformers on CPU | Encode documents and queries using the same model |
| Storage | PostgreSQL with pgvector | Keep opportunities, source evidence and vectors together |
| Search | Exact cosine search, Top-2 | Establish a small reproducible retrieval baseline |
| Corpus | Four manually prepared opportunities | Inspect relationships and results before expanding |
| Evaluation | Eight manually labelled queries | Six in-scope queries and two without a relevant sample record |

The [experiment design](../docs/first-retrieval-experiment.md) explains these choices. The current PostgreSQL instance runs on `127.0.0.1:55432`, separately from the existing system service.

## Prepare and run

Run from the project root. First-time setup needs Python 3.11, a PostgreSQL 18 installation with development headers and Visual Studio C++ build tools. The database setup script uses those existing Windows installations; it does not install them.

```powershell
.\scripts\setup-python.ps1
.\scripts\run-retrieval-experiment.ps1
```

The second command performs four stages:

| Stage | What happens | Output |
|---|---|---|
| 1. Prepare | Check the database and verify or download the checkpoint | SHA256-verified local model |
| 2. Index | Prepare four source-backed documents and encode them | Vectors stored with opportunity IDs and evidence versions |
| 3. Evaluate | Run the eight queries and compare SQL rankings with a local calculation | Rankings, scores and measured timings |
| 4. Review | Generate an Arabic review from the actual report | `results/retrieval-review.md` |

The model weights are about 2.27 GB. A first download requires internet; inference uses the local snapshot offline. Cached weights are checked by size and SHA256, and a stale snapshot can be repaired from a verified cached copy.

## Read the results

| File | Contents |
|---|---|
| [Human-readable review](../results/retrieval-review.md) | Findings, timings, limitations and next decisions |
| [Numeric report](../results/retrieval-report.json) | Model revision, versions, hashes and per-query results |
| [Indexed documents](../results/indexed-documents.json) | Exact search text and its source-backed parts |
| [Prepared sample](../examples/linked-data.sample.json) | Four opportunities, six announcements and 24 evidence items |
| [Evaluation queries](../examples/retrieval-eval.sample.json) | The original manual labels; completed-run status lives in the report |

The completed run reached **Recall@2 = 100% on the six in-scope queries**. Requests about cooking and first aid still returned nearest neighbours despite having no relevant sample opportunity. These neighbours are not recommendations; relevance and abstention handling remain application work.

## Inspect individual parts

| File | Responsibility |
|---|---|
| [local_retrieval.py](local_retrieval.py) | Validate excerpts, encode, store, search and measure |
| [model_integrity.py](model_integrity.py) | Verify checkpoint identity and recover a valid cached file |
| [check_database.py](check_database.py) | Exercise vector SQL and evidence relationships using synthetic vectors, then roll back |
| [test_model_integrity.py](test_model_integrity.py) | Cover stale pointers and reject corrupt cached weights |
| [review_results.py](review_results.py) | Turn the completed numeric report into a readable review |

Run a topic-only query after the environment and checkpoint are ready:

```powershell
.\.venv\Scripts\python.exe .\experiments\local_retrieval.py --query "ورشة ترجمة المحتوى التعليمي"
```

Check the database independently of the model:

```powershell
.\.venv\Scripts\python.exe .\experiments\check_database.py
```

That check uses synthetic vectors and reverses its writes. It tests storage behaviour, not Arabic understanding or embedding quality.

Stop the project database when needed:

```powershell
.\scripts\stop-postgres.ps1
```

---

**Next: [connect retrieval to the backend workflow](../backend/README.md).**
