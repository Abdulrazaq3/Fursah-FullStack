"""Evaluate explicit tool/activity vetoes without changing model scores/cutoffs."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from calibration_protocol import fingerprint, require_frozen_artifact, seal_artifact
from evaluate_expanded_relevance import prepare
from evaluate_joint_relevance import metrics
from local_reranker import LocalReranker, REVISION, SHA256
from app.topic_verifier import TopicPolicy, verify_topics
from app.request_requirements import RULE_VERSION, verify_with_requirements

ROOT=Path(__file__).resolve().parents[1]
FRESH='examples/request-requirements-holdout.sample.json'
REPORT='results/request-requirements-report.json'
FREEZE='results/request-requirements-freeze.json'
CODE=['backend/app/request_requirements.py','backend/app/topic_verifier.py','backend/app/relevance.py',
      'experiments/local_reranker.py','experiments/evaluate_request_requirements.py']


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8-sig'))


def cached_check(rows,candidate_map,policy):
    baseline,guarded=[],[]
    for row in rows:
        items=[candidate_map[d['opportunity_id']] for d in row['decisions']]
        versions={d['opportunity_id']:d['topic_evidence_version'] for d in row['decisions']}
        values=[d['score'] for d in row['decisions']]
        if any(v is None for v in values):raise ValueError('Cannot replay absent scores')
        requirements,decisions=verify_with_requirements(row['query'],items,versions,policy,lambda pairs:values)
        baseline.append({**row,'decisions':[{**d,'decision':d['semantic_decision']} for d in decisions]})
        guarded.append({**row,'requirements':asdict(requirements),'decisions':decisions})
    return baseline,guarded


def regressions(before,after):
    removed=[]
    for old,new in zip(before,after,strict=True):
        a={d['opportunity_id'] for d in old['decisions'] if d['decision']=='related'}
        b={d['opportunity_id'] for d in new['decisions'] if d['decision']=='related'}
        lost=(a-b)&set(old['relevant_ids'])
        if lost:removed.append({'id':old['id'],'query':old['query'],'lost_relevant_ids':sorted(lost)})
    return removed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['diagnostic','check-inputs','evaluate'],required=True)
    args=parser.parse_args()
    _,candidates,_,_,_,_,_,old_binding=prepare()
    lookup={c.opportunity_id:c for c in candidates}
    previous=read('results/joint-relevance-report.json')
    calibration=read('results/relevance-expanded-v1-policy.json')
    expanded=read('results/relevance-expanded-v1-report.json')
    policy=TopicPolicy(**expanded['new_policy'])
    prior=previous['results']+calibration['calibration_rows']+expanded['results']
    if len(prior)!=157 or previous['model_revision']!=REVISION or previous['weights_sha256']!=SHA256:
        raise ValueError('Unexpected diagnostic scores')
    old,new=cached_check(prior,lookup,policy)
    lost=regressions(old,new)
    diagnostic={'baseline':metrics(old),'guarded':metrics(new),'regressions':lost}
    if args.phase=='diagnostic':
        output={'generated_at':datetime.now(timezone.utc).isoformat(),'rule_version':RULE_VERSION,
                'metrics':diagnostic,'results':new,'scope':'Exposed development cases, not a fresh evaluation'}
        (ROOT/'results/request-requirements-diagnostic.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(diagnostic,ensure_ascii=False,indent=2))
        return
    fixture=read(FRESH)
    cases=fixture['queries']
    normalize=lambda value:' '.join(value.casefold().split())
    if len({normalize(r['query']) for r in cases+prior})!=len(cases)+len(prior):
        raise ValueError('Fresh queries overlap development data')
    if len({r['id'] for r in cases})!=len(cases):raise ValueError('Duplicate fresh IDs')
    if any(not set(r['relevant_ids'])<=set(lookup) for r in cases):raise ValueError('Invalid labels')
    binding={'prior_binding':old_binding,'baseline_report_sha256':fingerprint(expanded),
             'fresh_benchmark_sha256':fingerprint(fixture),'policy':asdict(policy),
             'code_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in CODE},
             'model_revision':REVISION,'weights_sha256':SHA256,'rule_version':RULE_VERSION}
    if args.phase=='check-inputs':
        print(json.dumps({'fresh_cases':len(cases),'search_cases':sum(not c['expected_review'] for c in cases),
                          'review_cases':sum(c['expected_review'] for c in cases),
                          'diagnostic':diagnostic},ensure_ascii=False,indent=2))
        return
    if (ROOT/REPORT).exists():raise FileExistsError('Fresh evaluation already recorded')
    if (ROOT/FREEZE).exists():
        frozen=read(FREEZE)
        require_frozen_artifact(frozen,binding)
    else:
        frozen=seal_artifact({'frozen_at':datetime.now(timezone.utc).isoformat(),'binding':binding,
                             'criterion':'No accepted false-positive search candidates, a relevant hit for each positive search case, correct review disposition, no lost previously accepted relevant candidates.',
                             'enabled_in_application':False})
        (ROOT/FREEZE).write_text(json.dumps(frozen,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Rules, test and unchanged cutoff frozen. Loading existing offline model.',flush=True)
    scorer=LocalReranker()
    raw=[]
    versions={c.opportunity_id:c.topic_evidence_version for c in candidates}
    for index,case in enumerate(cases,1):
        started=perf_counter()
        decisions=verify_topics(case['query'],candidates,versions,policy,scorer)
        raw.append({**case,'decisions':decisions,'verification_seconds':round(perf_counter()-started,4)})
        if index%4==0 or index==len(cases):print(f'Fresh requests: {index}/{len(cases)} scored.',flush=True)
    baseline,guarded=cached_check(raw,lookup,policy)
    search_old=[r for r in baseline if not r['expected_review']]
    search_new=[r for r in guarded if not r['expected_review']]
    plan_errors=[]
    review_errors=[]
    for row in guarded:
        req=row['requirements']
        required=sorted({m['tool'] for m in req['tools'] if m['polarity']=='required'})
        actual_activities=[m['activity'] for m in req['activities']]
        if required!=sorted(row['expected_required_tools']) or req['tool_mode']!=row['expected_mode'] or (
            not row['expected_review'] and actual_activities!=([row['expected_activity']] if row['expected_activity'] else [])):
            plan_errors.append(row['id'])
        accepted=[d for d in row['decisions'] if d['decision']=='related']
        if bool(req['review_reasons'])!=row['expected_review'] or (row['expected_review'] and accepted):
            review_errors.append(row['id'])
    fresh_metrics={'baseline':metrics(search_old),'guarded':metrics(search_new)}
    fresh_lost=regressions(search_old,search_new)
    m=fresh_metrics['guarded']
    full_pass=(m['false_positive_candidates']==0 and m['positive_queries_with_relevant_hit']==m['positive_queries']
               and not lost and not fresh_lost and not plan_errors and not review_errors)
    no_new_accepts=all({d['opportunity_id'] for d in r['decisions'] if d['decision']=='related'} <=
                     {d['opportunity_id'] for d in r['decisions'] if d['semantic_decision']=='related'} for r in guarded)
    component_pass=not lost and not fresh_lost and not plan_errors and not review_errors and no_new_accepts
    require_frozen_artifact(read(FREEZE),binding)
    if fingerprint(read(FRESH))!=binding['fresh_benchmark_sha256']:raise ValueError('Benchmark changed')
    if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=v for p,v in binding['code_sha256'].items()):
        raise ValueError('Frozen implementation changed during evaluation')
    output={'generated_at':datetime.now(timezone.utc).isoformat(),'binding':binding,'freeze_sha256':frozen['artifact_sha256'],
            'fresh_search_metrics':fresh_metrics,'diagnostic_metrics':diagnostic,
            'plan_error_ids':plan_errors,'review_error_ids':review_errors,'fresh_regressions':fresh_lost,
            'guard_component_check_passed':component_pass,'full_relevance_acceptance_passed':full_pass,
            'guard_never_promoted_a_match':no_new_accepts,'enabled_in_application':False,
            'results':guarded,'diagnostic_results':new,
            'limitations':['Bounded lexical tool/activity vocabulary; not a general language planner.',
                          'Vetoes only: low semantic scores cannot be rescued by a keyword match.',
                          'Unknown scope remains not_checked; complex recognized scopes require review.',
                          'Same 16 manually curated candidates; all scored, no retrieval recall measured.',
                          'Labels by the implementer, not independent adjudication. No eligibility or registration checks.']}
    (ROOT/REPORT).write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# فحص الأداة والنشاط المطلوبين','','تجربة محلية على طلبات جديدة بعد تثبيت القواعد والاختبار والحد العددي.','',
           '| المجموعة | صحيح مقبول / متوقع | خاطئ مقبول | طلبات مناسبة لها نتيجة |',
           '|---|---|---|---|']
    for label,values in [('السابق: ١٥٧ طلبًا — النموذج',diagnostic['baseline']),('السابق: ١٥٧ طلبًا — مع الفحص',diagnostic['guarded']),
                         ('الاختبار الجديد — النموذج',fresh_metrics['baseline']),('الاختبار الجديد — مع الفحص',m)]:
        lines.append(f"| {label} | {values['true_positive_candidates']} / {values['true_positive_candidates']+values['missed_relevant_candidates']} | {values['false_positive_candidates']} | {values['positive_queries_with_relevant_hit']} / {values['positive_queries']} |")
    lines+=['','## أخطاء الاختبار الجديد','']
    errors=[]
    for row in search_new:
        accepted={d['opportunity_id'] for d in row['decisions'] if d['decision']=='related'}
        if accepted!=set(row['relevant_ids']):
            errors.append(row['id'])
            lines.append(f"- {row['id']}: {row['query']} — المتوقع {row['relevant_ids']}؛ المقبول {sorted(accepted)}.")
    if not errors:lines.append('طابقت النتائج المقبولة تصنيفات طلبات البحث الجديدة في هذه العينة.')
    lines+=['','## حدود القرار','',
        f'أخطاء استخراج الأداة والنشاط: {plan_errors}. أخطاء الإحالة للمراجعة: {review_errors}. الطلبات المركبة الأربعة مفصولة عن مقاييس البحث.','',
        f'اجتياز فحوص المكوّن المحدودة: {component_pass}. اجتياز معيار الصلة الكامل: {full_pass}. الفاحص خارج API.','',
        f'وسيط استدلال ١٦ مرشحًا: {median(r["verification_seconds"] for r in raw):.2f} ثانية بعد التحميل.','',
        'القواعد تمنع قبولًا غير مدعوم، ولا ترفع مرشحًا لمجرد تطابق كلمة، ولا تستبدل فهم اللغة العام. غياب الأداة أو النشاط من المقاطع يبقى نقص دليل، لا حقيقة بعدم وجوده.','',
        'المصادر والتصنيفات يدوية، والتجربة لا تفحص الأهلية أو التسجيل أو الميزانية أو استرجاع المرشحين.','',
        f'راجع [التقرير الرقمي]({Path(REPORT).name}) و[النسخة المثبتة]({Path(FREEZE).name}).']
    (ROOT/'results/request-requirements-review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:output[k] for k in ['fresh_search_metrics','diagnostic_metrics','plan_error_ids','review_error_ids',
                  'guard_component_check_passed','full_relevance_acceptance_passed']},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
