"""Golden eligibility and question scenarios run offline in the existing CI job."""
import unittest
from evaluate_eligibility import evaluate, read, FIXTURE, SAMPLE


class EligibilityCases(unittest.TestCase):
    def test_labelled_eligibility_cases(self):
        results, _ = evaluate(read(FIXTURE), read(SAMPLE))
        self.assertEqual(len(results), 28)
        for row in results:
            with self.subTest(case=row['id']):
                self.assertTrue(row['passed'], row)

    def test_labelled_question_impact_scenarios(self):
        _, results = evaluate(read(FIXTURE), read(SAMPLE))
        self.assertEqual(len(results), 10)
        for row in results:
            with self.subTest(scenario=row['id']):
                self.assertTrue(row['passed'], row)


if __name__ == '__main__':
    unittest.main()
