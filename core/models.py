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
    AUTO_APPROVED = "AUTO_APPROVED"
    REVALIDATION_REQUIRED = "REVALIDATION_REQUIRED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    ANALYZED = "ANALYZED"


class KillswitchState(str, Enum):
    AUTONOMY_ENABLED = "AUTONOMY_ENABLED"
    AUTONOMY_PAUSED = "AUTONOMY_PAUSED"
    WRITE_DISABLED = "WRITE_DISABLED"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class DisclosureRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AutonomyDecision(str, Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    AUTO_PUBLISH_ELIGIBLE = "AUTO_PUBLISH_ELIGIBLE"
    REQUIRE_HUMAN_APPROVAL = "REQUIRE_HUMAN_APPROVAL"
    HOLD_QUALITY = "HOLD_QUALITY"
    HOLD_FOR_ASSET = "HOLD_FOR_ASSET"
    REQUEST_ASSET_FROM_USER = "REQUEST_ASSET_FROM_USER"
    REJECTED = "REJECTED"
    REJECT_OR_REVISE = "REJECT_OR_REVISE"


class AssetSourcePriority(str, Enum):
    EXISTING_PROJECT_ASSET = "EXISTING_PROJECT_ASSET"          # Priority 1: Existing real project assets
    AUTO_CAPTURED_REAL_ASSET = "AUTO_CAPTURED_REAL_ASSET"      # Priority 2: Automatically captured real assets
    USER_REQUESTED_REAL_ASSET = "USER_REQUESTED_REAL_ASSET"    # Priority 3: Real assets requested from Serhat
    DETERMINISTIC_COMPOSED_ASSET = "DETERMINISTIC_COMPOSED_ASSET" # Priority 4: Deterministic composed assets from real evidence
    AI_GENERATED_FALLBACK = "AI_GENERATED_FALLBACK"            # Priority 5: AI-generated assets as final fallback only


class AssetArchetype(str, Enum):
    SCREENSHOT = "screenshot"
    APP_UI = "app_ui"
    CONTROLS_SETTINGS = "controls_settings"
    DEMO_RECORDING = "demo_recording"
    PRODUCT_PROTOTYPE_PHOTO = "product_prototype_photo"
    WORKBENCH_PHOTO = "workbench_photo"
    BENCHMARK_CHART = "benchmark_chart"
    TERMINAL_OUTPUT = "terminal_output"
    CAD_RENDER = "cad_render"
    ARCHITECTURE_DIAGRAM = "architecture_diagram"
    CODE_SNIPPET_DIFF = "code_snippet_diff"
    SCHEMATIC = "schematic"
    OSCILLOSCOPE_TRACE = "oscilloscope_trace"
    LOGIC_ANALYZER_TRACE = "logic_analyzer_trace"
    DETERMINISTIC_COMPOSITE = "deterministic_composite"
    TECHNICAL_CAROUSEL = "technical_carousel"
    CONCEPT_VISUAL_FALLBACK = "concept_visual_fallback"


class ActionScope(str, Enum):
    SOCIAL_SCHEDULE = "SOCIAL_SCHEDULE"
    SOCIAL_PUBLISH_NOW = "SOCIAL_PUBLISH_NOW"
    SOCIAL_COMMENT_REPLY = "SOCIAL_COMMENT_REPLY"
    BUFFER_SCHEDULE = "BUFFER_SCHEDULE"
    BUFFER_PUBLISH_NOW = "BUFFER_PUBLISH_NOW"
    BUFFER_LINKEDIN_SCHEDULE = "BUFFER_LINKEDIN_SCHEDULE"
    BUFFER_INSTAGRAM_SCHEDULE = "BUFFER_INSTAGRAM_SCHEDULE"
    BUFFER_TWITTER_SCHEDULE = "BUFFER_TWITTER_SCHEDULE"
    METRICOOL_SCHEDULE = "METRICOOL_SCHEDULE"
    METRICOOL_PUBLISH_NOW = "METRICOOL_PUBLISH_NOW"
    METRICOOL_COMMENT_REPLY = "METRICOOL_COMMENT_REPLY"


class SocialNetwork(str, Enum):
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"


class EditorialVerdict(str, Enum):
    PASSED_EDITORIAL = "PASSED_EDITORIAL"
    REVISE_REQUIRED = "REVISE_REQUIRED"
    REJECTED_SLOP_OR_DRC = "REJECTED_SLOP_OR_DRC"


class CandidateDecision(str, Enum):
    PROCEED_TO_DRAFT = "PROCEED_TO_DRAFT"
    HOLD_QUALITY = "HOLD_QUALITY"
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
    parent_candidate_id: Optional[str] = None
    revival_reason: Optional[str] = None
    revived_by: Optional[str] = None
    revived_at: Optional[str] = None
    override_reason: Optional[str] = None
    overridden_by: Optional[str] = None
    overridden_at: Optional[str] = None


class MediaAsset(BaseModel):
    asset_type: str = Field(..., description="schematic, code_snippet, logic_trace, cad_render, benchmark_chart, hardware_photo, app_ui, screenshot")
    asset_path: str
    asset_sha256: str
    caption: str
    source_priority: AssetSourcePriority = AssetSourcePriority.EXISTING_PROJECT_ASSET
    archetype: Optional[str] = None
    is_synthetic: bool = False
    synthetic_purpose: Optional[str] = None  # e.g. "concept_visual", "abstract_support", "cover_visual"
    real_evidence_ref: Optional[str] = None  # e.g. commit hash, benchmark table, hardware device ref


class HumanAssetRequest(BaseModel):
    request_id: str
    candidate_id: str
    target_platforms: List[str] = Field(default_factory=list)
    requested_asset_title: str
    specific_instructions: str
    why_needed: str
    recommended_shots: List[str] = Field(default_factory=list)
    status: str = "PENDING"  # PENDING, FULFILLED, SUPERSEDED
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fulfilled_asset_path: Optional[str] = None
    fulfilled_at: Optional[str] = None
    asset_sha256: Optional[str] = None


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
    buffer_post_id: Optional[str] = None
    remote_post_id: Optional[str] = None
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
    approval_type: str = "HUMAN"  # HUMAN or AUTO_APPROVAL
    autonomy_policy_version: Optional[str] = None
    signed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str
    ttl_hours: int = 168
    nonce: str
    action_scope: ActionScope
    target_platform: str = "linkedin"
    canonical_payload_sha256: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    signature_digest: str


class DisclosureCheck(BaseModel):
    passed: bool
    risk_level: DisclosureRisk
    prohibited_classes_detected: List[str] = Field(default_factory=list)
    public_safe_verification: bool = True
    rationale: str


class AutonomyEvaluation(BaseModel):
    decision: AutonomyDecision
    policy_version: str = "v1.1.0-hardening"
    mvts_score: float
    editorial_score: float
    grounding_percentage: float
    slop_score: float
    drc_passed: bool
    disclosure_risk: DisclosureRisk
    cooldown_passed: bool
    weekly_ceiling_passed: bool
    reasons: List[str] = Field(default_factory=list)
    candidate_id: Optional[str] = None
    post_id: Optional[str] = None
    canonical_payload_sha256: Optional[str] = None
    evaluation_hash: Optional[str] = None
    ttl_hours: int = 168
    evaluated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DispatchResult(BaseModel):
    dispatch_id: str
    post_id: str
    status: str  # SUCCESS, SHADOW_SUCCESS, ABORTED
    idempotency_token: str
    mode: str  # LIVE, DRY_RUN, SHADOW_MODE
    publisher_backend: str = "buffer"
    remote_post_id: Optional[str] = None
    buffer_post_id: Optional[str] = None
    metricool_post_id: Optional[str] = None
    scheduled_publish_time: str
    payload_sha256: str
    dispatched_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reconciliation_notes: Optional[str] = None


class BufferPayload(BaseModel):
    channel_id: Optional[str] = None
    text: str = Field(..., min_length=5)
    scheduling_type: str = "automatic"
    due_at: Optional[str] = None
    mode: str = "customScheduled"
    assets: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    approval_token_id: str
    verified_payload_sha256: str


class ChannelIdentity(BaseModel):
    channel_id: str
    network: SocialNetwork
    service: str
    display_name: str
    username_handle: str
    account_type: str
    descriptor: str
    editorial_role: str
    mvts_threshold: float = Field(..., ge=0, le=10)
    tone_profile: str
    content_types: List[str] = Field(default_factory=list)
    requires_media: bool = False
    max_character_length: int = 3000
    direct_publishing_supported: bool = True
    queue_limit: int = 10


BUFFER_BOUND_CHANNELS: Dict[str, ChannelIdentity] = {
    "linkedin": ChannelIdentity(
        channel_id="6aa34050cd8b9c702c48769e",
        network=SocialNetwork.LINKEDIN,
        service="linkedin",
        display_name="Serhat Yavuz",
        username_handle="serhat-yavuz-70593b370",
        account_type="profile",
        descriptor="LinkedIn Profile",
        editorial_role="Professional engineering reputation",
        mvts_threshold=9.0,
        tone_profile="Rigorous, credible, restrained, architectural, measured, evidence-grounded",
        content_types=[
            "important project milestones",
            "deep architecture breakdowns",
            "measured technical results & benchmarks",
            "system launches",
            "hackathon & system retrospects"
        ],
        requires_media=True,
        max_character_length=3000,
        direct_publishing_supported=True,
        queue_limit=10
    ),
    "instagram": ChannelIdentity(
        channel_id="6aa340c6cd8b9c702c487833",
        network=SocialNetwork.INSTAGRAM,
        service="instagram",
        display_name="serhatyvz_38",
        username_handle="serhatyvz_38",
        account_type="business",
        descriptor="Instagram Professional Account",
        editorial_role="Visual creative / build journal",
        mvts_threshold=7.5,
        tone_profile="Visual, creative, build-in-public, workbench, behind-the-scenes, concise caption",
        content_types=[
            "hardware lab workbench",
            "3D printing timelapse & CAD renders",
            "workbench photos & PCB teardowns",
            "visual milestone artifacts",
            "behind-the-scenes build logs"
        ],
        requires_media=True,
        max_character_length=2200,
        direct_publishing_supported=True,
        queue_limit=10
    ),
    "twitter": ChannelIdentity(
        channel_id="6aa340e1cd8b9c702c487894",
        network=SocialNetwork.TWITTER,
        service="twitter",
        display_name="Arkhino_DEV",
        username_handle="Arkhino_DEV",
        account_type="profile",
        descriptor="X Free Profile",
        editorial_role="Developer feed",
        mvts_threshold=6.5,
        tone_profile="Direct, concise, developer-native, punchy, zero corporate fluff, fast insight",
        content_types=[
            "fast technical updates",
            "micro-learnings & gotchas",
            "tool & library discovery",
            "real-time debugging insights",
            "direct technical opinions"
        ],
        requires_media=True,
        max_character_length=280,
        direct_publishing_supported=True,
        queue_limit=10
    )
}


class PlatformVariant(BaseModel):
    variant_id: str = Field(..., pattern=r"^var_[a-z0-9_]+$")
    story_id: str
    candidate_id: str
    channel_id: str
    target_platform: SocialNetwork
    lifecycle_state: LifecycleState = LifecycleState.DRAFT
    content_text: str
    media_assets: List[MediaAsset] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    approval_type: Optional[str] = None  # HUMAN or AUTO_APPROVAL
    approval_token_id: Optional[str] = None
    canonical_payload_sha256: Optional[str] = None
    dispatch_state: str = "PENDING"  # PENDING, APPROVED, AUTO_APPROVED, SCHEDULED, PUBLISHED, REJECTED, HOLD
    scheduled_publish_time: Optional[str] = None
    remote_post_id: Optional[str] = None
    dispatch_result: Optional[DispatchResult] = None
    adaptation_notes: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class LinkedInVariant(PlatformVariant):
    target_platform: SocialNetwork = SocialNetwork.LINKEDIN
    technical_depth: str = "deep_architectural"
    mentions: List[Dict[str, Any]] = Field(default_factory=list)


class InstagramVariant(PlatformVariant):
    target_platform: SocialNetwork = SocialNetwork.INSTAGRAM
    sub_type: str = "post"  # post, reel, story
    should_share_to_feed: bool = True
    hashtags: List[str] = Field(default_factory=list)
    is_ai_generated: bool = False


class XVariant(PlatformVariant):
    target_platform: SocialNetwork = SocialNetwork.TWITTER
    is_thread: bool = False
    thread_items: List[str] = Field(default_factory=list)


class CanonicalStory(BaseModel):
    story_id: str = Field(..., pattern=r"^story_[a-z0-9_]+$")
    candidate_id: str
    project_id: str
    title: str
    core_engineering_thesis: str
    verified_evidence: List[str] = Field(default_factory=list)
    shared_media_assets: List[MediaAsset] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    mvts_score: float
    eligible_channels: List[SocialNetwork] = Field(default_factory=list)
    variants: Dict[str, PlatformVariant] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SocialPublishPayload(BaseModel):
    platform: str = "linkedin"
    text: str = Field(..., min_length=20)
    scheduled_publish_time: Optional[str] = None
    media: List[Dict[str, str]] = Field(default_factory=list)
    approval_token_id: str
    verified_payload_sha256: str
    channel_id: Optional[str] = None


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
