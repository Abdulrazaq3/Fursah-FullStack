"""Two-phase expanded calibration and fresh evaluation; no runtime activation."""
import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter

from calibration_protocol import fingerprint, require_frozen_artifact, seal_artifact, validate_splits
from evaluate_joint_relevance import metrics
from local_reranker import LocalReranker, REVISION, SHA256

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.topic_verifier import TopicPolicy, build_candidate, calibrate_policy, verify_topics

INPUTS = ['results/indexed-documents.json', 'examples/reranker-eval.sample.json',
          'examples/expanded-topic-corpus.sample.json', 'examples/expanded-calibration.sample.json',
          'examples/expanded-holdout.sample.json', 'examples/relevance-eval.sample.json',
          'examples/relevance-confirmation.sample.json', 'results/joint-relevance-report.json']


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def prepare():
    inputs = {path: read(path) for path in INPUTS}
    corpus = inputs[INPUTS[2]]
    raw = ROOT / 'data/raw/raw_opportunities.csv'
    if hashlib.sha256(raw.read_bytes()).hexdigest() != corpus['raw_sha256']:
        raise ValueError('Raw source checksum differs from the frozen fixture')
    with raw.open(encoding='utf-8-sig', newline='') as stream:
        sources = {row['source_id']: row for row in csv.DictReader(stream)}
    candidates = []
    for doc in inputs[INPUTS[0]]:
        excerpts = [dict(role='title' if p['role']=='title' else 'activity', source_id=p['source_id'], quote=p['text'])
                    for p in doc['text_parts'] if p['role'] in {'title','activity_description'}]
        links = sorted({p['source_id'] for p in excerpts})
        candidates.append(build_candidate(doc['opportunity_id'], {s:sources[s] for s in links}, links, excerpts))
    for item in inputs[INPUTS[1]]['added_candidates'] + corpus['added_candidates']:
        links = item['source_ids']
        candidates.append(build_candidate(item['opportunity_id'], {s:sources[s] for s in links}, links, item['excerpts']))
    all_ids = {c.opportunity_id for c in candidates}
    if len(candidates) != 16 or len(all_ids) != 16:
        raise ValueError('Expected 16 distinct source candidates')
    unseen_ids = {item['opportunity_id'] for item in corpus['added_candidates'] if item['split']=='evaluation_only'}
    calibration_ids = all_ids - unseen_ids
    cal = inputs[INPUTS[3]]['queries']
    test = inputs[INPUTS[4]]['queries']
    prior = (inputs[INPUTS[5]]['queries'] + inputs[INPUTS[6]]['queries'] + inputs[INPUTS[1]]['fresh_queries'])
    validate_splits(cal,test,prior,calibration_ids,all_ids,unseen_ids)
    topics = {**corpus['base_topics'], **{x['opportunity_id']:x['topic'] for x in corpus['added_candidates']}}
    binding = {'input_sha256':{path:fingerprint(value) for path,value in inputs.items()},
               'raw_sha256':corpus['raw_sha256'], 'model_id':'BAAI/bge-reranker-v2-m3',
               'model_revision':REVISION, 'weights_sha256':SHA256,
               'candidate_topic_versions':{c.opportunity_id:c.topic_evidence_version for c in candidates},
               'max_pair_tokens':512,'batch_size':2,
               'calibration_rule':'existing_midpoint_zero_calibration_false_positives_v1',
               'acceptance_rule':'Zero accepted false-positive candidates and a relevant accepted result for every positive fresh query; diagnostic regressions block integration.'}
    return inputs,candidates,calibration_ids,unseen_ids,cal,test,topics,binding


def score_cases(cases,candidates,scorer,split):
    versions = {c.opportunity_id:c.topic_evidence_version for c in candidates}
    rows = []
    for index,case in enumerate(cases,1):
        started = perf_counter()
        decisions = verify_topics(case['query'], candidates, versions, TopicPolicy(None,None), scorer)
        rows.append({**case,'split':split,'decisions':decisions,'verification_seconds':round(perf_counter()-started,4)})
        if index % 5 == 0 or index == len(cases):
            print(f'{split}: {index}/{len(cases)} queries, {len(candidates)} candidates each.',flush=True)
    return rows


def apply_policy(rows,candidate_map,policy):
    results=[]
    for row in rows:
        items=[candidate_map[d['opportunity_id']] for d in row['decisions']]
        versions={d['opportunity_id']:d['topic_evidence_version'] for d in row['decisions']}
        values=[d['score'] for d in row['decisions']]
        if any(value is None for value in values):
            raise ValueError('Cached score missing; cannot silently rescore diagnostics')
        decisions=verify_topics(row['query'],items,versions,policy,lambda pairs:values)
        results.append({**row,'decisions':decisions})
    return results


def passes(values):
    return values['false_positive_candidates']==0 and values['positive_queries_with_relevant_hit']==values['positive_queries']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['check-inputs','calibrate','evaluate'],required=True)
    parser.add_argument('--run-id',default='expanded-v1')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}',args.run_id):
        raise ValueError('Invalid run ID')
    inputs,candidates,cal_ids,unseen_ids,cal,test,topics,binding=prepare()
    candidate_map={c.opportunity_id:c for c in candidates}
    policy_path=ROOT/f'results/relevance-{args.run_id}-policy.json'
    report_path=ROOT/f'results/relevance-{args.run_id}-report.json'
    review_path=ROOT/f'results/relevance-{args.run_id}-review.md'
    if args.phase=='check-inputs':
        print(json.dumps({'calibration_queries':len(cal),'calibration_candidates':len(cal_ids),
                          'calibration_topics':len({topics[i] for i in cal_ids}),
                          'holdout_queries':len(test),'holdout_candidates':len(candidates),
                          'unseen_topics':sorted(topics[i] for i in unseen_ids)},indent=2))
        return
    if args.phase=='calibrate' and policy_path.exists():
        raise FileExistsError('Policy already frozen; use a new run ID for another experiment')
    if args.phase=='evaluate':
        if report_path.exists():
            raise FileExistsError('Evaluation already recorded; preserve this report')
        artifact=read(policy_path)
        require_frozen_artifact(artifact,binding)
    print('Loading existing verified offline reranker; no download.',flush=True)
    started=perf_counter()
    scorer=LocalReranker()
    load_seconds=perf_counter()-started
    print(f'Model ready in {load_seconds:.1f}s.',flush=True)
    if args.phase=='calibrate':
        rows=score_cases(cal,[c for c in candidates if c.opportunity_id in cal_ids],scorer,'calibration')
        pairs=[(d['score'],d['opportunity_id'] in row['relevant_ids']) for row in rows for d in row['decisions']]
        policy=calibrate_policy(pairs)
        rows=apply_policy(rows,candidate_map,policy)
        highest_negative=max(score for score,label in pairs if not label)
        weakest_best_positive=min(max(d['score'] for d in row['decisions'] if d['opportunity_id'] in row['relevant_ids'])
                                  for row in rows if row['relevant_ids'])
        artifact=seal_artifact({'run_id':args.run_id,'frozen_at':datetime.now(timezone.utc).isoformat(),
            'binding':binding,'policy':asdict(policy),'calibration_metrics':metrics(rows),'calibration_rows':rows,
            'calibration_feasibility':{'highest_negative_score':highest_negative,
                'weakest_positive_query_best_score':weakest_best_positive,
                'global_cutoff_can_meet_calibration_query_coverage_without_false_positives':highest_negative<weakest_best_positive},
            'model_load_seconds':round(load_seconds,3),'enabled_in_application':False})
        if prepare()[-1]!=binding:
            raise ValueError('Inputs changed during calibration')
        policy_path.write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'frozen_policy':asdict(policy),'metrics':metrics(rows),'feasibility':artifact['calibration_feasibility']},indent=2),flush=True)
        return
    policy=TopicPolicy(**artifact['policy'])
    previous=inputs[INPUTS[-1]]
    if previous['model_revision']!=REVISION or previous['weights_sha256']!=SHA256:
        raise ValueError('Prior scores are not from the same checkpoint')
    baseline=TopicPolicy(**previous['policy'])
    raw=score_cases(test,candidates,scorer,'fresh_evaluation')
    new_rows=apply_policy(raw,candidate_map,policy)
    old_rows=apply_policy(raw,candidate_map,baseline)
    # Original candidate scopes and topic hashes are retained when replaying old scores.
    diagnostic_new=apply_policy(previous['results'],candidate_map,policy)
    diagnostic_old=apply_policy(previous['results'],candidate_map,baseline)
    new_metrics,old_metrics=metrics(new_rows),metrics(old_rows)
    diagnostic_new_metrics,diagnostic_old_metrics=metrics(diagnostic_new),metrics(diagnostic_old)
    changed_diagnostics=[]
    for old,new in zip(diagnostic_old,diagnostic_new,strict=True):
        old_accepted={d['opportunity_id'] for d in old['decisions'] if d['decision']=='related'}
        new_accepted={d['opportunity_id'] for d in new['decisions'] if d['decision']=='related'}
        relevant=set(old['relevant_ids'])
        if (new_accepted-relevant)-(old_accepted-relevant) or (old_accepted&relevant)-(new_accepted&relevant):
            changed_diagnostics.append(old['id'])
    passed=policy.accept_at is not None and passes(new_metrics) and not changed_diagnostics
    if prepare()[-1]!=binding:
        raise ValueError('Inputs changed during evaluation')
    require_frozen_artifact(read(policy_path),binding)
    unseen_cases=[row for row in new_rows if set(row['relevant_ids'])&unseen_ids]
    per_topic={topic:metrics([row for row in new_rows if row['topic']==topic]) for topic in sorted({row['topic'] for row in new_rows})}
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'run_id':args.run_id,
        'frozen_policy_sha256':artifact['artifact_sha256'],'binding':binding,
        'baseline_policy':asdict(baseline),'new_policy':asdict(policy),
        'calibration_metrics':artifact['calibration_metrics'],
        'fresh_metrics':{'baseline':old_metrics,'expanded':new_metrics},
        'diagnostic_metrics':{'baseline':diagnostic_old_metrics,'expanded':diagnostic_new_metrics},
        'diagnostic_regression_ids':changed_diagnostics,'unseen_topic_metrics':metrics(unseen_cases),
        'per_topic_metrics':per_topic,'limited_development_acceptance_passed':passed,
        'enabled_in_application':False,'model_load_seconds':round(load_seconds,3),
        'results':new_rows,'diagnostic_results':diagnostic_new,
        'limitations':['Fresh author-written queries, not independently adjudicated or randomly sampled.',
          'Four unseen topics assess transfer; all 16 candidates are scored, so retrieval recall is not measured.',
          'Original 70 queries are diagnostics only; old raw scores reused with matching model and topic hashes.',
          'No eligibility, structured constraints, registration, negation or multi-intent verification.',
          'Passing the local criterion permits a scoped integration trial, not production activation.']}
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# توسيع المعايرة والاختبار المستقل','','١٩ أكتوبر ٢٠٢٦ — مرحلة البناء والتقييم والتحسين.','',
        f'المعايرة: {len(cal)} طلبًا على {len(cal_ids)} مرشحًا. الاختبار الجديد: {len(test)} طلبًا على {len(candidates)} مرشحًا؛ أربعة موضوعات لم تُحسب درجاتها في المعايرة.','',
        f'السياسة القديمة: `{asdict(baseline)}`. السياسة الموسعة المثبتة قبل الاختبار: `{asdict(policy)}`. الدرجة ليست احتمالًا.','',
        '| المجموعة والسياسة | صحيح مقبول / متوقع | خاطئ مقبول | طلبات مناسبة لها نتيجة | طلبات خارج الموضوع لها نتيجة |',
        '|---|---|---|---|---|']
    for label,m in [('المعايرة الموسعة',artifact['calibration_metrics']),('الاختبار الجديد — السياسة القديمة',old_metrics),
                    ('الاختبار الجديد — السياسة الموسعة',new_metrics),('الموضوعات الأربعة الجديدة — الموسعة',metrics(unseen_cases)),
                    ('تشخيص ٧٠ طلبًا سابقًا — القديمة',diagnostic_old_metrics),('تشخيص ٧٠ طلبًا سابقًا — الموسعة',diagnostic_new_metrics)]:
        lines.append(f"| {label} | {m['true_positive_candidates']} / {m['true_positive_candidates']+m['missed_relevant_candidates']} | {m['false_positive_candidates']} | {m['positive_queries_with_relevant_hit']} / {m['positive_queries']} | {m['negative_queries_with_any_hit']} / {m['negative_queries']} |")
    lines+=['','## الأخطاء في الاختبار الجديد','']
    errors=[]
    for row in new_rows:
        accepted={d['opportunity_id'] for d in row['decisions'] if d['decision']=='related'}
        if accepted!=set(row['relevant_ids']):
            errors.append(row['id'])
            lines.append(f"- {row['id']}: {row['query']} — المتوقع {row['relevant_ids']}؛ المقبول {sorted(accepted)}.")
    if not errors:lines.append('طابقت جميع النتائج المقبولة التصنيفات اليدوية في الاختبار الجديد.')
    seconds=[row['verification_seconds'] for row in raw]
    lines+=['','## القرار والحدود','',
        'اجتازت السياسة معيار التجربة المحدود دون تراجع في التشخيص؛ تصلح مرشحًا لتجربة تكامل محدودة، ولم تُفعل داخل API.' if passed else 'لم تجتز السياسة معيار التجربة؛ تبقى خارج API، ولا نضبط الحد باستخدام أخطاء هذا الاختبار.','',
        f'عدد طلبات التشخيص التي تراجعت: {len(changed_diagnostics)}. وسيط فحص ١٦ مرشحًا: {median(seconds):.2f} ثانية؛ أقصى زمن: {max(seconds):.2f} ثانية بعد التحميل.','',
        'الاختبار جديد في الصياغات وأربعة موضوعات، لكنه ليس تحكيمًا بشريًا مستقلًا. المقاطع والتصنيفات يدوية، ولا يشمل القيود والتسجيل والأهلية أو جودة استرجاع المرشحين.','',
        f'التفاصيل في [التقرير الرقمي]({report_path.name})، و[سياسة المعايرة المثبتة]({policy_path.name}). التقارير السابقة بقيت محفوظة.']
    review_path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'new_policy':asdict(policy),'fresh':report['fresh_metrics'],'diagnostic':report['diagnostic_metrics'],
                      'unseen_topics':report['unseen_topic_metrics'],'passed':passed},indent=2),flush=True)


if __name__=='__main__':
    main()
