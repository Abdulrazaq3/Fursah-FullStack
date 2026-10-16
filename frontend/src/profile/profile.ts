import { CITIES, MAJORS, INTERESTS, SKILLS } from './choices';
import { EDUCATION_OPTIONS, LEVEL_OPTIONS, OPPORTUNITY_TYPES, DELIVERY_MODES } from '../labels';
import type { Constraints, Profile, OpportunityType, EducationLevel, SkillLevel, DeliveryMode } from '../types';

export interface ProfileBundle {
  profile: Profile;
  constraints: Constraints;
  notice?: string;
}

const blankProfile = (): ProfileBundle => ({
  profile: { user_id: null, education_level: null, field_of_study: null, city: null, interests: [], skills: null },
  constraints: { location_preference: null, opportunity_types: [], delivery_modes: [], available_from: null, available_to: null, max_duration_days: null, max_budget_sar: null },
});

const STORAGE_KEY = 'fursah.profile.v1';

/** Recover fields independently; one obsolete choice must not erase a profile. */
export function loadInitialProfile(): ProfileBundle {
  const clean = blankProfile();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return clean;
    const saved = JSON.parse(raw);
    const p = saved?.profile ?? {}, c = saved?.constraints ?? {};
    const chosen = (v: unknown, options: string[]) => typeof v === 'string' && options.includes(v) ? v : null;
    const choices = (v: unknown, options: string[]) => Array.isArray(v) ? [...new Set(v.filter((x): x is string => typeof x === 'string' && options.includes(x)))] : [];
    clean.profile = {
      user_id: typeof p.user_id === 'string' ? p.user_id : null,
      city: chosen(p.city, CITIES), field_of_study: chosen(p.field_of_study, MAJORS),
      education_level: chosen(p.education_level, EDUCATION_OPTIONS.map(([v]) => v).filter(Boolean)) as EducationLevel | null,
      interests: choices(p.interests, INTERESTS), skills: null,
    };
    if (Array.isArray(p.skills)) {
      const seen = new Set<string>();
      const skills: Profile['skills'] = [];
      for (const skill of p.skills) {
        const name = chosen(skill?.name, SKILLS);
        if (!name || seen.has(name)) continue;
        seen.add(name);
        skills.push({ name, level: chosen(skill.level, LEVEL_OPTIONS.map(([v]) => v).filter(Boolean)) as SkillLevel | null });
      }
      // Dropping unsupported skills never becomes a declaration of no skills.
      clean.profile.skills = skills.length ? skills : p.skills.length === 0 && saved.version ? [] : null;
    }
    const cities = choices(typeof c.location_preference === 'string' ? [c.location_preference] : c.location_preference, CITIES);
    clean.constraints = {
      location_preference: cities.length ? cities : null,
      opportunity_types: choices(c.opportunity_types, OPPORTUNITY_TYPES) as OpportunityType[],
      delivery_modes: choices(c.delivery_modes, DELIVERY_MODES.map(([v]) => v)) as DeliveryMode[],
      available_from: validDate(c.available_from) ? c.available_from : null,
      available_to: validDate(c.available_to) ? c.available_to : null,
      max_duration_days: validDuration(c.max_duration_days) ? c.max_duration_days ?? null : null,
      max_budget_sar: validBudget(c.max_budget_sar) ? c.max_budget_sar ?? null : null,
    };
    if (clean.constraints.available_from && clean.constraints.available_to && clean.constraints.available_from > clean.constraints.available_to) clean.constraints.available_to = null;
    const sameFields = (old: Record<string, unknown>, current: object) => Object.entries(current).every(([key, value]) => JSON.stringify(old[key]) === JSON.stringify(value));
    if (!sameFields(p, clean.profile) || !sameFields(c, clean.constraints)) clean.notice = 'تم تحديث الحقول غير الصالحة في الملف المحفوظ مع الاحتفاظ بالمعلومات الصالحة. راجع ملفك قبل البحث.';
    return clean;
  } catch {
    return { ...clean, notice: 'تعذّر قراءة الملف المحفوظ. يرجى مراجعة بياناتك.' };
  }
}

export function persistProfile(profile: Profile, constraints: Constraints) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 3, profile, constraints })); } catch { /* Storage may be unavailable. */ }
}

const validDuration = (v: unknown) => v == null || typeof v === 'number' && Number.isSafeInteger(v) && v > 0;
const validBudget = (v: unknown) => v == null || typeof v === 'number' && Number.isFinite(v) && v >= 0;
const validDate = (v: unknown): v is string => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString().slice(0, 10) === v;

export function validateConstraints(c: Constraints): string | null {
  if (!validDuration(c.max_duration_days)) return 'أقصى مدة يجب أن تكون عددًا صحيحًا من الأيام أكبر من صفر.';
  if (!validBudget(c.max_budget_sar)) return 'أدخل ميزانية لا تقل عن صفر.';
  if ((c.available_from !== null && !validDate(c.available_from)) || (c.available_to !== null && !validDate(c.available_to))) return 'أدخل تاريخًا صالحًا.';
  if (c.available_from && c.available_to && c.available_from > c.available_to) return 'تاريخ بداية التوفر يجب ألا يتجاوز تاريخ نهايته.';
  return null;
}


export interface Draft {
  education_level: string;
  city: string;
  field_of_study: string;
  interests: string[];
  skills_state: 'unknown' | 'none' | 'listed';
  skills: { name: string; level: string }[];
  location_preference: string[];
  opportunity_types: OpportunityType[];
  delivery_modes: DeliveryMode[];
  available_from: string;
  available_to: string;
  max_duration_days: string;
  max_budget_sar: string;
}

export function toDraft(p: Profile, c: Constraints): Draft {
  return {
    education_level: p.education_level ?? '',
    city: p.city ?? '',
    field_of_study: p.field_of_study ?? '',
    interests: [...p.interests],
    skills_state: p.skills === null ? 'unknown' : p.skills.length ? 'listed' : 'none',
    skills: (p.skills ?? []).map(s => ({ name: s.name, level: s.level ?? '' })),
    location_preference: [...(c.location_preference ?? [])],
    opportunity_types: [...c.opportunity_types],
    delivery_modes: [...c.delivery_modes],
    available_from: c.available_from ?? '',
    available_to: c.available_to ?? '',
    max_duration_days: c.max_duration_days == null ? '' : String(c.max_duration_days),
    max_budget_sar: c.max_budget_sar == null ? '' : String(c.max_budget_sar),
  };
}

/** Empty fields become null — the frontend never invents values. */
export function fromDraft(d: Draft, userId: string | null): { profile: Profile; constraints: Constraints } | string {
  const activeSkills = d.skills_state === 'listed' ? d.skills : [];
  const allowed = (v: string, choices: string[]) => !v || choices.includes(v);
  if (!allowed(d.city, CITIES) || !allowed(d.field_of_study, MAJORS) || d.interests.some(v => !INTERESTS.includes(v)) || d.location_preference.some(v => !CITIES.includes(v)) || activeSkills.some(v => !allowed(v.name, SKILLS)) || !EDUCATION_OPTIONS.some(([v]) => v === d.education_level) || activeSkills.some(s => !LEVEL_OPTIONS.some(([v]) => v === s.level))) return 'اختر القيم من القوائم المعتمدة فقط.';
  if (d.skills_state === 'listed' && (!d.skills.length || d.skills.some(s => !s.name))) return 'اختر اسم كل مهارة من القائمة، أو اختر غير معروف / لا أملك مهارات من القائمة.';
  if (new Set(activeSkills.map(s => s.name)).size !== activeSkills.length) return 'لا تضف المهارة نفسها أكثر من مرة.';
  const constraintError = validateConstraints({
    location_preference: d.location_preference, opportunity_types: d.opportunity_types, delivery_modes: d.delivery_modes,
    available_from: d.available_from || null, available_to: d.available_to || null,
    max_duration_days: d.max_duration_days === '' ? null : Number(d.max_duration_days),
    max_budget_sar: d.max_budget_sar === '' ? null : Number(d.max_budget_sar),
  });
  if (constraintError) return constraintError;
  const n = (v: string) => v.trim() || null;
  return {
    profile: {
      user_id: userId,
      education_level: (d.education_level || null) as EducationLevel | null,
      field_of_study: n(d.field_of_study),
      city: n(d.city),
      interests: [...new Set(d.interests.map(s => s.trim()).filter(Boolean))],
      skills: d.skills_state === 'unknown' ? null : d.skills_state === 'none' ? [] : d.skills.filter(s => s.name.trim()).map(s => ({ name: s.name.trim(), level: (s.level || null) as SkillLevel | null })),
    },
    constraints: {
      location_preference: d.location_preference.length ? [...new Set(d.location_preference)] : null,
      opportunity_types: d.opportunity_types,
      delivery_modes: d.delivery_modes,
      available_from: d.available_from || null,
      available_to: d.available_to || null,
      max_duration_days: d.max_duration_days === '' ? null : Number(d.max_duration_days),
      max_budget_sar: d.max_budget_sar === '' ? null : Number(d.max_budget_sar),
    },
  };
}
