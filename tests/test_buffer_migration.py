"""Tests for Buffer social gateway migration and SocialPublisher interface."""

import json
import uuid
import os
from pathlib import Path
import pytest

from core.models import (
    Post,
    ApprovalToken,
    LifecycleState,
    ActionScope,
    Citation,
    MediaAsset,
    BufferPayload,
    SocialPublishPayload
)
from core.approval_engine import ApprovalEngine
from core.publisher_dispatcher import PublisherDispatcher
from core.mcp_gateways import SocialPublisher, BufferGateway, MetricoolGateway
from core.policy_signer import PolicySigner
from core.autonomy_policy_engine import AutonomyPolicyEngine
from core.disclosure_reviewer import DisclosureReviewer
from core.models import Candidate, CandidateDecision, MVTSEvaluation
from tests.test_hardening_pass import make_test_scorecard


def make_test_candidate(mvts: float = 9.5) -> Candidate:
    return Candidate(
        candidate_id="cand_test_buf",
        idea_id="idea_test_buf",
        pillar="pillar_low_level_systems_and_graphics",
        target_audience=["Engineers"],
        angle="Architecture",
        mvts_evaluation=MVTSEvaluation(
            grounding_score=3.0,
            technical_artifact_score=3.0,
            engineering_tradeoff_score=1.8,
            actionable_takeaway_score=1.7,
            total_score=mvts
        ),
        decision=CandidateDecision.PROCEED_TO_DRAFT
    )


@pytest.fixture(autouse=True)
def reset_agency_state():
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    yield
    ae.set_killswitch_mode("AUTONOMY_PAUSED", "Restored after test")


def test_social_publisher_interface():
    """Verify that BufferGateway and MetricoolGateway properly implement SocialPublisher."""
    assert issubclass(BufferGateway, SocialPublisher)
    assert issubclass(MetricoolGateway, SocialPublisher)

    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    bg = BufferGateway(ae)
    assert isinstance(bg, SocialPublisher)


def test_buffer_gateway_unauthenticated_returns_blocked_buffer_auth():
    """Verify unauthenticated Buffer capability returns BLOCKED_BUFFER_AUTH."""
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    bg = BufferGateway(ae, override_oauth_authenticated=False)

    # Ensure no env tokens active for this test
    old_tok = os.environ.pop("BUFFER_ACCESS_TOKEN", None)
    old_key = os.environ.pop("BUFFER_API_KEY", None)
    try:
        cap = bg.verify_authenticated_capability()
        assert cap["status"] == "BLOCKED_BUFFER_AUTH"
        assert cap["authenticated"] is False
        assert cap["blocker_code"] == "BLOCKED_BUFFER_AUTH"
        assert cap["endpoint_url"] == "https://mcp.buffer.com/mcp"
        assert cap["plan_tier"] == "Free"
        assert cap["linkedin_target_type"] == "PERSONAL_PROFILE"
        assert cap["schedule_post_available"] is True
    finally:
        if old_tok:
            os.environ["BUFFER_ACCESS_TOKEN"] = old_tok
        if old_key:
            os.environ["BUFFER_API_KEY"] = old_key


def test_buffer_gateway_missing_channel_returns_blocked_no_linkedin():
    """Verify authenticated Buffer without LinkedIn channel returns BLOCKED_NO_LINKEDIN_ACCOUNT_CONNECTED."""
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    bg = BufferGateway(ae, override_has_linkedin=False)
    bg.access_token = "mock_test_token"
    bg.channel_id = ""

    cap = bg.verify_authenticated_capability()
    assert cap["status"] == "BLOCKED_NO_LINKEDIN_ACCOUNT_CONNECTED"
    assert cap["authenticated"] is True
    assert cap["linkedin_connected"] is False
    assert cap["blocker_code"] == "BLOCKED_NO_LINKEDIN_ACCOUNT_CONNECTED"


def test_buffer_gateway_ready_state():
    """Verify authenticated Buffer with LinkedIn channel returns BUFFER_LINKEDIN_READY."""
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    bg = BufferGateway(ae)
    bg.access_token = "mock_test_token"
    bg.channel_id = "chan_linkedin_personal_123"

    cap = bg.verify_authenticated_capability()
    assert cap["status"] == "BUFFER_LINKEDIN_READY"
    assert cap["authenticated"] is True
    assert cap["linkedin_connected"] is True
    assert cap["linkedin_channel_id"] == "chan_linkedin_personal_123"
    assert cap["blocker_code"] is None


def test_buffer_schedule_post_dry_run():
    """Verify BufferGateway.schedule_post creates exact BufferPayload in DRY_RUN."""
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    ae.set_killswitch_mode("AUTONOMY_ENABLED", "Testing Buffer DRY_RUN")
    bg = BufferGateway(ae, dry_run=True)
    bg.channel_id = "chan_linkedin_personal_123"

    tag = uuid.uuid4().hex[:8]
    post = Post(
        post_id=f"post_buf_{tag}",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title=f"Buffer Test Post {tag}",
        content_text=f"Testing Buffer migration with low-level systems writeup {tag}.",
        media_assets=[
            MediaAsset(
                asset_type="code_snippet",
                asset_path="assets/code.png",
                asset_sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                caption="DMA buffer logic"
            )
        ],
        citations=[Citation(claim_text="c", source_type="git_commit", reference_id="abc1234")]
    )
    scorecard = make_test_scorecard()
    req = ae.create_approval_request(post, scorecard)
    cand = make_test_candidate(mvts=9.5)
    cand.pillar = post.pillar
    disclosure = DisclosureReviewer(ws).review_post(post)
    autonomy_eval = AutonomyPolicyEngine(ws).evaluate(post, cand, scorecard, disclosure, recent_posts=[])
    token = PolicySigner(ws).sign_auto_approval(post, req, autonomy_eval, shadow_mode=True)

    res = bg.schedule_post(post, token, "2026-09-15T06:30:00+00:00")
    assert res["status"] == "SUCCESS"
    assert res["publisher_backend"] == "buffer"
    assert res["buffer_post_id"].startswith("buffer_mock_")
    assert res["verified_hash"] == token.canonical_payload_sha256


def test_publisher_dispatcher_with_buffer_gateway():
    """Verify PublisherDispatcher defaults to BufferGateway and dispatches in SHADOW_MODE."""
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    ae.set_killswitch_mode("AUTONOMY_ENABLED", "Testing Buffer Dispatcher")
    dispatcher = PublisherDispatcher(ws, ae)
    assert isinstance(dispatcher.publisher, BufferGateway)

    tag = uuid.uuid4().hex[:8]
    post = Post(
        post_id=f"post_disp_buf_{tag}",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title=f"Buffer Dispatcher Test {tag}",
        content_text=f"Content text for Buffer publisher dispatcher verification {tag}.",
        media_assets=[
            MediaAsset(
                asset_type="code_snippet",
                asset_path="assets/code.png",
                asset_sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                caption="DMA buffer logic"
            )
        ],
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="sqlite")]
    )
    scorecard = make_test_scorecard()
    req = ae.create_approval_request(post, scorecard)
    cand = make_test_candidate(mvts=9.5)
    cand.pillar = post.pillar
    disclosure = DisclosureReviewer(ws).review_post(post)
    autonomy_eval = AutonomyPolicyEngine(ws).evaluate(post, cand, scorecard, disclosure, recent_posts=[])
    token = PolicySigner(ws).sign_auto_approval(post, req, autonomy_eval, shadow_mode=True)
    post.lifecycle_state = LifecycleState.AUTO_APPROVED

    res = dispatcher.dispatch(post, token, mode="SHADOW_MODE")
    assert res.status == "SHADOW_SUCCESS"
    assert res.publisher_backend == "buffer"
    assert res.buffer_post_id.startswith("buffer_shadow_")
    assert res.remote_post_id.startswith("buffer_shadow_")


def test_buffer_read_only_analytics_and_comments():
    """Verify read-only inspection methods work safely without side effects."""
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    bg = BufferGateway(ae)

    analytics = bg.fetch_post_analytics("buf_test_123")
    assert "impressions" in analytics
    assert "clicks" in analytics
    assert analytics["impressions"] > 0

    comments = bg.fetch_comments("buf_test_123")
    assert len(comments) > 0
    assert "<untrusted_comment_data>" in comments[0]["text"]
