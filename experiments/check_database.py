"""Check source evidence and vector SQL using synthetic vectors, then roll back.

This checks database plumbing only. It does not measure embedding quality.
"""
import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from local_retrieval import ROOT, read_json, prepare_documents, save_corpus, search


class RollbackCheck(Exception):
    pass


def main():
    spec = read_json(ROOT / "examples" / "retrieval-eval.sample.json")
    sample = read_json(ROOT / "examples" / spec["corpus"]["file"])
    ids = spec["corpus"]["opportunity_ids"]
    documents = prepare_documents(sample, ids)
    vectors = np.eye(len(ids), 1024, dtype=np.float32)
    manifest = {"model_id": "synthetic-database-check", "revision": "test-only"}
    with psycopg.connect(**read_json(ROOT / ".local" / "database.json"), autocommit=True) as conn:
        register_vector(conn)
        before = conn.execute("SELECT to_regclass('retrieval_demo.documents')").fetchone()[0]
        before_count = conn.execute("SELECT count(*) FROM retrieval_demo.documents").fetchone()[0] if before else 0
        try:
            with conn.transaction():
                save_corpus(conn, sample, documents, vectors, manifest)
                hits = search(conn, vectors[0], ids, manifest, 2)
                assert hits[0]["opportunity_id"] == ids[0]
                assert abs(hits[0]["cosine_similarity"] - 1.0) < 1e-6
                bad_source = next(s["source_id"] for s in sample["sources"] if s["source_id"] not in sample["opportunities"][0]["source_ids"])
                try:
                    with conn.transaction():
                        conn.execute("INSERT INTO retrieval_demo.evidence VALUES (%s,%s,%s,'{}'::jsonb)", ("INVALID-CHECK", sample["opportunities"][0]["opportunity_id"], bad_source))
                except psycopg.errors.ForeignKeyViolation:
                    pass
                else:
                    raise AssertionError("Unlinked evidence was accepted")
                raise RollbackCheck()
        except RollbackCheck:
            pass
        after = conn.execute("SELECT to_regclass('retrieval_demo.documents')").fetchone()[0]
        assert after == before
        if after:
            assert conn.execute("SELECT count(*) FROM retrieval_demo.documents").fetchone()[0] == before_count
    print("PASS: source quotes, vector SQL, evidence relationship, rollback. No real embeddings or retrieval-quality measurements.")


if __name__ == "__main__":
    main()
