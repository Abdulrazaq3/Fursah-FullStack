"""Versioned real catalog. Publication is atomic; the historical demo is untouched."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from .details import canonical, map_details
from .infrastructure.config import PROJECT_ROOT
from .infrastructure.errors import DataAccessError
from .topic_verifier import build_candidate

EMBEDDING_MODEL = 'BAAI/bge-m3'
EMBEDDING_REVISION = '5617a9f61b028005a4858fdac845db406aefb181'


def connect_catalog(settings, *, write=False):
    conn = None
    try:
        if settings.database_url:
            conn = psycopg.connect(settings.database_url, connect_timeout=5)
        else:
            config = json.loads(settings.database_config_file.read_text(encoding='utf-8'))
            conn = psycopg.connect(**{**config, 'connect_timeout': 5})
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ' + ('' if write else ' READ ONLY'))
        conn.execute("SELECT set_config('statement_timeout', %s, true)", ('30000' if write else '5000',))
        return conn
    except (OSError, ValueError, TypeError, psycopg.Error):
        if conn is not None:
            conn.close()
        raise DataAccessError() from None


def migrate(conn):
    conn.execute('CREATE SCHEMA IF NOT EXISTS fursah_catalog')
    conn.execute('CREATE TABLE IF NOT EXISTS fursah_catalog.migrations '
                 '(version text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())')
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('fursah.catalog.migrate'))")
    for path in sorted((PROJECT_ROOT / 'backend/migrations').glob('*.sql')):
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        previous = conn.execute('SELECT sha256 FROM fursah_catalog.migrations WHERE version=%s', (path.name,)).fetchone()
        if previous:
            if previous[0] != digest:
                raise ValueError('Applied migration checksum changed: ' + path.name)
            continue
        conn.execute(data.decode('utf-8'))
        conn.execute('INSERT INTO fursah_catalog.migrations(version,sha256) VALUES (%s,%s)', (path.name, digest))


def vector_literal(vector):
    if (len(vector) != 1024 or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
            or abs(sum(v*v for v in vector) - 1) > .002):
        raise DataAccessError()
    return '[' + ','.join(str(float(v)) for v in vector) + ']'


def checked_package(package):
    if package.get('schema_version') != 'real-catalog-v1' or not package.get('reviewed_by'):
        raise ValueError('Unreviewed catalog package')
    sources = {s['source_id']: s for s in package['sources']}
    evidence = {e['evidence_id']: e for e in package['evidence']}
    opportunities = package['opportunities']
    if (not opportunities or len(sources) != len(package['sources']) or len(evidence) != len(package['evidence'])
            or len({o['opportunity_id'] for o in opportunities}) != len(opportunities)):
        raise ValueError('Empty or duplicated catalog identities')
    documents = []
    linked_evidence = set()
    for opp in opportunities:
        if opp.get('publication_state') not in {'active', 'withdrawn'}:
            raise ValueError('Invalid publication state')
        owned = {s: sources[s] for s in opp['source_ids']}
        proofs = {k: e for k, e in evidence.items() if e['opportunity_id'] == opp['opportunity_id']}
        details = map_details(opp, owned, proofs)
        linked_evidence.update(proofs)
        parts = opp['search_parts']
        excerpts = [{'role': p['role'], 'source_id': p['source_id'], 'quote': p['text']} for p in parts]
        candidate = build_candidate(opp['opportunity_id'], owned, opp['source_ids'], excerpts)
        if not {'title', 'activity'} <= {p['role'] for p in parts}:
            raise ValueError('Missing title/activity evidence')
        documents.append({'opportunity_id': opp['opportunity_id'], 'evidence_version': details.evidence_version,
                          'text_parts': parts, 'search_text': candidate.passage})
    if linked_evidence != set(evidence):
        raise ValueError('Orphaned evidence')
    return sources, evidence, documents


def package_version(package):
    return hashlib.sha256(canonical(package).encode('utf-8')).hexdigest()


def publish_catalog(conn, package, vectors, *, reason='reviewed source refresh'):
    sources, evidence, documents = checked_package(package)
    if set(vectors) != {d['opportunity_id'] for d in documents}:
        raise ValueError('Embeddings must cover this package exactly')
    literals = {key: vector_literal(value) for key, value in vectors.items()}
    digest = package_version(package)
    release = 'catalog-' + digest[:24]
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('fursah.catalog.publish'))")
    existing = conn.execute('SELECT package_sha256 FROM fursah_catalog.releases WHERE release_id=%s', (release,)).fetchone()
    if existing and existing[0] != digest:
        raise ValueError('Release identity collision')
    if not existing:
        conn.execute('INSERT INTO fursah_catalog.releases VALUES (%s,%s,%s,%s,1024,%s,DEFAULT,%s)',
                     (release, digest, EMBEDDING_MODEL, EMBEDDING_REVISION, len(documents), package['reviewed_by']))
        for source in sources.values():
            conn.execute('INSERT INTO fursah_catalog.sources VALUES (%s,%s,%s)',
                         (release, source['source_id'], Jsonb(source)))
        for opp in package['opportunities']:
            conn.execute('INSERT INTO fursah_catalog.opportunities VALUES (%s,%s,%s,%s,%s)',
                         (release, opp['opportunity_id'], opp['canonical_url'], opp['publication_state'], Jsonb(opp)))
            for source_id in opp['source_ids']:
                conn.execute('INSERT INTO fursah_catalog.opportunity_sources VALUES (%s,%s,%s)',
                             (release, opp['opportunity_id'], source_id))
        for item in evidence.values():
            conn.execute('INSERT INTO fursah_catalog.evidence VALUES (%s,%s,%s,%s,%s)',
                         (release, item['evidence_id'], item['opportunity_id'], item['source_id'], Jsonb(item)))
        for doc in documents:
            conn.execute('INSERT INTO fursah_catalog.documents VALUES (%s,%s,%s,%s,%s::vector)',
                         (release, doc['opportunity_id'], doc['evidence_version'], Jsonb(doc['text_parts']),
                          literals[doc['opportunity_id']]))
    activate_release(conn, release, reason=reason)
    return release


def activate_release(conn, release, *, reason, rollback=False):
    if not reason.strip():
        raise ValueError('Publication/rollback reason is required')
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('fursah.catalog.publish'))")
    counts = conn.execute('SELECT r.opportunity_count,count(d.opportunity_id) '
        'FROM fursah_catalog.releases r LEFT JOIN fursah_catalog.documents d USING(release_id) '
        'WHERE r.release_id=%s GROUP BY r.opportunity_count', (release,)).fetchone()
    if not counts or counts[0] != counts[1]:
        raise ValueError('Unknown or incomplete release')
    conn.execute('INSERT INTO fursah_catalog.state(singleton,active_release) VALUES (true,%s) '
                 'ON CONFLICT (singleton) DO UPDATE SET active_release=EXCLUDED.active_release,changed_at=now()', (release,))
    conn.execute('INSERT INTO fursah_catalog.events(release_id,event_type,reason) VALUES (%s,%s,%s)',
                 (release, 'rollback' if rollback else 'publish', reason))


READ_ROWS = """
 SELECT o.payload,
   (SELECT jsonb_object_agg(s.source_id,s.payload) FROM fursah_catalog.opportunity_sources l
    JOIN fursah_catalog.sources s USING(release_id,source_id)
    WHERE l.release_id=o.release_id AND l.opportunity_id=o.opportunity_id),
   (SELECT jsonb_object_agg(e.evidence_id,e.payload) FROM fursah_catalog.evidence e
    WHERE e.release_id=o.release_id AND e.opportunity_id=o.opportunity_id),
   d.text_parts,d.evidence_version,r.model_id,r.model_revision,o.release_id
 FROM fursah_catalog.state current
 JOIN fursah_catalog.releases r ON r.release_id=current.active_release
 JOIN fursah_catalog.opportunities o ON o.release_id=r.release_id
 JOIN fursah_catalog.documents d ON d.release_id=o.release_id AND d.opportunity_id=o.opportunity_id
 WHERE o.publication_state='active'
"""


def _row(row, similarity=0):
    from .repository import RetrievedOpportunity
    opp, sources, evidence, parts, version, model, revision, release = row
    if model != EMBEDDING_MODEL or revision != EMBEDDING_REVISION:
        raise DataAccessError()
    details = map_details(opp, sources, evidence)
    if details.evidence_version != version:
        raise DataAccessError()
    details = details.model_copy(update={'information_url': opp.get('information_url'),
        'data_warnings': list(dict.fromkeys([*details.data_warnings, *opp.get('data_notes', [])]))})
    candidate = build_candidate(opp['opportunity_id'], sources, opp['source_ids'],
        [{'role': p['role'], 'source_id': p['source_id'], 'quote': p['text']} for p in parts])
    return RetrievedOpportunity(opp, sources, evidence, details, candidate, float(similarity))


class CatalogReader:
    def __init__(self, settings):
        self.settings = settings

    def search(self, vector, *, limit=None):
        limit = limit or self.settings.catalog_retrieval_limit
        literal = vector_literal(vector)
        if not 1 <= limit <= 20:
            raise ValueError('Search limit must be 1..20')
        try:
            with connect_catalog(self.settings) as conn:
                rows = conn.execute(READ_ROWS + ' ORDER BY d.embedding <=> %s::vector,o.opportunity_id LIMIT %s',
                                    (literal, limit)).fetchall()
            return [_row(row) for row in rows]
        except psycopg.Error:
            raise DataAccessError() from None

    def get_details(self, identifier):
        try:
            with connect_catalog(self.settings) as conn:
                row = conn.execute(READ_ROWS + ' AND o.opportunity_id=%s', (identifier,)).fetchone()
            return _row(row).details if row else None
        except psycopg.Error:
            raise DataAccessError() from None

    def confirm_versions(self, versions):
        if not versions:
            return
        try:
            with connect_catalog(self.settings) as conn:
                rows = conn.execute(READ_ROWS + ' AND o.opportunity_id=ANY(%s)', (list(versions),)).fetchall()
            if {r.details.opportunity_id: r.details.evidence_version for r in map(_row, rows)} != versions:
                raise DataAccessError()
        except psycopg.Error:
            raise DataAccessError() from None

    def is_ready(self):
        try:
            with connect_catalog(self.settings) as conn:
                row = conn.execute('SELECT count(*) FROM fursah_catalog.state s '
                    'JOIN fursah_catalog.opportunities o ON o.release_id=s.active_release '
                    "WHERE o.publication_state='active'").fetchone()
            return row[0] > 0
        except (psycopg.Error, DataAccessError):
            return False
