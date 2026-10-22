![SAAI](https://i.imgur.com/YHRhgqv.png)

**English** | [العربية](README.ar.md)

# Instrumentation — see each request stage

[Evaluation guide](../../../evals/README.md) · [Backend](../../README.md)

A **trace** represents a request. A **span** measures one operation inside it. We record understanding, embeddings, retrieval, reranking, candidate checks and selection so we can explain both failures and latency.

| File | Purpose |
|---|---|
| [spans.py](spans.py) | Stage measurements and evaluation outputs |
| [phoenix.py](phoenix.py) | OpenTelemetry connection to Phoenix |
| [../catalog_workflow.py](../catalog_workflow.py) | The `eval_span` calls around actual workflow stages |

Run `./evals/run.ps1 -Demo -Open` from the project root. In Phoenix, open **fursah-eval → eval.case**. Inspect child spans to locate slow stages, then annotations to understand grading. For example, retrieval can be fast while reranking dominates the request time.

Phoenix displays measurements; it does not establish answer quality by itself. [Code graders](../../../evals/catalog_graders.py) supply the scores. Detailed evaluation outputs are enabled for synthetic evaluation runs; keep that mode off for normal traffic.
