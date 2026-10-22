import unittest
from app.normalized_alternatives import normalize_branch, plan_normalized_alternatives, verify_alternatives
from app.topic_verifier import TopicPolicy
import test_query_alternatives as fixtures


class NormalizedAlternativeTests(unittest.TestCase):
    def test_only_known_request_words_leave_learning_goal_and_tool(self):
        plan=plan_normalized_alternatives('أبحث عن فرصة أتعلم فيها إكسل أو SQL ضمن نشاط مناسب')
        self.assertEqual(plan.branches,('تعلم Excel','تعلم SQL'))
        self.assertIn('أبحث',plan.literal_branches[0])

    def test_trying_is_not_rewritten_to_learning(self):
        self.assertEqual(normalize_branch('أريد تجربة بايثون ضمن نشاط مناسب'),'تجربة Python')

    def test_unknown_prefix_prevents_dropping_domain_constraints(self):
        for query in ['أتعلم المحاسبة باستخدام Excel','أبحث عن وظيفة في SQL','أتعلم وأجرب Python']:
            self.assertEqual(normalize_branch(query),query)

    def test_unknown_suffix_and_practical_qualifier_survive_verbatim(self):
        for tail in [' بشكل عملي',' في الرياض فقط',' لتطبيقات مالية',' لمستوى متقدم']:
            self.assertEqual(normalize_branch('أريد تعلم Excel'+tail),'تعلم Excel'+tail)

    def test_original_guards_still_block_nonrequested_tools(self):
        candidates=fixtures.QueryAlternativeTests().candidates()
        versions={c.opportunity_id:c.topic_evidence_version for c in candidates}
        result=verify_alternatives('أريد تعلم Excel أو SQL',candidates,versions,TopicPolicy(.1,.01),
                                  lambda pairs:[.9]*len(pairs),original_scores=[.001]*3)
        self.assertEqual([d['opportunity_id'] for d in result['decisions'] if d['decision']=='related'],['E','S'])
