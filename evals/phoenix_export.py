"""Publish grades after Phoenix's asynchronous span ingestion has committed."""
import time

import httpx


def publish_annotations(client, annotations, timeout=15):
    deadline = time.monotonic() + timeout
    while True:
        try:
            return client.spans.log_span_annotations(span_annotations=annotations, sync=True)
        except httpx.HTTPStatusError as exc:
            # OTLP can acknowledge a batch before its final/root span is queryable.
            if exc.response.status_code != 404 or time.monotonic() >= deadline:
                raise
            time.sleep(0.5)
