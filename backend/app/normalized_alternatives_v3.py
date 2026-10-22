"""Versioned fixes for normalized request words and explicit learning-by-trying.

V2 remains unchanged for reproducibility. A learning purpose is inferred only
from an exact supported phrase; unfamiliar context remains verbatim.
"""
from dataclasses import asdict, dataclass
import hashlib
import re

from .details import canonical
from .normalized_alternatives import PREFIX_WORDS, LEARN_WORDS, TRY_WORDS
from .query_alternatives import plan_alternatives
from .request_requirements import (TOOLS, normalized, tool_mentions, check_requirements,
                                  verify_with_requirements)

POLICY_VERSION = 'normalized-tool-alternatives-v3'


def _keys(words):
    return frozenset(normalized(word)[0] for word in words)


PREFIX_KEYS, LEARN_KEYS, TRY_KEYS = map(_keys, (PREFIX_WORDS, LEARN_WORDS, TRY_WORDS))
CONTEXT = r'(?:ضمن|في|من\s+خلال)\s+(?:فرصة|فرصه|نشاط|برنامج)(?:\s+(?:مناسب|مناسبة|تعليمي|تعليمية))?'
LEARNING_PURPOSE = re.compile(r'^\s*' + CONTEXT + r'\s+(?:للتعلم|بهدف\s+التعلم)(?!\w)')
GENERIC_TAIL = re.compile(r'\s*(?:' + CONTEXT + r')?\s*')


def normalize_branch_details(branch):
    mentions = tool_mentions(branch)
    if len(mentions) != 1 or mentions[0]['polarity'] != 'required':
        raise ValueError('Expected one positive literal tool')
    mention = mentions[0]
    prefix = normalized(branch[:mention['start']])[0].split()
    base = {'original_branch': branch, 'normalized_query': branch, 'goal': None,
            'method': None, 'evidence': [], 'retained_suffix': branch[mention['end']:],
            'reason': 'unknown_prefix_or_goal'}
    if not prefix or not set(prefix) <= PREFIX_KEYS:
        return base
    learned, tried = bool(set(prefix) & LEARN_KEYS), bool(set(prefix) & TRY_KEYS)
    if learned == tried:
        return base
    suffix = branch[mention['end']:]
    value, offsets = normalized(suffix)
    purpose = LEARNING_PURPOSE.match(value)
    goal, method = ('learn', None) if learned else ('try', None)
    refs = [{'quote': branch[:mention['start']], 'start': 0, 'end': mention['start'], 'role': 'goal'}]
    if purpose:
        raw_end = offsets[purpose.end()-1] + 1
        refs.append({'quote': suffix[:raw_end], 'start': mention['end'],
                     'end': mention['end'] + raw_end, 'role': 'explicit_learning_purpose'})
        suffix = suffix[raw_end:]
        if tried:
            goal, method = 'learn', 'try'
    elif GENERIC_TAIL.fullmatch(value):
        suffix = ''
    tool = TOOLS[mention['tool']][0]
    query = ('تعلم ' if goal == 'learn' else 'تجربة ') + tool
    if method == 'try':
        query += ' بالتجربة'
    query += suffix
    return {**base, 'normalized_query': query, 'goal': goal, 'method': method,
            'evidence': refs, 'retained_suffix': suffix, 'reason': 'bounded_goal_and_context_parsed'}


def normalize_branch(branch):
    return normalize_branch_details(branch)['normalized_query']


@dataclass(frozen=True)
class NormalizedPlan:
    original_query: str
    literal_branches: tuple[str, ...]
    branches: tuple[str, ...]
    branch_interpretations: tuple[dict, ...]
    decision: str
    reason: str
    version: str


def plan_normalized_alternatives(query):
    literal = plan_alternatives(query)
    interpretations = tuple(normalize_branch_details(b) for b in literal.branches)
    branches = tuple(b['normalized_query'] for b in interpretations)
    payload = dict(policy_version=POLICY_VERSION, literal_plan=asdict(literal), branches=branches,
                   interpretations=interpretations)
    version = 'sha256:' + hashlib.sha256(canonical(payload).encode('utf-8')).hexdigest()
    return NormalizedPlan(query, literal.branches, branches, interpretations,
                          literal.decision, literal.reason, version)


def verify_alternatives(query, candidates, expected_versions, policy, score_pairs, *, original_scores=None):
    plan = plan_normalized_alternatives(query)
    requirements, baseline = verify_with_requirements(query, candidates, expected_versions, policy,
        score_pairs if original_scores is None else lambda pairs: original_scores)
    branches = []
    for branch in plan.branches:
        _, decisions = verify_with_requirements(branch, candidates, expected_versions, policy, score_pairs)
        branches.append({'query': branch, 'decisions': decisions})
    merged = []
    for index, (candidate, original) in enumerate(zip(candidates, baseline, strict=True)):
        proofs = [{'query': b['query'], **b['decisions'][index]} for b in branches]
        guard = check_requirements(requirements, candidate)
        recovered = (original['decision'] != 'related' and guard['status'] == 'supported'
                     and any(p['decision'] == 'related' for p in proofs))
        merged.append({**original, 'decision': 'related' if recovered else original['decision'],
            'reason_code': 'normalized_literal_branch_and_original_guard_passed' if recovered else original['reason_code'],
            'original_decision': original['decision'], 'branch_decisions': proofs,
            'alternative_plan_version': plan.version, 'alternative_policy_version': POLICY_VERSION})
    return {'plan': plan, 'baseline': baseline, 'decisions': merged}
