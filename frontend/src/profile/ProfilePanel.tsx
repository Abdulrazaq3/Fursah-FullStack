import { useState } from 'react';
import type { Constraints, DeliveryMode, OpportunityType, Profile } from '../types';
import { fieldLabel, DELIVERY_MODES, EDUCATION_OPTIONS, LEVEL_OPTIONS, OPPORTUNITY_TYPES, eduLabel, fmtDate, label, modeLabel } from '../labels';
import { toDraft, fromDraft, type Draft } from './profile';
import { CITIES, MAJORS, SKILLS } from './choices';
import Drawer from '../components/Drawer';
import { Choice, InterestChoices, MultiChoice } from './ProfileChoices';

/* ───────────────────────── Summary chips ───────────────────────── */

interface SummaryProps {
  profile: Profile;
  constraints: Constraints;
  missing: string[];
  onEdit: () => void;
}

export function ProfileSummary({ profile: p, constraints: c, missing, onEdit }: SummaryProps) {
  const chips: { key: string; text: string; kicker?: string; unknown?: boolean }[] = [];
  chips.push(p.education_level ? { key: 'edu', text: eduLabel(p.education_level) } : { key: 'edu', text: '+ المستوى التعليمي', unknown: true });
  if (p.field_of_study) chips.push({ key: 'field', text: p.field_of_study });
  chips.push(p.city ? { key: 'city', text: p.city } : { key: 'city', text: '+ المدينة', unknown: true });
  p.interests.forEach((i, n) => chips.push({ key: `int${n}`, text: i }));
  if (p.skills === null) chips.push({ key: 'skills-state', text: 'المهارات: لم تُحدّد بعد', unknown: true });
  else if (p.skills.length === 0) chips.push({ key: 'skills-state', text: 'المهارات: لا توجد — حسب اختيارك' });
  (p.skills ?? []).forEach((s, n) => chips.push({ key: `sk${n}`, text: s.level ? `${s.name} · ${label(s.level)}` : s.name }));
  if (c.location_preference) chips.push({ key: 'loc', text: c.location_preference.join('، '), kicker: 'الموقع' });
  if (c.opportunity_types.length) chips.push({ key: 'types', text: c.opportunity_types.map(label).join('، '), kicker: 'الأنواع' });
  if (c.delivery_modes.length) chips.push({ key: 'modes', text: c.delivery_modes.map(modeLabel).join('، '), kicker: 'الطريقة' });
  if (c.available_from || c.available_to) chips.push({ key: 'avail', text: `${fmtDate(c.available_from) ?? '…'} – ${fmtDate(c.available_to) ?? '…'}`, kicker: 'التوفر' });
  if (c.max_duration_days != null) chips.push({ key: 'dur', text: `≤ ${c.max_duration_days} يوم`, kicker: 'المدة' });
  if (c.max_budget_sar != null) chips.push({ key: 'bud', text: `≤ ${c.max_budget_sar} ريال`, kicker: 'الميزانية' });

  return (
    <section className="profile-summary" aria-label="ملفك الشخصي">
      <div className="profile-summary__head">
        <div className="section-label">البحث وفق ملفك الشخصي</div>
        <button className="btn btn--link" onClick={onEdit}>تعديل</button>
      </div>
      <div className="chips">
        {chips.map(ch => (
          <button
            key={ch.key}
            className={`chip${ch.unknown ? ' chip--unknown' : ''}${ch.unknown && missing.length ? ' chip--missing' : ''}`}
            onClick={onEdit}
          >
            {ch.kicker && <span className="chip__kicker">{ch.kicker}</span>}
            <span>{ch.text}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

/* ───────────────────────── Editor drawer ───────────────────────── */

interface EditorProps {
  profile: Profile;
  constraints: Constraints;
  missing: string[];
  onSave: (p: Profile, c: Constraints, andSearch: boolean) => void;
  onClose: () => void;
}

export function ProfileEditor({ profile, constraints, missing, onSave, onClose }: EditorProps) {
  const [d, setD] = useState<Draft>(() => toDraft(profile, constraints));

  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<Draft>) => { setError(null); setD(x => ({ ...x, ...patch })); };
  const isMissing = (path: string) => missing.some(field => {
    const normalize = (value: string) => value.replace(/^(profile|constraints)\./, '').split(/[.\[]/)[0];
    return normalize(field) === normalize(path);
  });
  const miss = (path: string) => (isMissing(path) ? ' is-missing' : '');

  const commit = (andSearch: boolean) => {
    const r = fromDraft(d, profile.user_id);
    if (typeof r === 'string') { setError(r); return; }
    onSave(r.profile, r.constraints, andSearch);
  };
  const toggleType = (t: OpportunityType) =>
    set({ opportunity_types: d.opportunity_types.includes(t) ? d.opportunity_types.filter(x => x !== t) : [...d.opportunity_types, t] });
  const toggleMode = (m: DeliveryMode) =>
    set({ delivery_modes: d.delivery_modes.includes(m) ? d.delivery_modes.filter(x => x !== m) : [...d.delivery_modes, m] });
  const setSkill = (i: number, patch: Partial<Draft['skills'][number]>) =>
    set({ skills: d.skills.map((s, j) => (j === i ? { ...s, ...patch } : s)) });

  return (
    <Drawer
      title="ملفك الشخصي"
      onClose={onClose}
      footer={
        <>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="btn btn--primary" onClick={() => commit(false)}>حفظ الملف</button>
          <button className="btn btn--outline" onClick={() => commit(true)}>حفظ وبحث</button>
          <span className="spacer" />
          <button className="btn btn--ghost" onClick={onClose}>إلغاء</button>
        </>
      }
    >
      {missing.length > 0 && <p className="notice" role="status">معلومات مطلوبة لاستكمال البحث: {missing.map(field => fieldLabel(field)).join('، ')}</p>}
      <div className="form-section">الملف الشخصي</div>
      <div className="grid">
        <label className="field">
          المستوى التعليمي
          <select aria-invalid={isMissing('profile.education_level') || undefined} className={`input${miss('profile.education_level')}`} value={d.education_level} onChange={e => set({ education_level: e.target.value })}>
            {EDUCATION_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <Choice label="المدينة" missing={isMissing('profile.city')} options={CITIES} value={d.city} onChange={city => set({ city })} />
        <div className="field--full"><Choice label="التخصص" missing={isMissing('profile.field_of_study')} options={MAJORS} value={d.field_of_study} searchable onChange={field_of_study => set({ field_of_study })} /></div>
        <InterestChoices missing={isMissing('profile.interests')} values={d.interests} onChange={interests => set({ interests })} />
      </div>

      <div className="field">
        <label className="field">المهارات{isMissing('profile.skills') && <span className="field__required">مطلوب لاستكمال البحث — حدد حالة المهارات ومستوياتها</span>}
          <select aria-invalid={isMissing('profile.skills') || undefined} className={`input${miss('profile.skills')}`} value={d.skills_state} onChange={e => set({ skills_state: e.target.value as Draft['skills_state'] })}>
            <option value="unknown">لم أحدد مهاراتي بعد</option>
            <option value="none">لا أملك مهارات من القائمة</option>
            <option value="listed">تحديد مهاراتي ومستوياتها</option>
          </select>
        </label>
        {d.skills_state === 'listed' && d.skills.map((s, i) => (
          <div className="skill-row" key={i}>
            <Choice label="اسم المهارة" missing={isMissing('profile.skills')} searchable options={SKILLS} value={s.name} onChange={name => setSkill(i, { name })} />
            <label className="field skill-level">المستوى
            <select aria-invalid={isMissing('profile.skills') || undefined} className={`input${miss('profile.skills')}`} aria-label="مستوى المهارة" value={s.level} onChange={e => setSkill(i, { level: e.target.value })}>
              {LEVEL_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            </label>
            <button className="btn btn--icon" aria-label={`حذف المهارة ${s.name || i + 1}`} onClick={() => set({ skills: d.skills.filter((_, j) => j !== i) })}>×</button>
          </div>
        ))}
        <div><button className="btn btn--link btn--plain" onClick={() => set({ skills_state: 'listed', skills: [...d.skills, { name: '', level: '' }] })}>+ إضافة مهارة</button></div>
      </div>

      <div className="form-section">القيود</div>
      <MultiChoice label="المدن المفضلة" missing={isMissing('constraints.location_preference')} options={CITIES} values={d.location_preference} onChange={location_preference => set({ location_preference })} />
      <fieldset aria-invalid={isMissing('constraints.opportunity_types') || undefined} className={`field-group${miss('constraints.opportunity_types')}`}>
        <legend>أنواع الفرص</legend>
        <div className="toggles">
          {OPPORTUNITY_TYPES.map(t => (
            <button key={t} className="toggle" aria-pressed={d.opportunity_types.includes(t)} onClick={() => toggleType(t)}>{label(t)}</button>
          ))}
        </div>
      </fieldset>
      <fieldset aria-invalid={isMissing('constraints.delivery_modes') || undefined} className={`field-group${miss('constraints.delivery_modes')}`}>
        <legend>طريقة التقديم</legend>
        <div className="toggles">
          {DELIVERY_MODES.map(([m, l]) => (
            <button key={m} className="toggle" aria-pressed={d.delivery_modes.includes(m)} onClick={() => toggleMode(m)}>{l}</button>
          ))}
        </div>
      </fieldset>
      <div className="grid grid--narrow">
        <label className="field">
          متاح من
          <input type="date" aria-invalid={isMissing('constraints.available_from') || undefined} className={`input${miss('constraints.available_from')}`} value={d.available_from} onChange={e => set({ available_from: e.target.value })} />
        </label>
        <label className="field">
          متاح حتى
          <input type="date" aria-invalid={isMissing('constraints.available_to') || undefined} className={`input${miss('constraints.available_to')}`} value={d.available_to} onChange={e => set({ available_to: e.target.value })} />
        </label>
        <label className="field">
          أقصى مدة (بالأيام)
          <input type="number" min={1} step={1} aria-invalid={isMissing('constraints.max_duration_days') || undefined} className={`input${miss('constraints.max_duration_days')}`} value={d.max_duration_days} placeholder="بلا حد" onChange={e => set({ max_duration_days: e.target.value })} />
        </label>
        <label className="field">
          أقصى ميزانية (ريال)
          <input type="number" min={0} step="any" aria-invalid={isMissing('constraints.max_budget_sar') || undefined} className={`input${miss('constraints.max_budget_sar')}`} value={d.max_budget_sar} placeholder="بلا حد" onChange={e => set({ max_budget_sar: e.target.value })} />
        </label>
      </div>


      <p className="form-note">تُرسَل الحقول الفارغة كقيم غير معروفة، ولا تملؤها «فرصة» نيابةً عنك.</p>
    </Drawer>
  );
}
