# مراجعة الأهلية والمعلومات المؤثرة

الأهلية: 28 / 28. اختيار السؤال: 10 / 10.

أربع حالات من عينة المصادر، والبقية مصطنعة. الشروط المجهولة في الفرص الأربع أبقت أهليتها غير مؤكدة دون سؤال المستخدم عن كل حقل ناقص.

| الحالة | حكم الأهلية | حقول مستخدم ناقصة | اجتازت؟ |
|---|---|---|---|
| E01 | uncertain | — | True |
| E02 | uncertain | — | True |
| E03 | uncertain | — | True |
| E04 | uncertain | — | True |
| E05 | confirmed | — | True |
| E06 | uncertain | profile.skills | True |
| E07 | ineligible | — | True |
| E08 | confirmed | — | True |
| E09 | ineligible | — | True |
| E10 | uncertain | profile.skills | True |
| E11 | uncertain | profile.skills | True |
| E12 | confirmed | — | True |
| E13 | ineligible | — | True |
| E14 | uncertain | profile.education_level | True |
| E15 | uncertain | — | True |
| E16 | uncertain | — | True |
| E17 | confirmed | — | True |
| E18 | ineligible | — | True |
| E19 | uncertain | profile.city | True |
| E20 | confirmed | — | True |
| E21 | uncertain | — | True |
| E22 | uncertain | — | True |
| E23 | uncertain | — | True |
| E24 | uncertain | — | True |
| E25 | uncertain | — | True |
| E26 | ineligible | — | True |
| E27 | confirmed | — | True |
| E28 | confirmed | — | True |

| سيناريو الأسئلة | القرار | الحقول | اجتاز؟ |
|---|---|---|---|
| Q01 | ask_user | profile.skills | True |
| Q02 | eligible_candidates_available | — | True |
| Q03 | no_viable_candidates | — | True |
| Q04 | no_viable_candidates | — | True |
| Q05 | no_actionable_question | — | True |
| Q06 | no_actionable_question | — | True |
| Q07 | no_actionable_question | — | True |
| Q08 | ask_user | profile.education_level | True |
| Q09 | no_viable_candidates | — | True |
| Q10 | no_viable_candidates | — | True |

هذه فحوص قواعد محددة. بوابات الصلة والقيود في سيناريوهات السؤال محاكاة، وليست رحلة بحث كاملة. لم نغيّر الخام أو القاعدة أو عقد الواجهة، ولم نشغّل نموذجًا.

السؤال يقترح فقط لمرشح اجتاز البوابات ولا يمنعه إلا معلومة مستخدم قابلة للإجابة. وجود مرشح مؤكد يمنع إيقاف النتيجة لسؤال غير لازم. العمر وسنة الدراسة والشرط المركب لا تتحول إلى حقول وهمية.

[السياسة](../docs/eligibility-policy.md) · [التقرير الرقمي](eligibility-check-v1-report.json) · [النسخة المثبتة](eligibility-check-v1-freeze.json)
