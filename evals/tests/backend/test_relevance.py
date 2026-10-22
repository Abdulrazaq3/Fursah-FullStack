"""Check calibration boundaries and distinguish empty results from invalid scores."""
import copy
import unittest

from app.relevance import calibrate_threshold, gate_candidates, summarize


class TopicGateTests(unittest.TestCase):
    def test_calibration_rejects_all_known_negatives_without_forcing_positive_count(self):
        pairs = [(0.7, True), (0.6, True), (0.4, False), (0.5, False)]
        threshold = calibrate_threshold(pairs)
        self.assertGreater(threshold, 0.5)
        self.assertLess(threshold, 0.6)
        self.assertTrue(all(score < threshold for score, label in pairs if not label))

    def test_overlapping_scores_disable_acceptance_instead_of_inventing_a_cutoff(self):
        self.assertIsNone(calibrate_threshold([(0.6, True), (0.6, False), (0.7, False)]))

    def test_calibration_requires_both_classes_and_valid_scores(self):
        for pairs in [[], [(0.7, True)], [(0.2, False)], [(float('nan'), True), (0.4, False)], [(1.1, True), (0.4, False)]]:
            with self.subTest(pairs=pairs), self.assertRaises(ValueError):
                calibrate_threshold(pairs)

    def test_filter_can_return_zero_one_or_multiple_without_mutating_hits(self):
        hits = [{'opportunity_id': 'A', 'cosine_similarity': 0.7}, {'opportunity_id': 'B', 'cosine_similarity': 0.6}]
        original = copy.deepcopy(hits)
        self.assertEqual(gate_candidates(hits, 0.8), [])
        self.assertEqual([hit['opportunity_id'] for hit in gate_candidates(hits, 0.65)], ['A'])
        self.assertEqual(gate_candidates(hits, 0.6), hits)
        self.assertEqual(gate_candidates(hits, None), [])
        self.assertEqual(hits, original)

    def test_invalid_candidates_are_not_treated_as_a_valid_empty_result(self):
        for hits in [[{'opportunity_id':'A', 'cosine_similarity':float('inf')}],
                     [{'opportunity_id':'A', 'cosine_similarity':True}],
                     [{'opportunity_id':'A', 'cosine_similarity':0.5}] * 2]:
            with self.subTest(hits=hits), self.assertRaises(ValueError):
                gate_candidates(hits, None)

    def test_metrics_expose_missed_relevant_candidates_and_false_acceptance(self):
        rows = [
            {'relevant_ids':['A', 'B'], 'hits':[{'opportunity_id':'A', 'cosine_similarity':0.8}, {'opportunity_id':'B', 'cosine_similarity':0.4}]},
            {'relevant_ids':[], 'hits':[{'opportunity_id':'C', 'cosine_similarity':0.6}]},
        ]
        summary = summarize(rows, 0.5)
        self.assertEqual(summary['true_positive_candidates'], 1)
        self.assertEqual(summary['false_positive_candidates'], 1)
        self.assertEqual(summary['missed_relevant_candidates'], 1)
        self.assertEqual(summary['candidate_precision'], 0.5)
        self.assertEqual(summary['candidate_recall'], 0.5)
        self.assertEqual(summary['negative_queries_with_any_hit'], 1)


if __name__ == '__main__':
    unittest.main()
