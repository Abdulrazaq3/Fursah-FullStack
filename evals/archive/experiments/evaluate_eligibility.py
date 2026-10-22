"""Check bounded eligibility and question impact without inference, DB or API calls."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))

from app.infrastructure.reference_paths import reference_path
from app.details import map_details
from app.eligibility import POLICY_VERSION, check_eligibility, select_eligibility_questions
from app.schemas import UserProfile
from calibration_protocol import fingerprint, require_frozen_artifact, seal_artifact
from evaluate_constraints import record_for

FIXTURE = 'examples/eligibility-check-cases.sample.json'
SAMPLE = 'examples/linked-data.sample.json'
PREFIX = 'results/eligibility-check-v1'
CODE = ['backend/app/eligibility.py', 'backend/app/eligibility_catalog.json',
        'backend/app/details.py', 'backend/app/schemas.py', 'backend/app/request_requirements.py',
        'experiments/evaluate_constraints.py', 'experiments/evaluate_eligibility.py',
        'frontend/src/profile/choices.ts', 'frontend/src/labels.ts']


def read(name):
    return json.loads(reference_path(name).read_text(encoding='utf-8-sig'))


def evaluate(fixture, sample):
    results, question_results = [], []
    cases = {case['id']: case for case in fixture['cases']}
    versions = {d['opportunity_id']: d['evidence_version'] for d in read('results/indexed-documents.json')}
    if len(cases) != len(fixture['cases']):
        raise ValueError('Duplicate eligibility IDs')

    def check(case):
        record = record_for(case, fixture, sample)
        expected = versions[case['record']] if case['record'] != 'synthetic' else map_details(*record).evidence_version
        return check_eligibility(*record, UserProfile(**case['profile']), expected_evidence_version=expected)

    for case in cases.values():
        output = check(case)
        passed = output['status'] == case['expected_status'] and output['user_missing_fields'] == case['expected_missing']
        results.append({'id': case['id'], 'record_kind': case['record'], 'passed': passed,
                        'expected': case, 'actual': output})
    for scenario in fixture['question_scenarios']:
        evaluations, gates, aliases, profile = [], {}, {}, None
        for candidate in scenario['candidates']:
            case = cases[candidate['case']]
            current_profile = UserProfile(**case['profile'])
            if profile is not None and profile != current_profile:
                raise ValueError('Question scenario mixes different user profiles')
            profile = current_profile
            output = check(case)
            identifier = output['opportunity_id']
            if identifier in gates:
                raise ValueError('Duplicate opportunity in a question scenario')
            evaluations.append(output)
            aliases[identifier] = candidate['id']
            gates[identifier] = {'evidence_version': output['evidence_version'],
                                'topic_decision': candidate['topic'], 'constraint_decision': candidate['constraints']}
        proposal = select_eligibility_questions(evaluations, gates, profile or UserProfile())
        selected = aliases.get(proposal['selected_candidate_id'])
        passed = (proposal['decision'] == scenario['expected_decision']
                  and proposal['missing_fields'] == scenario['expected_fields']
                  and selected == scenario.get('expected_candidate'))
        question_results.append({'id': scenario['id'], 'passed': passed, 'expected': scenario,
                                 'actual': proposal, 'selected_fixture_candidate': selected,
                                 'scope': 'Simulated upstream gates for question selection, not a retrieval/HTTP test.'})
    return results, question_results


def main():
    report_path, freeze_path = ROOT / (PREFIX + '-report.json'), ROOT / (PREFIX + '-freeze.json')
    if report_path.exists():
        raise FileExistsError('Preserve the completed eligibility round')
    fixture, sample = read(FIXTURE), read(SAMPLE)
    binding = {'policy_version': POLICY_VERSION, 'fixture_sha256': fingerprint(fixture),
               'sample_sha256': fingerprint(sample), 'indexed_sha256': fingerprint(read('results/indexed-documents.json')),
               'raw_sha256': hashlib.sha256((ROOT / 'data/raw/raw_opportunities.csv').read_bytes()).hexdigest(),
               'code_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in CODE}}
    if freeze_path.exists():
        frozen = read(PREFIX + '-freeze.json')
        require_frozen_artifact(frozen, binding)
    else:
        frozen = seal_artifact({'frozen_at': datetime.now(timezone.utc).isoformat(), 'binding': binding,
                               'scope': 'Author-written deterministic cases, not general language accuracy.'})
        freeze_path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
    results, question_results = evaluate(fixture, sample)
    require_frozen_artifact(read(PREFIX + '-freeze.json'), binding)
    if any(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != v for p, v in binding['code_sha256'].items()):
        raise ValueError('Code changed during evaluation')
    if fingerprint(read(FIXTURE)) != binding['fixture_sha256'] or fingerprint(read(SAMPLE)) != binding['sample_sha256']:
        raise ValueError('Labels or source sample changed during evaluation')
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'binding': binding,
              'freeze_sha256': frozen['artifact_sha256'], 'eligibility_cases': len(results),
              'eligibility_passed': sum(r['passed'] for r in results),
              'question_scenarios': len(question_results), 'questions_passed': sum(r['passed'] for r in question_results),
              'all_passed': all(r['passed'] for r in results + question_results),
              'source_sample_cases': sum(r['record_kind'] != 'synthetic' for r in results),
              'synthetic_eligibility_cases': sum(r['record_kind'] == 'synthetic' for r in results),
              'new_neural_inferences': 0, 'enabled_in_application': False,
              'limitations': ['Bounded whole-clause parser, not a general requirement interpreter.',
                             'Four existing records have incomplete eligibility facts; none is declared confirmed.',
                             'Question gates are simulated, not API or retrieval integration.',
                             'Self-reported profile, fixed frontend catalog, author-written labels; no independent adjudication.',
                             'Current registration, request-plan resolution and complete recommendations remain pending.'],
              'results': results, 'question_results': question_results}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# مراجعة الأهلية والمعلومات المؤثرة', '',
        f"الأهلية: {report['eligibility_passed']} / {report['eligibility_cases']}. اختيار السؤال: {report['questions_passed']} / {report['question_scenarios']}.", '',
        'أربع حالات من عينة المصادر، والبقية مصطنعة. الشروط المجهولة في الفرص الأربع أبقت أهليتها غير مؤكدة دون سؤال المستخدم عن كل حقل ناقص.', '',
        '| الحالة | حكم الأهلية | حقول مستخدم ناقصة | اجتازت؟ |', '|---|---|---|---|']
    for row in results:
        lines.append(f"| {row['id']} | {row['actual']['status']} | {', '.join(row['actual']['user_missing_fields']) or '—'} | {row['passed']} |")
    lines += ['', '| سيناريو الأسئلة | القرار | الحقول | اجتاز؟ |', '|---|---|---|---|']
    for row in question_results:
        lines.append(f"| {row['id']} | {row['actual']['decision']} | {', '.join(row['actual']['missing_fields']) or '—'} | {row['passed']} |")
    lines += ['', 'هذه فحوص قواعد محددة. بوابات الصلة والقيود في سيناريوهات السؤال محاكاة، وليست رحلة بحث كاملة. لم نغيّر الخام أو القاعدة أو عقد الواجهة، ولم نشغّل نموذجًا.', '',
              'السؤال يقترح فقط لمرشح اجتاز البوابات ولا يمنعه إلا معلومة مستخدم قابلة للإجابة. وجود مرشح مؤكد يمنع إيقاف النتيجة لسؤال غير لازم. العمر وسنة الدراسة والشرط المركب لا تتحول إلى حقول وهمية.', '',
              '[السياسة](../docs/eligibility-policy.md) · [التقرير الرقمي](eligibility-check-v1-report.json) · [النسخة المثبتة](eligibility-check-v1-freeze.json)']
    (ROOT / (PREFIX + '-review.md')).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('all_passed', 'eligibility_passed', 'eligibility_cases', 'questions_passed', 'question_scenarios')}, indent=2))
    if not report['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
