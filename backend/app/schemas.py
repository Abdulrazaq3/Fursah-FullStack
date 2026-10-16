"""Fixed public HTTP contracts consumed by the frontend. Internal models live separately."""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator


NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DiscoveryStatus(str, Enum):
    OK = "ok"
    NO_MATCH = "no_match"
    NEEDS_INFO = "needs_info"
    ERROR = "error"


class EligibilityStatus(str, Enum):
    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"


class Skill(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    level: str | None = Field(default=None, max_length=80)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("skill name must contain non-whitespace characters")
        return value



class UserProfile(BaseModel):
    user_id: str | None = Field(default=None, max_length=120)
    education_level: str | None = Field(default=None, max_length=120)
    field_of_study: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    interests: list[str] = Field(default_factory=list)
    skills: list[Skill] | None = None

    @field_validator("skills")
    @classmethod
    def unique_skills(cls, values):
        names = [s.name for s in values or []]
        if len(names) != len(set(names)):
            raise ValueError('لا تضف المهارة نفسها أكثر من مرة.')
        return values


class SearchConstraints(BaseModel):
    location_preference: list[str] | None = None
    opportunity_types: list[Literal['workshop','course','internship','competition','volunteering','event']] = Field(default_factory=list)
    delivery_modes: list[Literal['in_person','online','hybrid']] = Field(default_factory=list)
    available_from: date | None = None
    available_to: date | None = None
    max_duration_days: int | None = Field(default=None, strict=True, gt=0)
    max_budget_sar: float | None = Field(default=None, strict=True, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_dates(self) -> "SearchConstraints":
        if (
            self.available_from is not None
            and self.available_to is not None
            and self.available_from > self.available_to
        ):
            raise ValueError("available_from must be before or equal to available_to")
        return self


class DiscoveryRequest(BaseModel):
    request_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    constraint_resolution: Literal["profile", "query"] | None = None
    query: str = Field(min_length=1, max_length=2000)
    profile: UserProfile
    constraints: SearchConstraints

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must contain non-whitespace characters")
        return value


class Recommendation(BaseModel):
    evidence_version: NonBlank | None = None
    opportunity_id: NonBlank
    title: NonBlank
    opportunity_type: str | None = None
    location: str | None = None
    delivery_mode: str | None = None
    deadline: str | None = None
    application_status: str | None = None
    eligibility_status: EligibilityStatus
    reason: str
    caveats: list[str] = Field(default_factory=list)
    source_ids: list[NonBlank] = Field(min_length=1)
    relevance_score: float | None = Field(default=None, ge=0, le=100)
    next_action: str | None = None


class DiscoveryResponse(BaseModel):
    request_id: NonBlank
    status: DiscoveryStatus
    message: str
    recommendations: list[Recommendation] = Field(default_factory=list)
    missing_fields: list[NonBlank] = Field(default_factory=list)
    error_code: NonBlank | None = None
    interpreted_filters: list[str] = Field(default_factory=list)
    missing_explanations: list[str] = Field(default_factory=list)
    constraint_conflict: bool = False

    @model_validator(mode="after")
    def enforce_outcome_contract(self) -> "DiscoveryResponse":
        if self.status is DiscoveryStatus.OK:
            if not 1 <= len(self.recommendations) <= 3:
                raise ValueError("ok responses require 1 to 3 recommendations")
            if self.missing_fields:
                raise ValueError("ok responses cannot include missing_fields")
            if self.error_code is not None:
                raise ValueError("ok responses cannot include error_code")
        elif self.status is DiscoveryStatus.NO_MATCH:
            if self.recommendations or self.missing_fields or self.error_code is not None:
                raise ValueError("no_match must have empty recommendations/missing_fields and no error_code")
        elif self.status is DiscoveryStatus.NEEDS_INFO:
            if self.recommendations:
                raise ValueError("needs_info cannot include recommendations")
            if not self.missing_fields:
                raise ValueError("needs_info requires at least one missing field")
            if self.error_code is not None:
                raise ValueError("needs_info cannot include error_code")
        elif self.status is DiscoveryStatus.ERROR:
            if self.recommendations or self.missing_fields:
                raise ValueError("error must have empty recommendations and missing_fields")
            if not self.error_code:
                raise ValueError("error requires error_code")
        return self


class ApiErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ApiErrorResponse(BaseModel):
    request_id: NonBlank
    error_code: NonBlank
    message: str
    details: list[ApiErrorDetail] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, bool]
    details: dict[str, str] = Field(default_factory=dict)


class EligibilityRequirements(BaseModel):
    """Source-supported Arabic statements; null is unknown, [] explicitly none."""
    mandatory: list[NonBlank] | None = None
    preferred: list[NonBlank] | None = None


class OpportunityDetailsResponse(BaseModel):
    evidence_version: NonBlank | None = None
    opportunity_id: NonBlank
    canonical_id: str | None = None
    title: NonBlank
    opportunity_type: str | None = None
    description: str | None = None
    location: str | None = None
    delivery_mode: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    remote_participation_allowed: bool | None = None
    physical_attendance_required: bool | None = None
    duration: int | None = Field(default=None, gt=0)
    session_count: int | None = Field(default=None, gt=0)
    hours_per_session: float | None = Field(default=None, gt=0, le=24)
    total_hours: float | None = Field(default=None, gt=0)
    application_url: str | None = None
    required_documents_ar: list[str] | None = None
    application_steps_ar: list[str] | None = None
    capacity: int | None = Field(default=None, gt=0)
    deadline: str | None = None
    application_status: str | None = None
    topics: list[str] = Field(default_factory=list)
    eligibility_requirements: EligibilityRequirements | None = None
    required_skills: list[str] | None = None
    cost: float | None = None
    source_ids: list[NonBlank] = Field(min_length=1)
    last_verified_at: str | None = None
    data_warnings: list[str] = Field(default_factory=list)


class TraceEvent(BaseModel):
    request_id: NonBlank
    sequence: int = Field(ge=1)
    step: str
    component: str
    outcome: str
    elapsed_ms: float = Field(ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
