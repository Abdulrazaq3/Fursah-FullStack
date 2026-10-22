"""Run the labelled constraint examples in CI without models, storage or report writes."""
from datetime import datetime
import unittest

from evaluate_constraints import read, record_for
from app.constraints import check_opportunity_constraints
from app.details import map_details
from app.schemas import SearchConstraints


class LabelledConstraintCases(unittest.TestCase):
    def test_prewritten_source_and_synthetic_cases(self):
        fixture = read('examples/constraint-check-cases.sample.json')
        sample = read('examples/linked-data.sample.json')
        versions = {d['opportunity_id']: d['evidence_version'] for d in read('results/indexed-documents.json')}
        for case in fixture['cases']:
            with self.subTest(case=case['id']):
                record = record_for(case, fixture, sample)
                expected = (versions[case['record']] if case['record'] != 'synthetic'
                            else map_details(*record).evidence_version)
                output = check_opportunity_constraints(*record, SearchConstraints(**case['constraints']),
                    expected_evidence_version=expected,
                    evaluation_time=datetime.fromisoformat(case.get('evaluation_time', fixture['evaluation_time'])),
                    required_locations=case.get('required_locations', ()))
                self.assertEqual(output['decision'], case['expected_decision'])
                checks = {c['name']: c['status'] for c in output['checks']}
                for name, status in case['expected_checks'].items():
                    self.assertEqual(checks[name], status)
                if 'expected_registration' in case:
                    self.assertEqual(output['registration']['status'], case['expected_registration'])
                if 'expected_preference_match' in case:
                    self.assertEqual(output['location_preference']['matches'], case['expected_preference_match'])
                self.assertFalse(output['registration']['currently_open_verified'])
                self.assertEqual(output['user_missing_fields'], [])


if __name__ == '__main__':
    unittest.main()
