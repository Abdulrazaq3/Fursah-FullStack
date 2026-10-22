"""One resolved request must preserve constraints, provenance and the saved profile."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import unittest

from app.constraints import check_opportunity_constraints
from app.eligibility import check_eligibility
from app.request_plan import (build_request_plan, conflict_response, fingerprint,
                              interpret_query, resolved_plan_inputs)
from app.schemas import DiscoveryRequest
from app.request_requirements import verify_with_requirements
from app.topic_verifier import TopicPolicy, build_candidate

ROOT = Path(__file__).resolve().parents[3]


class RequestPlanTests(unittest.TestCase):
    def request(self, query='أبي ورشة ترجمة مجانية وعن بعد بالكامل', *, constraints=None, profile=None, resolution=None):
        return DiscoveryRequest(query=query, constraints=constraints or {}, profile=profile or {}, constraint_resolution=resolution)

    def test_all_three_numeric_limit_states_and_inclusive_intersection(self):
        for saved, query, expected in [(None, 50, 50), (0, 50, 0), (100, 50, 50), (50, 100, 50), (50, 50, 50)]:
            with self.subTest(saved=saved, query=query):
                plan = build_request_plan(self.request(f'ورشة ترجمة بميزانية لا تتجاوز {query} ريال', constraints={'max_budget_sar': saved}))
                self.assertEqual(plan['status'], 'resolved')
                self.assertEqual(plan['effective_constraints']['max_budget_sar'], expected)

    def test_compatible_type_and_mode_sets_are_intersected(self):
        plan = build_request_plan(self.request('ورشة أو دورة ترجمة حضورية أو عن بعد بالكامل',
            constraints={'opportunity_types': ['course'], 'delivery_modes': ['online', 'hybrid']}))
        self.assertEqual(plan['effective_constraints']['opportunity_types'], ['course'])
        self.assertEqual(plan['effective_constraints']['delivery_modes'], ['online'])

    def test_disjoint_sets_have_no_executable_inputs_before_a_choice(self):
        request = self.request(constraints={'delivery_modes': ['in_person']})
        plan = build_request_plan(request)
        self.assertEqual(plan['status'], 'constraint_conflict')
        self.assertIsNone(plan['effective_constraints'])
        self.assertIsNone(plan['required_locations'])
        with self.assertRaisesRegex(ValueError, 'unresolved_request_plan'):
            resolved_plan_inputs(request, plan)

    def test_source_choice_only_resolves_conflicting_groups_and_never_mutates_inputs(self):
        for choice, expected in [('profile', ['in_person']), ('query', ['online'])]:
            request = self.request(constraints={'delivery_modes': ['in_person'], 'max_duration_days': 2}, resolution=choice)
            original = request.model_dump()
            plan = build_request_plan(request)
            effective = plan['effective_constraints']
            self.assertEqual(effective['delivery_modes'], expected)
            self.assertEqual(effective['max_budget_sar'], 0)
            self.assertEqual(effective['max_duration_days'], 2)
            self.assertEqual(request.model_dump(), original)
            inputs = resolved_plan_inputs(request, plan)
            inputs['profile'].city = 'جدة'
            inputs['constraints'].max_budget_sar = 900
            self.assertEqual(request.model_dump(), original)

    def test_source_choice_does_not_remove_compatible_query_limits(self):
        request = self.request('ورشة ترجمة مجانية', constraints={'max_budget_sar': 100}, resolution='profile')
        plan = build_request_plan(request)
        self.assertEqual(plan['effective_constraints']['max_budget_sar'], 0)
        self.assertFalse(plan['conflicts'])

    def test_availability_intersection_is_inclusive_and_conflicting_bundle_is_atomic(self):
        constraints = {'available_from': '2026-12-01', 'available_to': '2026-12-10'}
        query = 'ورشة ترجمة من 2026-12-10 إلى 2026-12-20'
        plan = build_request_plan(self.request(query, constraints=constraints))
        self.assertEqual(plan['effective_constraints']['available_from'], '2026-12-10')
        self.assertEqual(plan['effective_constraints']['available_to'], '2026-12-10')
        later = 'ورشة ترجمة مجانية من 2027-01-01 إلى 2027-01-10'
        for choice, expected in [('profile', ('2026-12-01', '2026-12-10')), ('query', ('2027-01-01', '2027-01-10'))]:
            plan = build_request_plan(self.request(later, constraints=constraints, resolution=choice))
            self.assertEqual((plan['effective_constraints']['available_from'], plan['effective_constraints']['available_to']), expected)
            self.assertEqual(plan['effective_constraints']['max_budget_sar'], 0)

    def test_city_preferences_are_soft_and_home_city_never_becomes_a_filter(self):
        plan = build_request_plan(self.request('ورشة ترجمة أفضل الرياض', profile={'city': 'تبوك'}, constraints={'location_preference': ['جدة']}))
        self.assertEqual(plan['effective_constraints']['location_preference'], ['جدة', 'الرياض'])
        self.assertEqual(plan['required_locations'], [])
        hard = build_request_plan(self.request('ورشة ترجمة في الرياض فقط', profile={'city': 'جدة'}))
        self.assertEqual(hard['required_locations'], ['الرياض'])

    def test_rejected_query_constraints_do_not_reappear_in_semantic_query(self):
        plan = build_request_plan(self.request(constraints={'delivery_modes': ['in_person']}, resolution='profile'))
        self.assertIn('ترجمة', plan['semantic_query'])
        self.assertNotIn('عن بعد', plan['semantic_query'])
        self.assertNotIn('مجانية', plan['semantic_query'])
        self.assertIn('عن بعد', plan['original_query'])

    def test_budget_negation_is_scoped_but_other_negation_and_history_abstain(self):
        good = build_request_plan(self.request('ورشة ترجمة بميزانية لا تتجاوز 50 ريال'))
        self.assertEqual(good['status'], 'resolved')
        for query in ('ورشة ترجمة ما أبي مجانية', 'ورشة ترجمة مو عن بعد بالكامل',
                      'كنت أفضل الرياض لورشة ترجمة', 'أفضل ورشة ترجمة', 'ورشة ترجمة الشهر القادم'):
            with self.subTest(query=query):
                plan = build_request_plan(self.request(query, resolution='profile'))
                self.assertEqual(plan['status'], 'requires_interpretation')
                self.assertIsNone(plan['effective_constraints'])

    def test_unsupported_and_scope_is_not_silently_turned_into_or(self):
        plan = build_request_plan(self.request('ورشة ودورة ترجمة'))
        self.assertEqual(plan['status'], 'requires_interpretation')
        plan = build_request_plan(self.request('ورشة Excel أو SQL'))
        self.assertEqual(plan['status'], 'resolved')
        self.assertEqual(plan['requirements']['tool_mode'], 'any')

    def test_invalid_or_multiple_query_values_are_not_repaired_silently(self):
        for query in ('ورشة ترجمة مجانية بميزانية لا تتجاوز 100 ريال',
                      'ورشة ترجمة مدتها لا تتجاوز 0 أيام',
                      'ورشة ترجمة من 2026-12-30 إلى 2026-12-01',
                      'ورشة ترجمة من 2026-02-30 إلى 2026-03-10'):
            with self.subTest(query=query):
                self.assertEqual(build_request_plan(self.request(query))['status'], 'requires_interpretation')

    def test_original_spans_survive_diacritics_and_arabic_digits(self):
        request = self.request('أبي وَرْشَة ترجمة مَجَّانية وعن بُعد بالكامل')
        plan = build_request_plan(request)
        self.assertEqual(plan['status'], 'resolved')
        for claim in plan['query_claims']:
            self.assertEqual(request.query[claim['start']:claim['end']], claim['quote'])
        plan = build_request_plan(self.request('ورشة ترجمة بميزانية لا تتجاوز ٥٠٫٢٥ ريال'))
        self.assertEqual(plan['effective_constraints']['max_budget_sar'], 50.25)

    def test_missing_topic_can_use_only_declared_major_or_interests(self):
        no_context = build_request_plan(self.request('ورشة مجانية', profile={'city': 'الرياض'}))
        self.assertEqual(no_context['status'], 'requires_interpretation')
        context = build_request_plan(self.request('ورشة مجانية', profile={'field_of_study': 'الترجمة'}))
        self.assertEqual(context['status'], 'resolved')
        self.assertEqual(context['semantic_query'], 'الترجمة')
        self.assertEqual(context['topic_origin'], 'profile_context')

    def test_proposed_plan_cannot_omit_change_or_invent_supported_claims(self):
        request = self.request()
        proposal = interpret_query(request.query)
        good = build_request_plan(request, interpretation=proposal)
        self.assertEqual(good, build_request_plan(request))
        for modify in ('omit', 'change', 'quote', 'add'):
            bad = deepcopy(proposal)
            if modify == 'omit':bad['claims'].pop()
            elif modify == 'change':bad['claims'][0]['value'] = ['internship']
            elif modify == 'quote':bad['claims'][0]['quote'] = 'اقتباس مختلق'
            else:bad['claims'].append(deepcopy(bad['claims'][0]))
            with self.subTest(modify=modify), self.assertRaisesRegex(ValueError, 'unsupported_or_missing_query_claim'):
                build_request_plan(request, interpretation=bad)

    def test_model_declarations_cannot_override_review_status_or_change_topic(self):
        request = self.request('ورشة ترجمة مو مجانية')
        proposal = interpret_query(request.query)
        proposal.update(status='resolved', review_reasons=[], semantic_query='طب بشري')
        plan = build_request_plan(request, interpretation=proposal)
        self.assertEqual(plan['status'], 'requires_interpretation')
        self.assertNotEqual(plan['semantic_query'], 'طب بشري')

    def test_stale_request_or_interpretation_and_tampered_plan_are_rejected(self):
        request = self.request()
        plan = build_request_plan(request)
        changed = request.model_copy(deep=True)
        changed.profile.city = 'جدة'
        with self.assertRaisesRegex(ValueError, 'stale_request_plan'):
            resolved_plan_inputs(changed, plan)
        changed = deepcopy(plan)
        changed['effective_constraints']['max_budget_sar'] = 1000
        changed['plan_version'] = fingerprint({k: v for k, v in changed.items() if k != 'plan_version'})
        with self.assertRaisesRegex(ValueError, 'request_plan_changed'):
            resolved_plan_inputs(request, changed)
        with self.assertRaisesRegex(ValueError, 'stale_query_interpretation'):
            build_request_plan(self.request('دورة ترجمة'), interpretation=interpret_query(request.query))

    def test_conflict_response_uses_existing_buttons_contract_and_readable_explanations(self):
        request = self.request(constraints={'delivery_modes': ['in_person']})
        plan = build_request_plan(request)
        response = conflict_response(request, plan, request_id='conflict-test')
        self.assertEqual(response.status.value, 'needs_info')
        self.assertTrue(response.constraint_conflict)
        self.assertEqual(response.missing_fields, ['constraints.delivery_modes'])
        self.assertFalse(response.recommendations)
        explanation = ' '.join(response.missing_explanations)
        self.assertIn('حضوري', explanation)
        self.assertIn('عن بعد', explanation)
        self.assertNotIn('delivery_modes', explanation)

    def test_uninterpreted_query_is_not_misrepresented_as_a_profile_edit_question(self):
        request = self.request('ورشة ترجمة الشهر القادم')
        plan = build_request_plan(request)
        self.assertEqual(plan['missing_fields'], [])
        with self.assertRaises(ValueError):
            conflict_response(request, plan, request_id='wrong')

    def test_plan_flows_into_real_sample_constraints_and_keeps_unknown_eligibility(self):
        sample = json.loads((ROOT / 'evals/archive/fixtures/linked-data.sample.json').read_text(encoding='utf-8'))
        opportunity = next(o for o in sample['opportunities'] if o['opportunity_id'] == 'OPP-DEMO-001')
        sources = {s['source_id']: s for s in sample['sources'] if s['source_id'] in opportunity['source_ids']}
        evidence = {e['evidence_id']: e for e in sample['evidence'] if e['opportunity_id'] == opportunity['opportunity_id']}
        versions = json.loads((ROOT / 'evals/archive/reports/indexed-documents.json').read_text(encoding='utf-8'))
        version = next(v['evidence_version'] for v in versions if v['opportunity_id'] == opportunity['opportunity_id'])
        for choice, expected in [('profile', 'excluded'), ('query', 'constraints_satisfied')]:
            request = self.request(constraints={'delivery_modes': ['in_person']}, resolution=choice)
            plan = build_request_plan(request)
            inputs = resolved_plan_inputs(request, plan)
            checked = check_opportunity_constraints(opportunity, sources, evidence, inputs['constraints'],
                required_locations=inputs['required_locations'], expected_evidence_version=version,
                evaluation_time=datetime.fromisoformat('2026-10-18T12:00:00+03:00'))
            self.assertEqual(checked['decision'], expected)
            eligibility = check_eligibility(opportunity, sources, evidence, inputs['profile'], expected_evidence_version=version)
            self.assertEqual(eligibility['status'], 'uncertain')

    def test_provenance_covers_all_effective_constraint_fields(self):
        plan = build_request_plan(self.request())
        fields = {p['field'] for p in plan['provenance']}
        self.assertTrue(set(plan['effective_constraints']) <= fields)
        self.assertIn('required_locations', fields)

    def test_tool_or_survives_the_semantic_query_and_downstream_verifier(self):
        title, activity = 'استعلامات SQL', 'طرح الأسئلة على الجداول'
        source = {'S': {'source_id': 'S', 'content': title + '. ' + activity}}
        candidate = build_candidate('SQL-TEST', source, ['S'], [
            {'role': 'title', 'source_id': 'S', 'quote': title},
            {'role': 'activity', 'source_id': 'S', 'quote': activity}])
        for query in ('ورشة Excel أو SQL', 'ورشة أو دورة Excel أو SQL'):
            with self.subTest(query=query):
                plan = build_request_plan(self.request(query))
                self.assertEqual(plan['status'], 'resolved')
                requirements, checked = verify_with_requirements(plan['semantic_query'], [candidate],
                    {'SQL-TEST': candidate.topic_evidence_version}, TopicPolicy(0.7, 0.3), lambda pairs: [0.99])
                self.assertEqual(requirements.tool_mode, 'any')
                self.assertEqual(checked[0]['decision'], 'related')


if __name__ == '__main__':
    unittest.main()
