/** The only HTTP boundary. Field names match backend/app/schemas.py; no fallback data. */
import { validateConstraints } from '../profile/profile';
import { fieldLabel } from '../labels';
import type { ApiResult, DiscoveryRequest, DiscoveryResponse, OpportunityDetails, Recommendation } from '../types';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL?.trim() || window.location.origin).replace(/\/+$/, '');
const TIMEOUT_MS = 100_000;
const DISCOVER_PATH = '/api/v1/discover';
const DETAILS_PATH = '/api/v1/opportunities/';

type JsonObject = Record<string, unknown>;
type HttpResult = { kind: 'http'; status: number; body: unknown } | { kind: 'failure'; code: string };
const object = (value: unknown): value is JsonObject => typeof value === 'object' && value !== null && !Array.isArray(value);
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === 'string');
const nonempty = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0;
const optionalText = (value: unknown) => value == null || typeof value === 'string';
const optionalNumber = (value: unknown) => value == null || (typeof value === 'number' && Number.isFinite(value));
const errorCode = (body: unknown): string | null => object(body) && nonempty(body.error_code) ? body.error_code : null;

async function send(path: string, init: RequestInit = {}): Promise<HttpResult> {
  try {
    const url = new URL(BASE_URL);
    if (!['http:', 'https:'].includes(url.protocol) || url.pathname !== '/' || url.search || url.hash || url.username || url.password)
      return { kind: 'failure', code: 'FURSAH_CONFIG_ERROR' };
  } catch {
    return { kind: 'failure', code: 'FURSAH_CONFIG_ERROR' };
  }
  const controller = new AbortController();
  const cancel = () => controller.abort();
  init.signal?.addEventListener('abort', cancel, { once: true });
  if (init.signal?.aborted) controller.abort();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(BASE_URL + path, {
      ...init, signal: controller.signal,
      headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
    });
    return { kind: 'http', status: response.status, body: await response.json().catch(() => null) };
  } catch (error) {
    return { kind: 'failure', code: error instanceof Error && error.name === 'AbortError' ? 'FURSAH_TIMEOUT' : 'FURSAH_NETWORK_ERROR' };
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener('abort', cancel);
  }
}

function failure(requestId: string, code: string, message = ''): DiscoveryResponse {
  return { request_id: requestId, status: 'error', message, recommendations: [], missing_fields: [], error_code: code };
}

function validRecommendation(value: unknown): value is Recommendation {
  if (!object(value)) return false;
  return (value.evidence_version == null || nonempty(value.evidence_version)) && nonempty(value.opportunity_id) && nonempty(value.title)
    && (value.eligibility_status === 'confirmed' || value.eligibility_status === 'uncertain')
    && typeof value.reason === 'string' && strings(value.caveats) && strings(value.source_ids) && value.source_ids.length > 0 && value.source_ids.every(nonempty)
    && ['opportunity_type', 'location', 'delivery_mode', 'deadline', 'application_status', 'next_action'].every(key => optionalText(value[key]))
    && optionalNumber(value.relevance_score)
    && (value.relevance_score == null || (typeof value.relevance_score === 'number' && value.relevance_score >= 0 && value.relevance_score <= 100));
}

function validDiscovery(value: unknown): value is DiscoveryResponse {
  if (!object(value) || !nonempty(value.request_id) || typeof value.message !== 'string'
    || !Array.isArray(value.recommendations) || !value.recommendations.every(validRecommendation)
    || !strings(value.missing_fields) || !optionalText(value.error_code)) return false;
  if (value.interpreted_filters !== undefined && !strings(value.interpreted_filters) || value.missing_explanations !== undefined && !strings(value.missing_explanations) || value.constraint_conflict !== undefined && typeof value.constraint_conflict !== 'boolean') return false;
  const count = value.recommendations.length;
  switch (value.status) {
    case 'ok': return count >= 1 && count <= 3 && value.missing_fields.length === 0 && value.error_code == null;
    case 'needs_info': return count === 0 && value.missing_fields.length > 0 && value.missing_fields.every(nonempty) && value.error_code == null;
    case 'no_match': return count === 0 && value.missing_fields.length === 0 && value.error_code == null;
    case 'error': return count === 0 && value.missing_fields.length === 0 && nonempty(value.error_code);
    default: return false;
  }
}

function validDetails(value: unknown): value is OpportunityDetails {
  return object(value) && (value.evidence_version == null || nonempty(value.evidence_version)) && nonempty(value.opportunity_id) && nonempty(value.title)
    && strings(value.source_ids) && value.source_ids.length > 0 && value.source_ids.every(nonempty) && strings(value.data_warnings) && strings(value.topics) && (value.required_skills === null || strings(value.required_skills))
    && ['canonical_id', 'opportunity_type', 'description', 'location', 'delivery_mode', 'start_date', 'end_date', 'deadline', 'application_status', 'last_verified_at'].every(key => optionalText(value[key]))
    && ['remote_participation_allowed', 'physical_attendance_required'].every(key => value[key] == null || typeof value[key] === 'boolean')
    && ['session_count', 'capacity'].every(key => value[key] == null || typeof value[key] === 'number' && Number.isSafeInteger(value[key]) && value[key] > 0)
    && ['hours_per_session', 'total_hours'].every(key => value[key] == null || typeof value[key] === 'number' && Number.isFinite(value[key]) && value[key] > 0)
    && optionalText(value.application_url)
    && ['required_documents_ar', 'application_steps_ar'].every(key => value[key] == null || strings(value[key]))
    && (value.hours_per_session == null || typeof value.hours_per_session === 'number' && value.hours_per_session <= 24)
    && optionalNumber(value.cost)
    && (value.duration == null || typeof value.duration === 'number' && Number.isSafeInteger(value.duration) && value.duration > 0)
    && (value.eligibility_requirements == null || object(value.eligibility_requirements) && ['mandatory', 'preferred'].every(key => value.eligibility_requirements && object(value.eligibility_requirements) && (value.eligibility_requirements[key] === null || strings(value.eligibility_requirements[key]) && (value.eligibility_requirements[key] as string[]).every(nonempty))));
}

function validationMessage(body: unknown): string {
  if (!object(body) || !Array.isArray(body.details)) return 'يرجى تصحيح بيانات الطلب.';
  const fields = body.details.flatMap(detail => object(detail) && typeof detail.field === 'string'
    ? [fieldLabel(detail.field)] : []);
  return fields.length ? `يرجى تصحيح بيانات الطلب: ${[...new Set(fields)].join('، ')}` : 'يرجى تصحيح بيانات الطلب.';
}

/** A valid HTTP request can still return needs_info, no_match or error. */
export async function discover(request: DiscoveryRequest, signal?: AbortSignal): Promise<DiscoveryResponse> {
  const requestId = request.request_id || globalThis.crypto?.randomUUID?.() || `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const constraints = request.constraints;
  if (!request.query.trim() || request.query.length > 2000)
    return failure(requestId, 'FURSAH_REQUEST_VALIDATION_ERROR', 'اكتب طلبًا من 1 إلى 2000 حرف.');
  const constraintError = validateConstraints(constraints);
  if (constraintError) return failure(requestId, 'FURSAH_REQUEST_VALIDATION_ERROR', constraintError);

  const response = await send(DISCOVER_PATH, {
    method: 'POST', signal, body: JSON.stringify({ ...request, query: request.query.trim(), request_id: requestId }),
  });
  if (response.kind === 'failure') return failure(requestId, response.code);
  if (response.status < 200 || response.status >= 300) {
    const code = errorCode(response.body) ?? `FURSAH_HTTP_${response.status}`;
    return failure(requestId, code, response.status === 422 ? validationMessage(response.body) : '');
  }
  return validDiscovery(response.body) ? response.body : failure(requestId, 'FURSAH_BAD_RESPONSE');
}

export async function getOpportunity(id: string): Promise<ApiResult<OpportunityDetails>> {
  const response = await send(DETAILS_PATH + encodeURIComponent(id));
  if (response.kind === 'failure') return { ok: false, error_code: response.code };
  if (response.status < 200 || response.status >= 300)
    return { ok: false, error_code: errorCode(response.body) ?? `FURSAH_HTTP_${response.status}` };
  return validDetails(response.body) && response.body.opportunity_id === id
    ? { ok: true, data: response.body } : { ok: false, error_code: 'FURSAH_BAD_RESPONSE' };
}
