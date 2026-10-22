"""Experimental literal tool-OR branches; no synonyms, inferred intent or lower cutoff.

The original query and unchanged verifier remain the baseline. An additional
acceptance needs a complete literal branch AND support for the original tool
constraint. This module is not enabled in discovery.
"""
from dataclasses import dataclass
import hashlib
import re

from .details import canonical
from .request_requirements import extract_requirements, normalized, check_requirements, verify_with_requirements

POLICY_VERSION = 'literal-tool-alternatives-v1'


@dataclass(frozen=True)
class AlternativePlan:
    original_query: str
    branches: tuple[str, ...]
    decision: str
    reason: str
    version: str


def plan_alternatives(query: str) -> AlternativePlan:
    requirements = extract_requirements(query)
    tools = requirements.tools
    branches, reason = (), 'no_supported_literal_tool_alternative'
    if requirements.review_reasons:
        reason = 'original_requirements_need_review'
    elif (requirements.tool_mode == 'any' and len(tools) == 2
          and len({t['tool'] for t in tools}) == 2
          and all(t['polarity'] == 'required' for t in tools)
          and not requirements.activities):
        left, right = tools
        between = normalized(query[left['end']:right['start']])[0].strip()
        text = normalized(query)[0]
        risky = r'(?<!\w)(?:معا|كلاهما|كليهما|الاثنين|تجمع|يجمع|تدمج|ادمج|both|together|متقدم|مبتدئ|فقط)(?!\w)'
        connectors = re.findall(r'(?<!\w)(?:او|or)(?!\w)', text)
        if between in {'او', 'or'} and len(connectors) == 1 and not re.search(risky, text):
            # Replace only the literal A-or-B span; retain every other character.
            branches = tuple(query[:left['start']] + tool['quote'] + query[right['end']:]
                             for tool in tools)
            for branch, tool in zip(branches, tools, strict=True):
                parsed = extract_requirements(branch)
                if (parsed.review_reasons or len(parsed.tools) != 1
                        or parsed.tools[0]['tool'] != tool['tool'] or parsed.activities):
                    raise ValueError('Branch does not preserve a single literal tool')
            reason = 'two_adjacent_positive_tools_with_one_literal_or'
        else:
            reason = 'alternative_scope_outside_checked_slice'
    decision = 'expanded' if branches else 'original_only'
    payload = dict(policy_version=POLICY_VERSION, original_query=query, branches=branches,
                   decision=decision, reason=reason)
    version = 'sha256:' + hashlib.sha256(canonical(payload).encode('utf-8')).hexdigest()
    return AlternativePlan(query, branches, decision, reason, version)


def verify_alternatives(query, candidates, expected_versions, policy, score_pairs, *, original_scores=None):
    """Return baseline and branch evidence, preserving errors and bounded work."""
    plan = plan_alternatives(query)
    baseline_scorer = score_pairs if original_scores is None else lambda pairs: original_scores
    requirements, baseline = verify_with_requirements(query, candidates, expected_versions, policy, baseline_scorer)
    branch_results = []
    for branch in plan.branches:
        _, decisions = verify_with_requirements(branch, candidates, expected_versions, policy, score_pairs)
        branch_results.append({'query': branch, 'decisions': decisions})
    merged = []
    for index, (candidate, original) in enumerate(zip(candidates, baseline, strict=True)):
        proofs = [{'query': r['query'], **r['decisions'][index]} for r in branch_results]
        valid = [p for p in proofs if p['decision'] == 'related']
        guard = check_requirements(requirements, candidate)
        recovered = original['decision'] != 'related' and bool(valid) and guard['status'] == 'supported'
        merged.append({**original, 'decision': 'related' if recovered else original['decision'],
            'reason_code': 'literal_branch_passed_unchanged_policy_and_original_guard' if recovered else original['reason_code'],
            'original_decision': original['decision'], 'branch_decisions': proofs,
            'alternative_plan_version': plan.version, 'alternative_policy_version': POLICY_VERSION})
    return {'plan': plan, 'baseline': baseline, 'decisions': merged}
