"""Data models for the personal media agency with Pydantic validation."""

from __future__ import annotations
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator


class LifecycleState(str, Enum):
    IDEA = "IDEA"
    CANDIDATE = "CANDIDATE"
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    ANALYZED = "ANALYZED"


class ActionScope(str, Enum):
    METRICOOL_SCHEDULE = "METRICOOL_SCHEDULE"
    METRICOOL_PUBLISH_NOW = "METRICOOL_PUBLISH_NOW"
    METRICOOL_COMMENT_REPLY = "METRICOOL_COMMENT_REPLY"


class EditorialVerdict(str, Enum):
    PASSED_EDITORIAL = "PASSED_EDITORIAL"
    REVISE_REQUIRED = "REVISE_REQUIRED"
    REJECTED_SLOP_OR_DRC = "REJECTED_SLOP_OR_DRC"


class CandidateDecision(str, Enum):
    PROCEED_TO_DRAFT = "PROCEED_TO_DRAFT"
    HOLD_NO_OP = "HOLD_NO_OP"
    REJECT = "REJECT"


class Idea(BaseModel):
    idea_id: str = Field(..., pattern=r"^idea_[a-z0-9_]+$")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_type: str = Field(..., description="github_commit, github_issue, lab_note, bench_result, direct_user_input")
    title: str = Field(..., min_length=5, max_length=120)
    raw_notes: str = Field(..., min_length=10)
    pillar_affinity: str
    technical_artifacts_available: List[str] = Field(default_factory=list)
    project_id: Optional[str] = None


class MVTSEvaluation(BaseModel):
    grounding_score: float = Field(..., ge=0, le=3)
    technical_artifact_score: float = Field(..., ge=0, le=3)
    engineering_tradeoff_score: float = Field(..., ge=0, le=2)
    actionable_takeaway_score: float = Field(..., ge=0, le=2)
    total_score: float = Field(..., ge=0, le=10)


class Candidate(BaseModel):
    candidate_id: str = Field(..., pattern=r"^cand_[a-z0-9_]+$")
    idea_id: str
    pillar: str
    target_audience: List[str]
    angle: str
    mvts_evaluation: MVTSEvaluation
    decision: CandidateDecision
    hold_rationale: Optional[str] = None


class MediaAsset(BaseModel):
    asset_type: str = Field(..., description="schematic, code_snippet, logic_trace, cad_render, benchmark_chart, hardware_photo")
    asset_path: str
    asset_sha256: str
    caption: str


class Citation(BaseModel):
    claim_text: str
    source_type: str = Field(..., description="knowledge_fact, project_registry, git_commit, lab_spec")
    reference_id: str


class Scores(BaseModel):
    technical_rigor: float = Field(..., ge=0, le=25)
    clarity_and_flow: float = Field(..., ge=0, le=25)
    visual_utility: float = Field(..., ge=0, le=25)
    reader_roi: float = Field(..., ge=0, le=25)
    composite_score: float = Field(..., ge=0, le=100)


class SlopAnalysis(BaseModel):
    slop_score: float
    detected_buzzwords: List[str]
    emoji_count: int
    slop_detected: bool


class DomainDRCChecks(BaseModel):
    passed: bool
    checks_run: List[str]
    violations: List[str]


class GroundingVerification(BaseModel):
    grounding_percentage: float = Field(..., ge=0, le=100)
    unverified_claims: List[str]
    cited_sources: List[str]


class EditorialScorecard(BaseModel):
    evaluation_id: str
    post_id: str
    evaluated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    scores: Scores
    slop_analysis: SlopAnalysis
    domain_drc_checks: DomainDRCChecks
    grounding_verification: GroundingVerification
    verdict: EditorialVerdict


class Post(BaseModel):
    post_id: str = Field(..., pattern=r"^post_[a-z0-9_]+$")
    state_version: int = Field(default=1, ge=1)
    lifecycle_state: LifecycleState = LifecycleState.DRAFT
    pillar: str
    author: str = "Serhat"
    title: str
    content_text: str
    media_assets: List[MediaAsset] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    scorecard_id: Optional[str] = None
    approval_request_id: Optional[str] = None
    scheduled_publish_time: Optional[str] = None
    metricool_post_id: Optional[str] = None
    linkedin_url: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ApprovalRequest(BaseModel):
    request_id: str = Field(..., pattern=r"^appr_req_[a-z0-9_]+$")
    post_id: str
    requested_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    action_scope: ActionScope
    target_platform: str = "linkedin"
    proposed_schedule_time: str
    canonical_payload_sha256: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    content_summary: str
    content_full_text: str
    media_asset_hashes: List[str]
    scorecard_summary: Dict[str, Any]


class ApprovalToken(BaseModel):
    token_id: str = Field(..., pattern=r"^token_[a-z0-9_]+$")
    request_id: str
    post_id: str
    approved_by: str = "Serhat"
    signed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str
    nonce: str
    action_scope: ActionScope
    target_platform: str = "linkedin"
    canonical_payload_sha256: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    signature_digest: str


class MetricoolPayload(BaseModel):
    platform: str = "linkedin"
    text: str = Field(..., min_length=20)
    dateTime: str
    media: List[Dict[str, str]]
    approval_token_id: str
    verified_payload_sha256: str


class AnalyticsReport(BaseModel):
    report_id: str
    period_start: str
    period_end: str
    total_posts_published: int
    total_impressions: int
    quality_engagement_ratio: float
    inbound_technical_leads: int
    top_performing_pillar: Optional[str] = None
    key_learnings: List[str]
