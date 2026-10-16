import type { DiscoveryResponse, Recommendation, ViewState } from '../types';
import { fieldLabel, ERROR_MESSAGES } from '../labels';
import OpportunityCard from './OpportunityCard';

interface Props {
  view: ViewState;
  res: DiscoveryResponse | null;
  onResolve: (choice: 'profile' | 'query') => void;
  onEditProfile: () => void;
  onRetry: () => void;
  onFocusQuery: () => void;
  onOpenDetails: (rec: Recommendation) => void;
}

/** Renders exactly one of: initial / loading / ok / needs_info / no_match / error. */
export default function SearchResults({ view, res, onEditProfile, onRetry, onFocusQuery, onOpenDetails, onResolve }: Props) {
  return (
    <section className="results" aria-live="polite" aria-label="النتائج">
      {res?.interpreted_filters?.length ? <div className="notice"><strong>فهمنا بحثك بهذه القيود:</strong><ul>{res.interpreted_filters.map(f => <li key={f}>{f}</li>)}</ul></div> : null}
      {view === 'initial'  && (
        <p className="results__intro">صِف ما تبحث عنه، وستطابق «فرصة» الفرص المتاحة مع ملفك الشخصي وقيودك.</p>
      )}

      {view === 'loading' && (
        <>
          <p className="muted">جارٍ البحث عن الفرص المناسبة…</p>
          {[0, 1].map(i => (
            <div key={i} className="card skeleton" aria-hidden="true">
              <span style={{ width: '55%', height: 18 }} />
              <span style={{ width: '35%' }} />
              <span style={{ width: '80%' }} />
            </div>
          ))}
        </>
      )}

      {view === 'ok' && res && (
        <>
          <div className="results__head">
            <h2>الفرص المقترحة</h2>
            <p>{summaryText(res.recommendations.length)}</p>
          </div>
          {res.message && <p className="notice">{res.message}</p>}
          {res.recommendations.map(r => (
            <OpportunityCard key={r.opportunity_id} rec={r} onOpen={() => onOpenDetails(r)} />
          ))}
        </>
      )}

      {view === 'needs_info' && res && (
        <div className="card state state--warn">
          <h2>نحتاج إلى معلومات إضافية</h2>
          {res.message && <p>{res.message}</p>}
          {res.missing_explanations?.map(text => <p key={text}>{text}</p>)}
          {!res.constraint_conflict && <><p className="muted">للتحقق من الفرص المتاحة بدقة، يرجى إضافة:</p>
          <ul>
            {res.missing_fields.map(f => <li key={f}>{fieldLabel(f)}</li>)}
          </ul></>}
          <div className="state__actions">
            {res.constraint_conflict && <>
              <button className="btn btn--primary" onClick={() => onResolve('profile')}>استخدم قيود ملفي لهذا البحث</button>
              <button className="btn btn--outline" onClick={() => onResolve('query')}>استخدم قيود نص البحث هذه المرة</button>
            </>}
            <button className="btn btn--primary" onClick={onEditProfile}>تحديث الملف الشخصي</button>
            <button className="btn btn--quiet" onClick={onRetry}>البحث مجددًا</button>
          </div>
        </div>
      )}

      {view === 'no_match' && (
        <div className="card state">
          <h2>لم نجد فرصًا تدعمها البيانات</h2>
          <p>{res?.message || 'لا توجد فرص مدعومة بالبيانات تطابق ملفك وقيودك الحالية.'}</p>
          <p className="muted">يمكنك تعديل تفضيلاتك والبحث مرة أخرى.</p>
          <div className="state__actions">
            <button className="btn btn--primary" onClick={onEditProfile}>تعديل الملف والقيود</button>
            <button className="btn btn--quiet" onClick={onFocusQuery}>تعديل البحث</button>
          </div>
        </div>
      )}

      {view === 'error' && (
        <div className="card state state--error" role="alert">
          <div className="state__title">
            <span className="state__icon" aria-hidden="true">!</span>
            <h2>تعذّر إكمال البحث</h2>
          </div>
          <p>{res?.message || ERROR_MESSAGES[res?.error_code ?? ''] || 'حدث خطأ أثناء معالجة طلبك.'} يرجى المحاولة مرة أخرى.</p>
          <div className="ref">
            المرجع: <span className="mono" dir="ltr">{res?.error_code ?? 'FURSAH_INTERNAL_ERROR'}</span>
            {res?.request_id && <span className="mono muted" dir="ltr">· {res.request_id}</span>}
          </div>
          <div className="state__actions">
            <button className="btn btn--outline" onClick={onEditProfile}>تعديل الملف والقيود</button>
            <button className="btn btn--primary" onClick={onRetry}>إعادة المحاولة</button>
          </div>
        </div>
      )}
    </section>
  );
}

function summaryText(n: number) {
  if (n === 1) return 'فرصة واحدة تطابق ملفك وقيودك الحالية';
  if (n === 2) return 'فرصتان تطابقان ملفك وقيودك الحالية';
  return `${n} فرص تطابق ملفك وقيودك الحالية`;
}
