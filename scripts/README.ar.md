![ساعي — تعلم الذكاء الاصطناعي بالتطبيق](../docs/assets/saai-header.png)

[English](README.md) | **العربية**

# أوامر التشغيل — الإعداد والتنفيذ

**السابق:** [الواجهة](../frontend/README.ar.md) · **الرئيسي:** [فرصة](../README.ar.md) · **التالي:** [الحالة الحالية](../README.ar.md#status)

نفّذ الأوامر من `fursah-fullstack/`. اختر تشغيل التطبيق أو تجربة الاسترجاع المستقلة؛ لكل منهما مكتبات وموارد مختلفة.

## أوامر التطبيق

| الأمر | ماذا يفعل؟ |
|---|---|
| `.\scripts\setup-fullstack.ps1` | تجهيز بيئة Python في الجذر، وتثبيت مكتبات API ومكتبات الواجهة |
| `.\scripts\start-backend.ps1` | تشغيل FastAPI على 127.0.0.1:8000 |
| `.\scripts\start-backend.ps1 -Reload` | التشغيل مع إعادة التحميل أثناء التطوير |
| `.\scripts\start-frontend.ps1` | تشغيل Vite على 127.0.0.1:5173 |

استخدم طرفية للخلفية وأخرى للواجهة، وأوقف كل خدمة بـCtrl+C. تشغيل الهيكل وحده لا ينفذ البحث أو التفاصيل أو تنسيق الذكاء الاصطناعي.

## أوامر الاسترجاع

| الأمر | ماذا يفعل؟ |
|---|---|
| `.\scripts\setup-python.ps1` | تثبيت PyTorch على CPU ومكتبات الاسترجاع التي تحققنا منها |
| `.\scripts\setup-postgres.ps1` | تجهيز وتشغيل PostgreSQL مع pgvector بصورة مستقلة على 55432 |
| `.\.venv\Scripts\python.exe .\scripts\download-model.py` | التحقق من النموذج المحدد أو تنزيله وتسجيل نسخته |
| `.\.venv\Scripts\python.exe .\scripts\download-model.py --check-only` | فحص النسخة المحلية أو استعادة ربطها دون تنزيل |
| `.\scripts\run-retrieval-experiment.ps1` | التجهيز والفهرسة والتقييم وكتابة المراجعة |
| `.\scripts\stop-postgres.ps1` | إيقاف قاعدة المشروع وحدها |

يحتاج سكربت القاعدة تثبيت PostgreSQL 18 وأدوات Visual Studio لبناء C++ مسبقًا. اقرأ [إعداد التجربة](../experiments/README.ar.md) قبل تشغيله على جهاز آخر.

## الفحوص والبناء

لبناء الواجهة:

```powershell
npm --prefix frontend run build
```

لتشغيل فحوص عقود API:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path 'backend'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

يفحص [سكربت المتصفح الاختياري](smoke-fullstack.cjs) وصول الطلب من الواجهة إلى API وظهور الحالة غير المنفذة. طريقة تجهيزه والأدلة في [سجل التحقق](../docs/fullstack-verification.md).

## تعريفات الحاويات

```powershell
docker compose up --build -d
docker compose down
```

تحتاج Docker. عنوان الواجهة الافتراضي `http://127.0.0.1:8080`، ويمرر nginx طلبات API إلى حاوية الخلفية. لم تُبنَ هذه التعريفات على الجهاز الحالي. تحزم الواجهة وهيكل API فقط؛ النموذج المحلي وقاعدة التجربة ليسا ضمنها بعد.

لتخصيص الإعدادات استخدم قوالب [الجذر](../.env.example) و[الخلفية](../backend/.env.example) و[الواجهة](../frontend/.env.example)، دون الكتابة فوق إعدادات محلية موجودة. توزيع الحاويات وCI في [دليل الهيكلة](../docs/project-structure.md).

---

**التالي: [مراجعة الحالة وتحديد خطوة التنفيذ القادمة](../README.ar.md#status).**
