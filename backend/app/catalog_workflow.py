"""Simple local RAG: checked query -> vector search -> rerank -> source checks."""
from __future__ import annotations

import asyncio
import math
import time

from .active_understanding import analyze_request, build_active_plan, PATTERNS
from .constraints import check_opportunity_constraints
from .eligibility import check_eligibility, select_eligibility_questions
from .infrastructure.errors import (
    DataAccessError, InvalidModelOutputError, ModelExecutionError, WorkflowBudgetExceededError,
)
from .infrastructure.local_inference import get_local_inference
from .instrumentation.spans import eval_span, record_output
from .request_plan import resolved_plan_inputs
from .request_requirements import RequestRequirements, TOOLS, check_requirements, normalized
from .schemas import DiscoveryResponse, Recommendation


NOTICE = 'النتائج من قاعدة بيانات فرصة المجهزة، مع الرجوع إلى أدلة كل إعلان.'


def _retrieve_and_rank(request, deps, plan):
    inputs = resolved_plan_inputs(request, plan)
    with get_local_inference().session() as runtime:
        with eval_span(deps.settings, 'fursah.embedding', **{'embedding.model':'BAAI/bge-m3'}) as span:
            vector = runtime.encode(inputs['semantic_query'])
            span.set_attribute('embedding.dimensions', len(vector))
        with eval_span(deps.settings, 'fursah.retrieval', **{'retrieval.limit':deps.settings.catalog_retrieval_limit}) as span:
            rows = deps.repository.search(vector)
            record_output(span, [r.details.opportunity_id for r in rows])
        with eval_span(deps.settings, 'fursah.rerank', **{'rerank.model':'BAAI/bge-reranker-v2-m3'}) as span:
            scores = runtime.score_pairs([(inputs['semantic_query'], row.topic.passage) for row in rows]) if rows else []
            if len(scores) != len(rows) or any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in scores):
                raise ModelExecutionError()
            record_output(span, [{'opportunity_id':r.details.opportunity_id,'score':score}
                for r,score in sorted(zip(rows,scores),key=lambda pair:(-pair[1],pair[0].details.opportunity_id))])
    ranked = sorted(zip(rows, scores), key=lambda pair: (-pair[1], pair[0].details.opportunity_id))
    checked = inputs['requirements']
    # Preserve the checked AND/OR scope. New tool aliases use PATTERNS below;
    # the existing evidence guard retains polarity checks for its known tools.
    requirements = RequestRequirements(tuple(t for t in checked['tools'] if t['tool'] in TOOLS),
        tuple(checked['activities']), checked['tool_mode'], tuple(checked['review_reasons']))
    accepted = set()
    for row, score in ranked:
        guard = check_requirements(requirements, row.topic)
        tools = [bool(PATTERNS[t['tool']].search(normalized(row.topic.passage)[0])) for t in plan['requirements']['tools']]
        tools_pass = not tools or (any(tools) if plan['requirements']['tool_mode'] == 'any' else all(tools))
        if (score >= deps.settings.catalog_min_rerank_score and tools_pass
                and guard['status'] not in {'mismatch', 'unknown', 'needs_review'}):
            accepted.add(row.details.opportunity_id)
        with eval_span(deps.settings, 'fursah.requirements') as span:
            record_output(span, {'opportunity_id':row.details.opportunity_id,
                'accepted':row.details.opportunity_id in accepted,'requirements_status':guard['status']})
    return [row for row, _ in ranked], accepted


def _finish(request, deps, plan, rows, accepted):
    inputs = resolved_plan_inputs(request, plan)
    evaluated, gates, available = [], {}, []
    for row in rows:
        details = row.details
        with eval_span(deps.settings, 'fursah.candidate_check') as span:
            constraints = check_opportunity_constraints(row.opportunity, row.sources, row.evidence,
                inputs['constraints'], expected_evidence_version=details.evidence_version,
                evaluation_time=deps.evaluation_time, required_locations=inputs['required_locations'])
            eligibility = check_eligibility(row.opportunity, row.sources, row.evidence, inputs['profile'],
                                           expected_evidence_version=details.evidence_version)
            if deps.settings.eval_telemetry_enabled:
                record_output(span, {'opportunity_id':details.opportunity_id,
                    'evidence_version':details.evidence_version,'source_ids':details.source_ids,
                    'constraint_decision':constraints['decision'],'eligibility_status':eligibility['status'],
                    'evidence_quotes':[quote for _,_,quote in row.topic.excerpts],
                    'source_contents':{sid:source['content'] for sid,source in row.sources.items()}})
        related = details.opportunity_id in accepted
        evaluated.append(eligibility)
        gates[details.opportunity_id] = {'evidence_version': details.evidence_version,
            'topic_decision': 'related' if related else 'unrelated',
            'constraint_decision': constraints['decision']}
        if (related and constraints['decision'] in {'constraints_satisfied', 'no_constraints_requested'}
                and eligibility['status'] != 'ineligible'):
            available.append((row, eligibility, constraints['location_preference']['matches']))
    question = select_eligibility_questions(evaluated, gates, inputs['profile'])
    common = {'request_id': request.request_id, 'interpreted_filters': plan['interpreted_filters']}
    if question['decision'] == 'ask_user':
        deps.repository.confirm_versions({question['selected_candidate_id']: question['evidence_version']})
        return DiscoveryResponse(**common, status='needs_info', message='نحتاج معلومة تؤثر في شرط قبول موثق.',
            missing_fields=question['missing_fields'], missing_explanations=question['missing_explanations'])
    # Stable sort keeps the rerank order within equal eligibility/preference groups.
    available.sort(key=lambda item: (item[1]['status'] != 'confirmed', item[2] is not True))
    recommendations = []
    for row, eligibility, _ in available[:3]:
        details = row.details
        quote = next(text for role, _, text in row.topic.excerpts if role == 'activity')
        caveats = list(dict.fromkeys([*details.data_warnings, *row.opportunity.get('data_notes', []),
            'المعلومات غير المذكورة تحتاج مراجعة المصدر.',
            'الأهلية غير مؤكدة عند نقص الشروط أو عدم تفسيرها.']))
        recommendations.append(Recommendation(
            **{key: getattr(details, key) for key in ('opportunity_id', 'evidence_version', 'title',
                'opportunity_type', 'location', 'delivery_mode', 'deadline', 'application_status', 'source_ids')},
            eligibility_status=eligibility['status'], reason='يدعم المصدر هذا النشاط: «' + quote + '»',
            caveats=caveats, relevance_score=None, next_action='راجع المصدر الرسمي والتفاصيل قبل البدء.'))
    deps.repository.confirm_versions({r.opportunity_id: r.evidence_version for r in recommendations})
    if recommendations:
        return DiscoveryResponse(**common, status='ok', message=NOTICE, recommendations=recommendations)
    return DiscoveryResponse(**common, status='no_match', message=NOTICE +
        ' لم نجد فرصة موثقة تطابق الطلب وقيوده في هذا النطاق؛ قد يكون السبب نقص معلومات التكلفة أو المواعيد أو الأهلية.')


async def discover_catalog(request, deps):
    if deps.settings.understanding_mode != 'active':
        raise ModelExecutionError()
    started = time.monotonic()
    try:
        async with asyncio.timeout(deps.settings.workflow_timeout_seconds):
            with eval_span(deps.settings, 'fursah.understanding', **{'llm.model':'google/gemini-3.8-flash'}) as span:
                proposal = await analyze_request(request, deps)
                try:
                    plan = build_active_plan(request, proposal)
                except (ValueError, KeyError, TypeError):
                    raise InvalidModelOutputError() from None
                record_output(span, {k:plan[k] for k in ('status','semantic_query','effective_constraints',
                    'required_locations','requirements','interpreted_filters')})
            deps.tracer.emit(request_id=request.request_id, step='active_request_plan_checked',
                component='gemini_grounded_v1', outcome=plan['status'], elapsed_ms=(time.monotonic()-started)*1000)
            if plan['status'] == 'constraint_conflict':
                from .request_plan import conflict_response
                return conflict_response(request, plan, request_id=request.request_id)
            if plan['status'] != 'resolved':
                return DiscoveryResponse(request_id=request.request_id, status='error',
                    error_code='FURSAH_QUERY_UNSUPPORTED', message='نحتاج صياغة أوضح للهدف والقيود؛ استخدم حدودًا مباشرة وتواريخ كاملة عند الحاجة.')
            rows, accepted = await asyncio.to_thread(_retrieve_and_rank, request, deps, plan)
            deps.tracer.emit(request_id=request.request_id, step='local_catalog_retrieved_and_reranked',
                component='catalog', outcome='success', elapsed_ms=(time.monotonic()-started)*1000,
                evidence_ids=[s for row in rows for s in row.details.source_ids])
            with eval_span(deps.settings, 'fursah.selection') as span:
                result = await asyncio.to_thread(_finish, request, deps, plan, rows, accepted)
                record_output(span, {'status':result.status.value,
                    'opportunity_ids':[r.opportunity_id for r in result.recommendations]})
                return result
    except TimeoutError:
        raise WorkflowBudgetExceededError() from None
