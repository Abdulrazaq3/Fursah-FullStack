"""Eligibility must not turn incomplete rules or profiles into confident outcomes."""
from copy import deepcopy
import json
from pathlib import Path
import re
import unittest

from app.details import map_details
from app.eligibility import CATALOG, check_eligibility, select_eligibility_questions
from app.infrastructure.errors import DataAccessError
from app.schemas import DiscoveryResponse, UserProfile

ROOT = Path(__file__).resolve().parents[3]


class EligibilityTests(unittest.TestCase):
    def record(self, mandatory=None, skills=None, preferred=None):
        values = {'title': 'Synthetic eligibility test', 'mandatory_requirements': mandatory or [],
                  'required_skills': skills or [], 'preferred_requirements': preferred or []}
        source, facts, evidence = {'source_id': 'S', 'content': ''}, {}, {}
        for index, (field, value) in enumerate(values.items()):
            identifier = f'E{index}'
            quote = f'{field}: {json.dumps(value, ensure_ascii=False)}'
            source['content'] += quote + '\n'
            facts[field] = {'status': 'known', 'value': value, 'evidence_ids': [identifier]}
            evidence[identifier] = {'evidence_id': identifier, 'source_id': 'S', 'opportunity_id': 'TEST',
                                    'field': field, 'asserted_value': value, 'quote': quote}
        return {'opportunity_id': 'TEST', 'source_ids': ['S'], 'facts': facts}, {'S': source}, evidence

    def check(self, record=None, **profile):
        record = record or self.record()
        return check_eligibility(*record, UserProfile(**profile), expected_evidence_version=map_details(*record).evidence_version)

    def gates(self, result, *, topic='related', constraints='constraints_satisfied'):
        return {result['opportunity_id']: {'topic_decision': topic, 'constraint_decision': constraints,
                                         'evidence_version': result['evidence_version']}}

    def test_only_two_explicit_empty_requirement_categories_confirm_no_requirements(self):
        self.assertEqual(self.check()['status'], 'confirmed')
        for field in ('mandatory_requirements', 'required_skills'):
            record = self.record()
            del record[0]['facts'][field]
            result = self.check(record)
            self.assertEqual(result['status'], 'uncertain')
            self.assertTrue(result['non_user_blockers'])
            self.assertEqual(result['user_missing_fields'], [])

    def test_null_skills_and_explicit_empty_skills_have_different_meanings(self):
        record = self.record(skills=['Excel'])
        missing = self.check(record, skills=None)
        none = self.check(record, skills=[])
        self.assertEqual(missing['status'], 'uncertain')
        self.assertEqual(missing['user_missing_fields'], ['profile.skills'])
        self.assertEqual(none['status'], 'ineligible')
        self.assertEqual(none['user_missing_fields'], [])
        self.assertIsNone(none['public_eligibility_status'])

    def test_partial_skill_list_is_not_an_exhaustive_denial(self):
        result = self.check(self.record(skills=['Excel']), skills=[{'name': 'Python', 'level': 'advanced'}])
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(result['user_missing_fields'], ['profile.skills'])

    def test_aliases_match_but_skill_level_is_never_invented(self):
        record = self.record(skills=['إكسل بمستوى متوسط على الأقل'])
        for level, expected in [('advanced', 'confirmed'), ('intermediate', 'confirmed'),
                                ('beginner', 'ineligible'), (None, 'uncertain')]:
            with self.subTest(level=level):
                result = self.check(record, skills=[{'name': 'Excel', 'level': level}])
                self.assertEqual(result['status'], expected)

    def test_name_only_requirement_does_not_ask_for_an_unrequired_level(self):
        result = self.check(self.record(skills=['Excel']), skills=[{'name': 'Excel', 'level': None}])
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(result['user_information_gaps'], [])

    def test_question_for_unanswered_skills_includes_the_required_level(self):
        result = self.check(self.record(skills=['Excel بمستوى متقدم على الأقل']))
        question = result['user_information_gaps'][0]['question']
        self.assertIn('Excel', question)
        self.assertIn('متقدم', question)

    def test_interest_and_major_do_not_prove_a_skill(self):
        result = self.check(self.record(skills=['Python']), field_of_study='علوم الحاسب', interests=['Python'])
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(result['user_missing_fields'], ['profile.skills'])

    def test_education_minimum_exact_and_unspecified_scope(self):
        minimum = self.record(mandatory=['المستوى التعليمي المطلوب: بكالوريوس فأعلى'])
        self.assertEqual(self.check(minimum, education_level='master')['status'], 'confirmed')
        self.assertEqual(self.check(minimum, education_level='diploma')['status'], 'ineligible')
        exact = self.record(mandatory=['المستوى التعليمي المطلوب: بكالوريوس فقط'])
        self.assertEqual(self.check(exact, education_level='master')['status'], 'ineligible')
        ambiguous = self.record(mandatory=['المستوى التعليمي المطلوب: بكالوريوس'])
        self.assertEqual(self.check(ambiguous, education_level='master')['status'], 'uncertain')

    def test_age_study_year_and_student_status_never_request_nonexistent_fields(self):
        for requirement in ('العمر 18 سنة على الأقل', 'يشترط أن يكون المتقدم في السنة الثالثة',
                            'يشترط أن يكون المتقدم طالبًا جامعيًا'):
            with self.subTest(requirement=requirement):
                result = self.check(self.record(mandatory=[requirement]), education_level='bachelor')
                self.assertEqual(result['status'], 'uncertain')
                self.assertEqual(result['user_missing_fields'], [])

    def test_negation_alternatives_and_extra_clauses_are_not_partially_executed(self):
        for requirement in ('Excel أو SQL', 'بدون Excel', 'Excel بمستوى خبير',
                            'Excel بمستوى متوسط على الأقل والعمر 18 سنة'):
            with self.subTest(requirement=requirement):
                result = self.check(self.record(skills=[requirement]), skills=[{'name': 'Excel', 'level': 'advanced'}])
                self.assertEqual(result['status'], 'uncertain')
                self.assertEqual(result['user_missing_fields'], [])

    def test_preferred_requirement_cannot_fail_eligibility_or_ask_a_question(self):
        result = self.check(self.record(preferred=['إجادة Excel بمستوى متقدم على الأقل']), skills=[])
        self.assertEqual(result['status'], 'confirmed')
        self.assertTrue(any(c['status'] == 'failed' and not c['mandatory'] for c in result['checks']))
        self.assertEqual(result['user_missing_fields'], [])

    def test_known_failure_wins_over_missing_skills_and_suppresses_questions(self):
        result = self.check(self.record(mandatory=['المستوى التعليمي المطلوب: ماجستير فأعلى'], skills=['Excel']), education_level='bachelor')
        self.assertEqual(result['status'], 'ineligible')
        self.assertEqual(result['user_missing_fields'], [])
        self.assertFalse(result['eligible_for_question_selection'])

    def test_conflicting_requirements_do_not_select_a_convenient_value(self):
        for requirements in (['المدينة المطلوبة: الرياض', 'المدينة المطلوبة: جدة'],
                             ['المستوى التعليمي المطلوب: بكالوريوس فقط', 'المستوى التعليمي المطلوب: ماجستير فأعلى']):
            result = self.check(self.record(mandatory=requirements), city='الرياض', education_level='bachelor')
            self.assertEqual(result['status'], 'uncertain')
            self.assertEqual(result['user_missing_fields'], [])

    def test_source_conflict_and_source_gap_cannot_be_fixed_by_a_user_question(self):
        record = self.record(skills=['Excel'])
        record[0]['facts']['mandatory_requirements'] = {'status': 'conflicted', 'value': None, 'evidence_ids': []}
        result = self.check(record)
        self.assertEqual(result['user_missing_fields'], ['profile.skills'])
        self.assertFalse(result['eligible_for_question_selection'])
        selected = select_eligibility_questions([result], self.gates(result), UserProfile())
        self.assertEqual(selected['decision'], 'no_actionable_question')

    def test_catalog_unsupported_skill_cannot_generate_an_unanswerable_question(self):
        result = self.check(self.record(skills=['Rust']))
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(result['user_missing_fields'], [])
        self.assertFalse(result['eligible_for_question_selection'])

    def test_duplicate_skill_aliases_do_not_pick_the_strongest_level(self):
        result = self.check(self.record(skills=['Excel بمستوى متقدم على الأقل']),
                            skills=[{'name': 'Excel', 'level': 'beginner'}, {'name': 'إكسل', 'level': 'advanced'}])
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(result['user_missing_fields'], ['profile.skills'])

    def test_duplicate_aliases_do_not_request_a_level_when_only_possession_matters(self):
        profile = {'skills': [{'name': 'Excel', 'level': 'beginner'}, {'name': 'إكسل', 'level': 'advanced'}]}
        result = self.check(self.record(skills=['Excel']), **profile)
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(result['user_missing_fields'], [])

    def test_ask_only_for_a_viable_candidate_and_emit_public_contract_fields(self):
        result = self.check(self.record(skills=['Excel بمستوى متوسط على الأقل']))
        for topic, constraints, expected in [('related', 'constraints_satisfied', 'ask_user'),
                                             ('unrelated', 'constraints_satisfied', 'no_viable_candidates'),
                                             ('related', 'excluded', 'no_viable_candidates'),
                                             ('related', 'needs_source_info', 'no_viable_candidates')]:
            proposal = select_eligibility_questions([result], self.gates(result, topic=topic, constraints=constraints), UserProfile())
            self.assertEqual(proposal['decision'], expected)
            if expected == 'ask_user':
                response = DiscoveryResponse(request_id='test', status='needs_info', message='حدد مستواك',
                    missing_fields=proposal['missing_fields'], missing_explanations=proposal['missing_explanations'])
                self.assertEqual(response.missing_fields, ['profile.skills'])

    def test_fewer_fields_for_one_candidate_beat_asking_about_every_candidate(self):
        two = self.check(self.record(mandatory=['المستوى التعليمي المطلوب: بكالوريوس'], skills=['Excel']))
        one_record = self.record(mandatory=['التخصص المطلوب: علوم الحاسب'])
        one_record[0]['opportunity_id'] = 'SECOND'
        for e in one_record[2].values():
            e['opportunity_id'] = 'SECOND'
        one = self.check(one_record)
        proposal = select_eligibility_questions([two, one], {**self.gates(two), **self.gates(one)}, UserProfile())
        self.assertEqual(proposal['selected_candidate_id'], 'SECOND')
        self.assertEqual(proposal['missing_fields'], ['profile.field_of_study'])

    def test_stale_profile_evidence_or_missing_gates_stop_question_selection(self):
        result = self.check(self.record(skills=['Excel']))
        with self.assertRaisesRegex(ValueError, 'stale_profile'):
            select_eligibility_questions([result], self.gates(result), UserProfile(city='جدة'))
        gate = self.gates(result)
        gate['TEST']['evidence_version'] = 'old'
        with self.assertRaisesRegex(ValueError, 'stale_evidence'):
            select_eligibility_questions([result], gate, UserProfile())
        with self.assertRaises(ValueError):
            select_eligibility_questions([result], {}, UserProfile())

    def test_forged_quotes_wrong_version_and_malformed_requirement_lists_are_errors(self):
        record = self.record()
        with self.assertRaisesRegex(ValueError, 'stale_evidence'):
            check_eligibility(*record, UserProfile(), expected_evidence_version='old')
        record[2]['E0']['quote'] = 'forged source text'
        with self.assertRaises(DataAccessError):
            self.check(record)
        record = self.record(skills=['   '])
        with self.assertRaises(DataAccessError):
            self.check(record)

    def test_inputs_are_unchanged_and_decisions_retain_exact_requirement_provenance(self):
        record = self.record(skills=['إكسل'])
        before = deepcopy(record)
        result = self.check(record, skills=[{'name': 'Excel', 'level': None}])
        self.assertEqual(record, before)
        check = next(c for c in result['checks'] if c.get('requirement_text') == 'إكسل')
        proof = check['source']['evidence'][0]
        self.assertIn(proof['quote'], record[1]['S']['content'])
        self.assertEqual(proof['source_id'], 'S')

    def test_answerable_catalog_stays_synchronized_with_frontend_choices(self):
        text = (ROOT / 'frontend/src/profile/choices.ts').read_text(encoding='utf-8-sig')
        for key, name in [('skills', 'SKILLS'), ('cities', 'CITIES'), ('majors', 'MAJORS')]:
            values = json.loads(re.search(r'export const ' + name + r': string\[\] = (\[[\s\S]*?\]);', text)[1])
            self.assertEqual(CATALOG[key], values)


if __name__ == '__main__':
    unittest.main()
