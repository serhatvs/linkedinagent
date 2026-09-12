"""Comprehensive test suite for Multi-Channel Onboarding & Cross-Platform Distribution."""

import json
import uuid
from pathlib import Path
import pytest

from core.models import (
    Candidate,
    CandidateDecision,
    MVTSEvaluation,
    Post,
    MediaAsset,
    Citation,
    LifecycleState,
    SocialNetwork,
    ChannelIdentity,
    BUFFER_BOUND_CHANNELS,
    LinkedInVariant,
    InstagramVariant,
    XVariant,
    ActionScope,
    ApprovalToken,
    AutonomyDecision
)
from core.distribution_adapter import DistributionAdapter
from core.approval_engine import ApprovalEngine
from core.mcp_gateways import BufferGateway
from core.publisher_dispatcher import PublisherDispatcher
from core.policy_signer import PolicySigner
from core.autonomy_policy_engine import AutonomyPolicyEngine
from core.disclosure_reviewer import DisclosureReviewer
from tests.test_hardening_pass import make_test_scorecard


def make_candidate(cand_id: str, mvts: float, is_reject: bool = False) -> Candidate:
    dec = CandidateDecision.REJECT if is_reject else (CandidateDecision.PROCEED_TO_DRAFT if mvts >= 9.0 else CandidateDecision.HOLD_QUALITY)
    return Candidate(
        candidate_id=cand_id,
        idea_id=f"idea_{cand_id}",
        pillar="pillar_low_level_systems_and_graphics",
        target_audience=["Engineers"],
        angle="Test Angle",
        mvts_evaluation=MVTSEvaluation(
            grounding_score=min(mvts * 0.3, 3.0),
            technical_artifact_score=min(mvts * 0.3, 3.0),
            engineering_tradeoff_score=min(mvts * 0.2, 2.0),
            actionable_takeaway_score=min(mvts * 0.2, 2.0),
            total_score=mvts
        ),
        decision=dec
    )


def test_channel_identities_and_bound_channels():
    """Verify that all 3 channels are bound with exact IDs and editorial thresholds."""
    assert len(BUFFER_BOUND_CHANNELS) == 3
    assert "linkedin" in BUFFER_BOUND_CHANNELS
    assert "instagram" in BUFFER_BOUND_CHANNELS
    assert "twitter" in BUFFER_BOUND_CHANNELS

    li = BUFFER_BOUND_CHANNELS["linkedin"]
    assert li.channel_id == "6aa34050cd8b9c702c48769e"
    assert li.network == SocialNetwork.LINKEDIN
    assert li.mvts_threshold == 9.0
    assert li.username_handle == "serhat-yavuz-70593b370"

    ig = BUFFER_BOUND_CHANNELS["instagram"]
    assert ig.channel_id == "6aa340c6cd8b9c702c487833"
    assert ig.network == SocialNetwork.INSTAGRAM
    assert ig.mvts_threshold == 7.5
    assert ig.requires_media is True
    assert ig.username_handle == "serhatyvz_38"

    tw = BUFFER_BOUND_CHANNELS["twitter"]
    assert tw.channel_id == "6aa340e1cd8b9c702c487894"
    assert tw.network == SocialNetwork.TWITTER
    assert tw.mvts_threshold == 6.5
    assert tw.max_character_length == 280
    assert tw.username_handle == "Arkhino_DEV"


def test_distribution_adapter_eligibility():
    """Verify channel eligibility evaluation based on substance and visual requirements."""
    adapter = DistributionAdapter()

    # Case 1: High MVTS (9.5) with visual asset -> Eligible for all 3
    cand_high = make_candidate("cand_high", 9.5)
    assets = [MediaAsset(
        asset_type="hardware_photo",
        asset_path="assets/photo.jpg",
        asset_sha256="abc123def456abc123def456abc123def456abc123def456abc123def456abc1",
        caption="Workbench"
    )]
    el_high = adapter.evaluate_channel_eligibility(cand_high, assets)
    assert el_high["linkedin"][0] is True
    assert el_high["instagram"][0] is True
    assert el_high["twitter"][0] is True

    # Case 2: High MVTS (9.5) WITHOUT visual asset -> ALL channels INELIGIBLE (Universal Asset Mandate)
    el_no_visual = adapter.evaluate_channel_eligibility(cand_high, [])
    assert el_no_visual["linkedin"][0] is False
    assert "text-only posts are prohibited" in el_no_visual["linkedin"][1]
    assert el_no_visual["instagram"][0] is False
    assert "strictly requires at least one verified image or video asset" in el_no_visual["instagram"][1]
    assert el_no_visual["twitter"][0] is False
    assert "text-only posts are prohibited" in el_no_visual["twitter"][1]

    # Case 3: Medium MVTS (8.0) -> LinkedIn INELIGIBLE (<9.0), X Eligible, Instagram (with asset) Eligible
    cand_med = make_candidate("cand_med", 8.0)
    el_med = adapter.evaluate_channel_eligibility(cand_med, assets)
    assert el_med["linkedin"][0] is False
    assert "below LinkedIn threshold" in el_med["linkedin"][1]
    assert el_med["instagram"][0] is True
    assert el_med["twitter"][0] is True

    # Case 4: Terminally rejected candidate -> All channels INELIGIBLE
    cand_rej = make_candidate("cand_rej", 9.5, is_reject=True)
    el_rej = adapter.evaluate_channel_eligibility(cand_rej, assets)
    assert el_rej["linkedin"][0] is False
    assert el_rej["instagram"][0] is False
    assert el_rej["twitter"][0] is False


def test_cross_platform_rule_voice_adaptation():
    """Verify that variants are distinctly adapted and never identical."""
    adapter = DistributionAdapter()
    cand = make_candidate("cand_nvenc", 9.8)
    base_text = (
        "When the GPU can draw 2560x1600 but the tablet video decoder refuses it: "
        "How NVENC dual-strip tiling works. We measured a 48ms latency reduction by splitting "
        "the framebuffer into two independent slices. This prevented the hardware decoder FIFO from stalling."
    )
    assets = [MediaAsset(
        asset_type="code_snippet",
        asset_path="assets/nvenc.png",
        asset_sha256="abc123def456abc123def456abc123def456abc123def456abc123def456abc1",
        caption="NVENC dual-strip pipeline"
    )]

    story = adapter.generate_story_variants(cand, base_text, assets)
    assert len(story.variants) == 3

    li_var = story.variants["linkedin"]
    ig_var = story.variants["instagram"]
    tw_var = story.variants["twitter"]

    # Invariant: Variants must never have identical text
    assert li_var.content_text != ig_var.content_text
    assert li_var.content_text != tw_var.content_text
    assert ig_var.content_text != tw_var.content_text

    # LinkedIn checks
    assert isinstance(li_var, LinkedInVariant)
    assert li_var.target_platform == SocialNetwork.LINKEDIN
    assert "NVENC dual-strip tiling" in li_var.content_text

    # Instagram checks
    assert isinstance(ig_var, InstagramVariant)
    assert ig_var.target_platform == SocialNetwork.INSTAGRAM
    assert "Build Log" in ig_var.content_text
    assert "#buildinpublic" in ig_var.content_text

    # X checks
    assert isinstance(tw_var, XVariant)
    assert tw_var.target_platform == SocialNetwork.TWITTER
    assert len(tw_var.content_text) <= 280

    # Invariant: Independent payload hashes
    assert li_var.canonical_payload_sha256 != ig_var.canonical_payload_sha256
    assert li_var.canonical_payload_sha256 != tw_var.canonical_payload_sha256


def test_canary_payload_serialization_all_three_channels():
    """Verify canary payload generation produces compliant Buffer MCP structures with 0 network bytes."""
    adapter = DistributionAdapter()

    for ch_key in ["linkedin", "instagram", "twitter"]:
        payload = adapter.build_canary_buffer_payload(ch_key)
        assert payload.channel_id == BUFFER_BOUND_CHANNELS[ch_key].channel_id
        assert payload.mode == "customScheduled"
        assert payload.scheduling_type == "automatic"
        assert "+03:00" in payload.due_at
        assert len(payload.verified_payload_sha256) == 64

        if ch_key == "instagram":
            assert len(payload.assets) > 0
            assert payload.metadata["instagram"]["type"] == "post"
            assert payload.metadata["instagram"]["shouldShareToFeed"] is True

        if ch_key == "twitter":
            assert len(payload.text) <= 280


def test_buffer_gateway_multichannel_scheduling_simulation():
    """Verify BufferGateway simulates scheduling for all 3 channels with appropriate constraints."""
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    bg = BufferGateway(ae, dry_run=True)

    for ch_key in ["linkedin", "instagram", "twitter"]:
        ch = BUFFER_BOUND_CHANNELS[ch_key]
        tag = uuid.uuid4().hex[:6]
        content = "Benchmarked DMA bus contention down 24% on STM32H7." if ch_key == "twitter" else "Deep architectural breakdown of STM32H7 DMA bus contention."
        media = [
            MediaAsset(
                asset_type="code_snippet",
                asset_path="assets/code.png",
                asset_sha256="abc123def456abc123def456abc123def456abc123def456abc123def456abc1",
                caption="DMA snippet"
            )
        ]

        post = Post(
            post_id=f"post_test_{ch_key}_{tag}",
            pillar="pillar_low_level_systems_and_graphics",
            author="Serhat",
            title=f"Test Post {ch_key}",
            content_text=content,
            media_assets=media,
            citations=[Citation(claim_text="c", source_type="git_commit", reference_id="abc1234")]
        )
        scorecard = make_test_scorecard()
        req = ae.create_approval_request(post, scorecard, target_platform=ch_key)
        token = ae.sign_approval_request(req, "Serhat")

        res = bg.schedule_post(post, token, "2026-09-15T09:00:00+03:00", target_channel_id=ch.channel_id)
        assert res["status"] == "SUCCESS"
        assert res["mode"] == "DRY_RUN"
        assert res["channel_id"] == ch.channel_id
        assert res["target_platform"] == ch_key


def test_publisher_dispatcher_rejects_instagram_without_media():
    """Verify PublisherDispatcher enforces mandatory media for Instagram."""
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    ae.set_killswitch_mode("AUTONOMY_ENABLED", "Testing Instagram dispatcher rule")
    dispatcher = PublisherDispatcher(ws, ae)

    tag = uuid.uuid4().hex[:6]
    post = Post(
        post_id=f"post_ig_nomedia_{tag}",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Instagram No Media",
        content_text="Trying to post on Instagram without an image or video.",
        media_assets=[],  # Empty media
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="sqlite")]
    )
    scorecard = make_test_scorecard()
    req = ae.create_approval_request(post, scorecard, target_platform="instagram")
    token = ae.sign_approval_request(req, "Serhat")
    post.lifecycle_state = LifecycleState.APPROVED

    with pytest.raises(PermissionError) as excinfo:
        dispatcher.dispatch(post, token, mode="SHADOW_MODE")
    assert "E_MEDIA_REQUIRED" in str(excinfo.value)


def test_publisher_dispatcher_rejects_twitter_overflow():
    """Verify PublisherDispatcher enforces 280 char limit for Twitter."""
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    ae.set_killswitch_mode("AUTONOMY_ENABLED", "Testing Twitter char limit")
    dispatcher = PublisherDispatcher(ws, ae)

    tag = uuid.uuid4().hex[:6]
    overflow_text = "A" * 300
    post = Post(
        post_id=f"post_tw_overflow_{tag}",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Twitter Overflow",
        content_text=overflow_text,
        media_assets=[MediaAsset(
            asset_type="code_snippet",
            asset_path="assets/snippet.png",
            asset_sha256="abc123def456abc123def456abc123def456abc123def456abc123def456abc1",
            caption="Code diff"
        )],
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="sqlite")]
    )
    scorecard = make_test_scorecard()
    req = ae.create_approval_request(post, scorecard, target_platform="twitter")
    token = ae.sign_approval_request(req, "Serhat")
    post.lifecycle_state = LifecycleState.APPROVED

    with pytest.raises(PermissionError) as excinfo:
        dispatcher.dispatch(post, token, mode="SHADOW_MODE")
    assert "E_COPY_OVERFLOW" in str(excinfo.value)


def test_autonomy_engine_channel_policies_and_hold_for_asset():
    """Verify AutonomyPolicyEngine enforces per-channel MVTS thresholds and HOLD_FOR_ASSET."""
    ws = Path(__file__).resolve().parent.parent
    pe = AutonomyPolicyEngine(ws)
    disclosure_rev = DisclosureReviewer(ws)

    # 1. Instagram with MVTS 8.0 but NO media -> HOLD_FOR_ASSET
    cand_ig = make_candidate("cand_ig_test", 8.0)
    post_ig = Post(
        post_id="post_ig_no_media",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Instagram Hardware Setup",
        content_text="Detailed build log without media asset.",
        media_assets=[],
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="c++")]
    )
    scorecard_ig = make_test_scorecard(composite=92.0)
    disclosure_ig = disclosure_rev.review_post(post_ig)
    eval_ig = pe.evaluate(post_ig, cand_ig, scorecard_ig, disclosure_ig, recent_posts=[], target_platform="instagram")
    assert eval_ig.decision == AutonomyDecision.HOLD_FOR_ASSET
    assert any("HOLD_FOR_ASSET" in r or "strictly requires" in r for r in eval_ig.reasons)

    # 2. X with MVTS 7.0 and valid asset -> AUTO_APPROVE (MVTS >= 6.5)
    cand_x = make_candidate("cand_x_test", 7.0)
    post_x = Post(
        post_id="post_x_pass",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Developer Quick Insight",
        content_text="Developer-native punchy takeaway under 280 chars.",
        media_assets=[MediaAsset(
            asset_type="code_snippet",
            asset_path="assets/snippet.png",
            asset_sha256="abc123def456abc123def456abc123def456abc123def456abc123def456abc1",
            caption="Code snippet"
        )],
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="c++")]
    )
    scorecard_x = make_test_scorecard(composite=93.0)
    disclosure_x = disclosure_rev.review_post(post_x)
    eval_x = pe.evaluate(post_x, cand_x, scorecard_x, disclosure_x, recent_posts=[], target_platform="twitter")
    assert eval_x.decision == AutonomyDecision.AUTO_APPROVE

    # 3. LinkedIn with MVTS 8.0 -> HOLD_QUALITY (< 9.0)
    cand_li = make_candidate("cand_li_test", 8.0)
    post_li = Post(
        post_id="post_li_sub9",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Architecture Insight",
        content_text="Content text with MVTS 8.0.",
        media_assets=[MediaAsset(
            asset_type="architecture_diagram",
            asset_path="assets/diag.png",
            asset_sha256="abc123def456abc123def456abc123def456abc123def456abc123def456abc1",
            caption="Diagram"
        )],
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="c++")]
    )
    scorecard_li = make_test_scorecard(composite=93.0)
    disclosure_li = disclosure_rev.review_post(post_li)
    eval_li = pe.evaluate(post_li, cand_li, scorecard_li, disclosure_li, recent_posts=[], target_platform="linkedin")
    assert eval_li.decision == AutonomyDecision.HOLD_QUALITY


def test_channel_scheduling_horizon_and_ceilings():
    """Verify channel-specific 7-day ceilings (LinkedIn: 2, X: 3, Instagram: 1)."""
    ws = Path(__file__).resolve().parent.parent
    pe = AutonomyPolicyEngine(ws)
    from core.scheduler_engine import AgencyScheduler
    scheduler = AgencyScheduler(ws)

    post = Post(post_id="post_ceil_test", pillar="pillar_software_infrastructure", author="Serhat", title="Ceil", content_text="C", citations=[])

    # LinkedIn ceiling is 2
    post_li_other1 = Post(post_id="post_li_other1", pillar="pillar_software_infrastructure", author="Serhat", title="O1", content_text="O1", citations=[])
    post_li_other2 = Post(post_id="post_li_other2", pillar="pillar_software_infrastructure", author="Serhat", title="O2", content_text="O2", citations=[])
    
    pass_li_1, _ = pe._check_weekly_ceiling(post, recent_posts=[post, post_li_other1], target_platform="linkedin")
    assert pass_li_1 is True

    pass_li_2, reason_li_2 = pe._check_weekly_ceiling(post, recent_posts=[post, post_li_other1, post_li_other2], target_platform="linkedin")
    assert pass_li_2 is False
    assert "Weekly ceiling reached" in reason_li_2
    assert "LINKEDIN is 2" in reason_li_2

    # Instagram ceiling is 1
    post_ig_other = Post(post_id="post_ig_other", pillar="pillar_software_infrastructure", author="Serhat", title="IG", content_text="IG", citations=[])
    pass_ig_0, _ = pe._check_weekly_ceiling(post, recent_posts=[post], target_platform="instagram")
    assert pass_ig_0 is True

    pass_ig_1, reason_ig_1 = pe._check_weekly_ceiling(post, recent_posts=[post, post_ig_other], target_platform="instagram")
    assert pass_ig_1 is False
    assert "Weekly ceiling reached" in reason_ig_1
    assert "INSTAGRAM is 1" in reason_ig_1
