![SAAI](../frontend/readme-header.png)

[English](README.md) | **العربية**

# Backend

الخلفية تستقبل الطلب بـFastAPI، وتتحقق منه بـPydantic، وتفهمه عبر Gemini، ثم تسترجع الفرص من القاعدة وتعيد ترتيبها وتفحص الأدلة والقيود والأهلية.

```powershell
# من جذر المشروع
.\backend\run.ps1 -Port 8019
```

| المكان | دوره |
|---|---|
| `app/catalog_workflow.py` | رحلة الطلب كاملة |
| `app/schemas.py` | شكل الطلب والرد |
| `app/infrastructure/config.py` | الإعدادات الفعلية؛ تقرأ `backend/.env` |
| `app/infrastructure/models/` | تشغيل نماذج BGE المحلية |
| [app/instrumentation/](app/instrumentation/README.md) | نقاط قياس المراحل وربط Phoenix |
| `scripts/` | خمس أدوات لازمة لإعادة تجهيز البيئة والبيانات |
| [../evals/](../evals/README.md) | كل الاختبارات والتقييمات |

## أدوات التجهيز

| الملف | دوره |
|---|---|
| `setup.ps1` | تثبيت الاعتماديات؛ خيارات `-Models -Evals -Frontend` |
| `scripts/setup-postgres.ps1` | تجهيز وتشغيل قاعدة البيانات المحلية |
| `scripts/stop-postgres.ps1` | إيقاف قاعدة المشروع |
| `scripts/download-model.py` | تحميل BGE-M3 أو التحقق منه بـ`--check-only` |
| `scripts/download-reranker.py` | تحميل نموذج إعادة الترتيب والتحقق من بصمته |
| `scripts/prepare-catalog.py` | تنظيف وتجهيز البيانات وفهرستها ونشر إصدارها |

هذه الأدوات تحتاجها عند الإعداد أو تحديث البيانات؛ التشغيل اليومي من `run.ps1`. أوامر الإعداد بالترتيب في [README الرئيسي](../README.ar.md)، وتجهيز البيانات في [دليل البيانات](../data/README.ar.md).

المفتاح في `.env` المحلي خارج Git. `/health` لفحص حياة الخدمة، و`/ready` يبقى 503 حتى اعتماد الجودة والنشر.
