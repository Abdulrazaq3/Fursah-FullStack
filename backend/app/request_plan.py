"""Bounded query interpretation and one evidence-bound, nonmutating request plan.

The merger is deterministic. The reference phrase reader is intentionally not a
general language model or proof that every constraint in open text was understood.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import date
import hashlib
import re

from .details import canonical
from .eligibility import CATALOG
from .request_requirements import RequestRequirements, extract_requirements, normalized
from .schemas import DiscoveryRequest, DiscoveryResponse, SearchConstraints

POLICY_VERSION = 'request-plan-v1.1'
TYPE_LABELS = {'workshop': 'ورشة', 'course': 'دورة', 'internship': 'تدريب عملي',
               'competition': 'مسابقة', 'volunteering': 'تطوع', 'event': 'فعالية'}
MODE_LABELS = {'online': 'عن بعد', 'in_person': 'حضوري', 'hybrid': 'مدمج'}
DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫', '01234567890123456789.')


def fingerprint(value):
    return 'sha256:' + hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def request_version(request):
    return fingerprint(request.model_dump(mode='json', exclude={'request_id'}))


def _key(value):
    return ' '.join(normalized(value)[0].translate(DIGITS).split())


def interpret_query(query):
    """Literal adapter with exact original spans; unfamiliar scope abstains."""
    value, offsets = normalized(query)
    value = value.translate(DIGITS)
    claims, issues, covered_connectors = [], [], []

    def collect(field, pattern, convert):
        for match in re.finditer(r'(?<!\w)(?:و)?(?:' + pattern + r')(?!\w)', value):
            start, end = offsets[match.start()], offsets[match.end() - 1] + 1
            try:
                parsed = convert(match)
            except (ValueError, OverflowError):
                issues.append('invalid_literal_value')
                continue
            claims.append({'field': field, 'value': parsed, 'start': start, 'end': end,
                           'quote': query[start:end]})

    collect('max_budget_sar', r'مجانية|مجاني|مجانا|بدون\s+رسوم|دون\s+رسوم|بلا\s+رسوم', lambda m: 0)
    collect('max_budget_sar', r'(?:بميزانية|ميزانية)\s+لا\s+تتجاوز\s+(\d+(?:\.\d+)?)\s+ريال(?:ا|ات)?',
            lambda m: float(m[1]))
    collect('max_duration_days', r'مدتها\s+لا\s+تتجاوز\s+(\d+)\s+(?:ايام|يوم|يوما)', lambda m: int(m[1]))
    for kind, aliases in {'workshop': 'ورشة|ورشه', 'course': 'دورة|دوره', 'internship': 'تدريب\s+عملي',
                          'competition': 'مسابقة', 'volunteering': 'تطوع', 'event': 'فعالية'}.items():
        collect('opportunity_types', aliases, lambda m, k=kind: [k])
    for mode, aliases in {'online': 'عن\s+بعد(?:\s+بالكامل)?', 'in_person': 'حضوري(?:ة|ا)?', 'hybrid': 'مدمج(?:ة)?'}.items():
        collect('delivery_modes', aliases, lambda m, k=mode: [k])

    for match in re.finditer(r'(?<!\w)من\s+(\d{4}-\d{2}-\d{2})\s+الي\s+(\d{4}-\d{2}-\d{2})(?!\w)', value):
        start, end = offsets[match.start()], offsets[match.end()-1] + 1
        try:
            begin, finish = date.fromisoformat(match[1]), date.fromisoformat(match[2])
            if begin > finish:
                raise ValueError('reversed dates')
            for field, parsed in [('available_from', begin.isoformat()), ('available_to', finish.isoformat())]:
                claims.append({'field': field, 'value': parsed, 'start': start, 'end': end, 'quote': query[start:end]})
        except ValueError:
            issues.append('invalid_query_availability')
    for city in CATALOG['cities']:
        city_pattern = re.escape(_key(city)).replace(r'\ ', r'\s+')
        collect('required_locations', r'في\s+' + city_pattern + r'\s+فقط', lambda m, c=city: [c])
        collect('location_preference', r'افضل\s+' + city_pattern, lambda m, c=city: [c])

    claims.sort(key=lambda c: (c['start'], c['end'], c['field']))
    for field in {'opportunity_types', 'delivery_modes', 'required_locations', 'location_preference'}:
        rows = [c for c in claims if c['field'] == field]
        if len({canonical(c['value']) for c in rows}) > 1:
            for left, right in zip(rows, rows[1:]):
                between = _key(query[left['end']:right['start']])
                if between not in {'او', 'or'}:
                    issues.append('multiple_query_values_need_scope')
                else:
                    covered_connectors.append((left['end'], right['start']))
    for field in {'max_budget_sar', 'max_duration_days', 'available_from', 'available_to'}:
        if len({canonical(c['value']) for c in claims if c['field'] == field}) > 1:
            issues.append('multiple_query_limits_need_scope')

    # Numeric upper bounds contain literal negation (لا تتجاوز); that scope is
    # already checked as a complete claim, not a negated tool/activity request.
    semantic_chars = list(query)
    for start, end in {(c['start'], c['end']) for c in claims} | set(covered_connectors):
        semantic_chars[start:end] = ' ' * (end-start)
    semantic_input = ''.join(semantic_chars)
    categorical_connectors = tuple(covered_connectors)
    requirements = (extract_requirements(semantic_input) if semantic_input.strip()
                    else RequestRequirements((), (), 'all', ()))
    issues.extend(requirements.review_reasons)
    # Explicit OR between two tool names belongs to the existing tool constraint.
    for left, right in zip(requirements.tools, requirements.tools[1:]):
        if _key(query[left['end']:right['start']]) in {'او', 'or'}:
            covered_connectors.append((left['end'], right['start']))
    masked = list(query)
    for start, end in {(c['start'], c['end']) for c in claims} | set(covered_connectors):
        masked[start:end] = ' ' * (end-start)
    rest = _key(''.join(masked))
    # Tool alternatives remain semantic requirements. Only connectors belonging
    # to separately applied categorical filters leave the downstream query.
    topic_chars = list(query)
    for start, end in {(c['start'], c['end']) for c in claims} | set(categorical_connectors):
        topic_chars[start:end] = ' ' * (end-start)
    remaining = ''.join(topic_chars)
    risky = (r'(?<!\w)(?:لا|ليس|ليست|مو|غير|بدون|الا|عدا|لكن|بدل|سابقا|مثلا|افضل|فقط|او|or|not|without|'
             r'ما|مابي|مابغي|لست|مش|لو|اذا|كنت|سبق|خبرتي|اشتغلت|'
             r'ميزانية|بميزانية|رسوم|ريال|دولار|مدتها|مدة|ساعات|ساعة|الشهر|الاسبوع|القادم|غدا|اليوم|'
             r'ديسمبر|يناير|فبراير|مارس|ابريل|مايو|يونيو|يوليو|اغسطس|سبتمبر|اكتوبر|نوفمبر)(?!\w)')
    if re.search(risky, rest) or re.search(r'\d', rest):
        issues.append('unhandled_constraint_or_scope_marker')
    return {'query_version': fingerprint(query), 'claims': claims,
            'review_reasons': list(dict.fromkeys(issues)), 'remaining_query': remaining,
            'requirements': asdict(requirements), 'reader_scope': 'bounded_literal_reference'}


def validate_query_interpretation(query, proposal):
    expected = interpret_query(query)
    if not isinstance(proposal, dict) or proposal.get('query_version') != expected['query_version']:
        raise ValueError('stale_query_interpretation')
    if canonical(proposal.get('claims')) != canonical(expected['claims']):
        raise ValueError('unsupported_or_missing_query_claim')
    return expected  # Never trust proposed status, topic or coverage declarations.


def _labels(constraints, required_locations):
    lines = []
    if constraints['max_budget_sar'] is not None:
        lines.append(f"الميزانية القصوى: {constraints['max_budget_sar']:g} ريال")
    if constraints['max_duration_days'] is not None:
        lines.append(f"المدة القصوى المصرح بها: {constraints['max_duration_days']} يوم")
    for field, title, labels in [('opportunity_types', 'أنواع الفرص', TYPE_LABELS), ('delivery_modes', 'أنماط الحضور المسموحة', MODE_LABELS)]:
        if constraints[field]:
            lines.append(title + ': ' + ' أو '.join(labels[v] for v in constraints[field]))
    if constraints['available_from'] or constraints['available_to']:
        lines.append('التفرغ: من ' + (constraints['available_from'] or 'بداية غير محددة') + ' إلى ' + (constraints['available_to'] or 'نهاية غير محددة'))
    if constraints['location_preference']:
        lines.append('مدن مفضلة دون استبعاد غيرها: ' + '، '.join(constraints['location_preference']))
    if required_locations:
        lines.append('المدن الإلزامية: ' + ' أو '.join(required_locations))
    return lines


def build_request_plan(request: DiscoveryRequest, *, interpretation=None):
    if not isinstance(request, DiscoveryRequest):
        raise ValueError('Expected a DiscoveryRequest')
    request = DiscoveryRequest.model_validate(request.model_dump())
    parsed = (interpret_query(request.query) if interpretation is None else
              validate_query_interpretation(request.query, interpretation))
    return _merge_parsed_request(request, parsed)


def _merge_parsed_request(request, parsed):
    """Shared deterministic merger; callers must validate their own reader output."""
    saved = request.constraints.model_dump(mode='json')
    effective, query_constraints, provenance, conflicts = deepcopy(saved), {}, [], []
    issues = list(parsed['review_reasons'])
    for claim in parsed['claims']:
        field = claim['field']
        if isinstance(claim['value'], list):
            query_constraints[field] = list(dict.fromkeys(query_constraints.get(field, []) + claim['value']))
        else:
            query_constraints[field] = claim['value']
    # Validate known values even when other language must be interpreted.
    try:
        SearchConstraints(**{k: v for k, v in query_constraints.items() if k != 'required_locations'})
    except ValueError:
        issues.append('invalid_query_constraint_values')
    for field in ('max_budget_sar', 'max_duration_days'):
        if field in query_constraints:
            value = query_constraints[field]
            effective[field] = value if saved[field] is None else min(saved[field], value)
            provenance.append({'field': field, 'operation': 'minimum_upper_bound', 'profile': saved[field],
                               'query': value, 'effective': effective[field]})
    for field in ('opportunity_types', 'delivery_modes'):
        if field not in query_constraints:
            continue
        requested = query_constraints[field]
        overlap = [v for v in saved[field] if v in requested] if saved[field] else requested
        if overlap:
            effective[field] = overlap
            operation = 'allowed_set_intersection'
        else:
            conflicts.append({'fields': ['constraints.' + field], 'profile': saved[field], 'query': requested})
            effective[field] = requested if request.constraint_resolution == 'query' else saved[field]
            operation = 'unresolved' if request.constraint_resolution is None else 'selected_' + request.constraint_resolution
        provenance.append({'field': field, 'operation': operation, 'profile': saved[field], 'query': requested,
                           'effective': effective[field] if operation != 'unresolved' else None})
    if 'available_from' in query_constraints or 'available_to' in query_constraints:
        lower = [v for v in [saved['available_from'], query_constraints.get('available_from')] if v]
        upper = [v for v in [saved['available_to'], query_constraints.get('available_to')] if v]
        begin, finish = max(lower) if lower else None, min(upper) if upper else None
        window_conflict = bool(begin and finish and begin > finish)
        if window_conflict:
            conflicts.append({'fields': ['constraints.available_from', 'constraints.available_to'],
                              'profile': {k: saved[k] for k in ('available_from', 'available_to')},
                              'query': {k: query_constraints.get(k) for k in ('available_from', 'available_to')}})
            chosen = saved if request.constraint_resolution != 'query' else query_constraints
            begin, finish = chosen.get('available_from'), chosen.get('available_to')
        effective.update(available_from=begin, available_to=finish)
        window_operation = ('window_intersection' if not window_conflict else
                            'unresolved' if request.constraint_resolution is None else 'selected_' + request.constraint_resolution)
        provenance.append({'field': 'availability_window', 'operation': window_operation,
                           'profile': {k: saved[k] for k in ('available_from', 'available_to')},
                           'query': {k: query_constraints.get(k) for k in ('available_from', 'available_to')},
                           'effective': {'available_from': begin, 'available_to': finish}})
    if query_constraints.get('location_preference'):
        effective['location_preference'] = list(dict.fromkeys((saved['location_preference'] or []) + query_constraints['location_preference']))
    required_locations = query_constraints.get('required_locations', [])
    recorded = {p['field'] for p in provenance}
    if 'availability_window' in recorded:
        recorded.update(('available_from', 'available_to'))
    for field in effective:
        if field not in recorded:
            provenance.append({'field': field, 'operation': 'soft_preference_union' if field in query_constraints else 'profile_or_no_constraint',
                               'profile': saved[field], 'query': query_constraints.get(field), 'effective': effective[field]})
    provenance.append({'field': 'required_locations', 'operation': 'explicit_query_only',
                       'profile': None, 'query': required_locations, 'effective': required_locations})
    # Keep original semantic words/tools; only separately interpreted constraint spans leave the topic.
    semantic = re.sub(r'[,،؛;.!؟\s]+', ' ', parsed['remaining_query']).strip()
    meaningful = [w for w in _key(semantic).split() if w not in {'ابي', 'ابغي', 'ابغى', 'اريد', 'في', 'و', 'عن', 'فرص', 'فرصة', 'ابحث'}]
    topic_origin = 'query'
    if not meaningful:
        fallback = [request.profile.field_of_study] if request.profile.field_of_study else request.profile.interests
        semantic = '، '.join(v for v in fallback if v and v.strip())
        topic_origin = 'profile_context'
        if not semantic:
            issues.append('topic_not_established')
    status = ('requires_interpretation' if issues else
              'constraint_conflict' if conflicts and request.constraint_resolution is None else 'resolved')
    if status == 'resolved':
        effective = SearchConstraints(**effective).model_dump(mode='json')
    result = {'policy_version': POLICY_VERSION, 'request_version': request_version(request),
              'status': status, 'reader_scope': parsed['reader_scope'],
              'original_query': request.query, 'semantic_query': semantic, 'topic_origin': topic_origin,
              'query_claims': parsed['claims'], 'requirements': parsed['requirements'],
              'review_reasons': list(dict.fromkeys(issues)), 'conflicts': conflicts,
              'constraint_resolution': request.constraint_resolution,
              'effective_constraints': effective if status == 'resolved' else None,
              'required_locations': required_locations if status == 'resolved' else None,
              'provenance': provenance, 'interpreted_filters': _labels(effective, required_locations) if status == 'resolved' else [],
              'missing_fields': sorted({field for c in conflicts for field in c['fields']}) if status == 'constraint_conflict' else [],
              'general_understanding_verified': False}
    return {**result, 'plan_version': fingerprint(result)}


def _check_current_plan(request, plan):
    if isinstance(plan, dict) and plan.get('reader_scope') == 'gemini-grounded-v1':
        from .active_understanding import build_active_plan
        current = build_active_plan(request, plan.get('model_interpretation'))
    else:
        current = build_request_plan(request)
    if not isinstance(plan, dict) or plan.get('request_version') != current['request_version']:
        raise ValueError('stale_request_plan')
    if canonical(plan) != canonical(current):
        raise ValueError('request_plan_changed_or_unverified')


def resolved_plan_inputs(request, plan):
    """One checked plan supplies all downstream callers; do not reapply raw query limits."""
    _check_current_plan(request, plan)
    if plan['status'] != 'resolved':
        raise ValueError('unresolved_request_plan')
    return {'constraints': SearchConstraints(**plan['effective_constraints']),
            'required_locations': tuple(plan['required_locations']),
            'semantic_query': plan['semantic_query'], 'requirements': deepcopy(plan['requirements']),
            'profile': request.profile.model_copy(deep=True),
            'request_version': plan['request_version'], 'plan_version': plan['plan_version']}


def conflict_response(request, plan, *, request_id):
    _check_current_plan(request, plan)
    if plan['status'] != 'constraint_conflict':
        raise ValueError('No unresolved cross-source constraint conflict')
    explanations = ['يوجد تعارض بين قيود الملف ونص البحث. اختر المصدر لهذه القيود المتعارضة فقط؛ تبقى القيود المتوافقة ويظل ملفك محفوظًا.']
    for conflict in plan['conflicts']:
        field = conflict['fields'][0]
        if field == 'constraints.available_from':
            title = 'فترة التفرغ'
            describe = lambda v: f"من {v['available_from'] or 'بداية غير محددة'} إلى {v['available_to'] or 'نهاية غير محددة'}"
        else:
            title, labels = (('طريقة الحضور', MODE_LABELS) if field == 'constraints.delivery_modes'
                             else ('نوع الفرصة', TYPE_LABELS))
            describe = lambda v: ' أو '.join(labels[item] for item in v)
        explanations.append(f"{title}: في الملف «{describe(conflict['profile'])}»، وفي نص البحث «{describe(conflict['query'])}».")
    return DiscoveryResponse(request_id=request_id, status='needs_info', message='نحتاج اختيار القيود المستخدمة لهذا البحث.',
                             missing_fields=plan['missing_fields'], missing_explanations=explanations,
                             constraint_conflict=True)
