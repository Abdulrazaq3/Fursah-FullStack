"""Opt-in integration on four prepared records; not general readiness."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time

from .constraints import check_opportunity_constraints
from .alternative_approval import check_alternative_approval
from .eligibility import check_eligibility, select_eligibility_questions
from .infrastructure.config import PROJECT_ROOT
from .infrastructure.reference_paths import reference_path
from .infrastructure.dependencies import AppDependencies
from .infrastructure.errors import EvidenceValidationError, WorkflowBudgetExceededError
from .infrastructure.local_inference import get_local_inference
from .request_plan import build_request_plan, conflict_response, resolved_plan_inputs
from .request_requirements import verify_with_requirements
from .normalized_alternatives_v31 import plan_normalized_alternatives, verify_alternatives
from .schemas import DiscoveryRequest, DiscoveryResponse, Recommendation
from .topic_verifier import TopicPolicy


def application_is_ready(deps: AppDependencies) -> bool:
    # Integration alone does not establish general accuracy or corpus readiness.
    return False


def _notice(deps):
    text = 'تشغيل تجريبي على أربع فرص من العينة المجهزة؛ الأهلية وفتح التسجيل يحتاجان تحققًا.'
    if deps.settings.evaluation_time:
        text += ' وقت اختبار ثابت: ' + deps.evaluation_time.isoformat() + '.'
    return text


def _checked_topic_policy(candidates):
    try:
        policy = json.loads(reference_path('examples/discovery-pilot-policy.sample.json').read_text(encoding='utf-8'))
        prior_bytes = reference_path('results/relevance-expanded-v1-policy.json').read_bytes()
        if (hashlib.sha256(prior_bytes).hexdigest() != policy['prior_policy_sha256']
                or policy['policy'] != json.loads(prior_bytes)['policy']):
            raise ValueError('Pilot thresholds must match the frozen experiment')
        expected = policy['candidate_topic_versions']
        if any(expected.get(c.opportunity_id) != c.topic_evidence_version for c in candidates):
            raise ValueError('Uncalibrated topic input')
        return TopicPolicy(**policy['policy']), expected
    except (ValueError, KeyError, OSError, TypeError) as exc:
        raise EvidenceValidationError() from exc


def _run(request, deps, plan):
    started = time.monotonic()

    def mark(step, outcome='success', evidence_ids=None):
        if time.monotonic() - started >= deps.settings.workflow_timeout_seconds:
            raise WorkflowBudgetExceededError()
        deps.tracer.emit(request_id=request.request_id, step=step, component='discovery_pilot',
                         outcome=outcome, elapsed_ms=(time.monotonic()-started)*1000,
                         evidence_ids=evidence_ids)

    inputs = resolved_plan_inputs(request, plan)
    with get_local_inference().session() as runtime:
        vector = runtime.encode(inputs['semantic_query'])
        mark('query_embedded')
        rows = deps.repository.search(vector)
        mark('candidates_retrieved', evidence_ids=[s for r in rows for s in r.details.source_ids])
        try:
            candidates = [r.topic for r in rows]
            policy, expected = _checked_topic_policy(candidates)
            alternative_plan = plan_normalized_alternatives(inputs['semantic_query'])

            def score_with_budget(pairs):
                mark('semantic_pass_started')
                scores = runtime.score_pairs(pairs)
                mark('semantic_pass_finished')
                return scores

            if alternative_plan.branches:
                check_alternative_approval(candidates, policy)
                topics = verify_alternatives(inputs['semantic_query'], candidates, expected,
                    policy, score_with_budget)['decisions']
                mark('literal_alternatives_checked', outcome='approved_v3.1')
            else:
                _, topics = verify_with_requirements(inputs['semantic_query'], candidates, expected,
                    policy, score_with_budget)
        except (ValueError, KeyError, OSError, TypeError) as exc:
            raise EvidenceValidationError() from exc
        mark('topic_and_requirements_checked')
        by_id = {t['opportunity_id']: t for t in topics}
        evaluated, gates, ready = [], {}, []
        for row in rows:
            d = row.details
            constraints = check_opportunity_constraints(row.opportunity, row.sources, row.evidence,
                inputs['constraints'], expected_evidence_version=d.evidence_version,
                evaluation_time=deps.evaluation_time, required_locations=inputs['required_locations'])
            eligibility = check_eligibility(row.opportunity, row.sources, row.evidence, inputs['profile'],
                                            expected_evidence_version=d.evidence_version)
            topic = by_id[d.opportunity_id]
            gates[d.opportunity_id] = {'evidence_version': d.evidence_version,
                'topic_decision': topic['decision'], 'constraint_decision': constraints['decision']}
            evaluated.append(eligibility)
            if (topic['decision'] == 'related' and constraints['decision'] in
                    {'constraints_satisfied', 'no_constraints_requested'} and eligibility['status'] != 'ineligible'):
                ranking_score = max([topic['score']] + [p['score'] for p in topic.get('branch_decisions', [])
                                                       if p['decision'] == 'related'])
                ready.append((row, eligibility, ranking_score, constraints['location_preference']['matches']))
            mark('candidate_checked', outcome=f"{d.opportunity_id}:{topic['decision']}:{constraints['decision']}:{eligibility['status']}",
                 evidence_ids=d.source_ids)
        question = select_eligibility_questions(evaluated, gates, inputs['profile'])
        common = dict(request_id=request.request_id, interpreted_filters=plan['interpreted_filters'])
        if question['decision'] == 'ask_user':
            deps.repository.confirm_versions({question['selected_candidate_id']: question['evidence_version']})
            mark('question_evidence_confirmed')
            return DiscoveryResponse(**common, status='needs_info',
                message=_notice(deps) + ' نحتاج معلومات تؤثر في شرط قبول موثق.',
                missing_fields=question['missing_fields'], missing_explanations=question['missing_explanations'])
        ready.sort(key=lambda r: (r[1]['status'] != 'confirmed', -r[2], r[3] is not True, r[0].details.opportunity_id))
        recommendations = []
        for row, eligibility, _, _ in ready[:3]:
            d = row.details
            activity = next(quote for role, _, quote in row.topic.excerpts if role == 'activity')
            caveats = ['فتح التسجيل حاليًا غير متحقق؛ راجع المصدر قبل اتخاذ قرار.']
            if eligibility['status'] == 'uncertain':
                caveats.append('الأهلية غير محسومة من المعلومات الموثقة؛ هذه معاينة لفرصة مرتبطة ببحثك.')
            caveats.extend(d.data_warnings)
            recommendations.append(Recommendation(
                **{k: getattr(d, k) for k in ('opportunity_id', 'evidence_version', 'title', 'opportunity_type',
                   'location', 'delivery_mode', 'deadline', 'application_status', 'source_ids')},
                eligibility_status=eligibility['status'], reason='من النشاط الموثق في المصدر: «' + activity + '»',
                caveats=list(dict.fromkeys(caveats)), relevance_score=None,
                next_action='اطلع على التفاصيل وتحقق من شروط القبول وفتح التسجيل من الجهة.'))
        deps.repository.confirm_versions({r.opportunity_id: r.evidence_version for r in recommendations})
        mark('response_evidence_confirmed')
        if recommendations:
            return DiscoveryResponse(**common, status='ok', message=_notice(deps), recommendations=recommendations)
        return DiscoveryResponse(**common, status='no_match', message=_notice(deps) +
            ' لم تتجاوز أي فرصة في العينة فحوص الصلة والقيود والأهلية؛ قد يكون السبب نقص معلومات المصدر. لا يشمل هذا الحكم بقية البيانات الخام.')


async def discover(request: DiscoveryRequest, deps: AppDependencies) -> DiscoveryResponse:
    if deps.settings.catalog_mode == 'prepared':
        from .catalog_workflow import discover_catalog
        return await discover_catalog(request, deps)
    if not deps.settings.discovery_pilot_enabled:
        raise NotImplementedError('Discovery pilot is disabled')
    plan = build_request_plan(request)
    deps.tracer.emit(request_id=request.request_id, step='request_plan_checked',
                     component='discovery_pilot', outcome=plan['status'])
    if plan['status'] == 'constraint_conflict':
        response = conflict_response(request, plan, request_id=request.request_id)
        response.message = _notice(deps) + ' ' + response.message
        return response
    if plan['status'] != 'resolved':
        return DiscoveryResponse(request_id=request.request_id, status='error', error_code='FURSAH_QUERY_UNSUPPORTED',
            message=_notice(deps) + ' صياغة البحث تتجاوز الفهم المتحقق في هذه التجربة. اذكر الموضوع والقيود مباشرة، واستخدم تواريخ محددة عند الحاجة.')
    try:
        return await asyncio.wait_for(asyncio.to_thread(_run, request, deps, plan),
                                      timeout=deps.settings.workflow_timeout_seconds)
    except TimeoutError as exc:
        raise WorkflowBudgetExceededError() from exc
