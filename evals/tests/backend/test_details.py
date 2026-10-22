"""Details must preserve unknowns, source ownership, conflicts and updates."""
import copy
import json
from pathlib import Path
import unittest
from dataclasses import replace
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.details import map_details
from app.infrastructure.dependencies import get_app_dependencies
from app.infrastructure.config import Settings
from app.infrastructure.data_package import DatasetLoader
from app.repository import OpportunityRepository
from app.infrastructure.errors import DataAccessError
from app.main import app

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = json.loads((ROOT / 'evals/archive/fixtures/linked-data.sample.json').read_text(encoding='utf-8'))


def record(identifier):
    opportunity = next(item for item in SAMPLE['opportunities'] if item['opportunity_id'] == identifier)
    sources = {item['source_id']: item for item in SAMPLE['sources'] if item['source_id'] in opportunity['source_ids']}
    evidence = {item['evidence_id']: item for item in SAMPLE['evidence'] if item['opportunity_id'] == identifier}
    return copy.deepcopy((opportunity, sources, evidence))


class DetailsMappingTests(unittest.TestCase):
    def test_free_is_zero_but_unanswered_requirements_and_application_url_are_null(self):
        details = map_details(*record('OPP-DEMO-001'))
        self.assertEqual(details.cost, 0)
        self.assertIs(details.physical_attendance_required, False)
        self.assertIsNone(details.required_skills)
        self.assertIsNone(details.eligibility_requirements.mandatory)
        self.assertIsNone(details.application_url)  # An information URL is not an application URL.
        self.assertIsNone(details.last_verified_at)
        self.assertEqual(details.application_status, 'requires_verification')
        self.assertEqual(details.deadline, '2026-10-19')
        self.assertTrue(any('ساعة الإغلاق' in warning for warning in details.data_warnings))

    def test_unknown_fee_is_not_free(self):
        details = map_details(*record('OPP-DEMO-002'))
        self.assertIsNone(details.cost)
        self.assertIsNone(details.deadline)
        self.assertTrue(any('رسوم المشاركة غير محدد' in warning for warning in details.data_warnings))

    def test_unresolved_opening_conflict_is_exposed_without_claiming_open_registration(self):
        details = map_details(*record('OPP-DEMO-003'))
        self.assertEqual(details.deadline, '2026-10-15')
        self.assertEqual(details.application_status, 'requires_verification')
        self.assertTrue(any('تعارض' in warning for warning in details.data_warnings))

    def test_explicit_update_selects_new_dates(self):
        details = map_details(*record('OPP-DEMO-004'))
        self.assertEqual(details.start_date, '2026-11-08')
        self.assertEqual(details.deadline, '2026-10-22')
        self.assertEqual(details.source_ids, ['SRC-0496', 'SRC-0497'])

    def test_version_matches_actual_retrieval_documents_and_changes_with_sources(self):
        indexed = json.loads((ROOT / 'evals/archive/reports/indexed-documents.json').read_text(encoding='utf-8'))
        for item in indexed:
            with self.subTest(item['opportunity_id']):
                self.assertEqual(map_details(*record(item['opportunity_id'])).evidence_version, item['evidence_version'])
        opportunity, sources, evidence = record('OPP-DEMO-001')
        before = map_details(opportunity, sources, evidence).evidence_version
        sources['SRC-0943']['content'] += '\nملاحظة إضافية من المصدر.'
        self.assertNotEqual(before, map_details(opportunity, sources, evidence).evidence_version)

    def test_bad_quote_source_or_field_is_rejected(self):
        changes = [('quote', 'اقتباس غير موجود'), ('source_id', 'SRC-0477'), ('field', 'cost_sar')]
        for key, value in changes:
            with self.subTest(key):
                opportunity, sources, evidence = record('OPP-DEMO-001')
                evidence['EV-001'][key] = value
                with self.assertRaises(DataAccessError):
                    map_details(opportunity, sources, evidence)

    def test_conflicting_evidence_cannot_be_marked_known_without_resolution(self):
        opportunity, sources, evidence = record('OPP-DEMO-003')
        opportunity['facts']['registration_opens_on'].update(status='known', value=evidence['EV-015']['asserted_value'])
        with self.assertRaises(DataAccessError):
            map_details(opportunity, sources, evidence)

    def test_malformed_storage_shape_is_a_controlled_data_error(self):
        opportunity, sources, evidence = record('OPP-DEMO-001')
        opportunity['facts'] = []
        with self.assertRaises(DataAccessError):
            map_details(opportunity, sources, evidence)


class DetailsHttpTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        settings=Settings(_env_file=None)
        self.repository=OpportunityRepository(DatasetLoader(settings),settings)
        deps=replace(get_app_dependencies(),settings=settings,repository=self.repository,model_config=None)
        app.dependency_overrides[get_app_dependencies]=lambda:deps
        self.addCleanup(app.dependency_overrides.clear)

    def test_stored_record_is_mapped_at_the_existing_endpoint(self):
        with patch.object(self.repository, '_connect') as connect:
            connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = record('OPP-DEMO-001')
            response = self.client.get('/api/v1/opportunities/OPP-DEMO-001')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['source_ids'], ['SRC-0943'])
        self.assertEqual(response.json()['cost'], 0)

    def test_missing_record_is_404(self):
        with patch.object(self.repository, '_connect') as connect:
            connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
            response = self.client.get('/api/v1/opportunities/ABSENT')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error_code'], 'FURSAH_OPPORTUNITY_NOT_FOUND')

    def test_storage_failure_is_503_and_never_a_missing_record_or_fallback(self):
        with patch.object(self.repository, '_connect', side_effect=DataAccessError('private connection diagnostic')):
            response = self.client.get('/api/v1/opportunities/OPP-DEMO-001')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error_code'], 'FURSAH_DATA_ERROR')
        self.assertNotIn('private', response.text)


if __name__ == '__main__':
    unittest.main()
