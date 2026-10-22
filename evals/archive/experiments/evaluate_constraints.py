"""Evaluate prewritten structured-constraint cases without model or database I/O."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))

from app.constraints import POLICY_VERSION, check_opportunity_constraints
from app.infrastructure.reference_paths import reference_path
from app.details import map_details
from app.schemas import SearchConstraints
from calibration_protocol import fingerprint, require_frozen_artifact, seal_artifact

FIXTURE = 'examples/constraint-check-cases.sample.json'
SAMPLE = 'examples/linked-data.sample.json'
PREFIX = 'results/constraint-check-v1'
CODE = ['backend/app/constraints.py', 'backend/app/details.py', 'backend/app/schemas.py',
        'experiments/evaluate_constraints.py']


def read(name):
    return json.loads(reference_path(name).read_text(encoding='utf-8-sig'))


def record_for(case, fixture, sample):
    if case['record'] != 'synthetic':
        opportunity = next(o for o in sample['opportunities'] if o['opportunity_id'] == case['record'])
        sources = {s['source_id']: s for s in sample['sources'] if s['source_id'] in opportunity['source_ids']}
        evidence = {e['evidence_id']: e for e in sample['evidence'] if e['opportunity_id'] == case['record']}
        return deepcopy((opportunity, sources, evidence))
    # Explicit test-only facts and quotations. Never copy overrides into a real record.
    identifier = 'SYNTHETIC-' + case['id']
    source_id = identifier + '-SOURCE'
    fields = {**fixture['synthetic_facts'], **case.get('overrides', {})}
    facts, evidence, quotes = {}, {}, []
    for field, item in fields.items():
        refs = []
        statements = item.get('alternatives', [item] if item.get('quote') else [])
        for statement in statements:
            evidence_id = f'{identifier}-{len(evidence) + 1}'
            refs.append(evidence_id)
            quotes.append(statement['quote'])
            evidence[evidence_id] = {'evidence_id': evidence_id, 'opportunity_id': identifier,
                'source_id': source_id, 'field': field, 'quote': statement['quote'],
                'asserted_value': statement['value']}
        facts[field] = {'value': item['value'], 'status': item.get('status', 'known'), 'evidence_ids': refs}
    opportunity = {'opportunity_id': identifier, 'source_ids': [source_id], 'facts': facts, 'last_verified_at': None}
    sources = {source_id: {'source_id': source_id, 'source_type': 'synthetic_test',
                          'content': '\n'.join(quotes)}}
    return opportunity, sources, evidence


def main():
    report_path, freeze_path = ROOT / (PREFIX + '-report.json'), ROOT / (PREFIX + '-freeze.json')
    if report_path.exists():
        raise FileExistsError('Preserve the completed constraint report; choose a new round for changed rules')
    fixture, sample = read(FIXTURE), read(SAMPLE)
    binding = {
        'policy_version': POLICY_VERSION,
        'fixture_sha256': fingerprint(fixture), 'sample_sha256': fingerprint(sample),
        'raw_sha256': hashlib.sha256((ROOT / 'data/raw/raw_opportunities.csv').read_bytes()).hexdigest(),
        'code_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in CODE},
        'indexed_documents_sha256': fingerprint(read('results/indexed-documents.json')),
    }
    if freeze_path.exists():
        frozen = read(PREFIX + '-freeze.json')
        require_frozen_artifact(frozen, binding)
    else:
        frozen = seal_artifact({'frozen_at': datetime.now(timezone.utc).isoformat(), 'binding': binding,
                               'scope': 'Deterministic, author-labelled component cases; no neural inference.'})
        freeze_path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
    cases = fixture['cases']
    if len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate case IDs')
    versions = {d['opportunity_id']: d['evidence_version'] for d in read('results/indexed-documents.json')}
    results = []
    for case in cases:
        record = record_for(case, fixture, sample)
        expected_version = (versions[case['record']] if case['record'] != 'synthetic'
                            else map_details(*record).evidence_version)
        output = check_opportunity_constraints(*record, SearchConstraints(**case['constraints']),
            expected_evidence_version=expected_version,
            evaluation_time=datetime.fromisoformat(case.get('evaluation_time', fixture['evaluation_time'])),
            required_locations=case.get('required_locations', ()))
        actual_checks = {c['name']: c['status'] for c in output['checks']}
        errors = []
        if output['decision'] != case['expected_decision']:
            errors.append('decision')
        if 'expected_registration' in case and output['registration']['status'] != case['expected_registration']:
            errors.append('registration')
        if 'expected_preference_match' in case and output['location_preference']['matches'] != case['expected_preference_match']:
            errors.append('location_preference')
        errors.extend(name for name, expected in case['expected_checks'].items() if actual_checks.get(name) != expected)
        if output['registration']['currently_open_verified'] or output['user_missing_fields']:
            errors.append('unsupported_registration_or_question')
        results.append({'id': case['id'], 'record_kind': case['record'], 'passed': not errors,
                        'errors': errors, 'expected': case, 'actual': output})
    require_frozen_artifact(read(PREFIX + '-freeze.json'), binding)
    if any(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != v for p, v in binding['code_sha256'].items()):
        raise ValueError('Implementation changed during evaluation')
    if fingerprint(read(FIXTURE)) != binding['fixture_sha256'] or fingerprint(read(SAMPLE)) != binding['sample_sha256']:
        raise ValueError('Fixture or corpus changed during evaluation')
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'policy_version': POLICY_VERSION,
        'freeze_sha256': frozen['artifact_sha256'], 'binding': binding, 'cases': len(results),
        'passed_cases': sum(r['passed'] for r in results), 'all_passed': all(r['passed'] for r in results),
        'real_sample_cases': sum(c['record'] != 'synthetic' for c in cases),
        'synthetic_cases': sum(c['record'] == 'synthetic' for c in cases),
        'enabled_in_application': False, 'new_neural_inferences': 0,
        'limitations': ['Author-written cases, not independent adjudication or a production quality estimate.',
                       'No query parsing, query/profile conflict resolution, eligibility or live registration verification.',
                       'Conservative full-period availability and date-only deadline margins.',
                       'No changes to the database, raw corpus, public HTTP contracts or existing scores.'],
        'results': results}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# مراجعة فحوص القيود المنظمة', '',
        f"اجتازت {report['passed_cases']} / {report['cases']} حالة: أربع على العينة المجهزة، والبقية مصطنعة ومعلّمة للاختبار.", '',
        '| الحالة | القرار الفعلي | التسجيل | اجتازت المتوقع؟ |', '|---|---|---|---|']
    for row in results:
        lines.append(f"| {row['id']} | {row['actual']['decision']} | {row['actual']['registration']['status']} | {row['passed']} |")
    lines += ['', 'نثبت سياسة المجهول والتعارض والحدود العددية والحضور والتفرغ على حالات مكتوبة مسبقًا. اجتياز القيود ليس أهلية أو إثبات فتح التسجيل، ولا توجد توصيات من API بعد.', '',
              'المواعيد بدقة يوم تستخدم هامش يوم على جانبي تاريخ UTC؛ لا نختلق ساعة أو منطقة إغلاق. لا نحسب المدة من فرق التواريخ.', '',
              'لم نشغّل النموذج أو نغير بيانات الخام والقاعدة. التالي فحص الأهلية ومعلومات المستخدم المؤثرة، وحسم خطة الطلب، ثم ربط رحلة واحدة وتقييمها كاملة.', '',
              '[التقرير الرقمي](constraint-check-v1-report.json) · [النسخة المثبتة](constraint-check-v1-freeze.json) · [السياسة](../docs/constraint-policy.md)']
    (ROOT / (PREFIX + '-review.md')).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('all_passed', 'passed_cases', 'cases', 'real_sample_cases', 'synthetic_cases')}, indent=2))
    if not report['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
