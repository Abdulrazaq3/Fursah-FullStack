"""Checks that keep calibration and a frozen-policy evaluation separate."""
import hashlib
import json
import unicodedata


def fingerprint(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return 'sha256:' + hashlib.sha256(encoded).hexdigest()


def validate_splits(calibration, holdout, previous, calibration_ids, all_ids, unseen_ids):
    def key(query):
        return ' '.join(unicodedata.normalize('NFKC', query).casefold().split())
    queries = [row['query'] for row in calibration + holdout]
    if len({key(q) for q in queries}) != len(queries):
        raise ValueError('Duplicate or overlapping calibration/holdout queries')
    if {key(q) for q in queries} & {key(row['query']) for row in previous}:
        raise ValueError('Previously measured queries belong in diagnostics, not the fresh splits')
    if len({row['id'] for row in calibration + holdout}) != len(calibration + holdout):
        raise ValueError('Duplicate case IDs')
    if not unseen_ids or calibration_ids & unseen_ids or calibration_ids | unseen_ids != all_ids:
        raise ValueError('Unseen candidates must be excluded from calibration')
    for rows, allowed in [(calibration, calibration_ids), (holdout, all_ids)]:
        if not any(row['relevant_ids'] for row in rows) or not any(not row['relevant_ids'] for row in rows):
            raise ValueError('Each split needs positive and negative queries')
        for row in rows:
            if not row['query'].strip() or len(row['query']) > 2000 or not set(row['relevant_ids']) <= allowed:
                raise ValueError('Invalid query or labels outside candidate scope')
            if len(set(row['relevant_ids'])) != len(row['relevant_ids']):
                raise ValueError('Duplicate relevant labels')


def seal_artifact(artifact):
    if 'artifact_sha256' in artifact:
        raise ValueError('Artifact already sealed')
    return {**artifact, 'artifact_sha256': fingerprint(artifact)}


def require_frozen_artifact(artifact, binding):
    payload = {k: v for k, v in artifact.items() if k != 'artifact_sha256'}
    if fingerprint(payload) != artifact.get('artifact_sha256'):
        raise ValueError('Frozen policy artifact changed')
    if artifact.get('binding') != binding:
        raise ValueError('Frozen policy does not match current model, corpus, labels or scoring configuration')
