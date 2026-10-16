# Learner guidance: Return source IDs with evidence. Compare timezone-aware deadlines
# using a timezone-aware evaluation_time >= deadline for expiry. Never assume hybrid means physical
# attendance is optional.
def search_opportunities(criteria, repo):
    """Return candidate evidence, not final rankings."""
    raise NotImplementedError(
        "TODO(FURSAH-LEARNER): implement the application search tool"
    )


def get_opportunity_details(opportunity_id, repo):
    """Return source-grounded details for one opportunity."""
    raise NotImplementedError(
        "TODO(FURSAH-LEARNER): implement the application detail tool"
    )


def check_deadline(opportunity_id, repo, evaluation_time):
    """Check the opportunity deadline using the supplied comparison time."""
    raise NotImplementedError(
        "TODO(FURSAH-LEARNER): implement the application deadline tool"
    )
