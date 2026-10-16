/**
 * Frontend data model. Components only ever see these shapes.
 * Public field names match backend/app/schemas.py. The API client validates responses.
 */

export type EducationLevel = 'high_school' | 'diploma' | 'bachelor' | 'master' | 'doctorate';
export type SkillLevel = 'beginner' | 'intermediate' | 'advanced';
export type OpportunityType = 'workshop' | 'course' | 'internship' | 'competition' | 'volunteering' | 'event';
export type DeliveryMode = 'in_person' | 'online' | 'hybrid';
export type EligibilityStatus = 'confirmed' | 'uncertain';
export type DiscoveryStatus = 'ok' | 'no_match' | 'needs_info' | 'error';
export type ViewState = 'initial' | 'loading' | DiscoveryStatus;

/* ---------- Request ---------- */

export interface Skill {
  name: string;
  level: SkillLevel | null;
}

/** Unknown values are null / empty — never guessed. */
export interface Profile {
  user_id: string | null;
  education_level: EducationLevel | null;
  field_of_study: string | null;
  city: string | null;
  interests: string[];
  skills: Skill[] | null;
}

export interface Constraints {
  location_preference: string[] | null;
  opportunity_types: OpportunityType[];
  delivery_modes: DeliveryMode[];
  available_from: string | null; // YYYY-MM-DD
  available_to: string | null;   // YYYY-MM-DD
  max_duration_days: number | null;
  max_budget_sar: number | null;
}

export interface DiscoveryRequest {
  constraint_resolution?: 'profile' | 'query';
  request_id: string | null;
  query: string; // 1–2000 chars
  profile: Profile;
  constraints: Constraints;
}

/* ---------- Discovery response ---------- */

export interface Recommendation {
  evidence_version?: string | null;
  opportunity_id: string;
  title: string;
  opportunity_type?: string | null;
  location?: string | null;
  delivery_mode?: string | null;
  deadline?: string | null;
  application_status?: string | null;
  eligibility_status: EligibilityStatus;
  reason: string;
  caveats: string[];
  source_ids: string[];
  relevance_score?: number | null; // 0–100
  next_action?: string | null;
}

export interface DiscoveryResponse {
  request_id: string;
  status: DiscoveryStatus;
  message: string;
  interpreted_filters?: string[];
  missing_explanations?: string[];
  constraint_conflict?: boolean;
  recommendations: Recommendation[]; // max 3 rendered
  missing_fields: string[];          // e.g. "profile.city"
  error_code: string | null;
}

/* ---------- Opportunity details ---------- */

export interface OpportunityDetails {
  evidence_version?: string | null;
  opportunity_id: string;
  canonical_id?: string | null;
  title: string;
  opportunity_type?: string | null;
  description?: string | null;
  location?: string | null;
  delivery_mode?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  remote_participation_allowed?: boolean | null;
  physical_attendance_required?: boolean | null;
  duration?: number | null;
  session_count?: number | null;
  hours_per_session?: number | null;
  total_hours?: number | null;
  application_url?: string | null;
  required_documents_ar?: string[] | null;
  application_steps_ar?: string[] | null;
  capacity?: number | null;
  deadline?: string | null;
  application_status?: string | null;
  topics: string[];
  eligibility_requirements?: { mandatory: string[] | null; preferred: string[] | null } | null;
  required_skills: string[] | null;
  cost?: number | null;
  source_ids: string[];
  last_verified_at?: string | null;
  data_warnings: string[];
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error_code: string };
