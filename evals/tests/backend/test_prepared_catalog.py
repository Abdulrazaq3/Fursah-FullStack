"""Local-catalog integrity, grounded understanding and retrieval/rerank contracts."""
import asyncio
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import Mock, patch

import httpx

from app.active_understanding import ActiveProposal, analyze_request, build_active_plan
from app.catalog_store import checked_package, package_version, vector_literal
from app.catalog_workflow import _retrieve_and_rank, discover_catalog
from app.dataset_preparation import prepare_catalog
from app.infrastructure.config import PROJECT_ROOT, Settings
from app.infrastructure.dependencies import get_app_dependencies, ModelClientConfig
from app.infrastructure.errors import InvalidModelOutputError, ModelExecutionError
from app.request_plan import interpret_query, resolved_plan_inputs
from app.schemas import DiscoveryRequest
from test_discovery_pilot import FakeInference, sample_rows


def request(query='أبي فرص Excel', **kwargs):
    return DiscoveryRequest(request_id='catalog-unit', query=query, profile={}, constraints={}, **kwargs)


def proposal(req):
    parsed = interpret_query(req.query)
    return ActiveProposal(topic='تعلم Excel', goal_quote=req.query,
        claims=[{k:c[k] for k in ('field','value','quote')} for c in parsed['claims']],
        tools=[{'name':'excel','quote':'Excel'}] if 'Excel' in req.query else [],
        tool_mode='all', needs_review=False)


class DatasetPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = json.loads((PROJECT_ROOT/'data/prepared/source_preparation.json').read_text(encoding='utf8'))
        cls.raw = [{k:r[k] for k in ('source_id','source_name','content','published_at')} for r in cls.helpers]

    def test_all_1000_sources_preserved_and_identified_without_fetching(self):
        package, report = prepare_catalog(self.raw, self.helpers)
        self.assertEqual(report['input_announcements'],1000)
        self.assertEqual(report['grouped_csv_opportunities'],900)
        self.assertEqual(report['quarantined_ambiguous_titles'],0)
        self.assertEqual({s['source_id']:s['content'] for s in package['sources']},
                         {s['source_id']:s['content'] for s in self.raw})
        self.assertEqual({sid for o in package['opportunities'] for sid in o['source_ids']},
                         {r['source_id'] for r in self.raw})
        checked_package(package)

    def test_quoted_publisher_is_not_a_second_activity_title(self):
        idx = next(i for i,r in enumerate(self.raw) if r['source_id']=='SRC-0008')
        package,_=prepare_catalog([self.raw[idx]],[self.helpers[idx]])
        o=package['opportunities'][0]
        self.assertEqual(o['facts']['title']['value'],'ترشيد المياه في المباني خطوة بخطوة')
        self.assertEqual(o['publication_state'],'active')

    def test_source_edits_and_duplicate_source_ids_are_rejected(self):
        helper=deepcopy(self.helpers[0]); helper['content']+='changed'
        with self.assertRaises(ValueError): prepare_catalog([self.raw[0]],[helper])
        with self.assertRaises(ValueError): prepare_catalog(self.raw[:2],[self.helpers[0]]*2)

    def test_same_url_from_different_publishers_does_not_merge(self):
        row=deepcopy(self.raw[0]); row.update(source_id='SECOND',source_name='جهة أخرى')
        helper=deepcopy(self.helpers[0]); helper.update(row)
        package,_=prepare_catalog([self.raw[0],row],[self.helpers[0],helper])
        self.assertEqual(len(package['opportunities']),2)
        checked_package(package)  # A URL is not a global identity.

    def test_conflicting_fee_is_preserved_not_overwritten(self):
        row=deepcopy(self.raw[0]); row.update(source_id='UPDATE',published_at='2026-10-19T12:00:00+03:00',
            content=row['content'].replace('المشاركة مجانية','رسوم المشاركة 50 ريالاً'))
        helper=deepcopy(self.helpers[0]); helper.update(row,fee_evidence='رسوم المشاركة 50 ريالاً',cost_sar=50)
        package,_=prepare_catalog([self.raw[0],row],[self.helpers[0],helper])
        self.assertEqual(package['opportunities'][0]['facts']['cost_sar']['status'],'conflicted')
        checked_package(package)

    def test_snapshot_accepts_more_than_four_and_detects_tampered_evidence(self):
        package=json.loads((PROJECT_ROOT/'data/prepared/catalog.json').read_text(encoding='utf8'))
        _,_,docs=checked_package(package)
        self.assertEqual(len(docs),913)
        package['evidence'][0]['quote']='not in the original source'
        with self.assertRaises(Exception): checked_package(package)

    def test_vector_dimension_and_normalization_checked(self):
        self.assertTrue(vector_literal([1.0]+[0.0]*1023).startswith('[1.0,'))
        for vector in ([1.0]*1024,[0.0]*1024,[1.0],[float('nan')]+[0.0]*1023):
            with self.assertRaises(Exception): vector_literal(vector)


class ActiveUnderstandingTests(unittest.TestCase):
    def test_grounded_constraints_are_merged_without_profile_mutation(self):
        req=request('أبي فرص Excel مجانية عن بعد')
        before=req.model_dump(mode='json')
        plan=build_active_plan(req,proposal(req))
        inputs=resolved_plan_inputs(req,plan)
        self.assertEqual(plan['status'],'resolved')
        self.assertEqual(inputs['constraints'].max_budget_sar,0)
        self.assertEqual(inputs['constraints'].delivery_modes,['online'])
        self.assertEqual(req.model_dump(mode='json'),before)

    def test_omitted_constraint_or_tool_cannot_silently_disappear(self):
        req=request('أبي فرص Excel مجانية')
        for field in ('claims','tools'):
            p=proposal(req).model_dump(); p[field]=[]
            with self.assertRaises(ValueError): build_active_plan(req,p)

    def test_invented_quote_rejected(self):
        req=request(); p=proposal(req).model_dump();p['goal_quote']='Python'
        with self.assertRaises(ValueError): build_active_plan(req,p)

    def test_negated_free_claim_is_not_zero_budget(self):
        req=request('أبي Excel مو مجاني');p=proposal(req).model_dump()
        p['claims']=[{'field':'max_budget_sar','value':0.0,'quote':'مو مجاني'}]
        with self.assertRaises(ValueError): build_active_plan(req,p)

    def test_changed_plan_cannot_be_used_downstream(self):
        req=request(); plan=build_active_plan(req,proposal(req));plan['semantic_query']='Python'
        with self.assertRaises(ValueError): resolved_plan_inputs(req,plan)

    def test_budget_upper_bound_merges_by_minimum(self):
        req=DiscoveryRequest(query='أبي Excel بميزانية لا تتجاوز 50 ريال',profile={},constraints={'max_budget_sar':100})
        plan=build_active_plan(req,proposal(req))
        self.assertEqual(plan['effective_constraints']['max_budget_sar'],50)

    def test_api_only_receives_request_context_and_one_structured_call(self):
        req=request();p=proposal(req); calls=[]
        def handle(r):
            calls.append(json.loads(r.content))
            return httpx.Response(200,json={'model':'google/gemini-3.8-flash','choices':[
                {'finish_reason':'stop','message':{'content':p.model_dump_json()}}]})
        deps=replace(get_app_dependencies(),model_config=ModelClientConfig('openrouter','google/gemini-3.8-flash',
            'unit-key','https://openrouter.ai/api/v1',40,0))
        actual=asyncio.run(analyze_request(req,deps,transport=httpx.MockTransport(handle)))
        self.assertEqual(actual,p);self.assertEqual(len(calls),1)
        data=json.loads(calls[0]['messages'][1]['content'])
        self.assertEqual(set(data),{'query','context','canonical_tool_keys'})
        self.assertEqual(calls[0]['reasoning']['effort'],'low')

    def test_provider_failure_is_not_no_match(self):
        deps=replace(get_app_dependencies(),model_config=ModelClientConfig('openrouter','google/gemini-3.8-flash',
            'unit-key','https://openrouter.ai/api/v1',40,0))
        with self.assertRaises(ModelExecutionError):
            asyncio.run(analyze_request(request(),deps,transport=httpx.MockTransport(lambda r:httpx.Response(503))))

    def test_empty_or_single_tool_conjunction_is_semantically_equivalent(self):
        for query in ['أبي أتعلم بناء وكلاء ذكاء اصطناعي','أبي فرص Excel']:
            req=request(query);p=proposal(req).model_dump();p['tool_mode']='any'
            plan=build_active_plan(req,p)
            self.assertEqual(plan['status'],'resolved')
            self.assertEqual(plan['requirements']['tool_mode'],'all')

    def test_multiple_tools_require_the_correct_conjunction(self):
        req=request('أبي Excel أو SQL');p=proposal(req).model_dump()
        p['tools'].append({'name':'sql','quote':'SQL'})
        with self.assertRaises(ValueError):build_active_plan(req,p)


class LocalRagTests(unittest.TestCase):
    def setUp(self):
        self.deps=replace(get_app_dependencies(),repository=Mock(),tracer=Mock(),
            settings=Settings(_env_file=None,catalog_mode='prepared',understanding_mode='active'),
            evaluation_time=datetime(2026,10,22,12,tzinfo=timezone.utc))
        self.deps.repository.search.return_value=sample_rows()

    def test_reranker_changes_vector_order_and_tool_guard_checks_passage(self):
        req=request(); plan=build_active_plan(req,proposal(req))
        runtime=FakeInference()
        with patch('app.catalog_workflow.get_local_inference',return_value=runtime):
            rows,accepted=_retrieve_and_rank(req,self.deps,plan)
        self.assertEqual(rows[0].details.opportunity_id,'OPP-DEMO-004')
        self.assertEqual(accepted,{'OPP-DEMO-004'})
        self.deps.repository.search.assert_called_once()

    def test_no_second_model_call_or_source_fetch_after_understanding(self):
        req=request(); runtime=FakeInference()
        with patch('app.catalog_workflow.analyze_request',return_value=proposal(req)) as understanding, \
             patch('app.catalog_workflow.get_local_inference',return_value=runtime), \
             patch('httpx.AsyncClient',side_effect=AssertionError('No external lookup in local retrieval')):
            response=asyncio.run(discover_catalog(req,self.deps))
        self.assertEqual(response.status,'ok');understanding.assert_awaited_once()
        self.assertEqual(response.recommendations[0].opportunity_id,'OPP-DEMO-004')
        self.deps.repository.confirm_versions.assert_called_once()

    def test_conflict_returns_before_embedding_and_reranking(self):
        req=DiscoveryRequest(request_id='catalog-conflict',query='أبي Excel عن بعد',profile={},constraints={'delivery_modes':['in_person']})
        with patch('app.catalog_workflow.analyze_request',return_value=proposal(req)), \
             patch('app.catalog_workflow.get_local_inference') as inference:
            response=asyncio.run(discover_catalog(req,self.deps))
        self.assertEqual(response.status,'needs_info');self.assertTrue(response.constraint_conflict)
        inference.assert_not_called()

    def test_unknown_cost_does_not_satisfy_free_request(self):
        req=DiscoveryRequest(request_id='catalog-free',query='أبي فرص Excel',profile={},constraints={'max_budget_sar':0})
        with patch('app.catalog_workflow.analyze_request',return_value=proposal(req)), \
             patch('app.catalog_workflow.get_local_inference',return_value=FakeInference()):
            response=asyncio.run(discover_catalog(req,self.deps))
        self.assertEqual(response.status,'no_match')

    def test_tool_alternatives_keep_or_after_constraint_removal(self):
        req=request('أبي تعلم Excel أو SQL')
        p=proposal(req).model_dump()
        p['tools'].append({'name':'sql','quote':'SQL'});p['tool_mode']='any'
        plan=build_active_plan(req,p)
        with patch('app.catalog_workflow.get_local_inference',return_value=FakeInference()):
            _,accepted=_retrieve_and_rank(req,self.deps,plan)
        self.assertEqual(accepted,{'OPP-DEMO-004'})

    def test_ranking_does_not_use_an_uncalibrated_probability_cutoff(self):
        req=request();plan=build_active_plan(req,proposal(req));runtime=FakeInference()
        runtime.score_pairs=lambda pairs:[.0005 if 'Excel' in p else .000001 for _,p in pairs]
        with patch('app.catalog_workflow.get_local_inference',return_value=runtime):
            rows,accepted=_retrieve_and_rank(req,self.deps,plan)
        self.assertEqual(rows[0].details.opportunity_id,'OPP-DEMO-004')
        self.assertEqual(accepted,{'OPP-DEMO-004'})


if __name__=='__main__': unittest.main()
