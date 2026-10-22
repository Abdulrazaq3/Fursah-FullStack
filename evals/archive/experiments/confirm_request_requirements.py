"""Confirm the deterministic guard after a reported parser defect, without model inference."""
from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path

from calibration_protocol import fingerprint, seal_artifact
from evaluate_expanded_relevance import prepare
from evaluate_joint_relevance import metrics
from evaluate_request_requirements import cached_check, regressions
from app.request_requirements import RULE_VERSION, extract_requirements, check_requirements
from app.topic_verifier import TopicPolicy

ROOT=Path(__file__).resolve().parents[1]


def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8-sig'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',choices=('v11','v12','v13'),default='v13')
    args=parser.parse_args()
    suffix='-'+args.version if args.version!='v11' else ''
    prefix='results/request-requirements-confirmation'+suffix
    fixture_name='examples/request-requirements-confirmation'+suffix+'.sample.json'
    output_path=ROOT/(prefix+'-report.json')
    if output_path.exists():raise FileExistsError('Preserve the completed confirmation report')
    _,candidates,_,_,_,_,_,binding=prepare()
    lookup={c.opportunity_id:c for c in candidates}
    fixture=read(fixture_name)
    prior_fresh=read('results/request-requirements-report.json')
    prior=(read('results/joint-relevance-report.json')['results']+
           read('results/relevance-expanded-v1-policy.json')['calibration_rows']+
           read('results/relevance-expanded-v1-report.json')['results']+prior_fresh['results'])
    cases=fixture['queries']
    if len({r['query'] for r in prior+cases})!=len(prior)+len(cases):raise ValueError('Duplicate confirmation queries')
    module_hash=hashlib.sha256((ROOT/'backend/app/request_requirements.py').read_bytes()).hexdigest()
    frozen=seal_artifact({'frozen_at':datetime.now(timezone.utc).isoformat(),'rule_version':RULE_VERSION,
        'code_sha256':module_hash,'confirmation_sha256':fingerprint(fixture),
        'prior_report_sha256':fingerprint(prior_fresh),'source_binding':binding,
        'scope':'Deterministic component only; all earlier scored requests are diagnostics.'})
    freeze_path=ROOT/(prefix+'-freeze.json')
    if freeze_path.exists():raise FileExistsError('Preserve the existing frozen confirmation inputs')
    freeze_path.write_text(json.dumps(frozen,ensure_ascii=False,indent=2),encoding='utf-8')
    results=[]
    for case in cases:
        requirements=extract_requirements(case['query'])
        actual_tools=sorted({m['tool'] for m in requirements.tools if m['polarity']=='required'})
        actual_activities=[a['activity'] for a in requirements.activities]
        checks={c.opportunity_id:check_requirements(requirements,c) for c in candidates}
        supported=sorted(k for k,v in checks.items() if v['status']=='supported')
        passed=(actual_tools==sorted(case['tools']) and requirements.tool_mode==case['mode']
            and actual_activities==([case['activity']] if case['activity'] else [])
            and bool(requirements.review_reasons)==case['review'] and supported==sorted(case['supported_ids']))
        results.append({**case,'requirements':asdict(requirements),'supported_ids_actual':supported,'passed':passed,'candidate_checks':checks})
    # Neural scores remain the original scores; this replay is no longer held out.
    search=[r for r in prior if not r.get('expected_review',False)]
    policy=TopicPolicy(**prior_fresh['binding']['policy'])
    old,new=cached_check(search,lookup,policy)
    lost=regressions(old,new)
    fixed=next(r for r in new if r['id']=='REQ-08')
    if hashlib.sha256((ROOT/'backend/app/request_requirements.py').read_bytes()).hexdigest()!=module_hash:
        raise ValueError('Rules changed during confirmation')
    if fingerprint(read(fixture_name))!=frozen['confirmation_sha256']:
        raise ValueError('Confirmation labels changed')
    output={'generated_at':datetime.now(timezone.utc).isoformat(),'rule_version':RULE_VERSION,
        'scope':f'{len(cases)} fresh deterministic component cases; zero new neural inference. Earlier 189 scored requests are now diagnostic.',
        'freeze_sha256':frozen['artifact_sha256'],'confirmation_passed':all(r['passed'] for r in results),
        'confirmation_cases':len(results),'confirmation_cases_passed':sum(r['passed'] for r in results),
        'parser_defect_REQ_08_resolved':[a['activity'] for a in fixed['requirements']['activities']]==['public_presentation'],
        'diagnostic_search_cases':len(search),'diagnostic_metrics':{'baseline':metrics(old),'guarded':metrics(new)},
        'diagnostic_regressions':lost,'results':results,'diagnostic_results':new,'enabled_in_application':False,
        'limitations':['Fresh author-written deterministic cases on the same source corpus, not independent adjudication.',
                      'No new neural inference or end-to-end semantic quality result in this confirmation.',
                      'Earlier failed v1 parser report is preserved; older queries are diagnostics only.',
                      'Bounded vocabulary, not general language understanding; unresolved source facts stay unknown.']}
    output_path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# تأكيد فاحص الأداة والنشاط بعد إصلاح الاستخراج','',
        f'إصدار القواعد: {RULE_VERSION}. تقارير الجولات السابقة محفوظة، وإعادة فحص طلباتها تشخيص وليست اختبارًا مستقلًا.','',
        f"اختبار المكوّن الجديد: {output['confirmation_cases_passed']} / {len(results)} حالة. لا تشغيل جديد للنموذج؛ نفحص الاستخراج ومطابقة المتطلبات بالمقاطع مباشرة.",'',
        f"حل حالة REQ-08: {output['parser_defect_REQ_08_resolved']}. مرشحون صحيحون سبق قبولهم وفقدناهم في التشخيص: {len(lost)}.",'',
        '| التشخيص على ١٨٥ طلب بحث سابقًا | صحيح مقبول / متوقع | خاطئ مقبول | طلبات مناسبة لها نتيجة |','|---|---|---|---|']
    for label,m in [('النموذج قبل الفحص',metrics(old)),('بعد فحص '+RULE_VERSION,metrics(new))]:
        lines.append(f"| {label} | {m['true_positive_candidates']} / {m['true_positive_candidates']+m['missed_relevant_candidates']} | {m['false_positive_candidates']} | {m['positive_queries_with_relevant_hit']} / {m['positive_queries']} |")
    lines+=['','أربع حالات مركبة من الجولة السابقة منفصلة عن مقاييس البحث. التأكيد لا يعالج المرشحين الذين فقدهم النموذج، ولا يثبت اكتمال التوصية أو فهم كل الصيغ اللغوية.','',
            'الفاحص خارج API. يمكن استخدام نجاح المكوّن المحدود لمواصلة بناء بقية فحوص النظام، مع بقاء معيار جودة الرحلة الكاملة مفتوحًا.','',
            f'التفاصيل في [التقرير الرقمي]({output_path.name})، والاختبار الأول في [مراجعته المحفوظة](request-requirements-review.md).']
    (ROOT/(prefix+'-review.md')).write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:output[k] for k in ['confirmation_passed','confirmation_cases_passed',
        'parser_defect_REQ_08_resolved','diagnostic_metrics','diagnostic_regressions']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
