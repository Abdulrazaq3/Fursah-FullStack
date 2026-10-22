import unittest
from app.normalized_alternatives_v31 import normalize_branch, normalize_branch_details


class PracticalQualifierTests(unittest.TestCase):
    def test_practical_requirement_is_paraphrased_not_dropped(self):
        self.assertEqual(normalize_branch('أبحث على فرصة لتعلم إكسل بشكل عملي'), 'تعلم Excel عمليًا')

    def test_unknown_context_after_practical_requirement_survives(self):
        query='أريد تعلم SQL بشكل عملي لتطبيقات مالية'
        result=normalize_branch_details(query)
        self.assertEqual(result['normalized_query'], 'تعلم SQL عمليًا لتطبيقات مالية')
        self.assertEqual(result['retained_suffix'], ' لتطبيقات مالية')
        self.assertTrue(result['practical_qualifier'])
        for ref in result['evidence']:
            self.assertEqual(query[ref['start']:ref['end']], ref['quote'])

    def test_negated_or_different_practical_context_is_not_paraphrased(self):
        self.assertEqual(normalize_branch('أريد تعلم Excel بدون تطبيق عملي'), 'تعلم Excel بدون تطبيق عملي')
        self.assertEqual(normalize_branch('أريد تعلم Excel بشكل عملياته'), 'تعلم Excel بشكل عملياته')

    def test_trying_and_practical_requirement_both_survive(self):
        self.assertEqual(normalize_branch('أود تجربة Python ضمن فرصة للتعلم بشكل عملي'),
                         'تعلم Python بالتجربة عمليًا')
