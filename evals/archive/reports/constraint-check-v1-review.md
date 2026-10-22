# مراجعة فحوص القيود المنظمة

اجتازت 25 / 25 حالة: أربع على العينة المجهزة، والبقية مصطنعة ومعلّمة للاختبار.

| الحالة | القرار الفعلي | التسجيل | اجتازت المتوقع؟ |
|---|---|---|---|
| C01 | constraints_satisfied | requires_verification | True |
| C02 | needs_source_info | requires_verification | True |
| C03 | excluded | deadline_passed | True |
| C04 | needs_source_info | requires_verification | True |
| C05 | constraints_satisfied | requires_verification | True |
| C06 | excluded | requires_verification | True |
| C07 | no_constraints_requested | requires_verification | True |
| C08 | needs_source_info | requires_verification | True |
| C09 | excluded | requires_verification | True |
| C10 | needs_source_info | requires_verification | True |
| C11 | constraints_satisfied | requires_verification | True |
| C12 | excluded | requires_verification | True |
| C13 | constraints_satisfied | requires_verification | True |
| C14 | excluded | requires_verification | True |
| C15 | needs_source_info | requires_verification | True |
| C16 | no_constraints_requested | requires_verification | True |
| C17 | excluded | requires_verification | True |
| C18 | needs_source_info | requires_verification | True |
| C19 | constraints_satisfied | requires_verification | True |
| C20 | excluded | requires_verification | True |
| C21 | excluded | not_yet_open | True |
| C22 | constraints_satisfied | requires_verification | True |
| C23 | needs_source_info | requires_verification | True |
| C24 | excluded | requires_verification | True |
| C25 | constraints_satisfied | requires_verification | True |

نثبت سياسة المجهول والتعارض والحدود العددية والحضور والتفرغ على حالات مكتوبة مسبقًا. اجتياز القيود ليس أهلية أو إثبات فتح التسجيل، ولا توجد توصيات من API بعد.

المواعيد بدقة يوم تستخدم هامش يوم على جانبي تاريخ UTC؛ لا نختلق ساعة أو منطقة إغلاق. لا نحسب المدة من فرق التواريخ.

لم نشغّل النموذج أو نغير بيانات الخام والقاعدة. التالي فحص الأهلية ومعلومات المستخدم المؤثرة، وحسم خطة الطلب، ثم ربط رحلة واحدة وتقييمها كاملة.

[التقرير الرقمي](constraint-check-v1-report.json) · [النسخة المثبتة](constraint-check-v1-freeze.json) · [السياسة](../docs/constraint-policy.md)
