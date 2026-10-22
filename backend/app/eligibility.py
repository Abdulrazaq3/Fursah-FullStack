"""Bounded, source-backed eligibility and actionable missing-user information.

This is not a general requirement interpreter, an admission guarantee, or a
discovery workflow. Unknown text is preserved instead of partially executed.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from .details import canonical, map_details
from .infrastructure.errors import DataAccessError
from .request_requirements import TOOLS, normalized
from .schemas import UserProfile

POLICY_VERSION = 'eligibility-v1'
CATALOG = json.loads(Path(__file__).with_name('eligibility_catalog.json').read_text(encoding='utf-8'))
EDUCATION = {'high_school': 'ثانوي', 'diploma': 'دبلوم', 'bachelor': 'بكالوريوس',
             'master': 'ماجستير', 'doctorate': 'دكتوراه'}
LEVELS = {'beginner': 'مبتدئ', 'intermediate': 'متوسط', 'advanced': 'متقدم'}
QUESTION_FIELDS = {'profile.education_level', 'profile.field_of_study', 'profile.city', 'profile.skills'}


def text_key(value):
    return ' '.join(normalized(value)[0].split()).removesuffix('.').strip()


SKILL_NAMES = {text_key(v): v for v in CATALOG['skills']}
for aliases in TOOLS.values():
    target = next((SKILL_NAMES[text_key(a)] for a in aliases if text_key(a) in SKILL_NAMES), None)
    if target:
        SKILL_NAMES.update({text_key(a): target for a in aliases})


def profile_version(profile):
    return 'sha256:' + hashlib.sha256(canonical(profile.model_dump(mode='json')).encode('utf-8')).hexdigest()


def skill_rule(text):
    value = text_key(text)
    match = re.fullmatch(r'(.+?) ' + re.escape(text_key('بمستوى')) + r' (.+?) '
                         + re.escape(text_key('على الأقل')), value)
    level = None
    if match:
        value = match[1]
        level = next((k for k, label in LEVELS.items() if text_key(label) == match[2]), None)
        if level is None:
            return None
    name = SKILL_NAMES.get(value)
    return {'kind': 'skill', 'value': name, 'minimum_level': level, 'profile_field': 'profile.skills'} if name else None


def parse_requirement(text, *, skills_only=False):
    """Entire supported clauses only; OR, negation and trailing conditions abstain."""
    if skills_only:
        return skill_rule(text)
    value = text_key(text)
    for label, kind, field, catalog in (
        ('المستوى التعليمي المطلوب:', 'education', 'profile.education_level', list(EDUCATION.values())),
        ('التخصص المطلوب:', 'major', 'profile.field_of_study', CATALOG['majors']),
        ('المدينة المطلوبة:', 'city', 'profile.city', CATALOG['cities']),
    ):
        prefix = text_key(label) + ' '
        if not value.startswith(prefix):
            continue
        target = value[len(prefix):]
        operator = 'match_or_review' if kind == 'education' else 'equals'
        if kind == 'education':
            for suffix, op in [('فأعلى', 'at_least'), ('فقط', 'equals')]:
                ending = ' ' + text_key(suffix)
                if target.endswith(ending):
                    target, operator = target[:-len(ending)], op
                    break
        found = next((v for v in catalog if text_key(v) == target), None)
        if found:
            if kind == 'education':
                found = next(k for k, v in EDUCATION.items() if v == found)
            return {'kind': kind, 'value': found, 'operator': operator, 'profile_field': field}
        return None
    match = re.fullmatch(r'(?:' + re.escape(text_key('المهارة المطلوبة:')) + r' |(?:'
                         + re.escape(text_key('يشترط')) + r' )?' + re.escape(text_key('إجادة')) + r' )(.+)', value)
    return skill_rule(match[1]) if match else None


def check_eligibility(opportunity, sources, evidence, profile: UserProfile, *, expected_evidence_version: str):
    if not isinstance(profile, UserProfile):
        raise ValueError('Expected a UserProfile')
    profile = UserProfile.model_validate(profile.model_dump())
    details = map_details(opportunity, sources, evidence)
    if not expected_evidence_version or expected_evidence_version != details.evidence_version:
        raise ValueError('stale_evidence')
    facts = opportunity['facts']
    checks, rules = [], []

    def refs(field):
        fact = facts.get(field, {'status': 'unknown', 'value': None, 'evidence_ids': []})
        try:
            return {'field': field, 'status': fact['status'], 'value': deepcopy(fact['value']),
                    'resolution': deepcopy(fact.get('resolution')),
                    'evidence': [{k: deepcopy(evidence[i][k]) for k in
                                  ('evidence_id', 'source_id', 'quote', 'asserted_value')}
                                 for i in fact['evidence_ids']]}
        except (KeyError, TypeError) as exc:
            raise DataAccessError() from exc

    for field in ('mandatory_requirements', 'required_skills', 'preferred_requirements'):
        reference = refs(field)
        mandatory = field != 'preferred_requirements'
        if reference['status'] != 'known':
            checks.append({'id': field, 'mandatory': mandatory, 'status': reference['status'],
                           'reason_code': 'requirements_not_established', 'missing_origin': 'source',
                           'source': reference, 'rule': None, 'user_field': None, 'question': None})
            continue
        terms = reference['value']
        if not isinstance(terms, list) or any(not isinstance(t, str) or not t.strip() for t in terms):
            raise DataAccessError()
        if not terms:
            checks.append({'id': field, 'mandatory': mandatory, 'status': 'passed',
                           'reason_code': 'explicitly_no_requirements_in_category', 'missing_origin': None,
                           'source': reference, 'rule': None, 'user_field': None, 'question': None})
        for index, text in enumerate(terms):
            rule = parse_requirement(text, skills_only=field == 'required_skills')
            row = {'id': f'{field}:{index}', 'mandatory': mandatory, 'requirement_text': text,
                   'source': reference, 'rule': rule, 'user_field': None, 'question': None}
            if rule is None:
                row.update(status='unknown', reason_code='requirement_needs_interpretation_or_uncollected_attribute', missing_origin='interpretation')
                checks.append(row)
            else:
                rules.append(row)

    # Do not select a convenient value from incompatible single-valued clauses.
    ambiguous_ids = set()
    for kind in ('education', 'major', 'city'):
        group = [r for r in rules if r['mandatory'] and r['rule']['kind'] == kind
                 and r['rule']['operator'] != 'at_least']
        if len({r['rule']['value'] for r in group}) > 1:
            ambiguous_ids.update(r['id'] for r in group)
    # Explicit equality below a minimum is a contradictory education bundle.
    education_order = list(EDUCATION)
    education_rows = [r for r in rules if r['mandatory'] and r['rule']['kind'] == 'education']
    exact = [r for r in education_rows if r['rule']['operator'] == 'equals']
    minimum = [r for r in education_rows if r['rule']['operator'] == 'at_least']
    if any(education_order.index(e['rule']['value']) < education_order.index(m['rule']['value']) for e in exact for m in minimum):
        ambiguous_ids.update(r['id'] for r in education_rows)

    skill_rows = defaultdict(list)
    for index, skill in enumerate(profile.skills or []):
        skill_rows[SKILL_NAMES.get(text_key(skill.name), text_key(skill.name))].append((index, skill))

    for row in rules:
        rule = row['rule']
        status, reason, origin, question = 'passed', 'requirement_satisfied', None, None
        if row['id'] in ambiguous_ids:
            status, reason, origin = 'conflicted', 'single_value_requirement_scope_conflict', 'interpretation'
        elif rule['kind'] == 'skill':
            found = skill_rows.get(rule['value'], [])
            if profile.skills is None:
                status, reason, origin = 'unknown', 'skills_not_answered', 'user'
                question = f"هل تمتلك مهارة {rule['value']}؟ حددها في قسم المهارات أو اختر عدم امتلاك مهارات من القائمة."
            elif not profile.skills:
                status, reason = 'failed', 'explicitly_no_listed_skills'
            elif not found:
                status, reason, origin = 'unknown', 'required_skill_not_in_partial_profile', 'user'
                question = f"هل تمتلك مهارة {rule['value']}؟ وجود مهارات أخرى لا يحسم امتلاكها."
            elif rule['minimum_level'] and len({s.level for _, s in found}) > 1:
                status, reason, origin = 'unknown', 'duplicate_canonical_skill_needs_review', 'user'
                question = f"راجع مهارة {rule['value']}؛ وردت بأكثر من اسم أو مستوى."
            elif rule['minimum_level']:
                level = found[0][1].level
                if level not in LEVELS:
                    status, reason, origin = 'unknown', 'required_skill_level_not_established', 'user'
                    question = f"ما مستواك في {rule['value']}؟ الفرصة تشترط مستوى {LEVELS[rule['minimum_level']]} على الأقل."
                elif list(LEVELS).index(level) < list(LEVELS).index(rule['minimum_level']):
                    status, reason = 'failed', 'skill_level_below_required_minimum'
        else:
            actual = getattr(profile, rule['profile_field'].removeprefix('profile.'))
            missing = not actual or not actual.strip() or (rule['kind'] == 'education' and actual not in EDUCATION)
            if missing:
                status, reason, origin = 'unknown', 'required_profile_field_not_established', 'user'
                label = {'education': 'مستواك التعليمي', 'major': 'تخصصك', 'city': 'مدينتك الحالية'}[rule['kind']]
                question = f"حدد {label} للتحقق من الشرط: {row['requirement_text']}"
            elif rule['kind'] == 'education':
                if rule['operator'] == 'at_least':
                    if education_order.index(actual) < education_order.index(rule['value']):
                        status, reason = 'failed', 'education_below_required_minimum'
                elif actual != rule['value']:
                    if rule['operator'] == 'equals':
                        status, reason = 'failed', 'education_not_in_explicit_exact_scope'
                    else:
                        status, reason, origin = 'unknown', 'education_scope_not_explicit', 'interpretation'
            elif text_key(actual) != text_key(rule['value']):
                status, reason = 'failed', 'declared_profile_value_does_not_match'
        if question and rule['kind'] == 'skill' and rule['minimum_level'] and reason != 'required_skill_level_not_established':
            question += f" الفرصة تتطلب مستوى {LEVELS[rule['minimum_level']]} على الأقل؛ حدد مستواك أيضًا."
        row.update(status=status, reason_code=reason, missing_origin=origin,
                   user_field=rule['profile_field'] if origin == 'user' and row['mandatory'] else None,
                   question=question if row['mandatory'] else None)
        checks.append(row)

    mandatory = [c for c in checks if c['mandatory']]
    status = ('ineligible' if any(c['status'] == 'failed' for c in mandatory) else
              'uncertain' if any(c['status'] != 'passed' for c in mandatory) else 'confirmed')
    gaps = [c for c in mandatory if c['missing_origin'] == 'user' and c['user_field']] if status != 'ineligible' else []
    blockers = [c['id'] for c in mandatory if c['status'] in {'unknown', 'conflicted'} and c['missing_origin'] != 'user']
    return {
        'opportunity_id': details.opportunity_id, 'evidence_version': details.evidence_version,
        'policy_version': POLICY_VERSION, 'profile_version': profile_version(profile), 'status': status,
        'public_eligibility_status': status if status != 'ineligible' else None,
        'checks': checks, 'user_missing_fields': sorted({c['user_field'] for c in gaps}),
        'user_information_gaps': [{'check_id': c['id'], 'field': c['user_field'], 'question': c['question'],
                                  'requirement_text': c['requirement_text']} for c in gaps],
        'non_user_blockers': blockers,
        'eligible_for_question_selection': status == 'uncertain' and bool(gaps) and not blockers,
        'unchecked': ['semantic_relevance', 'structured_constraints', 'current_registration_verification',
                      'query_profile_conflict_resolution', 'general_requirement_interpretation'],
    }


def select_eligibility_questions(evaluations, gates, profile: UserProfile):
    """Use trusted upstream decisions; no question for unverified/blocked candidates.

    The gates must come from backend checks on the same evidence version, never
    directly from model claims. This produces an internal proposal, not an API call.
    """
    if not isinstance(profile, UserProfile):
        raise ValueError('Expected a UserProfile')
    profile = UserProfile.model_validate(profile.model_dump())
    version = profile_version(profile)
    identifiers = [r['opportunity_id'] for r in evaluations]
    if len(set(identifiers)) != len(identifiers) or set(gates) != set(identifiers):
        raise ValueError('Question selection needs unique candidates and matching gates')
    viable = []
    for result in evaluations:
        gate = gates[result['opportunity_id']]
        if result['policy_version'] != POLICY_VERSION or result['profile_version'] != version:
            raise ValueError('stale_profile_or_policy')
        if not result['evidence_version'] or gate.get('evidence_version') != result['evidence_version']:
            raise ValueError('stale_evidence')
        if gate.get('topic_decision') not in {'related', 'unrelated', 'insufficient_evidence'}:
            raise ValueError('Invalid topic gate')
        if gate.get('constraint_decision') not in {'constraints_satisfied', 'no_constraints_requested', 'needs_source_info', 'excluded'}:
            raise ValueError('Invalid constraint gate')
        if gate['topic_decision'] == 'related' and gate['constraint_decision'] in {'constraints_satisfied', 'no_constraints_requested'}:
            viable.append(result)
    base = {'profile_version': version, 'missing_fields': [], 'missing_explanations': [],
            'selected_candidate_id': None, 'evidence_version': None, 'question_checks': []}
    if not viable:
        return {**base, 'decision': 'no_viable_candidates'}
    if any(r['status'] == 'confirmed' for r in viable):
        return {**base, 'decision': 'eligible_candidates_available'}
    askable = [r for r in viable if r['eligible_for_question_selection']]
    if not askable:
        return {**base, 'decision': 'no_actionable_question'}
    selected = min(askable, key=lambda r: len(r['user_missing_fields']))
    fields = selected['user_missing_fields']
    if not fields or not set(fields) <= QUESTION_FIELDS:
        raise ValueError('Question targets unsupported profile fields')
    explanations = list(dict.fromkeys(g['question'] for g in selected['user_information_gaps']))
    return {**base, 'decision': 'ask_user', 'missing_fields': fields,
            'missing_explanations': explanations, 'selected_candidate_id': selected['opportunity_id'],
            'evidence_version': selected['evidence_version'],
            'question_checks': [c for c in selected['checks'] if c['user_field'] in fields]}
