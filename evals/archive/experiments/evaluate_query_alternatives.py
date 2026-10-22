"""Freeze literal-OR development and fresh evaluation; leave discovery unchanged."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter
import unicodedata

from calibration_protocol import fingerprint, require_frozen_artifact, seal_artifact
from evaluate_expanded_relevance import prepare
from evaluate_joint_relevance import metrics
from evaluate_request_requirements import regressions
from local_reranker import LocalReranker, REVISION, SHA256
from app.query_alternatives import POLICY_VERSION, plan_alternatives, verify_alternatives
from app.request_requirements import extract_requirements
from app.topic_verifier import TopicPolicy

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = 'examples/query-alternatives-holdout-v1.sample.json'
PREFIX = 'results/query-alternatives-v1'
CODE = ['backend/app/query_alternatives.py','backend/app/request_requirements.py',
        'backend/app/topic_verifier.py','backend/app/details.py','backend/app/relevance.py',
        'experiments/evaluate_query_alternatives.py','experiments/local_reranker.py']


def read(name):
    return json.loads((ROOT/name).read_text(encoding='utf-8-sig'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['check-inputs','diagnostic','evaluate'],required=True)
    args=parser.parse_args()
    _, candidates, *_, source_binding = prepare()
    lookup={c.opportunity_id:c for c in candidates}
    prior=read('results/request-requirements-confirmation-v13-report.json')['diagnostic_results']
    cases=read(FIXTURE)['queries']
    key=lambda q:' '.join(unicodedata.normalize('NFKC',q).casefold().split())
    exposed=[r['query'] for r in prior]
    for fixture in ROOT.glob('examples/*sample.json'):
        if fixture.name==Path(FIXTURE).name: continue
        obj=json.loads(fixture.read_text(encoding='utf-8-sig'))
        if isinstance(obj,dict):
            exposed.extend(r['query'] for r in obj.get('queries',[]) if isinstance(r,dict) and 'query' in r)
    if len({key(c['query']) for c in cases})!=len(cases) or {key(q) for q in exposed}&{key(c['query']) for c in cases}:
        raise ValueError('Fresh query overlap')
    if len({c['id'] for c in cases})!=len(cases) or any(not set(c['relevant_ids'])<=set(lookup) for c in cases):
        raise ValueError('Invalid labels or identifiers')
    policy=TopicPolicy(**read('results/relevance-expanded-v1-policy.json')['policy'])
    binding={'policy_version':POLICY_VERSION,'policy':asdict(policy),'model_revision':REVISION,'weights_sha256':SHA256,
             'source_binding':source_binding,'fixture_sha256':fingerprint(read(FIXTURE)),
             'prior_sha256':fingerprint(prior),
             'code_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in CODE}}
    expanded=sum(plan_alternatives(r['query']).decision=='expanded' for r in prior)
    if args.phase=='check-inputs':
        print(json.dumps({'development_cases':len(prior),'development_cases_with_branches':expanded,
                          'fresh_cases':len(cases),'binding':fingerprint(binding)},ensure_ascii=False))
        return
    freeze_path=ROOT/(PREFIX+'-freeze.json')
    if freeze_path.exists():
        require_frozen_artifact(read(PREFIX+'-freeze.json'),binding)
    else:
        if args.phase!='diagnostic': raise ValueError('Run frozen development diagnostics first')
        frozen=seal_artifact({'frozen_at':datetime.now(timezone.utc).isoformat(),'binding':binding,
            'criterion':read(FIXTURE)['acceptance'],'enabled_in_application':False})
        freeze_path.write_text(json.dumps(frozen,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    output=ROOT/(PREFIX+('-diagnostic.json' if args.phase=='diagnostic' else '-report.json'))
    if output.exists(): raise FileExistsError('Preserve completed evaluation')
    if args.phase=='evaluate':
        development=read(PREFIX+'-diagnostic.json')
        if not development['component_passed']: raise ValueError('Development failed; fresh split remains unused')
    cache_path=ROOT/'.local/query-alternatives-v1-score-cache.json'
    cache=json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {'binding':fingerprint(binding),'scores':{}}
    if cache['binding']!=fingerprint(binding): raise ValueError('Stale inference cache')
    scorer=None
    def score(pairs):
        nonlocal scorer
        cache_key=fingerprint(pairs)
        if cache_key not in cache['scores']:
            if scorer is None:
                print('Loading existing SHA256-verified offline reranker; no model/threshold change.',flush=True)
                scorer=LocalReranker()
            cache['scores'][cache_key]=scorer(pairs)
            cache_path.parent.mkdir(exist_ok=True)
            cache_path.write_text(json.dumps(cache,ensure_ascii=False),encoding='utf-8')
        return cache['scores'][cache_key]
    rows=prior if args.phase=='diagnostic' else cases
    baseline, proposed=[],[]
    for index,row in enumerate(rows,1):
        items=[lookup[d['opportunity_id']] for d in row['decisions']] if args.phase=='diagnostic' else candidates
        versions={c.opportunity_id:c.topic_evidence_version for c in items}
        original=[d['score'] for d in row['decisions']] if args.phase=='diagnostic' else None
        start=perf_counter()
        result=verify_alternatives(row['query'],items,versions,policy,score,original_scores=original)
        common={k:v for k,v in row.items() if k not in {'decisions','requirements','verification_seconds'}}
        baseline.append({**common,'decisions':result['baseline']})
        proposed.append({**common,'alternative_plan':asdict(result['plan']),'decisions':result['decisions'],
                         'verification_seconds':round(perf_counter()-start,4)})
        if result['plan'].branches or index%4==0 or index==len(rows):
            print(f'{args.phase}: {index}/{len(rows)}; branches={len(result["plan"].branches)}',flush=True)
    require_frozen_artifact(read(PREFIX+'-freeze.json'),binding)
    if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h for p,h in binding['code_sha256'].items()):
        raise ValueError('Code changed during evaluation')
    if fingerprint(read(FIXTURE))!=binding['fixture_sha256']: raise ValueError('Labels changed during evaluation')
    search_old=[r for r in baseline if not r.get('expected_review',False)]
    search_new=[r for r in proposed if not r.get('expected_review',False)]
    measured={'baseline':metrics(search_old),'proposed':metrics(search_new)}
    lost=regressions(search_old,search_new)
    interpretation_errors=[]
    if args.phase=='evaluate':
        for row in proposed:
            review=bool(extract_requirements(row['query']).review_reasons)
            if (review!=row['expected_review'] or (row['alternative_plan']['decision']=='expanded')!=row['expected_expanded']
                    or (row['expected_review'] and any(d['decision']=='related' for d in row['decisions']))):
                interpretation_errors.append(row['id'])
    gained=measured['proposed']['true_positive_candidates']-measured['baseline']['true_positive_candidates']
    component=(not lost and measured['proposed']['false_positive_candidates']<=measured['baseline']['false_positive_candidates']
               and gained>0 and not interpretation_errors)
    full=(component and measured['proposed']['false_positive_candidates']==0 and
          measured['proposed']['positive_queries_with_relevant_hit']==measured['proposed']['positive_queries'])
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'phase':args.phase,'binding_sha256':fingerprint(binding),
        'scope':'Exposed development replay with real new branch inference' if args.phase=='diagnostic' else
                'Fresh author-labelled query wording on the same candidates, frozen before inference; not independent adjudication.',
        'metrics':measured,'regressions':lost,'interpretation_errors':interpretation_errors,
        'component_passed':component,'full_slice_passed':full,'enabled_in_application':False,
        'results':proposed,'baseline_results':baseline}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['metrics','component_passed','full_slice_passed','interpretation_errors']},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
