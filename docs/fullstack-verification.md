# تحقق هيكلة الواجهة والخلفية

١٦ أكتوبر ٢٠٢٦ — على الجهاز المحلي، دون نشر خارجي.

القصة التي تحققنا منها: المستخدم يفتح واجهة فرصة، ويرسل طلب بحث إلى API عبر عنوان الواجهة نفسه، ثم يرى الرد الذي يعبّر عن حالة التنفيذ الحالية.

| الجزء | النتيجة الفعلية |
|---|---|
| بناء الواجهة للإنتاج | نجح npm run build: TypeScript وVite، 39 وحدة |
| مكتبات Python | نجح pip check بعد إضافة مكتبات API |
| عقود API ومسارات البيانات | نجحت أربعة اختبارات: health/readiness، خطأ المسار غير المنفذ، رفض ميزانية سالبة، وقراءة 1000 إعلان من الجذر الجديد |
| عرض الواجهة في المتصفح | نجح فتح الصفحة وكتابة طلب عربي وإرساله |
| الواجهة إلى API | وصل POST إلى /api/v1/discover عبر Vite، دون عنوان localhost ثابت في حزمة الواجهة |
| الرد إلى الواجهة | ظهر خطأ FURSAH_NOT_IMPLEMENTED كما هو متوقع؛ لا توجد توصيات بديلة |
| أخطاء JavaScript غير المعالجة | صفر أثناء هذا المسار |
| liveness/readiness عبر عنوان الواجهة | /health أعاد 200، و/ready أعاد 503 لأن التطبيق غير مكتمل |
| ملفات التشغيل وCI | نجح فحص صياغة PowerShell وبنية YAML ومسارات Dockerfiles |
| بناء Docker وتشغيل الحاويات | نجح عبر GitHub Actions، بما يشمل الواجهة وhealth وreadiness. لم يُختبر على الجهاز المحلي لعدم توفر Docker |

الدليل الرقمي في [fullstack-smoke.json](../results/fullstack-smoke.json)، وصورة الحالة في [fullstack-shell.png](../results/fullstack-shell.png).

دليل فحص الحاويات على GitHub في [سجل CI](https://github.com/Abdulrazaq3/Fursah-FullStack/actions/runs/38888508034). نجحت مهام الواجهة والخلفية والحاويات جميعًا.

هذا تحقق من هيكلة وتشغيل الاتصال. جودة توصيات التطبيق الكامل لم تُختبر، لأن API لم يُربط بتجربة الاسترجاع والتحقق بعد.

## إعادة الفحص

من جذر المشروع، مع تشغيل الواجهة والـAPI في طرفيتين:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'backend'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
npm --prefix frontend run build
```

فحص المتصفح اختياري ويحتاج Playwright ومتصفحه. لا يُضافان إلى اعتماديات التطبيق:

```powershell
npm install --prefix .local/browser-check --no-save playwright@1.64.1
.\.local\browser-check\node_modules\.bin\playwright.cmd install chromium
node scripts/smoke-fullstack.cjs
```

استخدمنا أثناء التحقق متصفح Chromium headless الموجود على الجهاز بالمسار المحدد في FURSAH_BROWSER_EXECUTABLE، بدل تنزيل متصفح إضافي.

عند تنفيذ التوصية لاحقًا نحدّث اختبارات الحالة غير المنفذة إلى حالات قبول ورفض ونقص وتعارض مدعومة بالأدلة.
