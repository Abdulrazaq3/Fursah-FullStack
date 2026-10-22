# Learner guidance: prepare data/raw/raw_opportunities.csv using data/README.md.
# Choose your own storage and internal schema. The bridge is an optional CSV/JSON
# helper. Map your storage into the public API contract; rename/split this module freely.
from __future__ import annotations

import json
import math
from dataclasses import dataclass

import psycopg

from .infrastructure.data_package import DatasetLoader
from .infrastructure.config import Settings
from .infrastructure.errors import DataAccessError
from .details import map_details
from .topic_verifier import build_candidate, TopicCandidate
from .schemas import OpportunityDetailsResponse


@dataclass(frozen=True)
class RetrievedOpportunity:
    opportunity: dict
    sources: dict
    evidence: dict
    details: OpportunityDetailsResponse
    topic: TopicCandidate
    similarity: float


class OpportunityRepository:
    """Read and search the four-record, source-backed PostgreSQL pilot corpus."""

    def __init__(self, bridge: DatasetLoader, settings: Settings) -> None:
        self.bridge = bridge
        self.settings = settings
        self.catalog = None
        if settings.catalog_mode == 'prepared':
            from .catalog_store import CatalogReader
            self.catalog = CatalogReader(settings)

    def _connect(self):
        try:
            if self.settings.database_url:
                conn = psycopg.connect(self.settings.database_url, connect_timeout=3)
            else:
                config = json.loads(self.settings.database_config_file.read_text(encoding="utf-8"))
                conn = psycopg.connect(**{**config, "connect_timeout": 3})
            try:
                conn.execute("SET TRANSACTION READ ONLY")
                conn.execute("SELECT set_config('statement_timeout', '3000', true)")
                return conn
            except Exception:
                conn.close()
                raise
        except (OSError, ValueError, TypeError, psycopg.Error) as exc:
            raise DataAccessError() from exc

    def is_ready(self) -> bool:
        """Check that PostgreSQL contains opportunities linked to source evidence."""
        if self.catalog:
            return self.catalog.is_ready()
        try:
            with self._connect() as conn:
                return conn.execute("""SELECT EXISTS (
                    SELECT 1 FROM retrieval_demo.opportunities o
                    JOIN retrieval_demo.opportunity_sources l USING (opportunity_id)
                    JOIN retrieval_demo.evidence e USING (opportunity_id, source_id)
                )""").fetchone()[0] is True
        except (DataAccessError, psycopg.Error):
            return False

    def search(self, vector: list[float]) -> list[RetrievedOpportunity]:
        """Exact cosine over the four prepared records, with all evidence in one read.

        This pilot deliberately fails closed if the corpus changes. Expansion needs
        its own indexing/relevance evaluation rather than an implicit top-k rollout.
        """
        if self.catalog:
            return self.catalog.search(vector)
        if (len(vector) != 1024 or any(isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v) for v in vector)
                or abs(sum(v*v for v in vector) - 1) > .002):
            raise DataAccessError()
        literal = '[' + ','.join(str(float(v)) for v in vector) + ']'
        try:
            with self._connect() as conn:
                rows = conn.execute("""
                    SELECT o.payload,
                        (SELECT jsonb_object_agg(s.source_id,s.payload)
                         FROM retrieval_demo.opportunity_sources l
                         JOIN retrieval_demo.sources s USING(source_id)
                         WHERE l.opportunity_id=o.opportunity_id),
                        (SELECT jsonb_object_agg(e.evidence_id,e.payload)
                         FROM retrieval_demo.evidence e WHERE e.opportunity_id=o.opportunity_id),
                        d.text_parts,d.evidence_version,1-(d.embedding <=> %s::vector),
                        d.model_id,d.model_revision
                    FROM retrieval_demo.documents d
                    JOIN retrieval_demo.opportunities o USING(opportunity_id)
                    ORDER BY d.embedding <=> %s::vector,d.opportunity_id LIMIT 5
                """, (literal, literal)).fetchall()
            if len(rows) != 4:
                raise DataAccessError()
            result = []
            for opp, sources, evidence, parts, version, score, model, revision in rows:
                if model != 'BAAI/bge-m3' or revision != '5617a9f61b028005a4858fdac845db406aefb181':
                    raise DataAccessError()
                details = map_details(opp, sources, evidence)
                if details.evidence_version != version or not math.isfinite(score) or not -1.001 <= score <= 1.001:
                    raise DataAccessError()
                excerpts = [
                    {'role': 'title' if p['role'] == 'title' else 'activity',
                     'source_id': p['source_id'], 'quote': p['text']} for p in parts
                    if p['role'] in {'title', 'activity_description'}]
                linked = sorted({p['source_id'] for p in excerpts})
                topic = build_candidate(details.opportunity_id, {s: sources[s] for s in linked}, linked, excerpts)
                result.append(RetrievedOpportunity(opp, sources, evidence, details, topic, float(score)))
            if {r.details.opportunity_id for r in result} != {f'OPP-DEMO-{i:03}' for i in range(1, 5)}:
                raise DataAccessError()
            return result
        except (psycopg.Error, KeyError, TypeError, ValueError) as exc:
            raise DataAccessError() from exc

    def confirm_versions(self, versions: dict[str, str]) -> None:
        """Re-read published candidates together before returning source-bound results."""
        if self.catalog:
            return self.catalog.confirm_versions(versions)
        if not versions:
            return
        try:
            with self._connect() as conn:
                rows = conn.execute("""
                    SELECT o.payload,
                        (SELECT jsonb_object_agg(s.source_id,s.payload)
                         FROM retrieval_demo.opportunity_sources l
                         JOIN retrieval_demo.sources s USING(source_id)
                         WHERE l.opportunity_id=o.opportunity_id),
                        (SELECT jsonb_object_agg(e.evidence_id,e.payload)
                         FROM retrieval_demo.evidence e WHERE e.opportunity_id=o.opportunity_id)
                    FROM retrieval_demo.opportunities o WHERE o.opportunity_id=ANY(%s)
                """, (list(versions),)).fetchall()
            current = {d.opportunity_id: d.evidence_version for d in (map_details(*r) for r in rows)}
            if current != versions:
                raise DataAccessError()
        except (psycopg.Error, TypeError, ValueError) as exc:
            raise DataAccessError() from exc

    def get_details(self, opportunity_id: str):
        """Read a source-backed record, or return None for a missing identifier."""
        if self.catalog:
            return self.catalog.get_details(opportunity_id)
        try:
            with self._connect() as conn:
                row = conn.execute("""
                    SELECT o.payload,
                        COALESCE((SELECT jsonb_object_agg(s.source_id, s.payload)
                            FROM retrieval_demo.opportunity_sources l
                            JOIN retrieval_demo.sources s USING (source_id)
                            WHERE l.opportunity_id=o.opportunity_id), '{}'::jsonb),
                        COALESCE((SELECT jsonb_object_agg(e.evidence_id, e.payload)
                            FROM retrieval_demo.evidence e
                            WHERE e.opportunity_id=o.opportunity_id), '{}'::jsonb)
                    FROM retrieval_demo.opportunities o
                    WHERE o.opportunity_id=%s
                """, (opportunity_id,)).fetchone()
            if row is None:
                return None
            if not isinstance(row[0], dict) or row[0].get("opportunity_id") != opportunity_id:
                raise DataAccessError()
            return map_details(*row)
        except psycopg.Error as exc:
            raise DataAccessError() from exc
