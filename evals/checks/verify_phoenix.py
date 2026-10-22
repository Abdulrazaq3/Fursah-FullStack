"""Read the latest completed run back from Phoenix; never calls a model."""
from pathlib import Path
import json

from phoenix.client import Client

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / 'evals'


def main():
    latest = json.loads((EVALS / 'runs/latest.json').read_text(encoding='utf-8'))
    run_dir = EVALS / 'runs' / latest['run_dir']
    summary = json.loads((run_dir / 'summary.json').read_text(encoding='utf-8'))
    rows = [json.loads(line) for line in (run_dir / 'results.jsonl').read_text(encoding='utf-8').splitlines()]
    client = Client(base_url=summary['phoenix_url'])
    spans = client.spans.get_spans_dataframe(project_name=summary['phoenix_project'], limit=10000)
    expected_traces = {r['trace_id'] for r in rows}
    spans = spans[spans['context.trace_id'].isin(expected_traces)]
    roots = spans[spans['name'] == 'eval.case']
    annotations = client.spans.get_span_annotations_dataframe(spans_dataframe=roots,
        project_identifier=summary['phoenix_project'])
    assert len(roots) == len(rows), 'Missing case roots in Phoenix'
    assert len(annotations) == summary['phoenix_annotations'], 'Missing evaluation annotations'
    required = {'eval.case', 'fursah.understanding', 'fursah.embedding',
                'fursah.retrieval', 'fursah.rerank', 'fursah.selection'}
    assert required <= set(spans['name']), 'Missing workflow stages'
    report = {'run': latest['run_dir'], 'phoenix_url': summary['phoenix_url'],
              'project': summary['phoenix_project'], 'traces': len(roots), 'spans': len(spans),
              'annotations': len(annotations), 'stages': sorted(set(spans['name'])),
              'outcomes': summary['outcomes'], 'verified': True}
    (run_dir / 'phoenix-verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
