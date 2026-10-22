import json
import unittest
from types import SimpleNamespace

from evals.run import CaseSpans,grade_failures,run_graders,verify_manifest,BACKEND
from evals.grading import Grade
from evals import catalog_graders as g
from app.schemas import DiscoveryResponse,Recommendation


def spans(**values):
    return CaseSpans([(name.replace('_','.',1),{'output.value':json.dumps(value)}) for name,value in values.items()])


def response(ids=('A',),status='ok'):
    return DiscoveryResponse(request_id='eval-unit',status=status,message='test',recommendations=[Recommendation(
        opportunity_id=i,evidence_version='v1',title='Title',source_ids=['S1'],eligibility_status='uncertain',reason='المصدر «exact activity»') for i in ids])


class CatalogGraderTests(unittest.TestCase):
    def test_recall_counts_unique_ids_with_complete_denominator(self):
        s=spans(fursah_retrieval=['A','A','B'])
        self.assertEqual(g.grade_recall({'expected_relevant_ids':['A','B','C']},response(),s).score,2/3)

    def test_recall_missing_span_is_zero_not_unmeasured(self):
        self.assertEqual(g.grade_recall({'expected_relevant_ids':['A']},response(),CaseSpans([])).score,0)

    def test_ndcg_rewards_earlier_relevant_result(self):
        case={'expected_relevant_ids':['A']}
        early=g.grade_ndcg(case,response(),spans(fursah_rerank=[{'opportunity_id':'A'},{'opportunity_id':'B'}]))
        late=g.grade_ndcg(case,response(),spans(fursah_rerank=[{'opportunity_id':'B'},{'opportunity_id':'A'}]))
        self.assertEqual(early.score,1);self.assertLess(late.score,early.score)

    def test_partial_labels_do_not_falsely_penalize_unknown_alternatives(self):
        case={'expected_status':'ok','expected_relevant_ids':['A']}
        self.assertIsNone(g.grade_precision(case,response(('A','B')),CaseSpans([])))
        case['expected_allowed_ids']=['A']
        self.assertEqual(g.grade_precision(case,response(('A','B')),CaseSpans([])).score,.5)

    def test_empty_positive_case_cannot_pass_by_abstaining(self):
        case={'expected_status':'ok','expected_allowed_ids':['A']}
        self.assertEqual(g.grade_hit(case,response((),status='no_match'),CaseSpans([])).score,0)
        self.assertEqual(g.grade_precision(case,response((),status='no_match'),CaseSpans([])).score,0)

    def test_duplicated_recommendations_not_full_precision(self):
        self.assertEqual(g.grade_precision({'expected_status':'ok','expected_allowed_ids':['A']},response(('A','A')),CaseSpans([])).score,0)

    def test_budget_unknown_fails_even_if_runtime_gate_says_pass(self):
        s=spans(fursah_candidate_check={'opportunity_id':'A','constraint_decision':'constraints_satisfied','eligibility_status':'uncertain'},
                fursah_details={'opportunity_id':'A','details':{'cost':None}})
        self.assertEqual(g.grade_hard_constraints({'constraints':{'max_budget_sar':0}},response(),s).score,0)

    def test_per_query_resolution_controls_independent_constraint_grade(self):
        s=spans(fursah_candidate_check={'opportunity_id':'A','constraint_decision':'constraints_satisfied','eligibility_status':'uncertain'},
                fursah_details={'opportunity_id':'A','details':{'delivery_mode':'online'}})
        case={'constraints':{'delivery_modes':['in_person']},'expected_effective_constraints':{'delivery_modes':['online']}}
        self.assertEqual(g.grade_hard_constraints(case,response(),s).score,1)

    def test_invented_explanation_not_grounded(self):
        s=spans(fursah_candidate_check={'opportunity_id':'A','source_contents':{'S1':'different original'},'evidence_quotes':['exact activity']})
        self.assertEqual(g.grade_grounding({},response(),s).score,0)

    def test_source_version_mismatch_fails(self):
        s=spans(fursah_candidate_check={'opportunity_id':'A','evidence_version':'changed','source_ids':['S1']})
        self.assertEqual(g.grade_evidence({},response(),s).score,0)

    def test_adversarial_case_cannot_pass_by_missing_target(self):
        self.assertEqual(g.grade_target_coverage({'required_retrieved_ids':['CLOSED']},response(),spans(fursah_retrieval=['A'])).score,0)

    def test_ranking_diagnostics_not_implicitly_gated_at_one(self):
        grades=[Grade('retrieval.recall_at_20',.5),Grade('e2e.status',1)]
        self.assertEqual(grade_failures(grades,{},g.CRITICAL_METRICS),[])
        self.assertEqual(len(grade_failures(grades,{'metric_thresholds':{'retrieval.recall_at_20':.8}},g.CRITICAL_METRICS)),1)

    def test_all_old_graders_keep_original_failure_rule(self):
        self.assertEqual(len(grade_failures([Grade('old.metric',.5)],{})),1)

    def test_cases_and_catalog_are_frozen_before_any_model_call(self):
        self.assertIsInstance(verify_manifest(BACKEND.parent/'evals/cases/dev.jsonl'),str)

    def test_grader_errors_cannot_be_silently_passed(self):
        _,errors=run_graders([lambda *_:Grade('bad',float('nan'))],{},None,CaseSpans([]))
        self.assertEqual(len(errors),1)


if __name__=='__main__':unittest.main()
