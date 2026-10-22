"""Transactional storage checks; all diagnostic writes are rolled back."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.catalog_store import connect_catalog,migrate,publish_catalog,activate_release,CatalogReader
from app.infrastructure.config import get_settings


def main():
    settings=get_settings()
    package=json.loads((ROOT/'data/prepared/catalog.json').read_text(encoding='utf8'))
    conn=connect_catalog(settings,write=True)
    try:
        migrate(conn)
        original=conn.execute('SELECT active_release FROM fursah_catalog.state').fetchone()
        # Unit vectors verify storage, never model quality. They never commit.
        vectors={o['opportunity_id']:[1.0]+[0.0]*1023 for o in package['opportunities']}
        first=publish_catalog(conn,package,vectors,reason='transactional diagnostic')
        repeated=publish_catalog(conn,package,vectors,reason='idempotency diagnostic')
        assert first==repeated
        assert conn.execute('SELECT count(*) FROM fursah_catalog.releases WHERE release_id=%s',(first,)).fetchone()[0]==1
        counts=conn.execute('SELECT (SELECT count(*) FROM fursah_catalog.opportunities WHERE release_id=%s),'
            '(SELECT count(*) FROM fursah_catalog.sources WHERE release_id=%s),'
            '(SELECT count(*) FROM fursah_catalog.documents WHERE release_id=%s)',(first,first,first)).fetchone()
        assert counts==(913,1013,913),counts
        changed=deepcopy(package);changed['opportunities'][0]['publication_state']='withdrawn'
        second=publish_catalog(conn,changed,vectors,reason='withdrawal diagnostic')
        assert second!=first
        count=conn.execute("SELECT count(*) FROM fursah_catalog.opportunities WHERE release_id=%s AND publication_state='active'",(second,)).fetchone()[0]
        assert count==912
        activate_release(conn,first,reason='rollback diagnostic',rollback=True)
        assert conn.execute('SELECT active_release FROM fursah_catalog.state').fetchone()[0]==first
        try:
            activate_release(conn,'missing-release',reason='invalid rollback test',rollback=True)
        except ValueError: pass
        else: raise AssertionError('Accepted unknown release')
        report={'opportunities':counts[0],'sources':counts[1],'documents':counts[2],
            'idempotent_publication':True,'withdrawal_hides_one_record':True,'rollback_restores_release':True,
            'unknown_rollback_rejected':True,'diagnostic_writes_rolled_back':True,
            'checks_use_synthetic_vectors':True,'semantic_quality_measured':False}
    finally:
        conn.rollback();conn.close()
    (ROOT/'evals/runs/checks/catalog-storage-check.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report))


if __name__=='__main__':main()
