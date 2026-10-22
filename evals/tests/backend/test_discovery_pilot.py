"""Pipeline contracts with real source/check logic and deterministic model doubles.

These tests establish orchestration correctness, not semantic model accuracy.
"""
from contextlib import contextmanager
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
import unittest
import threading
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from app.main import app
from app.details import map_details
from app.infrastructure.config import PROJECT_ROOT, Settings
from app.infrastructure.dependencies import get_app_dependencies
from app.infrastructure.errors import DataAccessError, ModelExecutionError, WorkflowBudgetExceededError, WorkflowBusyError
from app.infrastructure.local_inference import LocalInference
from app.repository import RetrievedOpportunity
from app.topic_verifier import build_candidate
from app.workflow import _checked_topic_policy
from app.workflow import discover
from app.schemas import DiscoveryRequest


class FakeInference:
    def __init__(self, target='OPP-DEMO-004'):
        self.target = target
        self.calls = 0

    @contextmanager
    def session(self):
        yield self

    def encode(self, text):
        self.calls += 1
        return [1.0] + [0.0]*1023

    def score_pairs(self, pairs):
        return [.9 if ('Excel' in passage) == (self.target == 'OPP-DEMO-004') else .000001
                for _, passage in pairs]


def sample_rows():
    sample = json.loads((PROJECT_ROOT/'evals/archive/fixtures/linked-data.sample.json').read_text(encoding='utf-8'))
    docs = json.loads((PROJECT_ROOT/'evals/archive/reports/indexed-documents.json').read_text(encoding='utf-8'))
    result = []
    for doc in docs:
        opp = next(o for o in sample['opportunities'] if o['opportunity_id'] == doc['opportunity_id'])
        sources = {s['source_id']: s for s in sample['sources'] if s['source_id'] in opp['source_ids']}
        evidence = {e['evidence_id']: e for e in sample['evidence'] if e['opportunity_id'] == opp['opportunity_id']}
        excerpts = [dict(role='title' if p['role']=='title' else 'activity',source_id=p['source_id'],quote=p['text'])
                    for p in doc['text_parts'] if p['role'] in {'title','activity_description'}]
        links = sorted({e['source_id'] for e in excerpts})
        topic = build_candidate(opp['opportunity_id'], {s:sources[s] for s in links}, links, excerpts)
        result.append(RetrievedOpportunity(opp,sources,evidence,map_details(opp,sources,evidence),topic,.5))
    return result


class DiscoveryPilotTests(unittest.TestCase):
    def setUp(self):
        self.repo = Mock()
        self.repo.search.return_value = sample_rows()
        self.runtime = FakeInference()
        self.deps = replace(get_app_dependencies(), repository=self.repo,
            settings=Settings(_env_file=None, discovery_pilot_enabled=True,
                              evaluation_time=datetime(2026,10,21,12,tzinfo=timezone.utc)))
        app.dependency_overrides[get_app_dependencies] = lambda: self.deps
        self.addCleanup(app.dependency_overrides.clear)
        patcher = patch('app.workflow.get_local_inference', return_value=self.runtime)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def send(self, query='أبي فرص تحليل البيانات باستخدام Excel', constraints=None, **extra):
        return self.client.post('/api/v1/discover',json={'request_id':'pilot-unit', 'query':query,
            'profile':{},'constraints':constraints or {},**extra})

    def test_grounded_preview_does_not_invent_eligibility_or_percentage(self):
        response = self.send()
        self.assertEqual(response.status_code,200)
        data = response.json()
        self.assertEqual(data['status'],'ok')
        self.assertIn('وقت اختبار ثابت',data['message'])
        self.assertEqual(len(data['recommendations']),1)
        r = data['recommendations'][0]
        self.assertEqual(r['opportunity_id'],'OPP-DEMO-004')
        self.assertEqual(r['eligibility_status'],'uncertain')
        self.assertEqual(r['application_status'],'requires_verification')
        self.assertIsNone(r['relevance_score'])
        self.assertEqual(r['source_ids'],['SRC-0496','SRC-0497'])
        self.repo.confirm_versions.assert_called_once_with({r['opportunity_id']:r['evidence_version']})

    def test_unknown_cost_cannot_satisfy_zero_budget(self):
        data = self.send(constraints={'max_budget_sar':0}).json()
        self.assertEqual(data['status'],'no_match')
        self.assertEqual(data['recommendations'],[])
        self.assertEqual(data['missing_fields'],[])  # Source gap is not a profile question.

    def test_practical_alternative_is_recovered_only_by_a_passing_branch(self):
        def score(pairs):
            query=pairs[0][0]
            return [.9 if query=='تعلم Excel عمليًا' and 'Excel' in passage else .000001 for _,passage in pairs]
        with patch.object(self.runtime,'score_pairs',side_effect=score):
            data=self.send('أدور على فرصة لتعلم إكسل أو SQL بشكل عملي').json()
        self.assertEqual(data['status'],'ok')
        self.assertEqual([r['opportunity_id'] for r in data['recommendations']],['OPP-DEMO-004'])
        self.assertEqual(data['recommendations'][0]['eligibility_status'],'uncertain')

    def test_learning_purpose_does_not_bypass_unknown_hard_budget(self):
        data=self.send('أريد تجربة Excel أو Flutter ضمن فرصة للتعلم',constraints={'max_budget_sar':0}).json()
        self.assertEqual(data['status'],'no_match')
        self.assertEqual(data['missing_fields'],[])

    def test_unapproved_alternative_fails_before_model_scoring(self):
        from app.infrastructure.errors import EvidenceValidationError
        with patch('app.workflow.check_alternative_approval',side_effect=EvidenceValidationError()), \
             patch.object(self.runtime,'score_pairs') as scorer:
            response=self.send('أريد تعلم Excel أو SQL')
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['error_code'],'FURSAH_VALIDATION_ERROR')
        scorer.assert_not_called()

    def test_expired_deadline_wins_over_positive_topic(self):
        self.runtime.target = 'translation'
        data = self.send('أبي فرص ترجمة',constraints={'max_budget_sar':0}).json()
        self.assertEqual(data['status'],'no_match')

    def test_conflict_returns_before_any_model_or_database_call(self):
        data = self.send('أبي ورشة ترجمة عن بعد بالكامل',constraints={'delivery_modes':['in_person']}).json()
        self.assertEqual(data['status'],'needs_info')
        self.assertTrue(data['constraint_conflict'])
        self.assertEqual(self.runtime.calls,0)
        self.repo.search.assert_not_called()

    def test_unsupported_query_does_not_become_empty_recommendation(self):
        data = self.send('أبي ورشة الأسبوع الجاي').json()
        self.assertEqual(data['status'],'error')
        self.assertEqual(data['error_code'],'FURSAH_QUERY_UNSUPPORTED')
        self.assertEqual(self.runtime.calls,0)

    def test_query_override_is_temporary_and_retains_budget(self):
        body = {'query':'أبي ورشة ترجمة عن بعد بالكامل', 'profile':{},
                'constraints':{'delivery_modes':['in_person'],'max_budget_sar':0},'constraint_resolution':'query'}
        data = self.send(**body).json()
        self.assertNotEqual(data['status'],'needs_info')
        self.assertEqual(body['constraints']['delivery_modes'],['in_person'])
        self.assertTrue(any('مجانية' in f or '0' in f for f in data['interpreted_filters']))

    def test_model_failure_is_503_and_not_no_match(self):
        with patch.object(self.runtime,'encode',side_effect=ModelExecutionError()):
            response = self.send()
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['error_code'],'FURSAH_MODEL_ERROR')

    def test_changed_evidence_blocks_publication(self):
        self.repo.confirm_versions.side_effect = DataAccessError()
        response = self.send()
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['recommendations'],[])

    def test_invalid_model_score_is_not_treated_as_no_match(self):
        with patch.object(self.runtime,'score_pairs',return_value=[float('nan')]*4):
            response = self.send()
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['error_code'],'FURSAH_VALIDATION_ERROR')

    def test_changed_topic_binding_is_rejected(self):
        rows = sample_rows()
        candidates = [r.topic for r in rows]
        _checked_topic_policy(candidates)
        candidates[0] = replace(candidates[0],topic_evidence_version='sha256:changed')
        from app.infrastructure.errors import EvidenceValidationError
        with self.assertRaises(EvidenceValidationError):
            _checked_topic_policy(candidates)

    def test_pilot_never_claims_general_readiness(self):
        self.repo.is_ready.return_value = True
        response = self.client.get('/ready')
        self.assertEqual(response.status_code,503)
        self.assertFalse(response.json()['checks']['application'])

    def test_runtime_does_not_allow_overlapping_model_sessions(self):
        runtime = LocalInference()
        with runtime.session():
            with self.assertRaises(WorkflowBusyError):
                with runtime.session():
                    self.fail('Overlapping session')
        with runtime.session():
            pass

    def _with_skill_requirement(self):
        rows = sample_rows()
        row = rows[-1]
        source = {'source_id':'TEST-ELIG', 'content':'المهارات المطلوبة: Excel. لا توجد شروط إلزامية أخرى.'}
        row.sources[source['source_id']] = source
        row.opportunity['source_ids'].append(source['source_id'])
        for field, value, quote in [('mandatory_requirements', [], 'لا توجد شروط إلزامية أخرى.'),
                                    ('required_skills',['Excel'],'المهارات المطلوبة: Excel.')]:
            identifier = 'TEST-' + field
            row.evidence[identifier] = dict(evidence_id=identifier, source_id=source['source_id'],
                opportunity_id=row.details.opportunity_id, field=field, asserted_value=value, quote=quote)
            row.opportunity['facts'][field] = dict(status='known',value=value,evidence_ids=[identifier])
        rows[-1] = replace(row,details=map_details(row.opportunity,row.sources,row.evidence))
        self.repo.search.return_value = rows

    def test_actual_gates_select_only_actionable_missing_skill_then_resume(self):
        # Synthetic source update; not a change to the sample corpus or calibration.
        self._with_skill_requirement()
        question = self.send().json()
        self.assertEqual(question['status'],'needs_info')
        self.assertEqual(question['missing_fields'],['profile.skills'])
        answered = self.send(profile={'skills':[{'name':'Excel','level':None}]}).json()
        self.assertEqual(answered['status'],'ok')
        self.assertEqual(answered['recommendations'][0]['eligibility_status'],'confirmed')

    def test_explicit_absence_of_required_skill_excludes_candidate(self):
        self._with_skill_requirement()
        response = self.send(profile={'skills':[]}).json()
        self.assertEqual(response['status'],'no_match')


class WorkerCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_keeps_inference_locked_until_cpu_work_finishes(self):
        runtime = LocalInference()
        release = threading.Event()
        entered = threading.Event()
        repo = Mock()
        deps = replace(get_app_dependencies(), repository=repo,
            settings=Settings(_env_file=None,discovery_pilot_enabled=True,workflow_timeout_seconds=1),
            evaluation_time=datetime(2026,10,21,12,tzinfo=timezone.utc))
        request = DiscoveryRequest(request_id='timeout-unit',query='تحليل البيانات باستخدام Excel',profile={},constraints={})

        def slow_encode(text):
            entered.set()
            release.wait(5)
            return [1.0]+[0.0]*1023

        with patch('app.workflow.get_local_inference',return_value=runtime), patch.object(runtime,'encode',side_effect=slow_encode):
            try:
                task = asyncio.create_task(discover(request,deps))
                self.assertTrue(await asyncio.to_thread(entered.wait,2))
                with self.assertRaises(WorkflowBudgetExceededError):
                    await task
                with self.assertRaises(WorkflowBusyError):
                    with runtime.session():
                        self.fail('Timed-out CPU work still owns this lock')
                repo.search.assert_not_called()
            finally:
                release.set()
            for _ in range(100):
                if not runtime._lock.locked():
                    break
                await asyncio.sleep(.01)
            self.assertFalse(runtime._lock.locked())
