import unittest

from app.normalized_alternatives import normalize_branch as old_normalize
from app.normalized_alternatives_v3 import normalize_branch, normalize_branch_details, plan_normalized_alternatives


class NormalizedAlternativeV3Tests(unittest.TestCase):
    def test_request_lexicon_uses_same_arabic_normalization_as_input(self):
        for word in ['على', 'علي', 'عَلَى']:
            self.assertEqual(normalize_branch(f'أدور {word} فرصة لتعلم إكسل بشكل عملي'),
                             'تعلم Excel بشكل عملي')

    def test_explicit_learning_purpose_retains_trying_method(self):
        for tail in ['ضمن فرصة للتعلم', 'في نشاط بهدف التعلم', 'من خلال برنامج للتعلم']:
            self.assertEqual(normalize_branch('أريد تجربة SQL ' + tail), 'تعلم SQL بالتجربة')

    def test_trying_without_learning_purpose_remains_trying(self):
        self.assertEqual(normalize_branch('أريد تجربة SQL ضمن فرصة مناسبة'), 'تجربة SQL')

    def test_unknown_prefix_is_never_removed(self):
        query='أريد تجربة برمجية في SQL ضمن فرصة للتعلم'
        self.assertEqual(normalize_branch(query), query)

    def test_known_purpose_does_not_consume_following_constraints(self):
        for tail in [' في الرياض فقط',' بشكل عملي',' بدون شهادة',' لتطبيقات مالية']:
            self.assertEqual(normalize_branch('أريد تجربة SQL ضمن فرصة للتعلم'+tail),
                             'تعلم SQL بالتجربة'+tail)

    def test_purpose_word_boundaries_prevent_substring_interpretation(self):
        query='أريد تجربة SQL ضمن فرصة للتعلميات'
        self.assertEqual(normalize_branch(query), 'تجربة SQL ضمن فرصة للتعلميات')

    def test_goal_quotes_and_offsets_are_exact(self):
        branch='أريد تجربة إكسل ضمن فرصة للتعلم في جدة'
        result=normalize_branch_details(branch)
        self.assertEqual((result['goal'],result['method']), ('learn','try'))
        for ref in result['evidence']:
            self.assertEqual(branch[ref['start']:ref['end']], ref['quote'])
        self.assertEqual(result['retained_suffix'], ' في جدة')

    def test_old_version_preserved_and_new_plan_keeps_practical_qualifier(self):
        query='أدور على فرصة لتعلم إكسل أو SQL بشكل عملي'
        self.assertEqual(old_normalize('أدور على فرصة لتعلم إكسل بشكل عملي'),
                         'أدور على فرصة لتعلم إكسل بشكل عملي')
        plan=plan_normalized_alternatives(query)
        self.assertEqual(plan.branches, ('تعلم Excel بشكل عملي','تعلم SQL بشكل عملي'))
        self.assertEqual(plan.original_query, query)
