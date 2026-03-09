"""Pydantic request/response models for Tempus Sales Copilot API."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class BriefRequest(BaseModel):
    """Request body for POST /brief."""

    physician_name: str = Field(
        ..., description="Full name of the physician (e.g. Dr. Sarah Chen)"
    )
    physician_id: Optional[str] = Field(
        default=None,
        description="Optional physician_id to disambiguate name; if provided this is preferred for lookup.",
    )


class PhysicianProfile(BaseModel):
    """Profile of a physician from market data."""

    physician_id: str
    name: str
    specialty: str
    institution: str
    city: str
    state: str
    estimated_annual_patients: int
    current_tempus_user: bool
    primary_cancer_focus: str
    last_contact_date: Optional[date] = None
    priority_score: float


class ProviderRank(BaseModel):
    """Ranked provider for GET /providers."""

    physician_id: str
    name: str
    institution: str
    specialty: str
    estimated_annual_patients: int
    priority_score: float
    primary_cancer_focus: str
    current_tempus_user: bool
    last_contact_date: Optional[date] = None
    rank: int


class BriefResponse(BaseModel):
    """Response for POST /brief."""

    physician: PhysicianProfile
    meeting_script: str
    objection_handler: str
    priority_rationale: str
    retrieved_kb_chunks: list[str] = Field(
        default_factory=list,
        description="KB chunks used for transparency/citations",
    )


class ChatMessage(BaseModel):
    """Single message in chat history."""

    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    """Request body for POST /chat."""

    physician_id: str
    message: str
    conversation_history: list[ChatMessage] = Field(default_factory=list)
    brief_context: dict = Field(
        default_factory=dict,
        description="meeting_script, objection_handler, retrieved_kb_chunks",
    )


class ChatResponse(BaseModel):
    """Response for POST /chat."""

    response: str
    suggested_followups: list[str] = Field(
        default_factory=list,
        description="3 short follow-up question strings",
    )


class IntelRequest(BaseModel):
    """Request body for POST /intel."""

    physician_id: str
    days_lookback: int = 90


class IntelItem(BaseModel):
    """Single intel item."""

    headline: str
    detail: str
    relevance: str
    source_url: str = ""
    date: str = ""


class IntelResponse(BaseModel):
    """Response for POST /intel."""

    physician_name: str
    last_contact_date: str
    days_since_contact: int
    drug_updates: list[IntelItem] = Field(default_factory=list)
    publications: list[IntelItem] = Field(default_factory=list)
    tempus_updates: list[IntelItem] = Field(default_factory=list)
    competitive_intel: list[IntelItem] = Field(default_factory=list)
    generated_at: str = ""


class OutcomeRequest(BaseModel):
    """Request body for POST /outcomes."""

    physician_id: str
    outcome: str
    main_concern: str
    concern_detail: Optional[str] = None
    next_step: str
    meeting_date: Optional[str] = None


class OutcomeResponse(BaseModel):
    """Response for POST /outcomes."""

    physician_id: str
    new_priority_score: float
    score_delta: float
    suggested_next_action: str
    updated_at: str


class OutcomeLog(BaseModel):
    """Single logged outcome."""

    meeting_date: str
    outcome: str
    main_concern: str
    next_step: str
    priority_score: float
    score_delta: float

