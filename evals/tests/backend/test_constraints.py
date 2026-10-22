"""Constraint decisions must preserve evidence, uncertainty and public semantics."""
from copy import deepcopy
from datetime import datetime
import json
import unittest

from app.constraints import check_opportunity_constraints
from app.details import map_details
from app.infrastructure.errors import DataAccessError
from app.schemas import SearchConstraints


class ConstraintTests(unittest.TestCase):
    def record(self, **values):
        fields = {'title': 'Synthetic test only', 'cost_sar': 0, 'delivery_mode': 'online',
                  'physical_attendance_required': False, 'start_date': '2026-12-10',
                  'end_date': '2026-12-12', 'duration_days': 3, 'location': 'الرياض',
                  'deadline': {'date': '2026-11-01', 'time': None, 'timezone': None, 'precision': 'date'}}
        fields.update(values)
        record = ({'opportunity_id': 'TEST', 'source_ids': ['S'], 'facts': {}},
                  {'S': {'source_id': 'S', 'content': ''}}, {})
        for name, value in fields.items():
            self.set_fact(record, name, value)
        return record

    def set_fact(self, record, name, value, status='known', alternatives=None):
        opportunity, sources, evidence = record
        refs = []
        for assertion in alternatives if alternatives is not None else ([value] if status == 'known' else []):
            identifier = f'E{len(evidence)}'
            quote = f'{name}: {json.dumps(assertion, ensure_ascii=False)}'
            sources['S']['content'] += quote + '\n'
            evidence[identifier] = {'evidence_id': identifier, 'source_id': 'S', 'opportunity_id': 'TEST',
                                    'field': name, 'quote': quote, 'asserted_value': assertion}
            refs.append(identifier)
        opportunity['facts'][name] = {'status': status, 'value': value, 'evidence_ids': refs}

    def check(self, record=None, *, at='2026-10-18T12:00:00+03:00', cities=(), **constraints):
        record = record or self.record()
        return check_opportunity_constraints(*record, SearchConstraints(**constraints),
            expected_evidence_version=map_details(*record).evidence_version,
            evaluation_time=datetime.fromisoformat(at), required_locations=cities)

    def status(self, output, name):
        return next(c['status'] for c in output['checks'] if c['name'] == name)

    def test_zero_unknown_and_conflicted_cost_are_distinct(self):
        self.assertEqual(self.check(max_budget_sar=0)['decision'], 'constraints_satisfied')
        for state, alternatives in [('unknown', []), ('conflicted', [0, 100])]:
            record = self.record()
            self.set_fact(record, 'cost_sar', None, state, alternatives)
            output = self.check(record, max_budget_sar=0)
            self.assertEqual(output['decision'], 'needs_source_info')
            self.assertEqual(self.status(output, 'budget'), state)
            self.assertFalse(output['user_missing_fields'])

    def test_money_limit_is_inclusive_and_no_limit_is_not_zero(self):
        record = self.record(cost_sar=100.25)
        self.assertEqual(self.check(record, max_budget_sar=100.25)['decision'], 'constraints_satisfied')
        self.assertEqual(self.check(record, max_budget_sar=100.24)['decision'], 'excluded')
        self.assertEqual(self.check(record)['decision'], 'no_constraints_requested')

    def test_online_label_does_not_override_required_physical_attendance(self):
        output = self.check(self.record(physical_attendance_required=True), delivery_modes=['online'])
        self.assertEqual(output['decision'], 'excluded')
        self.assertEqual(self.status(output, 'delivery_mode'), 'passed')
        self.assertEqual(self.status(output, 'remote_attendance'), 'failed')

    def test_unknown_attendance_is_not_remote_permission(self):
        record = self.record()
        del record[0]['facts']['physical_attendance_required']
        output = self.check(record, delivery_modes=['online'])
        self.assertEqual(output['decision'], 'needs_source_info')
        self.assertIn('physical_attendance_required', output['missing_source_fields'])

    def test_explicitly_denied_or_conflicted_remote_permission_blocks_confirmation(self):
        record = self.record(remote_participation_allowed=False)
        self.assertEqual(self.check(record, delivery_modes=['online'])['decision'], 'excluded')
        self.set_fact(record, 'remote_participation_allowed', None, 'conflicted', [True, False])
        output = self.check(record, delivery_modes=['online'])
        self.assertEqual(output['decision'], 'needs_source_info')
        self.assertIn('remote_participation_allowed', output['conflicting_source_fields'])

    def test_delivery_alternatives_are_not_intersected_and_hybrid_is_not_online(self):
        record = self.record(delivery_mode='hybrid', physical_attendance_required=True)
        self.assertEqual(self.check(record, delivery_modes=['online', 'hybrid'])['decision'], 'constraints_satisfied')
        self.assertEqual(self.check(record, delivery_modes=['online'])['decision'], 'excluded')

    def test_partial_date_overlap_fails_but_exact_boundaries_pass(self):
        self.assertEqual(self.check(available_from='2026-12-10', available_to='2026-12-12')['decision'], 'constraints_satisfied')
        self.assertEqual(self.check(available_from='2026-12-11', available_to='2026-12-20')['decision'], 'excluded')
        self.assertEqual(self.check(available_to='2026-12-11')['decision'], 'excluded')

    def test_one_sided_availability_does_not_invent_the_other_bound(self):
        record = self.record()
        del record[0]['facts']['end_date']
        output = self.check(record, available_from='2026-12-01')
        self.assertEqual(output['decision'], 'constraints_satisfied')
        self.assertEqual(self.status(output, 'availability_to'), 'not_applicable')
        self.assertEqual(self.check(record, available_to='2026-12-31')['decision'], 'needs_source_info')

    def test_duration_is_not_inferred_from_dates_or_hours(self):
        record = self.record(total_hours=4, session_count=2)
        del record[0]['facts']['duration_days']
        output = self.check(record, max_duration_days=3)
        self.assertEqual(self.status(output, 'duration'), 'unknown')
        self.assertIn('duration_days', output['missing_source_fields'])

    def test_preferred_city_never_becomes_a_hard_filter(self):
        output = self.check(location_preference=['جدة'])
        self.assertEqual(output['decision'], 'no_constraints_requested')
        self.assertIs(output['location_preference']['matches'], False)
        self.assertFalse(output['location_preference']['excludes_candidate'])
        self.assertEqual(self.check(cities=['جدة'])['decision'], 'excluded')
        self.assertEqual(self.check(cities=['الرياض'])['decision'], 'constraints_satisfied')

    def test_joint_date_conflict_is_not_a_claimed_schedule_match(self):
        output = self.check(self.record(start_date='2026-12-20'), available_from='2026-12-01')
        self.assertEqual(output['decision'], 'needs_source_info')
        self.assertEqual(output['conflicting_source_fields'], ['end_date', 'start_date'])

    def test_definite_failure_wins_over_unknown_fields(self):
        record = self.record(cost_sar=200)
        del record[0]['facts']['duration_days']
        output = self.check(record, max_budget_sar=100, max_duration_days=2)
        self.assertEqual(output['decision'], 'excluded')
        self.assertIn('duration_days', output['missing_source_fields'])

    def test_date_only_deadline_abstains_near_unknown_timezone_boundary(self):
        record = self.record(deadline={'date': '2026-10-19', 'time': None, 'timezone': None, 'precision': 'date'})
        for at in ['2026-10-19T23:59:00+03:00', '2026-10-20T12:00:00+00:00']:
            output = self.check(record, at=at)
            self.assertEqual(self.status(output, 'deadline'), 'unknown')
            self.assertEqual(output['registration']['status'], 'requires_verification')
        output = self.check(record, at='2026-10-21T00:00:00+00:00')
        self.assertEqual(output['decision'], 'excluded')
        self.assertEqual(output['registration']['status'], 'deadline_passed')

    def test_same_instant_with_different_timezone_offsets_has_same_result(self):
        record = self.record()
        utc = self.check(record, at='2026-10-31T12:00:00+00:00')
        other = self.check(record, at='2026-11-01T02:00:00+14:00')
        self.assertEqual(utc, other)

    def test_past_or_future_dates_and_publication_status_do_not_prove_open_registration(self):
        record = self.record(registration_opens_on='2026-10-01', application_status_reported='open_at_publication')
        record[0]['last_verified_at'] = '2026-10-18T12:00:00+03:00'
        output = self.check(record, max_budget_sar=0)
        self.assertEqual(output['decision'], 'constraints_satisfied')
        self.assertEqual(output['registration']['status'], 'requires_verification')
        self.assertFalse(output['registration']['currently_open_verified'])

    def test_past_deadline_wins_even_when_opening_is_conflicted(self):
        record = self.record(deadline={'date': '2026-10-15', 'time': None, 'timezone': None, 'precision': 'date'})
        self.set_fact(record, 'registration_opens_on', None, 'conflicted', ['2026-10-09', '2026-10-13'])
        output = self.check(record)
        self.assertEqual(output['decision'], 'excluded')
        self.assertEqual(output['registration']['status'], 'deadline_passed')

    def test_unknown_eligibility_does_not_create_a_question_or_confirm_eligibility(self):
        record = self.record(mandatory_requirements=['العمر 18 سنة على الأقل'])
        output = self.check(record, max_budget_sar=0)
        self.assertEqual(output['user_missing_fields'], [])
        self.assertIn('eligibility', output['unchecked'])
        self.assertNotIn('eligibility_status', output)

    def test_unrequested_fields_do_not_block_constraints_but_errors_stay_errors(self):
        record = self.record()
        del record[0]['facts']['cost_sar']
        self.assertEqual(self.check(record, max_duration_days=3)['decision'], 'constraints_satisfied')
        for fields in ({'cost_sar': -1}, {'duration_days': True}, {'physical_attendance_required': 'false'},
                       {'registration_opens_on': 'next week'}, {'location': '  '}):
            with self.subTest(fields=fields), self.assertRaises(DataAccessError):
                self.check(self.record(**fields))

    def test_stale_evidence_naive_time_invalid_limits_and_forged_quotes_are_errors(self):
        record = self.record()
        args = {'expected_evidence_version': map_details(*record).evidence_version,
                'evaluation_time': datetime.fromisoformat('2026-10-18T12:00:00+03:00')}
        with self.assertRaisesRegex(ValueError, 'stale_evidence'):
            check_opportunity_constraints(*record, SearchConstraints(), **{**args, 'expected_evidence_version': 'old'})
        with self.assertRaises(ValueError):
            check_opportunity_constraints(*record, SearchConstraints(), **{**args, 'evaluation_time': datetime(2026, 10, 18)})
        constraints = SearchConstraints()
        constraints.max_budget_sar = -1
        with self.assertRaises(ValueError):
            check_opportunity_constraints(*record, constraints, **args)
        record[2]['E0']['quote'] = 'forged quotation'
        with self.assertRaises(DataAccessError):
            check_opportunity_constraints(*record, SearchConstraints(), **args)

    def test_inputs_unchanged_and_every_checked_fact_retains_source_evidence(self):
        record = self.record()
        before = deepcopy(record)
        output = self.check(record, max_budget_sar=0)
        self.assertEqual(record, before)
        budget = next(c for c in output['checks'] if c['name'] == 'budget')
        ref = budget['facts'][0]['evidence'][0]
        self.assertEqual(ref['source_id'], 'S')
        self.assertIn(ref['quote'], record[1]['S']['content'])
        self.assertEqual(ref['asserted_value'], 0)


if __name__ == '__main__':
    unittest.main()
