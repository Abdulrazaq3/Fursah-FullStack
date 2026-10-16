import { useEffect, useState, type ReactNode } from 'react';
import type { ApiResult, OpportunityDetails as Details, Recommendation } from '../types';
import { UNKNOWN, fmtCost, fmtDate, fmtDeadline, label, modeLabel } from '../labels';
import { getOpportunity } from '../api/client';
import { EligibilityBadge } from './OpportunityCard';
import Drawer from '../components/Drawer';

type State = { loading: true } | { loading: false; result: ApiResult<Details> };

/** Source-grounded detail view. Shows only what the backend returns. */
export default function OpportunityDetails({ rec, onClose }: { rec: Recommendation; onClose: () => void }) {
  const [state, setState] = useState<State>({ loading: true });

  useEffect(() => {
    let alive = true;
    setState({ loading: true });
    getOpportunity(rec.opportunity_id).then(result => { if (alive) setState({ loading: false, result }); }).catch(() => { if (alive) setState({ loading: false, result: { ok: false, error_code: 'FURSAH_CLIENT_ERROR' } }); });
    return () => { alive = false; };
  }, [rec.opportunity_id]);

  const det = !state.loading && state.result.ok ? state.result.data : null;
  const sourcesMatch = det && rec.source_ids.length > 0
    && [...new Set(rec.source_ids)].sort().join('\n') === [...new Set(det.source_ids)].sort().join('\n');
  const factsChanged = det && (['title', 'location', 'delivery_mode', 'opportunity_type', 'deadline', 'application_status'] as const)
    .some(key => rec[key] != null && det[key] !== rec[key]);
  const evidenceMatches = Boolean(det && sourcesMatch && rec.evidence_version
    && det.evidence_version && rec.evidence_version === det.evidence_version && !factsChanged);
  const changed = det && (!sourcesMatch || factsChanged ||
    Boolean(rec.evidence_version && det.evidence_version && rec.evidence_version !== det.evidence_version));
  const attendanceConflict = Boolean(det && (
    (det.delivery_mode === 'online' && (det.physical_attendance_required === true || det.remote_participation_allowed === false))
    || (det.remote_participation_allowed === true && det.physical_attendance_required === true)
  ));


  return (
    <Drawer title="تفاصيل الفرصة" onClose={onClose}>
      {state.loading && <p className="muted">جارٍ تحميل تفاصيل الفرصة…</p>}

      {!state.loading && !state.result.ok && (
        <p className="form-error" role="alert">
          تعذّر تحميل التفاصيل حاليًا. <span className="mono small" dir="ltr">{state.result.error_code}</span>
        </p>
      )}

      {det && (
        <>
          {changed && <p className="notice" role="status">تغيرت الأدلة أو تفاصيل الفرصة منذ البحث. الأهلية تحتاج إلى إعادة تحقق.</p>}
          {!changed && !evidenceMatches && <p className="notice" role="status">لا يمكن التحقق من تطابق الأدلة مع البحث السابق. الأهلية تحتاج إلى إعادة تحقق.</p>}
          {attendanceConflict && <p className="notice" role="status">توجد معلومات متعارضة عن طريقة المشاركة والحضور. تحقق من الجهة؛ لا يمكن تأكيد إمكانية المشاركة عن بعد.</p>}
          <div className="details__head">
            <div className="muted small">{[label(det.opportunity_type), det.opportunity_id].filter(Boolean).join(' · ')}</div>
            <h2 className="details__title">{det.title}</h2>
          </div>

          {det.data_warnings.length > 0 && (
            <div className="notice">
              <div className="notice__title">تنبيه بشأن البيانات</div>
              <ul className="list list--tight">{det.data_warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </div>
          )}

          {det.description && <p className="details__desc">{det.description}</p>}

          <dl className="kv-grid">
            {rows(det).map(([k, v]) => (
              <div key={k} className="kv-grid__row">
                <dt>{k}</dt>
                <dd className={v ? '' : 'is-unknown'}>{v || UNKNOWN}</dd>
              </div>
            ))}
          </dl>
        </>
      )}

      {!state.loading && (
        <div className="panel">
          <div className="form-section form-section--plain">لماذا اقترحتها «فرصة»</div>
          {!det && <p className="notice">هذه معلومات من البحث السابق؛ تعذّر التحقق من التفاصيل الحالية.</p>}
          <div><EligibilityBadge status={!evidenceMatches || attendanceConflict ? 'uncertain' : rec.eligibility_status} /></div>
          {!evidenceMatches || attendanceConflict ? <p className="muted">التقييم والتفسير السابقان غير معتمدين حاليًا. أعد البحث للتحقق من الأهلية.</p> : <>
            {rec.reason && <div className="block__text">{rec.reason}</div>}
          {rec.caveats.map((c, i) => <div key={i} className="caveat-line">! {c}</div>)}
          {rec.next_action && <div className="small"><strong>الخطوة التالية:</strong> {rec.next_action}</div>}
          </>}
        </div>
      )}

      {det && (
        <div className="evidence">
          <div className="section-label">الأدلة</div>
          <div>السجلات المصدرية: <span className="mono small" dir="ltr">{det.source_ids.join(', ') || '—'}</span></div>
          <div>آخر تحقق: {fmtDate(det.last_verified_at) ?? UNKNOWN}</div>
        </div>
      )}
    </Drawer>
  );
}

function rows(d: Details): [string, ReactNode][] {
  return [
    ['الموقع', d.location],
    ['طريقة التقديم', modeLabel(d.delivery_mode)],
    ['المشاركة الكاملة عن بعد', d.remote_participation_allowed == null ? null : d.remote_participation_allowed ? 'مسموحة' : 'غير مسموحة'],
    ['الحضور الفعلي', d.physical_attendance_required == null ? null : d.physical_attendance_required ? 'إلزامي' : 'غير إلزامي'],
    ['التواريخ', d.start_date || d.end_date ? `${fmtDate(d.start_date) ?? UNKNOWN} – ${fmtDate(d.end_date) ?? UNKNOWN}` : null],
    ['المدة التقويمية', d.duration == null ? null : `${d.duration} يوم`],
    ['عدد الجلسات', d.session_count == null ? null : String(d.session_count)],
    ['مدة الجلسة', d.hours_per_session == null ? null : `${d.hours_per_session} ساعة`],
    ['إجمالي وقت المشاركة', d.total_hours == null ? null : `${d.total_hours} ساعة`],
    ['آخر موعد', fmtDeadline(d.deadline)],
    ['حالة التقديم', d.application_status ? label(d.application_status) : null],
    ['شروط الأهلية', <EligibilityRequirements value={d.eligibility_requirements} />],
    ['المهارات المطلوبة', d.required_skills ? (d.required_skills.length ? d.required_skills.join('، ') : 'لا توجد مهارات مطلوبة') : null],
    ['المواضيع', d.topics?.length ? d.topics.map(label).join('، ') : null],
    ['التكلفة', fmtCost(d.cost)],
    ['السعة المنشورة (ليست المقاعد المتبقية)', d.capacity == null ? null : `${d.capacity} مشارك`],
    ['المستندات المطلوبة', d.required_documents_ar == null ? null : d.required_documents_ar.length ? <ul className="list list--tight">{d.required_documents_ar.map(v => <li key={v}>{v}</li>)}</ul> : 'لا توجد مستندات مطلوبة في السجل'],
    ['خطوات التقديم التجريبية', d.application_steps_ar == null ? null : d.application_steps_ar.length ? <ol className="list list--tight">{d.application_steps_ar.map(v => <li key={v}>{v}</li>)}</ol> : 'لا توجد خطوات مذكورة'],
    ['عنوان توضيحي — لا يستقبل طلبات', d.application_url ? <span dir="ltr">{d.application_url}</span> : null],
  ];
}


function EligibilityRequirements({ value }: { value: Details['eligibility_requirements'] }) {
  if (!value) return <span>{UNKNOWN}</span>;
  return <div className="eligibility-requirements">{([
    ['mandatory', 'الشروط المطلوبة'], ['preferred', 'يُفضّل (ليس شرطًا إلزاميًا)'],
  ] as const).map(([key, title]) => <div key={key}>
    <strong>{title}</strong>
    {value[key] === null ? <p>{UNKNOWN}</p> : value[key].length === 0 ? <p>لا توجد متطلبات من هذا النوع بحسب المصدر.</p> :
      <ul className="list list--tight">{value[key].map((text, i) => <li key={i}>{text}</li>)}</ul>}
  </div>)}</div>;
}
