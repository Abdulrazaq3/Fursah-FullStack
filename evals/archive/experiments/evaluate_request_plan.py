"""Measure deterministic request-plan cases without model, database or HTTP calls."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))

from app.infrastructure.reference_paths import reference_path
from app.request_plan import POLICY_VERSION, build_request_plan, conflict_response, resolved_plan_inputs
from app.schemas import DiscoveryRequest
from calibration_protocol import fingerprint, require_frozen_artifact, seal_artifact

FIXTURE = 'examples/request-plan-cases.sample.json'
CODE = ['backend/app/request_plan.py', 'backend/app/request_requirements.py', 'backend/app/schemas.py',
        'backend/app/details.py', 'backend/app/eligibility.py', 'backend/app/eligibility_catalog.json',
        'experiments/evaluate_request_plan.py', 'frontend/src/App.tsx', 'frontend/src/opportunities/SearchResults.tsx']


def read(name):
    return json.loads(reference_path(name).read_text(encoding='utf-8-sig'))


def evaluate(fixture):
    if len({c['id'] for c in fixture['cases']}) != len(fixture['cases']):
        raise ValueError('Duplicate request-plan case IDs')
    results = []
    for case in fixture['cases']:
        request = DiscoveryRequest(query=case['query'], profile=case.get('profile', {}),
                                   constraints=case['constraints'], constraint_resolution=case.get('resolution'))
        original = request.model_dump(mode='json')
        plan = build_request_plan(request)
        errors = []
        if plan['status'] != case['expected_status']:
            errors.append('status')
        for field, expected in case.get('expected_constraints', {}).items():
            if plan['effective_constraints'] is None or plan['effective_constraints'].get(field) != expected:
                errors.append(field)
        if 'expected_locations' in case and plan['required_locations'] != case['expected_locations']:
            errors.append('required_locations')
        if 'expected_conflicts' in case and plan['missing_fields'] != case['expected_conflicts']:
            errors.append('conflicting_fields')
        for claim in plan['query_claims']:
            if request.query[claim['start']:claim['end']] != claim['quote']:
                errors.append('claim_provenance')
        response = None
        if plan['status'] == 'resolved':
            inputs = resolved_plan_inputs(request, plan)
            if inputs['constraints'].model_dump(mode='json') != plan['effective_constraints']:
                errors.append('effective_input_mismatch')
        elif plan['status'] == 'constraint_conflict':
            response = conflict_response(request, plan, request_id=case['id']).model_dump(mode='json')
        else:
            if plan['effective_constraints'] is not None or plan['missing_fields']:
                errors.append('unresolved_query_exposed_as_executable_or_profile_question')
        if original != request.model_dump(mode='json'):
            errors.append('request_mutated')
        results.append({'id': case['id'], 'passed': not errors, 'errors': errors,
                        'expected': case, 'actual': plan, 'conflict_response_example': response})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', choices=['request-plan-v1', 'request-plan-v1.1'], default='request-plan-v1.1')
    args = parser.parse_args()
    prefix = 'results/' + args.run_id
    report_path, freeze_path = ROOT / (prefix + '-report.json'), ROOT / (prefix + '-freeze.json')
    if report_path.exists():
        raise FileExistsError('Preserve the completed request-plan report')
    fixture = read(FIXTURE)
    binding = {'policy_version': POLICY_VERSION, 'fixture_sha256': fingerprint(fixture),
               'code_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in CODE},
               'raw_sha256': hashlib.sha256((ROOT / 'data/raw/raw_opportunities.csv').read_bytes()).hexdigest()}
    if freeze_path.exists():
        frozen = read(prefix + '-freeze.json')
        require_frozen_artifact(frozen, binding)
    else:
        frozen = seal_artifact({'frozen_at': datetime.now(timezone.utc).isoformat(), 'binding': binding,
                               'scope': 'Author-written deterministic cases, not general query understanding.'})
        freeze_path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
    results = evaluate(fixture)
    require_frozen_artifact(read(prefix + '-freeze.json'), binding)
    if fingerprint(read(FIXTURE)) != binding['fixture_sha256'] or any(
            hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != value for p, value in binding['code_sha256'].items()):
        raise ValueError('Cases or implementation changed during evaluation')
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'policy_version': POLICY_VERSION,
              'binding': binding, 'freeze_sha256': frozen['artifact_sha256'], 'cases': len(results),
              'passed_cases': sum(r['passed'] for r in results), 'all_passed': all(r['passed'] for r in results),
              'new_neural_inferences': 0, 'enabled_in_application': False, 'general_understanding_verified': False,
              'scope': 'Replay of the same 30 known cases after a tool-OR transfer fix; not a fresh benchmark.',
              'limitations': ['Bounded phrase reader and deterministic resolver, not a general language-model adapter.',
                             'Author-written cases, not independent adjudication or query-language coverage estimates.',
                             'No search, API discovery or browser journey is implemented by this report.',
                             'Generic requirement understanding, semantic misses and application integration remain open.'],
              'results': results}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# مراجعة خطة الطلب وحسم التعارض', '',
             f"اجتازت {report['passed_cases']} / {report['cases']} حالة مكتوبة مسبقًا للقارئ المحدود وسياسة الدمج.", '',
             'هذه إعادة تشخيص للحالات الثلاثين نفسها بعد إصلاح حفظ «أو» بين الأدوات في النص الدلالي؛ ليست ثلاثين حالة جديدة. اختبار تركيب الوحدات يغطي الإصلاح، وتقرير الإصدار الأول محفوظ.', '',
             '| الحالة | القرار | اجتازت؟ |', '|---|---|---|']
    lines += [f"| {r['id']} | {r['actual']['status']} | {r['passed']} |" for r in results]
    lines += ['', 'الحدود المتوافقة تتقاطع؛ التعارض المؤثر ينتظر اختيار الملف أو النص. الاختيار يخص المجموعات المتعارضة لهذا البحث فقط، ولا يعدل الملف ولا يمحو القيود المتوافقة. الغموض داخل النص لا يتجاوزه اختيار المصدر.', '',
              'أمثلة رد التعارض تطابق عقد الواجهة القائم، لكنها لم تُربط بمسار الاكتشاف. القارئ مرجعي محدود؛ محول النموذج اللغوي العام لم يُنفذ، ولم نشغّل نموذجًا أو نغير البيانات.', '',
              f'[السياسة](../docs/request-plan.md) · [التقرير الرقمي]({args.run_id}-report.json) · [النسخة المثبتة]({args.run_id}-freeze.json)']
    (ROOT / (prefix + '-review.md')).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('all_passed', 'passed_cases', 'cases')}, indent=2))
    if not report['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
