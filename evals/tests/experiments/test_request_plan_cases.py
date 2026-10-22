"""The bounded reader/merge expectations run in CI without replacing reports."""
import unittest
from evaluate_request_plan import FIXTURE, evaluate, read


class RequestPlanCases(unittest.TestCase):
    def test_labelled_cases_and_unchanged_input_snapshots(self):
        results = evaluate(read(FIXTURE))
        self.assertEqual(len(results), 30)
        for row in results:
            with self.subTest(case=row['id']):
                self.assertTrue(row['passed'], row)


if __name__ == '__main__':
    unittest.main()
