import unittest
from app.query_alternatives import plan_alternatives, verify_alternatives
from app.topic_verifier import TopicPolicy, build_candidate


class QueryAlternativeTests(unittest.TestCase):
    def candidates(self):
        result = []
        for identifier, title in [('E','تعلم Excel'),('S','تعلم SQL'),('P','تعلم Python')]:
            source = {'source_id':identifier,'content':title+'\nتجربة الأداة وتطبيقها.'}
            result.append(build_candidate(identifier,{identifier:source},[identifier],[
                dict(role='title',source_id=identifier,quote=title),
                dict(role='activity',source_id=identifier,quote='تجربة الأداة وتطبيقها.')]))
        return result

    def test_literal_span_preserves_prefix_suffix_and_aliases(self):
        plan = plan_alternatives('أبحث عن فرصة أتعلم فيها إكسل أو SQL ضمن نشاط مناسب')
        self.assertEqual(plan.branches,('أبحث عن فرصة أتعلم فيها إكسل ضمن نشاط مناسب',
                                        'أبحث عن فرصة أتعلم فيها SQL ضمن نشاط مناسب'))
        self.assertEqual(plan.decision,'expanded')

    def test_english_or_and_attached_preposition(self):
        self.assertEqual(plan_alternatives('أتدرب بإكسل or SQL').branches,('أتدرب بإكسل','أتدرب SQL'))

    def test_conjunction_negation_history_mixed_scope_are_not_split(self):
        for query in ['أتعلم Excel وSQL','لا أريد Excel أو SQL','خبرتي في Excel أو SQL',
                      'Excel أو SQL وPython','Excel أو SQL معا','Excel متقدم أو SQL',
                      'تحليل البيانات باستخدام Excel أو SQL','Excel أو ورشة أو SQL']:
            with self.subTest(query=query):
                self.assertFalse(plan_alternatives(query).branches)

    def test_version_binds_original_wording(self):
        a=plan_alternatives('تعلم Excel أو SQL')
        self.assertEqual(a.version,plan_alternatives(a.original_query).version)
        self.assertNotEqual(a.version,plan_alternatives('أتعلم Excel أو SQL').version)

    def test_recovery_needs_branch_model_acceptance_and_original_support(self):
        candidates=self.candidates()
        versions={c.opportunity_id:c.topic_evidence_version for c in candidates}
        def score(pairs):
            query=pairs[0][0]
            if 'أو' in query: return [.001]*3
            return [.9 if query.split()[-1] in passage else .001 for _,passage in pairs]
        result=verify_alternatives('أتعلم Excel أو SQL',candidates,versions,TopicPolicy(.1,.01),score)
        self.assertTrue(all(d['decision']!='related' for d in result['baseline']))
        self.assertEqual([d['opportunity_id'] for d in result['decisions'] if d['decision']=='related'],['E','S'])
        self.assertTrue(result['decisions'][0]['branch_decisions'])

    def test_keyword_support_does_not_promote_low_branch_scores(self):
        candidates=self.candidates(); versions={c.opportunity_id:c.topic_evidence_version for c in candidates}
        result=verify_alternatives('Excel أو SQL',candidates,versions,TopicPolicy(.1,.01),lambda pairs:[.001]*len(pairs))
        self.assertTrue(all(d['decision']!='related' for d in result['decisions']))

    def test_stale_evidence_and_invalid_branch_scores_stop_inference(self):
        candidates=self.candidates(); versions={c.opportunity_id:c.topic_evidence_version for c in candidates}
        with self.assertRaises(ValueError):
            verify_alternatives('Excel أو SQL',candidates,{},TopicPolicy(.1,.01),lambda pairs:self.fail('stale scoring'))
        with self.assertRaises(ValueError):
            verify_alternatives('Excel أو SQL',candidates,versions,TopicPolicy(.1,.01),
                                lambda pairs:[float('nan')]*len(pairs),original_scores=[.001]*3)

    def test_no_branch_for_and_means_original_score_only(self):
        candidates=self.candidates(); versions={c.opportunity_id:c.topic_evidence_version for c in candidates}
        result=verify_alternatives('Excel وSQL',candidates,versions,TopicPolicy(.1,.01),
                                  lambda pairs:self.fail('Unexpected branch call'),original_scores=[.9]*3)
        self.assertTrue(all(d['decision']!='related' for d in result['decisions']))
