"""Prepare all 1000 supplied announcements + saved extras; never fetch the web."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'data'))
from app.catalog_store import (checked_package, connect_catalog, migrate, publish_catalog,
    activate_release, EMBEDDING_MODEL, EMBEDDING_REVISION, vector_literal)
from app.dataset_preparation import prepare_catalog
from app.infrastructure.config import get_settings
from app.infrastructure.local_inference import get_local_inference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--reuse-prepared', action='store_true')
    parser.add_argument('--rollback')
    parser.add_argument('--withdraw')
    parser.add_argument('--reason', default='local supplied dataset preparation')
    args = parser.parse_args()
    settings = get_settings()
    output = ROOT / 'data/prepared/catalog.json'
    if args.rollback:
        with connect_catalog(settings, write=True) as conn:
            activate_release(conn, args.rollback, reason=args.reason, rollback=True)
        print(json.dumps({'active_release': args.rollback, 'rollback': True}))
        return
    if args.reuse_prepared or args.withdraw:
        package = json.loads(output.read_text(encoding='utf-8'))
        previous = ROOT / 'data/prepared/preparation-report.json'
        report = json.loads(previous.read_text(encoding='utf-8')) if previous.exists() else {}
        report.update(reused_prepared_package=True)
    else:
        import pandas as pd
        from preparation_helpers import prepare_announcements, save_prepared_data
        raw = ROOT / 'data/raw/raw_opportunities.csv'
        before = hashlib.sha256(raw.read_bytes()).hexdigest()
        with raw.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
        # The helper's date review is an observation at the notebook instant,
        # never a permanent closure flag used by the API's actual request clock.
        frame = prepare_announcements(pd.DataFrame(rows), '2026-10-18T12:00:00+03:00')
        save_prepared_data(frame, ROOT / 'data/prepared/source_preparation.json')
        observations = json.loads((ROOT / 'data/prepared/source_preparation.json').read_text(encoding='utf-8'))
        extras = json.loads((ROOT / 'data/prepared/real-catalog.json').read_text(encoding='utf-8'))
        package, report = prepare_catalog(rows, observations, extras=extras)
        after = hashlib.sha256(raw.read_bytes()).hexdigest()
        if before != after:
            raise ValueError('Raw CSV changed')
        report.update(raw_csv_sha256=before, raw_csv_unchanged=True, external_fetches=0,
                      helper='data/preparation_helpers.py:prepare_announcements')
    if args.withdraw:
        found = next((o for o in package['opportunities'] if o['opportunity_id'] == args.withdraw), None)
        if not found:
            raise ValueError('Unknown opportunity')
        found.update(publication_state='withdrawn', withdrawal_reason=args.reason)
    _, _, documents = checked_package(package)
    provided = {s['source_id']: s['content'] for s in package['sources'] if s.get('dataset_origin')=='provided_csv'}
    with (ROOT/'data/raw/raw_opportunities.csv').open(encoding='utf-8-sig',newline='') as handle:
        original_sources = {s['source_id']:s['content'] for s in csv.DictReader(handle)}
    report.update(input_announcements=len(original_sources), prepared_source_observations=len(provided),
        grouped_csv_opportunities=sum(o.get('dataset_origin')=='provided_csv' for o in package['opportunities']),
        extra_opportunities=sum(o.get('dataset_origin')!='provided_csv' for o in package['opportunities']),
        explicit_update_resolutions=sum(bool(f.get('resolution')) for o in package['opportunities'] for f in o['facts'].values()),
        raw_csv_unchanged=provided==original_sources,
        raw_csv_sha256=hashlib.sha256((ROOT/'data/raw/raw_opportunities.csv').read_bytes()).hexdigest(),
        helper='data/preparation_helpers.py:prepare_announcements',
        total_opportunities=len(package['opportunities']), total_sources=len(package['sources']),
        active_opportunities=sum(o['publication_state']=='active' for o in package['opportunities']),
        raw_csv_sources=sum(s.get('dataset_origin')=='provided_csv' for s in package['sources']),
        external_fetches=0, embedding_model=EMBEDDING_MODEL, embedding_revision=EMBEDDING_REVISION,
        vector_dimensions=1024)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(package, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.publish:
        runtime = get_local_inference()
        cache_path = ROOT / '.local/catalog-vectors.json'
        cache = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
        if cache.get('model') != EMBEDDING_MODEL or cache.get('revision') != EMBEDDING_REVISION:
            cache = {'model': EMBEDDING_MODEL, 'revision': EMBEDDING_REVISION, 'vectors': {}}
        keys = {d['opportunity_id']: hashlib.sha256(d['search_text'].encode()).hexdigest() for d in documents}
        missing = list({keys[d['opportunity_id']]: d['search_text'] for d in documents
                        if keys[d['opportunity_id']] not in cache['vectors']}.items())
        with runtime.session():
            for offset in range(0, len(missing), 32):
                batch = missing[offset:offset+32]
                values = runtime.encode_many([text for _, text in batch])
                for (key, _), value in zip(batch, values, strict=True):
                    vector_literal(value)
                    cache['vectors'][key] = value
                cache_path.write_text(json.dumps(cache), encoding='utf-8')
                print(f'Indexed {min(offset+32,len(missing))}/{len(missing)} new documents', flush=True)
        vectors = {d['opportunity_id']: cache['vectors'][keys[d['opportunity_id']]] for d in documents}
        with connect_catalog(settings, write=True) as conn:
            migrate(conn)
            release = publish_catalog(conn, package, vectors, reason=args.reason)
        report.update(release_id=release, published=True)
    else:
        report['published'] = False
    report['recorded_at'] = datetime.now(timezone.utc).isoformat()
    (ROOT / 'data/prepared/preparation-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
