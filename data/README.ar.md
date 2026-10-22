![SAAI](../frontend/readme-header.png)

[English](README.md) | **العربية**

# البيانات

`raw/raw_opportunities.csv` يحفظ الألف إعلان الأصلي دون تغيير. أداة التنظيف الأصلية في `preparation_helpers.py`، وربط الإعلانات بالفرص والأدلة في `backend/app/dataset_preparation.py`.

الحزمة `prepared/catalog.json` تضم **٩١٣ فرصة و١٠١٣ سجل مصدر**: ٩٠٠ فرصة مجمعة من الخام، مع ١٣ إضافة محفوظة في `prepared/real-catalog.json`. يستخدمها البحث في PostgreSQL/pgvector.

```powershell
# من جذر المشروع: تجهيز وفهرسة ونشر
.\.venv\Scripts\python.exe backend/scripts/prepare-catalog.py --publish

# نشر الحزمة المجهزة بعد مراجعتها
.\.venv\Scripts\python.exe backend/scripts/prepare-catalog.py --reuse-prepared --publish
```

نحفظ النصوص والمعرفات الأصلية والأدلة والنقص والتعارض والتحديثات. الرسوم المفقودة تبقى مجهولة، وتواريخ البيانات لا تتغير. العملية تستخدم المصادر المحفوظة.

المخرجات: `prepared/source_preparation.json` و`prepared/catalog.json` و`prepared/preparation-report.json`. المتجهات المحلية في `.local/`، والإصدارات المنشورة في مخطط `fursah_catalog`. الأداة تدعم السحب والرجوع لإصدار محفوظ؛ شغّلها مع `--help` للتفاصيل.

اعتماديات التجهيز في `requirements.txt` ويثبتها `backend/setup.ps1 -Models`. فحوص الجودة وبصمات البيانات في [evals](../evals/README.md).
