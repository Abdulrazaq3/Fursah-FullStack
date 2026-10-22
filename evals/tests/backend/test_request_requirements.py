import unittest

from app.request_requirements import extract_requirements, verify_with_requirements
from app.topic_verifier import TopicPolicy, build_candidate


class RequestRequirementTests(unittest.TestCase):
    def candidate(self, title='تحليل البيانات باستخدام Excel', activity='ترتيب الجداول وقراءة المؤشرات'):
        source={'source_id':'S1','content':title+'. '+activity+'.'}
        return build_candidate('A',{'S1':source},['S1'],[
            {'role':'title','source_id':'S1','quote':title},
            {'role':'activity','source_id':'S1','quote':activity}])

    def verify(self,query,item,score=0.99):
        return verify_with_requirements(query,[item],{'A':item.topic_evidence_version},
                                        TopicPolicy(0.7,0.3),lambda pairs:[score])

    def test_arabic_alias_diacritics_and_exact_original_spans(self):
        query='أريد التحليل بِإِكْسِل وبايثون'
        requirements=extract_requirements(query)
        self.assertEqual({m['tool'] for m in requirements.tools},{'excel','python'})
        for mention in requirements.tools:
            self.assertEqual(query[mention['start']:mention['end']],mention['quote'])

    def test_tool_boundaries_do_not_confuse_sqlite_or_excellent_with_sql_excel(self):
        requirements=extract_requirements('excellent SQLite JavaScript')
        self.assertEqual({m['tool'] for m in requirements.tools},{'sqlite','javascript'})

    def test_activity_substrings_do_not_turn_cultural_design_into_poetry(self):
        self.assertEqual(extract_requirements('تصميم بوستر لفعالية ثقافية').activities,())
        self.assertEqual(extract_requirements('تعلم القافية والشعر').activities[0]['activity'],'poetry')

    def test_possessive_ideas_still_identify_a_public_presentation(self):
        requirements=extract_requirements('تجهيز عرض قصير أقدم به أفكاري للحاضرين')
        self.assertEqual([a['activity'] for a in requirements.activities],['public_presentation'])

    def test_presentation_verbs_require_an_idea_or_audience_anchor(self):
        for query in ('تدريب يساعدني أعرض أفكارهم بشكل منظم',
                      'نتعلم كيف نعرض فكرتنا', 'تعرض فكرة للجمهور', 'يعرض أفكاره'):
            with self.subTest(query=query):
                self.assertEqual([a['activity'] for a in extract_requirements(query).activities],
                                 ['public_presentation'])
        for query in ('شارع أعرض قرب المتجر', 'عرض منتجات', 'أعرض صور الرحلة'):
            with self.subTest(query=query):
                self.assertEqual(extract_requirements(query).activities,())

    def test_alias_match_preserves_semantic_decision_and_provenance(self):
        _,results=self.verify('تحليل البيانات بإكسل',self.candidate())
        result=results[0]
        self.assertEqual(result['decision'],'related')
        self.assertEqual(result['requirements_check']['status'],'supported')
        self.assertEqual(result['requirements_check']['checks'][0]['evidence'][0]['source_id'],'S1')
        self.assertFalse(result['eligibility_checked'])

    def test_high_model_score_does_not_supply_missing_excel_evidence(self):
        _,results=self.verify('تحليل الجداول في Excel',self.candidate('استعلامات SQL','طرح الأسئلة على الجداول'))
        self.assertEqual(results[0]['semantic_decision'],'related')
        self.assertEqual(results[0]['decision'],'insufficient_evidence')
        self.assertEqual(results[0]['requirements_check']['checks'][0]['status'],'unknown')

    def test_presentation_is_not_established_by_newsletter_editing(self):
        _,results=self.verify('عرض فكرة أمام الجمهور',self.candidate('تحرير نشرة مجتمعية','اختيار الأخبار ومراجعة العناوين'))
        self.assertEqual(results[0]['decision'],'insufficient_evidence')

    def test_shared_tool_does_not_promote_a_low_semantic_score(self):
        _,results=self.verify('تعلم Excel',self.candidate(),score=0.1)
        self.assertEqual(results[0]['decision'],'unrelated')

    def test_any_tool_and_all_tools_have_different_evidence_requirements(self):
        item=self.candidate()
        requirement,results=self.verify('تعلم Excel أو SQL',item)
        self.assertEqual(requirement.tool_mode,'any')
        self.assertEqual(results[0]['decision'],'related')
        requirement,results=self.verify('تعلم Excel وSQL',item)
        self.assertEqual(requirement.tool_mode,'all')
        self.assertEqual(results[0]['decision'],'insufficient_evidence')

    def test_negation_and_history_do_not_become_positive_tool_requirements(self):
        requirements=extract_requirements('ما أبي SQL، أبي Excel')
        self.assertEqual([(m['tool'],m['polarity']) for m in requirements.tools],
                         [('sql','excluded'),('excel','required')])
        requirements,results=self.verify('خبرتي في SQL وأبي أتعلم Excel',self.candidate())
        self.assertTrue(requirements.review_reasons)
        self.assertEqual(results[0]['decision'],'insufficient_evidence')

    def test_negation_must_be_a_separate_word(self):
        for query in ('مشروع صغير SQL', 'اختبار نمو Python', 'cannot Excel'):
            with self.subTest(query=query):
                requirements=extract_requirements(query)
                self.assertEqual([m['polarity'] for m in requirements.tools],['required'])
        requirements=extract_requirements('غير SQL')
        self.assertEqual([m['polarity'] for m in requirements.tools],['excluded'])

    def test_absent_negative_evidence_and_conflicting_source_stay_unknown(self):
        _,results=self.verify('تحليل بيانات بدون SQL',self.candidate())
        self.assertEqual(results[0]['decision'],'insufficient_evidence')
        _,results=self.verify('تعلم Excel',self.candidate('Excel','لا يشمل Excel'))
        self.assertEqual(results[0]['requirements_check']['status'],'unknown')
        self.assertEqual(results[0]['decision'],'insufficient_evidence')

    def test_explicitly_excluded_tool_blocks_even_a_high_score(self):
        _,results=self.verify('تدريب بدون Excel',self.candidate())
        self.assertEqual(results[0]['decision'],'unrelated')

    def test_multiple_activities_abstain_and_unknown_activity_remains_unchecked(self):
        requirements,results=self.verify('عرض فكرة للجمهور وتحرير نشرة',self.candidate())
        self.assertIn('multiple_activities_need_interpretation',requirements.review_reasons)
        self.assertEqual(results[0]['decision'],'insufficient_evidence')
        _,results=self.verify('التوعية بالنوم الصحي',self.candidate())
        self.assertEqual(results[0]['requirements_check']['status'],'not_checked')

    def test_stale_evidence_or_broken_model_output_remains_an_error(self):
        item=self.candidate()
        with self.assertRaisesRegex(ValueError,'stale_evidence'):
            verify_with_requirements('تعلم Excel',[item],{'A':'old'},TopicPolicy(0.7,0.3),lambda pairs:[0.9])
        with self.assertRaises(ValueError):
            verify_with_requirements('تعلم Excel',[item],{'A':item.topic_evidence_version},
                                     TopicPolicy(0.7,0.3),lambda pairs:[float('nan')])


if __name__=='__main__':
    unittest.main()
