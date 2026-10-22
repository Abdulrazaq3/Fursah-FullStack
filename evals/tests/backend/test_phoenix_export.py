"""OTLP acknowledgement can precede Phoenix's span transaction commit."""
import unittest
from unittest.mock import Mock, patch

import httpx

from evals.phoenix_export import publish_annotations


def failed_response(status):
    response = httpx.Response(status, request=httpx.Request('POST', 'http://localhost/v1/span_annotations'))
    return httpx.HTTPStatusError('test', request=response.request, response=response)


class PhoenixAnnotationExport(unittest.TestCase):
    @patch('evals.phoenix_export.time.sleep')
    def test_retries_uncommitted_span_then_returns_receipt(self, sleep):
        client = Mock()
        client.spans.log_span_annotations.side_effect = [failed_response(404), [{'id': 'annotation'}]]
        self.assertEqual(publish_annotations(client, [{'span_id': 'abc'}]), [{'id': 'annotation'}])
        self.assertEqual(client.spans.log_span_annotations.call_count, 2)
        sleep.assert_called_once()

    def test_propagates_non_ingestion_failures(self):
        client = Mock()
        client.spans.log_span_annotations.side_effect = failed_response(401)
        with self.assertRaises(httpx.HTTPStatusError):
            publish_annotations(client, [{'span_id': 'abc'}])
        self.assertEqual(client.spans.log_span_annotations.call_count, 1)

    def test_bounded_wait_does_not_report_an_export_success(self):
        client = Mock()
        client.spans.log_span_annotations.side_effect = failed_response(404)
        with self.assertRaises(httpx.HTTPStatusError):
            publish_annotations(client, [{'span_id': 'abc'}], timeout=0)
        self.assertEqual(client.spans.log_span_annotations.call_count, 1)
