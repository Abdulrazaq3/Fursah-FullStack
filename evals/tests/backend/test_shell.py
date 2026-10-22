"""Check the imported API contract without pretending the workflow is complete."""
import unittest
from dataclasses import replace
from unittest.mock import Mock
from fastapi.testclient import TestClient
from app.main import app
from app.infrastructure.config import Settings, PROJECT_ROOT
from app.infrastructure.data_package import DatasetLoader
from app.infrastructure.dependencies import get_app_dependencies


class ApiShellTests(unittest.TestCase):
    def setUp(self):
        deps=replace(get_app_dependencies(), settings=Settings(_env_file=None), model_config=None, repository=Mock())
        deps.repository.is_ready.return_value=False
        app.dependency_overrides[get_app_dependencies]=lambda:deps
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_health_is_live_but_application_is_not_ready(self):
        self.assertEqual(self.client.get('/health').status_code, 200)
        response = self.client.get('/ready')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'not_ready')

    def test_discovery_is_explicitly_unfinished(self):
        response = self.client.post('/api/v1/discover', json={
            'request_id': 'shell-check', 'query': 'ورشة ترجمة',
            'profile': {'interests': [], 'skills': None}, 'constraints': {},
        })
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error_code'], 'FURSAH_NOT_IMPLEMENTED')
        self.assertEqual(response.json()['recommendations'], [])

    def test_invalid_budget_is_rejected_at_http_boundary(self):
        response = self.client.post('/api/v1/discover', json={
            'query': 'ورشة', 'profile': {}, 'constraints': {'max_budget_sar': -1},
        })
        self.assertEqual(response.status_code, 422)

    def test_data_directory_survives_new_root_layout(self):
        settings = Settings(_env_file=None)
        self.assertEqual(settings.data_dir, PROJECT_ROOT / 'data')
        self.assertEqual(len(DatasetLoader(settings).load_raw_opportunities()), 1000)


if __name__ == '__main__':
    unittest.main()
