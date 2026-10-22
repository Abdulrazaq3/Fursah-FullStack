import unittest
from evals.source_audit import original_availability,audit_response


class SourceAuditTests(unittest.TestCase):
    def check(self,text):
        return original_availability({'source_id':'S','content':text},'2026-10-22T12:00:00+03:00')

    def test_explicit_diacritized_closed_status_is_detected(self):
        self.assertEqual(self.check('أُغلق التسجيل لاكتمال المقاعد.')[0]['rule'],'explicitly_closed_or_cancelled')

    def test_negated_closure_not_treated_as_closed(self):
        self.assertEqual(self.check('ليس التسجيل مغلق حالياً.'),[])

    def test_ended_activity_detected_without_a_deadline(self):
        self.assertEqual(self.check('يبدأ البرنامج يوم 7 أكتوبر 2026 وينتهي يوم 14 أكتوبر 2026.')[0]['rule'],'activity_ended')

    def test_date_only_boundary_not_invented_as_midnight(self):
        self.assertEqual(self.check('آخر يوم للتقديم 22 أكتوبر 2026.'),[])
        self.assertEqual(self.check('آخر يوم للتقديم 21 أكتوبر 2026.'),[])

    def test_future_event_does_not_fail(self):
        self.assertEqual(self.check('هذا نشاط ليوم واحد بتاريخ 10 نوفمبر 2026.'),[])

    def test_newer_source_reopening_not_overridden_by_older_closed_source(self):
        package={'sources':[{'source_id':'OLD','published_at':'2026-10-01','content':'أُغلق التسجيل لاكتمال المقاعد.'},
            {'source_id':'NEW','published_at':'2026-10-18','content':'باب التقديم مفتوح.'}]}
        got=audit_response({'evaluation_time':'2026-10-22T12:00:00+03:00'},
            {'recommendations':[{'opportunity_id':'A','source_ids':['OLD','NEW']}]},package)
        self.assertEqual(got['score'],1)
