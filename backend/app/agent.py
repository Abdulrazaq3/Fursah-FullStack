# Age and study stage are not collected by this profile. Keep eligibility uncertain
# when these requirements cannot be established; do not request nonexistent form fields.
# Learner guidance: Cities, majors, interests and skills arrive as displayed values. Extract
# restrictions from query text separately from saved constraints. Do not invent
# opportunity IDs or confirmed eligibility. Respect the public response contract
# regardless of your chosen framework.
from __future__ import annotations

from .internal import AgentContext, AgentResult


async def run_agent(context: AgentContext, deps) -> AgentResult:
    """Optional location for your model client, prompts and agent implementation.

    AgentContext and AgentResult are example internal types, not the public API.
    TODO: supply retrieved evidence or tools that access your store; the model
    cannot search local data merely because the files exist. Use resolved
    constraints consistently and bound calls, retries and execution time.
    A schema-valid plan can still omit explicit user constraints: check meaning,
    not only types. Return a controlled failure after bounded recovery attempts.
    """
    raise NotImplementedError(
        "TODO(FURSAH-LEARNER): connect your chosen model or agent implementation"
    )
