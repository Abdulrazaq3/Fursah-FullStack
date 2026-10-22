![SAAI](https://i.imgur.com/YHRhgqv.png)

[English](README.md) | **العربية**

# الواجهة — الملف الشخصي والبحث والأدلة

[الرئيسية](../README.ar.md) · [السابق: الخلفية](../backend/README.ar.md) · [التالي: التقييم](../evals/README.ar.md)

احتفظنا بواجهة starter المبنية بـ **React وTypeScript وVite** وربطناها بـAPI المنفّذ. يجمع المتصفح المدخلات ويعرض إجابات الخلفية؛ لا يشغّل النماذج ولا يحتفظ بمفاتيحها.

## ماذا يرى المستخدم؟

يعدّل الملف الشخصي، ويكتب الطلب، ويرى حالة التحميل، ثم توصيات أو سؤال توضيح أو عدم تطابق أو خطأ. ويمكنه فتح تفاصيل الفرصة وأدلتها.

مثلًا: إذا اعتمد شرط أهلية موثق على حقل لم يملأه المستخدم، تطلب `needs_info` استكماله. لا ينبغي عرض أهلية مؤكدة دون أدلة.

| الملف | ما الذي تقرؤه فيه؟ |
|---|---|
| [src/App.tsx](src/App.tsx) | حالة الملف الشخصي والبحث |
| [src/api/client.ts](src/api/client.ts) | طلبات HTTP والتحقق من الردود |
| [src/types.ts](src/types.ts) | أشكال بيانات API |
| [src/profile/](src/profile/) | محرر الملف والاختيارات والحفظ المحلي في المتصفح |
| [src/opportunities/](src/opportunities/) | البحث وبطاقات التوصيات وتفاصيل الأدلة |
| [src/labels.ts](src/labels.ts) | التسميات العربية والتنسيق |

## تشغيل الواجهة

من جذر المستودع، ثبّت الاعتماديات مرة واحدة ثم شغّل Vite:

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev
```

أنشئ `frontend/.env.local` من [.env.example](.env.example) إذا لم يكن موجودًا. تستخدم الخلفية المنفذ 8000 افتراضيًا:

```dotenv
FURSAH_DEV_API_TARGET=http://127.0.0.1:8000
VITE_API_BASE_URL=
```

إذا اخترت منفذًا آخر للخلفية، حدّث `FURSAH_DEV_API_TARGET` ليطابقه ثم أعد تشغيل الواجهة. قد يظهر تعذّر الاتصال بعنوان الخلفية على شكل HTTP 500 في المتصفح.

افتح [127.0.0.1:5173](http://127.0.0.1:5173). ترك `VITE_API_BASE_URL` فارغًا يستخدم وسيط Vite المحلي؛ للخلفية المستضافة منفصلة ضع عنوان أصلها دون `/api`.

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

تتحقق الواجهة من المدخلات لتسهيل الاستخدام، لكن [عقد الخلفية](../backend/app/schemas.py) يظل مسؤولًا عن التحقق من الطلبات الواردة. نجاح البناء لا يثبت جودة التوصيات؛ استخدم [دليل التقييم](../evals/README.ar.md).
