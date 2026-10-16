"""Small, offline BGE-M3 -> PostgreSQL/pgvector retrieval experiment.

This evaluates topic retrieval, not eligibility or the full user journey.
Run from the project root with .venv/Scripts/python.exe.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from model_integrity import verify_checkpoint

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
# Downloading is a separate explicit step. Inference uses the local snapshot only.
os.environ["HF_HOME"] = str(LOCAL / "huggingface")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import numpy as np
import psycopg
import torch
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb
from sentence_transformers import SentenceTransformer


SCHEMA = """
CREATE SCHEMA IF NOT EXISTS retrieval_demo;
CREATE TABLE IF NOT EXISTS retrieval_demo.sources (
    source_id text PRIMARY KEY,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS retrieval_demo.opportunities (
    opportunity_id text PRIMARY KEY,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS retrieval_demo.opportunity_sources (
    opportunity_id text REFERENCES retrieval_demo.opportunities NOT NULL,
    source_id text REFERENCES retrieval_demo.sources NOT NULL,
    PRIMARY KEY (opportunity_id, source_id)
);
CREATE TABLE IF NOT EXISTS retrieval_demo.evidence (
    evidence_id text PRIMARY KEY,
    opportunity_id text NOT NULL,
    source_id text NOT NULL,
    payload jsonb NOT NULL,
    FOREIGN KEY (opportunity_id, source_id)
        REFERENCES retrieval_demo.opportunity_sources
);
CREATE TABLE IF NOT EXISTS retrieval_demo.documents (
    opportunity_id text PRIMARY KEY REFERENCES retrieval_demo.opportunities,
    search_text text NOT NULL,
    model_id text NOT NULL,
    model_revision text NOT NULL,
    evidence_version text NOT NULL,
    text_parts jsonb NOT NULL,
    embedding vector(1024) NOT NULL
);
"""

# Hand-selected excerpts for this fixture, not an automatic extraction pipeline.
ACTIVITY_PARTS = {
    "OPP-DEMO-001": (
        "SRC-0943", "جلسة تدريبية عملية.",
        "سيتناول المشاركون مقارنة الصياغات وتحرير المصطلحات، ثم يناقشون أمثلة من واقع مدنهم.",
    ),
    "OPP-DEMO-002": (
        "SRC-0477", "ورشة عمل",
        "سيتناول المشاركون مقارنة الصياغات وتحرير المصطلحات، ثم يناقشون أمثلة من واقع مدنهم.",
    ),
    "OPP-DEMO-003": (
        "SRC-0251", "جلسة تدريبية عملية",
        "تدور الأنشطة حول كتابة النص وتسجيل المقاطع؛ وتتاح فرصة لتجريب الأفكار خلال اللقاء.",
    ),
    "OPP-DEMO-004": (
        "SRC-0496", "ورشة تطبيقية.",
        "سيتناول المشاركون ترتيب الجداول وقراءة المؤشرات، ثم يناقشون أمثلة من واقع مدنهم.",
    ),
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def prepare_documents(sample: dict, opportunity_ids: list[str]) -> list[dict]:
    sources = {item["source_id"]: item for item in sample["sources"]}
    opportunities = {item["opportunity_id"]: item for item in sample["opportunities"]}
    evidence = {item["evidence_id"]: item for item in sample["evidence"]}
    for item in evidence.values():
        assert item["quote"] in sources[item["source_id"]]["content"], "Evidence quote mismatch"
        assert item["source_id"] in opportunities[item["opportunity_id"]]["source_ids"]

    documents = []
    for identifier in opportunity_ids:
        opportunity = opportunities[identifier]
        title_fact = opportunity["facts"]["title"]
        assert title_fact["status"] == "known" and title_fact["evidence_ids"]
        title_source = evidence[title_fact["evidence_ids"][0]]["source_id"]
        source_id, activity_type, description = ACTIVITY_PARTS[identifier]
        parts = [
            {"role": "title", "source_id": title_source, "text": title_fact["value"]},
            {"role": "activity_type", "source_id": source_id, "text": activity_type},
            {"role": "activity_description", "source_id": source_id, "text": description},
        ]
        for part in parts:
            assert part["source_id"] in opportunity["source_ids"]
            assert part["text"] in sources[part["source_id"]]["content"], "Search excerpt mismatch"
        version = fingerprint({
            "opportunity": opportunity,
            "sources": [sources[key] for key in sorted(opportunity["source_ids"])],
            "evidence": sorted(
                (item for item in evidence.values() if item["opportunity_id"] == identifier),
                key=lambda item: item["evidence_id"],
            ),
        })
        documents.append({
            "opportunity_id": identifier,
            "search_text": "\n".join(part["text"] for part in parts),
            "text_parts": parts,
            "evidence_version": version,
        })
    return documents


def load_model(manifest: dict) -> SentenceTransformer:
    verify_checkpoint(manifest)
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    model = SentenceTransformer(
        manifest["snapshot_path"], device="cpu", local_files_only=True, trust_remote_code=False,
    )
    model.max_seq_length = 512
    assert model.get_sentence_embedding_dimension() == 1024
    return model


def encode(model: SentenceTransformer, texts: list[str]) -> np.ndarray:
    # Fail explicitly rather than silently truncate an unexpected long example.
    for text in texts:
        assert len(model.tokenizer.encode(text, add_special_tokens=True)) <= model.max_seq_length
    vectors = model.encode(
        texts, batch_size=2, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False,
    ).astype(np.float32)
    assert vectors.shape == (len(texts), 1024) and np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-4)
    return vectors


def save_corpus(conn: psycopg.Connection, sample: dict, documents: list[dict], vectors: np.ndarray, manifest: dict) -> None:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(SCHEMA)
        for source in sample["sources"]:
            cur.execute(
                "INSERT INTO retrieval_demo.sources VALUES (%s, %s) ON CONFLICT (source_id) DO UPDATE SET payload=EXCLUDED.payload",
                (source["source_id"], Jsonb(source)),
            )
        for opportunity in sample["opportunities"]:
            cur.execute(
                "INSERT INTO retrieval_demo.opportunities VALUES (%s, %s) ON CONFLICT (opportunity_id) DO UPDATE SET payload=EXCLUDED.payload",
                (opportunity["opportunity_id"], Jsonb(opportunity)),
            )
            for source_id in opportunity["source_ids"]:
                cur.execute(
                    "INSERT INTO retrieval_demo.opportunity_sources VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (opportunity["opportunity_id"], source_id),
                )
        for item in sample["evidence"]:
            cur.execute(
                """INSERT INTO retrieval_demo.evidence VALUES (%s, %s, %s, %s)
                ON CONFLICT (evidence_id) DO UPDATE SET payload=EXCLUDED.payload""",
                (item["evidence_id"], item["opportunity_id"], item["source_id"], Jsonb(item)),
            )
        for document, vector in zip(documents, vectors, strict=True):
            cur.execute(
                """INSERT INTO retrieval_demo.documents VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (opportunity_id) DO UPDATE SET
                    search_text=EXCLUDED.search_text, model_id=EXCLUDED.model_id,
                    model_revision=EXCLUDED.model_revision, evidence_version=EXCLUDED.evidence_version,
                    text_parts=EXCLUDED.text_parts, embedding=EXCLUDED.embedding""",
                (document["opportunity_id"], document["search_text"], manifest["model_id"],
                 manifest["revision"], document["evidence_version"], Jsonb(document["text_parts"]), vector),
            )


def search(conn: psycopg.Connection, vector: np.ndarray, ids: list[str], manifest: dict, top_k: int) -> list[dict]:
    rows = conn.execute(
        """SELECT d.opportunity_id, 1 - (d.embedding <=> %s) AS similarity,
                  o.payload, d.evidence_version
           FROM retrieval_demo.documents d
           JOIN retrieval_demo.opportunities o USING (opportunity_id)
           WHERE d.opportunity_id = ANY(%s) AND d.model_id=%s AND d.model_revision=%s
           ORDER BY d.embedding <=> %s, d.opportunity_id LIMIT %s""",
        (vector, ids, manifest["model_id"], manifest["revision"], vector, top_k),
    ).fetchall()
    return [{
        "opportunity_id": row[0], "cosine_similarity": float(row[1]),
        "title": row[2]["facts"]["title"]["value"], "source_ids": row[2]["source_ids"],
        "evidence_version": row[3],
    } for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", help="Run one topic-only query after preparing the sample")
    args = parser.parse_args()
    spec = read_json(ROOT / "examples" / "retrieval-eval.sample.json")
    sample = read_json(ROOT / "examples" / spec["corpus"]["file"])
    manifest = read_json(LOCAL / "model-manifest.json")
    assert manifest["model_id"] == "BAAI/bge-m3" and manifest["dimensions"] == 1024
    ids = spec["corpus"]["opportunity_ids"]
    documents = prepare_documents(sample, ids)
    started = perf_counter()
    model = load_model(manifest)
    load_seconds = perf_counter() - started
    print(f"Local model loaded in {load_seconds:.2f}s.", flush=True)
    started = perf_counter()
    vectors = encode(model, [item["search_text"] for item in documents])
    embedding_seconds = perf_counter() - started
    config = read_json(LOCAL / "database.json")
    with psycopg.connect(**config, connect_timeout=10, autocommit=True) as conn:
        register_vector(conn)
        started = perf_counter()
        save_corpus(conn, sample, documents, vectors, manifest)
        storage_seconds = perf_counter() - started
        assert conn.execute(
            "SELECT count(*) FROM retrieval_demo.documents WHERE opportunity_id=ANY(%s)", (ids,),
        ).fetchone()[0] == len(ids)
        extension_version = conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()[0]
        if args.query:
            query_vector = encode(model, [args.query])[0]
            print(json.dumps(search(conn, query_vector, ids, manifest, 2), ensure_ascii=False, indent=2))
            return

        results = []
        max_score_difference = 0.0
        for case in spec["queries"]:
            started = perf_counter()
            query_vector = encode(model, [case["query"]])[0]
            query_embedding_seconds = perf_counter() - started
            started = perf_counter()
            hits = search(conn, query_vector, ids, manifest, 2)
            db_seconds = perf_counter() - started
            assert len(hits) == 2
            # Cross-check pgvector's exact results against a direct local calculation.
            expected_scores = {identifier: float(score) for identifier, score in zip(ids, vectors @ query_vector, strict=True)}
            expected_order = sorted(ids, key=lambda identifier: (-expected_scores[identifier], identifier))[:2]
            assert [hit["opportunity_id"] for hit in hits] == expected_order, "Database and reference ranking disagree"
            for hit in hits:
                difference = abs(hit["cosine_similarity"] - expected_scores[hit["opportunity_id"]])
                max_score_difference = max(max_score_difference, difference)
                assert difference < 1e-5
            relevant = set(case["relevant_opportunity_ids"])
            recall = len(relevant.intersection(hit["opportunity_id"] for hit in hits)) / len(relevant) if relevant else None
            results.append({
                "case_id": case["id"], "query": case["query"], "relevant_opportunity_ids": sorted(relevant),
                "hits": hits, "recall_at_2": recall,
                "query_embedding_seconds": round(query_embedding_seconds, 4), "database_search_seconds": round(db_seconds, 6),
                "review": "Nearest neighbours only; no relevant sample record and no abstention policy tested." if not relevant else "Topic retrieval only; eligibility not evaluated.",
            })
            print(f"{case['id']}: recall@2={recall}; query={query_embedding_seconds:.2f}s; database={db_seconds:.4f}s", flush=True)

    positive = [item["recall_at_2"] for item in results if item["recall_at_2"] is not None]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Four manually prepared opportunities; eight development queries; topic retrieval only.",
        "inference": "Offline local snapshot; HF_HUB_OFFLINE=1; TRANSFORMERS_OFFLINE=1; local_files_only=True",
        "configuration": {**spec["proposed_configuration"], "model_revision": manifest["revision"], "torch_threads": 4},
        "versions": {name: importlib.metadata.version(name) for name in ["torch", "sentence-transformers", "transformers", "psycopg", "pgvector"]},
        "pgvector_extension_version": extension_version,
        "python": platform.python_version(),
        "sample_sha256": fingerprint(sample),
        "evaluation_sha256": fingerprint(spec),
        "counts": {"sources": len(sample["sources"]), "opportunities": len(documents), "evidence": len(sample["evidence"]), "queries": len(results), "positive_queries": len(positive), "out_of_scope_queries": len(results) - len(positive)},
        "timings_seconds": {"model_load": round(load_seconds, 3), "document_embedding": round(embedding_seconds, 3), "storage": round(storage_seconds, 3)},
        "macro_recall_at_2_positive_queries": sum(positive) / len(positive),
        "reference_check_max_similarity_difference": max_score_difference,
        "results": results,
        "limitations": [
            "Small hand-labelled development sample, not held-out evaluation or full-corpus preparation.",
            "No eligibility, registration, constraint-filtering or abstention policy was executed.",
            "Top-K returns neighbours even for unrelated queries; similarities are not acceptance probabilities.",
            "Query times are measured sequentially after model loading, not concurrent service latency.",
        ],
    }
    output = ROOT / "results"
    output.mkdir(exist_ok=True)
    (output / "retrieval-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "indexed-documents.json").write_text(json.dumps(documents, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report saved. Macro recall@2 on {len(positive)} positive queries: {report['macro_recall_at_2_positive_queries']:.3f}", flush=True)


if __name__ == "__main__":
    main()
