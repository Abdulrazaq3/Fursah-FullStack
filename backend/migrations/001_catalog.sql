CREATE SCHEMA IF NOT EXISTS fursah_catalog;

CREATE TABLE IF NOT EXISTS fursah_catalog.releases (
    release_id text PRIMARY KEY,
    package_sha256 text NOT NULL,
    model_id text NOT NULL,
    model_revision text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions = 1024),
    opportunity_count integer NOT NULL CHECK (opportunity_count > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    approved_by text NOT NULL CHECK (length(approved_by) > 0)
);
CREATE TABLE IF NOT EXISTS fursah_catalog.sources (
    release_id text NOT NULL REFERENCES fursah_catalog.releases,
    source_id text NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    PRIMARY KEY (release_id, source_id)
);
CREATE TABLE IF NOT EXISTS fursah_catalog.opportunities (
    release_id text NOT NULL REFERENCES fursah_catalog.releases,
    opportunity_id text NOT NULL,
    canonical_url text NOT NULL,
    publication_state text NOT NULL CHECK (publication_state IN ('active','withdrawn')),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    PRIMARY KEY (release_id, opportunity_id)
);
CREATE TABLE IF NOT EXISTS fursah_catalog.opportunity_sources (
    release_id text NOT NULL,
    opportunity_id text NOT NULL,
    source_id text NOT NULL,
    PRIMARY KEY (release_id, opportunity_id, source_id),
    FOREIGN KEY (release_id, opportunity_id) REFERENCES fursah_catalog.opportunities,
    FOREIGN KEY (release_id, source_id) REFERENCES fursah_catalog.sources
);
CREATE INDEX IF NOT EXISTS catalog_sources_reverse_idx
    ON fursah_catalog.opportunity_sources (release_id, source_id);
CREATE TABLE IF NOT EXISTS fursah_catalog.evidence (
    release_id text NOT NULL,
    evidence_id text NOT NULL,
    opportunity_id text NOT NULL,
    source_id text NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    PRIMARY KEY (release_id, evidence_id),
    FOREIGN KEY (release_id, opportunity_id, source_id) REFERENCES fursah_catalog.opportunity_sources
);
CREATE INDEX IF NOT EXISTS catalog_evidence_opportunity_idx
    ON fursah_catalog.evidence (release_id, opportunity_id);
CREATE TABLE IF NOT EXISTS fursah_catalog.documents (
    release_id text NOT NULL,
    opportunity_id text NOT NULL,
    evidence_version text NOT NULL,
    text_parts jsonb NOT NULL,
    embedding vector(1024) NOT NULL,
    PRIMARY KEY (release_id, opportunity_id),
    FOREIGN KEY (release_id, opportunity_id) REFERENCES fursah_catalog.opportunities
);
CREATE TABLE IF NOT EXISTS fursah_catalog.state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    active_release text NOT NULL REFERENCES fursah_catalog.releases,
    changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS fursah_catalog.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    release_id text NOT NULL REFERENCES fursah_catalog.releases,
    event_type text NOT NULL CHECK (event_type IN ('publish','rollback')),
    reason text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now()
);
