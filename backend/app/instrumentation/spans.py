"""Opt-in evaluation spans. No raw profiles, credentials or remote export here."""
from contextlib import contextmanager
import json
import math

from opentelemetry import trace


class _DisabledSpan:
    def set_attribute(self, *args, **kwargs):
        pass


@contextmanager
def eval_span(settings, name, **attributes):
    if not settings.eval_telemetry_enabled:
        yield _DisabledSpan()
        return
    with trace.get_tracer('fursah').start_as_current_span(name) as span:
        kind = {'fursah.understanding': 'LLM', 'fursah.embedding': 'EMBEDDING',
                'fursah.retrieval': 'RETRIEVER', 'fursah.rerank': 'RERANKER'}.get(name, 'CHAIN')
        span.set_attribute('openinference.span.kind', kind)
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
                if key == 'llm.model':
                    span.set_attribute('llm.model_name', value)
                elif key == 'embedding.model':
                    span.set_attribute('embedding.model_name', value)
                elif key == 'rerank.model':
                    span.set_attribute('reranker.model_name', value)
        yield span


def record_output(span, value):
    span.set_attribute('output.value', json.dumps(value, ensure_ascii=False, sort_keys=True))
    span.set_attribute('output.mime_type', 'application/json')


def record_model_usage(settings, usage):
    if not settings.eval_telemetry_enabled or not isinstance(usage,dict):
        return
    span=trace.get_current_span()
    for source,key in [('prompt_tokens','llm.input_tokens'),('completion_tokens','llm.output_tokens')]:
        value=usage.get(source)
        if type(value) is int and value>=0:
            span.set_attribute(key,value)
            span.set_attribute('llm.token_count.prompt' if source == 'prompt_tokens' else 'llm.token_count.completion', value)
    if all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('prompt_tokens', 'completion_tokens')):
        span.set_attribute('llm.token_count.total', usage['prompt_tokens'] + usage['completion_tokens'])
    cost=usage.get('cost')
    if type(cost) in (int,float) and math.isfinite(cost) and cost>=0:
        span.set_attribute('llm.reported_cost_usd',float(cost))
