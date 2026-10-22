"""Evidence-bound topic scoring, separate from registration and eligibility."""
from dataclasses import dataclass
import math
from typing import Callable

from .details import canonical
import hashlib
from .relevance import calibrate_threshold


@dataclass(frozen=True)
class TopicCandidate:
    opportunity_id: str
    topic_evidence_version: str
    passage: str
    excerpts: tuple[tuple[str, str, str], ...]  # role, source_id, exact quote


def build_candidate(identifier: str, sources: dict, linked_ids: list[str], excerpts: list[dict]) -> TopicCandidate:
    """Validate ownership and exact quotations before constructing model input.

    These excerpts are manually selected in the experiment. This is not an
    extraction pipeline or a proof that the source is truthful/current.
    """
    if not identifier or not linked_ids or set(sources) != set(linked_ids):
        raise ValueError('Invalid candidate identity or source ownership')
    for source_id, source in sources.items():
        if source.get('source_id') != source_id or not isinstance(source.get('content'), str):
            raise ValueError('Invalid source record')
    verified = []
    for item in excerpts:
        role, source_id, quote = item['role'], item['source_id'], item['quote']
        if role not in {'title', 'activity'} or source_id not in sources or not isinstance(quote, str) or not quote.strip():
            raise ValueError('Invalid excerpt ownership or role')
        if quote not in sources[source_id]['content']:
            raise ValueError('Excerpt is not an exact source quotation')
        verified.append((role, source_id, quote))
    if len(set(verified)) != len(verified):
        raise ValueError('Duplicate excerpts')
    version = 'sha256:' + hashlib.sha256(canonical({'id': identifier, 'sources': sources,
                                                  'excerpts': verified}).encode('utf-8')).hexdigest()
    # No source IDs, dates, costs or labels in the scoring text.
    passage = '\n'.join(quote for _, _, quote in verified)
    return TopicCandidate(identifier, version, passage, tuple(verified))


@dataclass(frozen=True)
class TopicPolicy:
    accept_at: float | None
    reject_below: float | None

    def __post_init__(self):
        for score in [self.accept_at, self.reject_below]:
            if score is not None and (isinstance(score, bool) or not math.isfinite(score) or not 0 <= score <= 1):
                raise ValueError('Invalid normalized reranker cutoff')
        if (self.accept_at is None) != (self.reject_below is None):
            raise ValueError('Both cutoffs must be present or absent')
        if self.accept_at is not None and self.reject_below > self.accept_at:
            raise ValueError('Reject cutoff exceeds accept cutoff')


def calibrate_policy(pairs: list[tuple[float, bool]]) -> TopicPolicy:
    if any(not 0 <= score <= 1 for score, _ in pairs):
        raise ValueError('Expected sigmoid scores, not raw logits or cosine similarity')
    cutoff = calibrate_threshold(pairs)
    if cutoff is None:
        return TopicPolicy(None, None)
    # Overlapping calibration scores become uncertain, not forced rejection.
    lowest_positive = min(score for score, relevant in pairs if relevant)
    return TopicPolicy(cutoff, min(cutoff, lowest_positive))


def verify_topics(query: str, candidates: list[TopicCandidate], expected_versions: dict[str, str],
                  policy: TopicPolicy, score_pairs: Callable) -> list[dict]:
    if not isinstance(query, str) or not query.strip() or len(query) > 2000 or len(candidates) > 20:
        raise ValueError('Query or candidate limit exceeded')
    if len({item.opportunity_id for item in candidates}) != len(candidates):
        raise ValueError('Duplicate candidates')
    for item in candidates:
        if expected_versions.get(item.opportunity_id) != item.topic_evidence_version:
            raise ValueError('stale_evidence')
    eligible = [item for item in candidates if {'title', 'activity'} <= {role for role, _, _ in item.excerpts}]
    scores = list(score_pairs([(query, item.passage) for item in eligible])) if eligible else []
    if len(scores) != len(eligible) or any(isinstance(s, bool) or not isinstance(s, (float, int))
            or not math.isfinite(s) or not 0 <= s <= 1 for s in scores):
        raise ValueError('Invalid reranker output')
    by_id = {item.opportunity_id: float(score) for item, score in zip(eligible, scores, strict=True)}
    results = []
    for item in candidates:
        score = by_id.get(item.opportunity_id)
        decision, reason = 'insufficient_evidence', 'missing_title_or_activity'
        if score is not None:
            if policy.accept_at is None:
                reason = 'no_separable_calibration_policy'
            elif score >= policy.accept_at:
                decision, reason = 'related', 'joint_score_above_calibrated_cutoff'
            elif score < policy.reject_below:
                decision, reason = 'unrelated', 'joint_score_below_calibrated_cutoff'
            else:
                reason = 'calibration_overlap'
        results.append({'opportunity_id': item.opportunity_id, 'topic_evidence_version': item.topic_evidence_version,
                        'decision': decision, 'reason_code': reason, 'score': score,
                        'excerpts': [dict(role=role, source_id=source_id, quote=quote)
                                     for role, source_id, quote in item.excerpts],
                        'eligibility_checked': False})
    return results
