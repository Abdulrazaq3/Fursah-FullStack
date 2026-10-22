"""Source/ID graders for the expanded catalog; no LLM judge or live lookup."""
import json
import math
from functools import lru_cache
from pathlib import Path
from .grading import Grade
from .source_audit import audit_response


def outputs(spans,name):
    values=[]
    for attrs in spans.all(name):
        try: values.append(json.loads(attrs['output.value']))
        except (KeyError,TypeError,ValueError):continue
    return values


def grade_status(case,response,spans):
    expected=case['expected_status']
    return Grade('e2e.status',float(response.status.value==expected),f"expected={expected}, actual={response.status.value}")


def grade_interpretation(case,response,spans):
    if 'expected_effective_constraints' not in case:return None
    plans=outputs(spans,'fursah.understanding')
    got=plans[-1].get('effective_constraints') if plans else None
    expected=case['expected_effective_constraints']
    passed=isinstance(got,dict) and all(got.get(k)==v for k,v in expected.items())
    return Grade('understanding.constraints',float(passed),f'expected subset={expected}; actual={got}')


def grade_recall(case,response,spans):
    if 'expected_relevant_ids' not in case or not case['expected_relevant_ids']:return None
    batches=outputs(spans,'fursah.retrieval')
    if not batches:return Grade('retrieval.recall_at_20',0,'Missing retrieval instrumentation')
    expected=set(case['expected_relevant_ids']);got=batches[-1][:20]
    score=len(set(got)&expected)/len(expected)
    return Grade('retrieval.recall_at_20',score,f'{len(set(got)&expected)}/{len(expected)} known relevant found; retrieved={len(got)}')


def grade_ndcg(case,response,spans):
    relevant=set(case.get('expected_relevant_ids',[]))
    if not relevant:return None
    batches=outputs(spans,'fursah.rerank')
    if not batches:return Grade('rerank.ndcg_at_20',0,'Missing rerank instrumentation')
    ids=[r['opportunity_id'] for r in batches[-1][:20]]
    if len(set(ids))!=len(ids):return Grade('rerank.ndcg_at_20',0,'Duplicated ranking IDs')
    dcg=sum(1/math.log2(i+2) for i,v in enumerate(ids) if v in relevant)
    ideal=sum(1/math.log2(i+2) for i in range(min(20,len(relevant))))
    return Grade('rerank.ndcg_at_20',dcg/ideal,f'Binary source-reviewed relevance; n={len(ids)}')


def grade_target_coverage(case,response,spans):
    if 'required_retrieved_ids' not in case:return None
    batches=outputs(spans,'fursah.retrieval')
    got=set(batches[-1]) if batches else set()
    missing=set(case['required_retrieved_ids'])-got
    return Grade('retrieval.target_coverage',float(not missing),f'Missing required adversarial target IDs={sorted(missing)}')


def grade_instrumentation(case,response,spans):
    required={'fursah.understanding'}
    if response.status.value=='ok':
        required.update({'fursah.embedding','fursah.retrieval','fursah.rerank','fursah.candidate_check','fursah.selection','fursah.details'})
    missing=sorted(name for name in required if not spans.all(name))
    return Grade('tracing.coverage',float(not missing),f'Missing required stage spans={missing}')


def grade_precision(case,response,spans):
    # Unlabelled alternatives cannot honestly be graded as incorrect.
    field='expected_allowed_ids' if 'expected_allowed_ids' in case else (
        'expected_relevant_ids' if case.get('annotations',{}).get('relevance_labels_exhaustive') else None)
    if field is None or case['expected_status']!='ok':return None
    expected=set(case[field]);ids=[r.opportunity_id for r in response.recommendations[:3]]
    score=len([i for i in ids if i in expected])/len(ids) if ids and len(set(ids))==len(ids) else 0
    metric='final.allowed_precision_at_3' if field=='expected_allowed_ids' else 'final.topic_precision_at_3'
    return Grade(metric,score,f'ID label set={field}; correct={len(set(ids)&expected)}, returned={len(ids)}')


def grade_hit(case,response,spans):
    if case['expected_status']!='ok':return None
    expected=case.get('expected_allowed_ids',case.get('expected_relevant_ids'))
    if expected is None:return None
    ids={r.opportunity_id for r in response.recommendations[:3]}
    return Grade('final.hit_at_3',float(bool(ids & set(expected))),f'Expected at least one of {len(expected)} known correct IDs')


def grade_forbidden(case,response,spans):
    if 'forbidden_ids' not in case:return None
    bad={r.opportunity_id for r in response.recommendations}&set(case['forbidden_ids'])
    return Grade('final.forbidden',float(not bad),f'Forbidden returned={sorted(bad)}')


def grade_missing(case,response,spans):
    if 'expected_missing_fields' not in case:return None
    expected=set(case['expected_missing_fields']);got=set(response.missing_fields)
    return Grade('e2e.missing_fields',float(got==expected),f'Expected={sorted(expected)}, actual={sorted(got)}')


def _candidates(spans):
    return {c['opportunity_id']:c for c in outputs(spans,'fursah.candidate_check')}


def grade_hard_constraints(case,response,spans):
    if not response.recommendations:return None
    candidates=_candidates(spans)
    passed=all((c:=candidates.get(r.opportunity_id)) and
        c.get('constraint_decision') in {'constraints_satisfied','no_constraints_requested'} and
        c.get('eligibility_status')!='ineligible' for r in response.recommendations)
    constraints={**case.get('constraints',{}),**case.get('expected_effective_constraints',{})}
    details={v['opportunity_id']:v.get('details',{}) for v in outputs(spans,'fursah.details')}
    for rec in response.recommendations:
        d=details.get(rec.opportunity_id,{})
        for field,key in [('max_budget_sar','cost'),('max_duration_days','duration')]:
            if constraints.get(field) is not None:
                value=d.get(key)
                passed=passed and type(value) in (int,float) and math.isfinite(value) and value<=constraints[field]
        for field,key in [('delivery_modes','delivery_mode'),('opportunity_types','opportunity_type')]:
            if constraints.get(field):passed=passed and d.get(key) in constraints[field]
        if constraints.get('available_from'):
            passed=passed and bool(d.get('start_date')) and d['start_date']>=constraints['available_from']
        if constraints.get('available_to'):
            passed=passed and bool(d.get('end_date')) and d['end_date']<=constraints['available_to']
    return Grade('final.hard_constraints',float(bool(passed)),'Source gates plus independent numeric/category/date checks against returned details')


def grade_evidence(case,response,spans):
    if not response.recommendations:return None
    candidates=_candidates(spans)
    passed=all((c:=candidates.get(r.opportunity_id)) and r.evidence_version and
        c['evidence_version']==r.evidence_version and set(c['source_ids'])==set(r.source_ids)
        for r in response.recommendations)
    return Grade('final.evidence',float(bool(passed)),'Recommendation IDs, source ownership and evidence versions must match checked candidate')


def grade_details(case,response,spans):
    if not response.recommendations:return None
    details={v['opportunity_id']:v for v in outputs(spans,'fursah.details')}
    passed=True
    for r in response.recommendations:
        item=details.get(r.opportunity_id,{});d=item.get('details',{})
        passed=passed and item.get('http_status')==200 and d.get('evidence_version')==r.evidence_version and set(d.get('source_ids',[]))==set(r.source_ids)
        passed=passed and all(d.get(k)==getattr(r,k) for k in ('title','location','delivery_mode','deadline','application_status','opportunity_type'))
    return Grade('details.consistency',float(bool(passed)),'Current details must match recommendation facts and evidence version')


def grade_grounding(case,response,spans):
    if not response.recommendations:return None
    candidates=_candidates(spans);passed=True
    for r in response.recommendations:
        c=candidates.get(r.opportunity_id,{})
        sources=c.get('source_contents',{})
        quotes=c.get('evidence_quotes',[])
        passed=passed and bool(sources) and any(q and q in r.reason and any(q in text for text in sources.values()) for q in quotes)
    return Grade('final.grounded_reason',float(bool(passed)),'Reason must contain an exact checked source excerpt, not a generated claim')


@lru_cache(maxsize=1)
def _source_package():
    path=Path(__file__).resolve().parents[1]/'data/prepared/catalog.json'
    return json.loads(path.read_text(encoding='utf-8'))


def grade_source_availability(case,response,spans):
    if not response.recommendations:return None
    audit=audit_response(case,response.model_dump(mode='json'),_source_package())
    return Grade('source.availability',audit['score'],json.dumps(audit['violations'],ensure_ascii=False))


CRITICAL_METRICS={'e2e.status','understanding.constraints','e2e.missing_fields','final.allowed_precision_at_3','final.topic_precision_at_3',
    'final.hit_at_3','final.forbidden','final.hard_constraints','final.evidence','details.consistency','final.grounded_reason',
    'tracing.coverage','retrieval.target_coverage','source.availability'}
GRADERS=[grade_status,grade_interpretation,grade_recall,grade_ndcg,grade_precision,grade_hit,
    grade_forbidden,grade_missing,grade_hard_constraints,grade_evidence,grade_details,grade_grounding,
    grade_target_coverage,grade_instrumentation,grade_source_availability]
