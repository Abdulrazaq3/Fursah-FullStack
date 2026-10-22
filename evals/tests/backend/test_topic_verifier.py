import unittest

from app.topic_verifier import TopicPolicy, build_candidate, calibrate_policy, verify_topics


class TopicVerifierTests(unittest.TestCase):
    def candidate(self, activity=True):
        source = {'source_id': 'S1', 'content': 'Clear writing. Edit letters.'}
        excerpts = [{'role': 'title', 'source_id': 'S1', 'quote': 'Clear writing.'}]
        if activity:
            excerpts.append({'role': 'activity', 'source_id': 'S1', 'quote': 'Edit letters.'})
        return build_candidate('A', {'S1': source}, ['S1'], excerpts)

    def test_forged_quote_and_foreign_source_are_rejected(self):
        for excerpt in [{'role': 'title', 'source_id': 'S1', 'quote': 'Learn SQL'},
                        {'role': 'title', 'source_id': 'S2', 'quote': 'Clear writing.'}]:
            with self.subTest(excerpt=excerpt), self.assertRaises(ValueError):
                build_candidate('A', {'S1': {'source_id': 'S1', 'content': 'Clear writing.'}}, ['S1'], [excerpt])

    def test_incomplete_activity_stays_uncertain_without_calling_model(self):
        item = self.candidate(False)
        def forbidden(pairs):
            self.fail('Missing evidence must not be scored')
        result = verify_topics('writing', [item], {'A': item.topic_evidence_version}, TopicPolicy(0.7, 0.3), forbidden)
        self.assertEqual(result[0]['decision'], 'insufficient_evidence')
        self.assertIsNone(result[0]['score'])

    def test_source_change_invalidates_topic_version_before_scoring(self):
        item = self.candidate()
        with self.assertRaisesRegex(ValueError, 'stale_evidence'):
            verify_topics('writing', [item], {'A': 'old'}, TopicPolicy(0.7, 0.3), lambda pairs: [0.99])
        changed = build_candidate('A', {'S1': {'source_id': 'S1', 'content': item.passage + ' New update.'}},
                                  ['S1'], [dict(role=r, source_id=s, quote=q) for r, s, q in item.excerpts])
        self.assertNotEqual(item.topic_evidence_version, changed.topic_evidence_version)

    def test_decisions_preserve_evidence_and_do_not_confirm_eligibility(self):
        item = self.candidate()
        for score, expected in [(0.8, 'related'), (0.5, 'insufficient_evidence'), (0.1, 'unrelated')]:
            with self.subTest(score=score):
                result = verify_topics('writing', [item], {'A': item.topic_evidence_version},
                                       TopicPolicy(0.7, 0.3), lambda pairs: [score])[0]
                self.assertEqual(result['decision'], expected)
                self.assertEqual(result['excerpts'][1]['quote'], 'Edit letters.')
                self.assertFalse(result['eligibility_checked'])

    def test_failed_model_output_is_error_instead_of_no_match(self):
        item = self.candidate()
        for output in [[], [float('nan')], [True], [1.1], [0.3, 0.4]]:
            with self.subTest(output=output), self.assertRaises(ValueError):
                verify_topics('writing', [item], {'A': item.topic_evidence_version},
                              TopicPolicy(0.7, 0.3), lambda pairs: output)

    def test_overlapping_calibration_allows_uncertainty(self):
        policy = calibrate_policy([(0.9, True), (0.5, True), (0.6, False), (0.2, False)])
        self.assertEqual(policy.reject_below, 0.5)
        self.assertGreater(policy.accept_at, 0.6)
        self.assertEqual(calibrate_policy([(0.4, True), (0.5, False)]), TopicPolicy(None, None))
        with self.assertRaises(ValueError):
            TopicPolicy(0.4, 0.6)


if __name__ == '__main__':
    unittest.main()
