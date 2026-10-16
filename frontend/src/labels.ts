import type { DeliveryMode, EducationLevel, OpportunityType, SkillLevel } from './types';

export const EDUCATION_OPTIONS: [EducationLevel | '', string][] = [
  ['', 'غير معروف'],
  ['high_school', 'ثانوي'],
  ['diploma', 'دبلوم'],
  ['bachelor', 'بكالوريوس'],
  ['master', 'ماجستير'],
  ['doctorate', 'دكتوراه'],
];

export const LEVEL_OPTIONS: [SkillLevel | '', string][] = [
  ['', 'المستوى غير معروف'],
  ['beginner', 'مبتدئ'],
  ['intermediate', 'متوسط'],
  ['advanced', 'متقدم'],
];

export const OPPORTUNITY_TYPES: OpportunityType[] = ['workshop', 'course', 'internship', 'competition', 'volunteering', 'event'];

export const DELIVERY_MODES: [DeliveryMode, string][] = [
  ['in_person', 'حضوري'],
  ['online', 'عن بُعد'],
  ['hybrid', 'مدمج'],
];

/** Human labels for missing_fields paths returned by the backend. */
export const FIELD_LABEL: Record<string, string> = {
  'profile.education_level': 'المستوى التعليمي',
  'profile.city': 'المدينة الحالية',
  'profile.field_of_study': 'التخصص',
  'profile.interests': 'الاهتمامات',
  'profile.skills': 'المهارات',
  'constraints.location_preference': 'الموقع المفضل',
  'constraints.available_from': 'تاريخ بداية التوفر',
  'constraints.available_to': 'تاريخ نهاية التوفر',
  'constraints.opportunity_types': 'أنواع الفرص',
  'constraints.delivery_modes': 'طريقة التقديم',
  'constraints.max_duration_days': 'أقصى مدة',
  'constraints.max_budget_sar': 'أقصى ميزانية',
};

/** Normalize nested paths; never expose an unknown technical path to users. */
export function fieldLabel(path: string): string {
  const normalized = path.replace(/\[(\d+)\]/g, '.$1').replace(/^body\./, '');
  const skill = /^(?:profile\.)?skills\.(\d+)\.(name|level)$/.exec(normalized);
  if (skill) return `${skill[2] === 'level' ? 'مستوى المهارة' : 'اسم المهارة'} ${Number(skill[1]) + 1}`;
  const base = normalized.replace(/\.\d+$/, '');
  return FIELD_LABEL[base] ?? FIELD_LABEL[`profile.${base}`]
    ?? FIELD_LABEL[`constraints.${base}`] ?? 'معلومات إضافية في الملف الشخصي أو قيود البحث';
}

const AR: Record<string, string> = {
  course: 'دورة', internship: 'تدريب عملي', volunteering: 'تطوع', event: 'فعالية', not_yet_open: 'لم يبدأ التسجيل', not_open_yet: 'لم يبدأ التسجيل',
  hackathon: 'هاكاثون', bootcamp: 'معسكر تدريبي', training: 'برنامج تدريبي', competition: 'مسابقة',
  fellowship: 'زمالة', workshop: 'ورشة عمل',
  open: 'مفتوح', closed: 'مغلق', cancelled: 'ملغى', unknown: 'غير معروف', requires_verification: 'يتطلب تحققًا',
  beginner: 'مبتدئ', intermediate: 'متوسط', advanced: 'متقدم',
};

/** Translate a backend enum value; unknown values are shown as-is. */
export const label = (v?: string | null) => (v ? AR[v] ?? v.replace(/_/g, ' ') : '');
export const modeLabel = (m?: string | null) => (m ? DELIVERY_MODES.find(x => x[0] === m)?.[1] ?? label(m) : '');
export const eduLabel = (e?: string | null) => (e ? EDUCATION_OPTIONS.find(x => x[0] === e)?.[1] ?? label(e) : '');

export const UNKNOWN = 'غير معروف';

export function fmtDate(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString('ar-u-ca-gregory-nu-latn', { day: 'numeric', month: 'long', year: 'numeric' });
}

/** Deadline instants are displayed in the display timezone, never the computer timezone. */
export function fmtDeadline(iso?: string | null): string | null {
  if (!iso) return null;
  // Do not invent a time or zone for incomplete source data.
  if (!/T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(iso)) return `${iso} — وقت الإغلاق أو المنطقة الزمنية غير محدد`;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return `${iso} — موعد غير صالح`;
  return `${date.toLocaleString('ar-u-ca-gregory-nu-latn', {
    timeZone: 'Asia/Riyadh', day: 'numeric', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  })} (Asia/Riyadh · UTC+03:00)`;
}

export const fmtCost = (c?: number | null) => (c == null ? null : c === 0 ? 'مجاني' : `${c} ريال`);

export const ERROR_MESSAGES: Record<string, string> = {
  FURSAH_MODEL_ERROR: 'تعذر إكمال الاتصال بالنموذج. تحقق من إعدادات مزود النموذج أو أعد المحاولة.',
  FURSAH_DATA_ERROR: 'تعذر قراءة بيانات التدريب.',
  FURSAH_NETWORK_ERROR: 'تعذر الاتصال بالخادم. تحقق من تشغيله وعنوان الاتصال.',
  FURSAH_TIMEOUT: 'انتهت مهلة الاتصال بالخادم.',
  FURSAH_BAD_RESPONSE: 'أعاد الخادم بيانات غير صالحة. لم تُعرض توصيات غير موثوقة.',
  FURSAH_REQUEST_VALIDATION_ERROR: 'يرجى مراجعة الملف الشخصي وقيود البحث.',
  FURSAH_CONFIG_ERROR: 'عنوان الخادم غير صحيح. راجع VITE_API_BASE_URL.',
  FURSAH_NOT_IMPLEMENTED: 'مسار البحث أو التفاصيل لم يُنفّذ بعد. أكمل ملفات المتعلم في الخادم.',
};
