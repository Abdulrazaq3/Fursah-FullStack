"""A measured topic-candidate gate; passing is never an eligibility decision."""
from __future__ import annotations

import math


def checked_score(score: float) -> float:
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not -1 <= score <= 1:
        raise ValueError("Cosine similarity must be a finite number between -1 and 1")
    return float(score)


def calibrate_threshold(pairs: list[tuple[float, bool]]) -> float | None:
    """Maximize retained positives subject to zero false positives on calibration.

    No evaluation queries belong here. Return None if every positive overlaps
    the negative range; a magic fallback threshold would conceal that failure.
    """
    if not pairs or any(type(label) is not bool for _, label in pairs):
        raise ValueError("Calibration needs labelled score pairs")
    positives = [checked_score(score) for score, label in pairs if label]
    negatives = [checked_score(score) for score, label in pairs if not label]
    if not positives or not negatives:
        raise ValueError("Both positive and negative examples are required")
    highest_negative = max(negatives)
    separable_positives = [score for score in positives if score > highest_negative]
    if not separable_positives:
        return None
    return (highest_negative + min(separable_positives)) / 2


def gate_candidates(hits: list[dict], threshold: float | None) -> list[dict]:
    """Filter independently scored candidates; do not force a fixed result count."""
    if threshold is not None:
        threshold = checked_score(threshold)
    seen = set()
    accepted = []
    for hit in hits:
        identifier = hit["opportunity_id"]
        if not identifier or identifier in seen:
            raise ValueError("Candidate IDs must be nonempty and unique")
        seen.add(identifier)
        score = checked_score(hit["cosine_similarity"])
        if threshold is not None and score >= threshold:
            accepted.append(hit)
    return accepted


def summarize(rows: list[dict], threshold: float | None, baseline_top_k: int | None = None) -> dict:
    """Measure pair-level errors and query-level behaviour separately."""
    tp = fp = fn = positive_queries = covered = negative_queries = false_accept_queries = 0
    for row in rows:
        relevant = set(row["relevant_ids"])
        hits = row["hits"]
        accepted = hits[:baseline_top_k] if baseline_top_k is not None else gate_candidates(hits, threshold)
        predicted = {item["opportunity_id"] for item in accepted}
        tp += len(predicted & relevant)
        fp += len(predicted - relevant)
        fn += len(relevant - predicted)
        if relevant:
            positive_queries += 1
            covered += bool(predicted & relevant)
        else:
            negative_queries += 1
            false_accept_queries += bool(predicted)
    return {
        "queries": len(rows), "true_positive_candidates": tp, "false_positive_candidates": fp,
        "missed_relevant_candidates": fn,
        "candidate_precision": tp / (tp + fp) if tp + fp else None,
        "candidate_recall": tp / (tp + fn) if tp + fn else None,
        "positive_queries": positive_queries, "positive_queries_with_relevant_hit": covered,
        "negative_queries": negative_queries, "negative_queries_with_any_hit": false_accept_queries,
    }
