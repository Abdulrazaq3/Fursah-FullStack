![SAAI](readme-header.png)

[English](README.md) | **العربية**

# Frontend

واجهة React وTypeScript وVite تجمع معلومات المستخدم وقيوده وطلبه، ثم تعرض نتائج الخلفية والأسئلة والتعارضات وتفاصيل الفرص.

```powershell
# من جذر المشروع
npm --prefix frontend run dev
```

افتح [127.0.0.1:5173](http://127.0.0.1:5173). عنوان الخلفية في `frontend/.env` المحلي، ويجب أن يطابق المنفذ المستخدم في `backend/run.ps1`. مفتاح النموذج يبقى في الخلفية.

| المكان | دوره |
|---|---|
| `src/App.tsx` | إدارة الحالة والبحث |
| `src/api/client.ts` | إرسال الطلب والتحقق من الرد |
| `src/types.ts` | عقود الاتصال |
| `src/profile/` | محرر الملف وحفظه في المتصفح |
| `src/opportunities/` | عرض النتائج والتفاصيل |
| `src/labels.ts` | التسميات والتنسيق بالعربية |

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

التقييم الكامل والتتبّع في [evals](../evals/README.md).
