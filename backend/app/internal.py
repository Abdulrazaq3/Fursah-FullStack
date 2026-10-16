"""Optional internal examples. Replace, split or delete these types for your design.
Nothing here defines a required storage schema or agent architecture.
"""
from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from .schemas import NonBlank, EligibilityStatus, UserProfile, SearchConstraints, DiscoveryRequest

class AgentOutcome(str, Enum):
    PROPOSED = "proposed"
    NEEDS_INFO = "needs_info"
    NO_MATCH = "no_match"


# Suggested internal types below. Teams may replace them with their own design;
# preserve the public request/response contract used by the frontend.
class ToolObservation(BaseModel):
    tool_name: str
    source_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AgentContext(BaseModel):
    request_id: NonBlank
    query: str
    profile: UserProfile
    constraints: SearchConstraints
    observations: list[ToolObservation] = Field(default_factory=list)


class AgentRecommendation(BaseModel):
    opportunity_id: NonBlank
    source_ids: list[NonBlank] = Field(min_length=1)
    eligibility_status: EligibilityStatus
    reason: str
    caveats: list[str] = Field(default_factory=list)
    relevance_score: float | None = Field(default=None, ge=0, le=100)
    next_action: str | None = None


class AgentResult(BaseModel):
    outcome: AgentOutcome
    recommendations: list[AgentRecommendation] = Field(default_factory=list)
    missing_fields: list[NonBlank] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_agent_contract(self) -> "AgentResult":
        if self.outcome is AgentOutcome.PROPOSED:
            if not 1 <= len(self.recommendations) <= 3:
                raise ValueError("proposed AgentResult requires 1 to 3 recommendations")
            if self.missing_fields:
                raise ValueError("proposed AgentResult cannot include missing_fields")
        elif self.outcome is AgentOutcome.NEEDS_INFO:
            if self.recommendations or not self.missing_fields:
                raise ValueError("needs_info AgentResult requires missing_fields and no recommendations")
        elif self.outcome is AgentOutcome.NO_MATCH:
            if self.recommendations or self.missing_fields:
                raise ValueError("no_match AgentResult must be empty")
        return self


class ValidationContext(BaseModel):
    request_id: NonBlank
    request: DiscoveryRequest
    evidence: dict[str, Any] = Field(default_factory=dict)
    evaluation_time: AwareDatetime
    known_data_warnings: list[str] = Field(default_factory=list)


class CheckedResult(BaseModel):
    outcome: AgentOutcome
    checked_recommendations: list[AgentRecommendation] = Field(default_factory=list)
    missing_fields: list[NonBlank] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
