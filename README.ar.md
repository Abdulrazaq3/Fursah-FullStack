![SAAI — Learn AI by building](frontend/readme-header.png)

[English](README.md) | **العربية**

# FURSAH — فرصة

نظام يرشح الفرص من قاعدة محلية تضم **٩١٣ فرصة**: الألف إعلان الأصلي جُمعت في ٩٠٠ فرصة، مع ١٣ إضافة محفوظة.

الواجهة → FastAPI → فهم الطلب بـGemini → متجه BGE-M3 → بحث PostgreSQL/pgvector → إعادة ترتيب BGE → فحص الأدلة والقيود والأهلية. البحث يستخدم القاعدة المحلية.

## تشغيل المشروع الحالي

افتح **PowerShell** داخل هذا المجلد. كل أمر في نافذة مستقلة:

```powershell
.\backend\run.ps1 -Port 8019
```

```powershell
npm --prefix frontend run dev
```

الواجهة: [127.0.0.1:5173](http://127.0.0.1:5173). توثيق API: [127.0.0.1:8019/docs](http://127.0.0.1:8019/docs). يجب أن يطابق منفذ الخلفية إعداد الواجهة. إعدادات `.env` الحالية وقاعدة البيانات والنماذج محفوظة.

## التقييم والعرض في Phoenix

ابدأ من [instrumentation](backend/app/instrumentation/README.md)، ثم شغّل:

```powershell
.\evals\run.ps1 -Demo -Open
```

هذا عرض من ٣ حالات. لتشغيل حالات التطوير الـ١٢:

```powershell
.\evals\run.ps1 -Label full-dev -Open
```

افتح مشروع **fursah-eval** في Phoenix وشاهد مراحل الطلب ودرجات الفحوص. لفتح النتائج السابقة: `.\evals\phoenix.ps1 -Open`. اختبارات البرمجة: `.\evals\test.ps1`. [دليل التقييم](evals/README.md).

## الإعداد على جهاز جديد

المتطلبات: Python 3.11 وNode.js 22 وPostgreSQL 18 وأدوات Visual Studio C++ لبناء pgvector محليًا.

```powershell
.\backend\setup.ps1 -Models -Evals -Frontend
.\backend\scripts\setup-postgres.ps1
.\.venv\Scripts\python.exe backend/scripts/download-model.py
.\.venv\Scripts\python.exe backend/scripts/download-reranker.py
.\.venv\Scripts\python.exe backend/scripts/prepare-catalog.py --publish
```

أنشئ `backend/.env` من المثال إذا لم يكن موجودًا، وضع مفتاح OpenRouter فيه. اختر `FURSAH_CATALOG_MODE=prepared` و`FURSAH_UNDERSTANDING_MODE=active`. [شرح الخلفية](backend/README.ar.md) · [البيانات](data/README.ar.md).

## خريطة المشروع

| المكان | دوره |
|---|---|
| [frontend/](frontend/README.ar.md) | الواجهة والاتصال بالخلفية |
| [backend/](backend/README.ar.md) | API ومسار الطلب والإعدادات وأدوات التشغيل |
| [data/](data/README.ar.md) | البيانات الأصلية وأداة التنظيف والفرص المجهزة |
| [evals/](evals/README.md) | الحالات والمقاييس والاختبارات والنتائج وPhoenix |
| `.local/` | قاعدة البيانات والنماذج وPhoenix والنسخة الاحتياطية المحلية؛ خارج Git |

الإعدادات الفعلية في `backend/app/infrastructure/config.py` و`backend/.env`. ملفات Docker في الجذر.

## الحالة الحالية

التكامل المحلي يعمل. خط الأساس السابق نجح في **٧ من ١٢** بعد الفحص المستقل للمصادر. عرض الحالات الثلاث يكشف مشكلة التسجيل المغلق. [التقرير](evals/archive/reports/catalog-eval-baseline-v1-review.md).

التالي إصلاح الإتاحة من المصدر، والامتناع عن النتائج البعيدة، وتوسيع حالات التطوير، وتحسين الزمن والتحقق من النشر. الحالات المستقلة الست محفوظة للاعتماد اللاحق. تبقى الجاهزية `/ready` على 503 حتى الاعتماد.
