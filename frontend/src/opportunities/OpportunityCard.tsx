import type { EligibilityStatus, Recommendation } from '../types';
import { UNKNOWN, fmtDeadline, label, modeLabel } from '../labels';


export function EligibilityBadge({ status }: { status: EligibilityStatus }) {
  const ok = status === 'confirmed';
  return (
    <span className={`elig elig--${ok ? 'confirmed' : 'uncertain'}`}>
      <span className="elig__icon" aria-hidden="true">{ok ? '✓' : '?'}</span>
      الأهلية: {ok ? 'مؤكدة' : 'غير مؤكدة'}
    </span>
  );
}

interface Props {
  rec: Recommendation;
  onOpen: () => void;
}

export default function OpportunityCard({ rec, onOpen }: Props) {
  const meta = [label(rec.opportunity_type), rec.location, modeLabel(rec.delivery_mode)].filter(Boolean).join(' · ') || 'النوع والموقع غير معروفين';
  return (
    <article className="card opp">
      <div className="opp__top">
        <div className="opp__titles">
          <h3 className="opp__title">{rec.title}</h3>
          <div className="opp__meta">{meta}</div>
        </div>
        {rec.relevance_score != null && (
          <div className="opp__score">
            <small>الملاءمة</small>
            <strong>{Math.round(rec.relevance_score)}%</strong>
          </div>
        )}
      </div>

      <div className="opp__status">
        <EligibilityBadge status={rec.eligibility_status} />
        <span className="kv"><span>آخر موعد</span> {fmtDeadline(rec.deadline) ?? UNKNOWN}</span>
        <span className="kv"><span>حالة التقديم</span> {rec.application_status ? label(rec.application_status) : UNKNOWN}</span>
      </div>
      {rec.eligibility_status !== 'confirmed' && <div className="opp__note">بعض المتطلبات لا تزال بحاجة إلى تحقق.</div>}

      {rec.reason && (
        <div className="block">
          <div className="section-label">لماذا تناسبك</div>
          <div className="block__text">{rec.reason}</div>
        </div>
      )}

      {rec.caveats.length > 0 && (
        <div className="notice">
          <div className="notice__title">ملاحظات مهمة</div>
          <ul className="list list--tight">
            {rec.caveats.map((c, i) => <li key={i}>! {c}</li>)}
          </ul>
        </div>
      )}

      {rec.next_action && <div className="opp__next"><strong>الخطوة التالية:</strong> {rec.next_action}</div>}

      <div className="opp__actions">
        <button className="btn btn--primary btn--sm" onClick={onOpen}>عرض التفاصيل</button>
        <span className="spacer" />
        {rec.source_ids.length > 0 && <span className="opp__sources" dir="ltr">{rec.source_ids.join(', ')}</span>}
      </div>
    </article>
  );
}
