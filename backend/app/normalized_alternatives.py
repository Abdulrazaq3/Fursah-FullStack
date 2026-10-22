"""V2 development: remove bounded request boilerplate from literal OR branches.

Meaningful unknown prefix words prevent normalization. Unknown suffix text is
retained verbatim. All source texts, thresholds and original tool guards remain.
"""
from dataclasses import asdict, dataclass
import hashlib
import re

from .details import canonical
from .query_alternatives import plan_alternatives
from .request_requirements import (TOOLS, normalized, tool_mentions, extract_requirements,
                                  check_requirements, verify_with_requirements)

POLICY_VERSION = 'normalized-tool-alternatives-v2'
PREFIX_WORDS = set('ابي ابغى ابغي اريد احتاج ارغب اود ودي ابحث ادور عن على فرصة فرصه فرص نشاط برنامج في فيها فيه التعلم تعلم اتعلم لتعلم بتعلم تجربة التجربة اجرب لتجربة بتجربة'.split())
LEARN_WORDS = {'التعلم','تعلم','اتعلم','لتعلم','بتعلم'}
TRY_WORDS = {'تجربة','التجربة','اجرب','لتجربة','بتجربة'}


def normalize_branch(branch):
    mentions=tool_mentions(branch)
    if len(mentions)!=1 or mentions[0]['polarity']!='required':
        raise ValueError('Expected one positive literal tool')
    mention=mentions[0]
    prefix=normalized(branch[:mention['start']])[0].split()
    if not prefix or not set(prefix)<=PREFIX_WORDS:
        return branch
    learned=bool(set(prefix)&LEARN_WORDS)
    tried=bool(set(prefix)&TRY_WORDS)
    if learned==tried:
        return branch
    suffix=branch[mention['end']:]
    generic_tail=r'\s*(?:(?:ضمن|في|من\s+خلال)\s+(?:فرصة|فرصه|نشاط)(?:\s+(?:مناسب|مناسبة|تعليمي|تعليمية))?)?\s*'
    if re.fullmatch(generic_tail,normalized(suffix)[0]):
        suffix=''
    # A practical qualifier, location, level or any unfamiliar suffix survives.
    return ('تعلم ' if learned else 'تجربة ')+TOOLS[mention['tool']][0]+suffix


@dataclass(frozen=True)
class NormalizedPlan:
    original_query: str
    literal_branches: tuple[str,...]
    branches: tuple[str,...]
    decision: str
    reason: str
    version: str


def plan_normalized_alternatives(query):
    literal=plan_alternatives(query)
    branches=tuple(normalize_branch(b) for b in literal.branches)
    payload=dict(policy_version=POLICY_VERSION,literal_plan=asdict(literal),branches=branches)
    version='sha256:'+hashlib.sha256(canonical(payload).encode('utf-8')).hexdigest()
    return NormalizedPlan(query,literal.branches,branches,literal.decision,literal.reason,version)


def verify_alternatives(query,candidates,expected_versions,policy,score_pairs,*,original_scores=None):
    plan=plan_normalized_alternatives(query)
    requirements,baseline=verify_with_requirements(query,candidates,expected_versions,policy,
        score_pairs if original_scores is None else lambda pairs:original_scores)
    branches=[]
    for branch in plan.branches:
        _,decisions=verify_with_requirements(branch,candidates,expected_versions,policy,score_pairs)
        branches.append({'query':branch,'decisions':decisions})
    merged=[]
    for index,(candidate,original) in enumerate(zip(candidates,baseline,strict=True)):
        proofs=[{'query':b['query'],**b['decisions'][index]} for b in branches]
        guard=check_requirements(requirements,candidate)
        recovered=(original['decision']!='related' and guard['status']=='supported'
                   and any(p['decision']=='related' for p in proofs))
        merged.append({**original,'decision':'related' if recovered else original['decision'],
            'reason_code':'normalized_literal_branch_and_original_guard_passed' if recovered else original['reason_code'],
            'original_decision':original['decision'],'branch_decisions':proofs,
            'alternative_plan_version':plan.version,'alternative_policy_version':POLICY_VERSION})
    return {'plan':plan,'baseline':baseline,'decisions':merged}
