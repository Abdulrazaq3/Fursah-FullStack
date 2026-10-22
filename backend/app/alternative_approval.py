"""Bind pilot activation to the measured version, sources and unchanged policy."""
import hashlib
import json

from .infrastructure.config import PROJECT_ROOT
from .infrastructure.reference_paths import reference_path
from .infrastructure.errors import EvidenceValidationError
from .normalized_alternatives_v31 import POLICY_VERSION


def check_alternative_approval(candidates, policy):
    try:
        approval = json.loads(reference_path('examples/query-alternatives-pilot-approval.json').read_text(encoding='utf-8'))
        if approval['scope'] != 'four_record_local_pilot_only' or approval['policy_version'] != POLICY_VERSION:
            raise ValueError('Wrong activation scope or version')
        for path, digest in approval['files_sha256'].items():
            if hashlib.sha256(reference_path(path).read_bytes()).hexdigest() != digest:
                raise ValueError('Measured implementation or evaluation changed')
        report = json.loads(reference_path('results/query-alternatives-v31-report.json').read_text(encoding='utf-8'))
        development = json.loads(reference_path('results/query-alternatives-v31-diagnostic.json').read_text(encoding='utf-8'))
        freeze = json.loads(reference_path('results/query-alternatives-v31-freeze.json').read_text(encoding='utf-8'))
        measured = report['metrics']['proposed']
        if (not report['full_slice_passed'] or report['interpretation_errors'] or report['regressions']
                or measured['false_positive_candidates'] != 0 or measured['positive_queries'] < 1
                or measured['positive_queries_with_relevant_hit'] != measured['positive_queries']
                or not development['exposed_failures_fixed'] or development['regressions']
                or freeze['binding']['policy'] != {'accept_at':policy.accept_at,'reject_below':policy.reject_below}):
            raise ValueError('Measured acceptance criterion not satisfied')
        if any(approval['candidate_topic_versions'].get(c.opportunity_id) != c.topic_evidence_version for c in candidates):
            raise ValueError('Unapproved topic evidence')
    except (KeyError, ValueError, TypeError, OSError) as exc:
        raise EvidenceValidationError() from exc
