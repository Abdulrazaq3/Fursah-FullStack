# Age and study stage are not collected by this profile. Keep eligibility uncertain
# when these requirements cannot be established; do not request nonexistent form fields.
# Learner guidance: Keep null skills distinct from an explicit empty list. Validate
# mandatory rules and skill proficiency, preserve source conflicts, and separate calendar
# duration from participation hours. Do not mark unknown requirements as confirmed.
from __future__ import annotations

from .internal import AgentResult, CheckedResult, ValidationContext


def validate_result(
    result: AgentResult,
    context: ValidationContext,
) -> CheckedResult:
    """TODO: proposed result + source context -> your checked internal outcome.

    Verify selected IDs and supporting evidence; do not invent missing rules.
    Ask for skill level only when a sourced requirement needs it. A changed start
    date alone does not establish a new end or duration. Retain unresolved source
    conflicts; source similarity alone does not authorize merging or deletion.
    Verify candidate IDs and source ownership; reject invented supporting quotes.
    A past opening date does not prove registration is now open. Keep the source
    statement and expose uncertainty when the current status is unverified.
    """
    raise NotImplementedError(
        "TODO(FURSAH-LEARNER): implement evidence and domain validation"
    )
