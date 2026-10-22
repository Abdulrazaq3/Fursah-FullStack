"""Source-backed structured constraints, separate from relevance and eligibility.

Inputs must already reflect a resolved request plan. This module never parses the
query, promotes a semantic match, or asserts current registration is open.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import math

from .details import map_details
from .infrastructure.errors import DataAccessError
from .schemas import SearchConstraints


POLICY_VERSION = 'structured-constraints-v1'
DELIVERY_MODES = {'online', 'in_person', 'hybrid'}
OPPORTUNITY_TYPES = {'workshop', 'course', 'internship', 'competition', 'volunteering', 'event'}


def _city(value: str) -> str:
    return ' '.join(value.split()).casefold()


def _checked_value(name, value):
    """Storage errors must not look like unknown facts or ordinary mismatches."""
    valid = True
    if name == 'cost_sar':
        valid = (type(value) in (int, float) and math.isfinite(value) and value >= 0)
    elif name == 'duration_days':
        valid = type(value) is int and value > 0
    elif name in {'physical_attendance_required', 'remote_participation_allowed'}:
        valid = type(value) is bool
    elif name in {'start_date', 'end_date', 'registration_opens_on'}:
        try:
            valid = isinstance(value, str) and date.fromisoformat(value).isoformat() == value
        except ValueError:
            valid = False
    elif name in {'location', 'delivery_mode', 'opportunity_type'}:
        valid = isinstance(value, str) and bool(value.strip())
        if valid and name == 'delivery_mode':
            valid = value in DELIVERY_MODES
        if valid and name == 'opportunity_type':
            valid = value in OPPORTUNITY_TYPES
    if not valid:
        raise DataAccessError()
    return value


def check_opportunity_constraints(
    opportunity: dict,
    sources: dict,
    evidence: dict,
    constraints: SearchConstraints,
    *,
    expected_evidence_version: str,
    evaluation_time: datetime,
    required_locations: tuple[str, ...] = (),
) -> dict:
    """Return internal decisions on one verified evidence version, without I/O.

    A known failure wins over missing information. Unknown required facts block
    constraint confirmation; unknown registration timing stays separately visible.
    Even constraints_satisfied is NOT a recommendation or eligibility result.
    """
    if not isinstance(evaluation_time, datetime) or evaluation_time.utcoffset() is None:
        raise ValueError('evaluation_time must be timezone-aware')
    if not isinstance(constraints, SearchConstraints):
        raise ValueError('Expected validated, resolved SearchConstraints')
    # Revalidate a possibly mutated model instead of accepting invalid limits.
    constraints = SearchConstraints.model_validate(constraints.model_dump())
    if (isinstance(required_locations, str) or not isinstance(required_locations, (list, tuple))
            or any(not isinstance(v, str) or not v.strip() for v in required_locations)):
        raise ValueError('required_locations must contain explicit nonblank city names')
    required_locations = tuple(dict.fromkeys(_city(v) for v in required_locations))
    details = map_details(opportunity, sources, evidence)
    if not expected_evidence_version or details.evidence_version != expected_evidence_version:
        raise ValueError('stale_evidence')
    facts = opportunity['facts']
    for name, fact in facts.items():
        if fact['status'] == 'known':
            _checked_value(name, fact['value'])

    def fact(name):
        return facts.get(name, {'status': 'unknown', 'value': None, 'evidence_ids': []})

    def value(name):
        item = fact(name)
        return item['value'] if item['status'] == 'known' else None

    def references(names):
        return [{
            'field': name, 'status': fact(name)['status'], 'value': value(name),
            'resolution': fact(name).get('resolution'),
            'evidence': [{key: evidence[identifier][key] for key in
                          ('evidence_id', 'source_id', 'quote', 'asserted_value')}
                         for identifier in fact(name)['evidence_ids']],
        } for name in names]

    checks = []

    def add(name, status, reason, fields=(), *, blocking=True):
        checks.append({'name': name, 'status': status, 'reason_code': reason,
                       'blocking_if_unresolved': blocking, 'facts': references(fields)})

    def compare(name, field, active, predicate, passed_reason, failed_reason):
        if not active:
            add(name, 'not_applicable', 'constraint_not_requested', blocking=False)
        elif fact(field)['status'] != 'known':
            add(name, fact(field)['status'], 'required_source_fact_not_established', [field])
        elif predicate(value(field)):
            add(name, 'passed', passed_reason, [field])
        else:
            add(name, 'failed', failed_reason, [field])

    compare('budget', 'cost_sar', constraints.max_budget_sar is not None,
            lambda cost: Decimal(str(cost)) <= Decimal(str(constraints.max_budget_sar)),
            'cost_within_budget', 'cost_exceeds_budget')
    compare('opportunity_type', 'opportunity_type', bool(constraints.opportunity_types),
            lambda kind: kind in constraints.opportunity_types,
            'type_allowed', 'type_not_allowed')
    compare('delivery_mode', 'delivery_mode', bool(constraints.delivery_modes),
            lambda mode: mode in constraints.delivery_modes,
            'delivery_mode_allowed', 'delivery_mode_not_allowed')

    online_only = set(constraints.delivery_modes) == {'online'}
    if not online_only:
        add('remote_attendance', 'not_applicable', 'online_only_not_requested', blocking=False)
    elif value('physical_attendance_required') is True:
        add('remote_attendance', 'failed', 'physical_attendance_is_required', ['physical_attendance_required'])
    elif value('remote_participation_allowed') is False:
        add('remote_attendance', 'failed', 'remote_participation_explicitly_denied', ['remote_participation_allowed'])
    elif fact('remote_participation_allowed')['status'] == 'conflicted':
        add('remote_attendance', 'conflicted', 'remote_permission_conflicted', ['remote_participation_allowed'])
    elif fact('physical_attendance_required')['status'] != 'known':
        add('remote_attendance', fact('physical_attendance_required')['status'],
            'physical_attendance_not_established', ['physical_attendance_required'])
    else:
        add('remote_attendance', 'passed', 'physical_attendance_not_required', ['physical_attendance_required'])

    compare('availability_from', 'start_date', constraints.available_from is not None,
            lambda start: date.fromisoformat(start) >= constraints.available_from,
            'start_within_availability', 'activity_starts_before_availability')
    compare('availability_to', 'end_date', constraints.available_to is not None,
            lambda end: date.fromisoformat(end) <= constraints.available_to,
            'end_within_availability', 'activity_ends_after_availability')
    compare('duration', 'duration_days', constraints.max_duration_days is not None,
            lambda days: days <= constraints.max_duration_days,
            'declared_duration_within_limit', 'declared_duration_exceeds_limit')
    compare('required_location', 'location', bool(required_locations),
            lambda location: _city(location) in required_locations,
            'required_location_matches', 'required_location_does_not_match')

    start, end = value('start_date'), value('end_date')
    if start is not None and end is not None and start > end:
        add('schedule_consistency', 'conflicted', 'start_after_end', ['start_date', 'end_date'])
    elif start is not None and end is not None:
        add('schedule_consistency', 'passed', 'dates_in_order', ['start_date', 'end_date'], blocking=False)
    else:
        add('schedule_consistency', 'unknown', 'complete_activity_dates_not_established',
            ['start_date', 'end_date'], blocking=False)

    # A date-only source has no closing timezone. Leave a full UTC-day margin on
    # both sides; this deliberately abstains near boundaries instead of inventing
    # a source midnight or borrowing the publication timezone.
    evaluated_at = evaluation_time.astimezone(timezone.utc)
    lower_day = evaluated_at.date() - timedelta(days=1)
    upper_day = evaluated_at.date() + timedelta(days=1)
    deadline, opens = value('deadline'), value('registration_opens_on')
    registration = 'requires_verification'
    if fact('deadline')['status'] != 'known':
        add('deadline', fact('deadline')['status'], 'deadline_not_established', ['deadline'], blocking=False)
    elif date.fromisoformat(deadline['date']) < lower_day:
        registration = 'deadline_passed'
        add('deadline', 'failed', 'deadline_definitely_passed', ['deadline'])
    elif date.fromisoformat(deadline['date']) > upper_day:
        add('deadline', 'passed', 'deadline_date_in_future_not_proof_of_open_registration', ['deadline'], blocking=False)
    else:
        add('deadline', 'unknown', 'date_only_deadline_near_boundary', ['deadline'], blocking=False)
    if fact('registration_opens_on')['status'] != 'known':
        add('registration_opening', fact('registration_opens_on')['status'],
            'registration_opening_not_established', ['registration_opens_on'], blocking=False)
    elif date.fromisoformat(opens) > upper_day:
        if registration != 'deadline_passed':
            registration = 'not_yet_open'
        add('registration_opening', 'failed', 'registration_definitely_not_started', ['registration_opens_on'])
    elif date.fromisoformat(opens) < lower_day:
        add('registration_opening', 'passed', 'opening_date_passed_not_proof_of_open_registration',
            ['registration_opens_on'], blocking=False)
    else:
        add('registration_opening', 'unknown', 'date_only_opening_near_boundary', ['registration_opens_on'], blocking=False)

    if any(check['status'] == 'failed' for check in checks):
        decision = 'excluded'
    elif any(check['blocking_if_unresolved'] and check['status'] in {'unknown', 'conflicted'} for check in checks):
        decision = 'needs_source_info'
    elif any(check['blocking_if_unresolved'] and check['status'] == 'passed' for check in checks):
        decision = 'constraints_satisfied'
    else:
        decision = 'no_constraints_requested'

    preferences = constraints.location_preference or []
    preference_match = (None if not preferences or value('location') is None else
                        _city(value('location')) in {_city(v) for v in preferences})
    blocking_fields = {item['field'] for check in checks if check['blocking_if_unresolved']
                       and check['status'] in {'unknown', 'conflicted'} for item in check['facts']
                       if item['status'] in {'unknown', 'conflicted'}}
    return {
        'opportunity_id': details.opportunity_id, 'evidence_version': details.evidence_version,
        'policy_version': POLICY_VERSION, 'evaluated_at': evaluated_at.isoformat(),
        'effective_constraints': constraints.model_dump(mode='json'),
        'required_locations': list(required_locations), 'decision': decision, 'checks': checks,
        'missing_source_fields': sorted(name for name in blocking_fields if fact(name)['status'] == 'unknown'),
        'conflicting_source_fields': sorted({item['field'] for check in checks
                                            if check['blocking_if_unresolved'] and check['status'] == 'conflicted'
                                            for item in check['facts']}),
        'user_missing_fields': [],
        'location_preference': {'requested': preferences, 'matches': preference_match, 'excludes_candidate': False,
                                'facts': references(['location']) if preferences else []},
        'registration': {'status': registration, 'currently_open_verified': False,
                         'date_only_policy': 'UTC_calendar_date_plus_or_minus_one_day'},
        'unchecked': ['semantic_relevance', 'eligibility', 'query_profile_conflict_resolution',
                      'current_registration_verification', 'participation_hours'],
    }
