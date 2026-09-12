"""Comprehensive tests for Phase 3: Autonomous LinkedIn Publishing & AutonomyPolicyEngine."""

import json
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest

from core.models import (
    Post,
    Candidate,
    CandidateDecision,
    MVTSEvaluation,
    EditorialScorecard,
    Scores,
    SlopAnalysis,
    DomainDRCChecks,
    GroundingVerification,
    EditorialVerdict,
    Citation,
    MediaAsset,
    ActionScope,
    DisclosureRisk,
    DisclosureCheck,
    AutonomyDecision,
    LifecycleState
)
from core.disclosure_reviewer import DisclosureReviewer
from core.autonomy_policy_engine import AutonomyPolicyEngine, AUTONOMY_POLICY_VERSION
from core.policy_signer import PolicySigner
from core.approval_engine import ApprovalEngine
from core.publisher_dispatcher import PublisherDispatcher
from core.lifecycle_manager import LifecycleManager


def make_qualifying_candidate() -> Candidate:
    return Candidate(
        candidate_id="cand_test_qualifying",
        idea_id="idea_test_qualifying",
        pillar="pillar_low_level_systems_and_graphics",
        target_audience=["Systems Engineers"],
        angle="Empirical Low-Level Systems",
        mvts_evaluation=MVTSEvaluation(
            grounding_score=3.0,
            technical_artifact_score=3.0,
            engineering_tradeoff_score=2.0,
            actionable_takeaway_score=1.5,
            total_score=9.5
        ),
        decision=CandidateDecision.PROCEED_TO_DRAFT
    )


def make_qualifying_scorecard() -> EditorialScorecard:
    return EditorialScorecard(
        evaluation_id="eval_test_qualifying",
        post_id="post_test_qualifying",
        scores=Scores(
            technical_rigor=24.0,
            clarity_and_flow=23.0,
            visual_utility=24.0,
            reader_roi=23.0,
            composite_score=94.0
        ),
        slop_analysis=SlopAnalysis(
            slop_score=0.0,
            detected_buzzwords=[],
            emoji_count=0,
            slop_detected=False
        ),
        domain_drc_checks=DomainDRCChecks(
            passed=True,
            checks_run=["mains_isolation", "lipo_protection", "benchmark_integrity"],
            violations=[]
        ),
        grounding_verification=GroundingVerification(
            grounding_percentage=100.0,
            unverified_claims=[],
            cited_sources=["knowledge/projects_registry.json"]
        ),
        verdict=EditorialVerdict.PASSED_EDITORIAL
    )


def make_test_media_asset() -> MediaAsset:
    return MediaAsset(
        asset_type="architecture_diagram",
        asset_path="assets/diagram.png",
        asset_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        caption="System Architecture Flow",
        source_priority="DETERMINISTIC_COMPOSED_ASSET",
        archetype="architecture_diagram",
        is_synthetic=False
    )


def test_low_risk_grounded_post_receives_policysigner_approval(tmp_path):
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    # Enable autonomy for this test
    ae.set_killswitch_mode("AUTONOMY_ENABLED", "Testing autonomy")

    policy_engine = AutonomyPolicyEngine(ws)
    signer = PolicySigner(ws)
    disclosure_rev = DisclosureReviewer(ws)

    post = Post(
        post_id="post_test_auto_pass",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Bypassing MediaCodec Macroblock Ceilings",
        content_text="A grounded, high-substance technical post describing dual-strip NVENC streaming without buzzwords.",
        media_assets=[make_test_media_asset()],
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="c++")]
    )

    cand = make_qualifying_candidate()
    scorecard = make_qualifying_scorecard()
    disclosure = disclosure_rev.review_post(post)
    assert disclosure.risk_level == DisclosureRisk.LOW

    evaluation = policy_engine.evaluate(post, cand, scorecard, disclosure, recent_posts=[])
    assert evaluation.decision == AutonomyDecision.AUTO_APPROVE

    req = ae.create_approval_request(post, scorecard)
    token = signer.sign_auto_approval(post, req, evaluation)

    assert token.approved_by == "PolicySigner"
    assert token.approval_type == "AUTO_APPROVAL"
    assert token.autonomy_policy_version == AUTONOMY_POLICY_VERSION

    # Verify token passes verification
    valid, reason = ae.verify_token_for_post(token, post)
    assert valid is True


def test_low_mvts_fails_autonomy(tmp_path):
    ws = Path(__file__).resolve().parent.parent
    policy_engine = AutonomyPolicyEngine(ws)
    disclosure_rev = DisclosureReviewer(ws)

    post = Post(
        post_id="post_low_mvts",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Shallow post",
        content_text="Some text that is not deep enough.",
        citations=[]
    )

    cand = Candidate(
        candidate_id="cand_low",
        idea_id="idea_low",
        pillar="pillar_low_level_systems_and_graphics",
        target_audience=["General"],
        angle="Shallow",
        mvts_evaluation=MVTSEvaluation(
            grounding_score=1.5,
            technical_artifact_score=1.0,
            engineering_tradeoff_score=1.0,
            actionable_takeaway_score=1.0,
            total_score=4.5  # Below 9.0
        ),
        decision=CandidateDecision.PROCEED_TO_DRAFT
    )

    scorecard = make_qualifying_scorecard()
    disclosure = disclosure_rev.review_post(post)

    evaluation = policy_engine.evaluate(post, cand, scorecard, disclosure)
    assert evaluation.decision != AutonomyDecision.AUTO_APPROVE
    assert any("MVTS score" in r for r in evaluation.reasons)


def test_editorial_failure_fails_autonomy():
    ws = Path(__file__).resolve().parent.parent
    policy_engine = AutonomyPolicyEngine(ws)
    disclosure_rev = DisclosureReviewer(ws)

    post = Post(
        post_id="post_fail_editorial",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Title",
        content_text="Content",
        citations=[]
    )
    cand = make_qualifying_candidate()
    scorecard = make_qualifying_scorecard()
    scorecard.scores.composite_score = 82.0  # Below 90.0

    disclosure = disclosure_rev.review_post(post)
    evaluation = policy_engine.evaluate(post, cand, scorecard, disclosure)
    assert evaluation.decision != AutonomyDecision.AUTO_APPROVE


def test_grounding_failure_fails_autonomy():
    ws = Path(__file__).resolve().parent.parent
    policy_engine = AutonomyPolicyEngine(ws)
    disclosure_rev = DisclosureReviewer(ws)

    post = Post(
        post_id="post_fail_grounding",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Title",
        content_text="Content",
        citations=[]
    )
    cand = make_qualifying_candidate()
    scorecard = make_qualifying_scorecard()
    scorecard.grounding_verification.grounding_percentage = 90.0  # Below 98.0%

    disclosure = disclosure_rev.review_post(post)
    evaluation = policy_engine.evaluate(post, cand, scorecard, disclosure)
    assert evaluation.decision != AutonomyDecision.AUTO_APPROVE


def test_security_vulnerability_requires_human_approval():
    ws = Path(__file__).resolve().parent.parent
    policy_engine = AutonomyPolicyEngine(ws)
    disclosure_rev = DisclosureReviewer(ws)

    post = Post(
        post_id="post_sec_vuln",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Found an RCE vulnerability CVE-2026-1192 in driver",
        content_text="Here is our proof of concept exploit and 0-day breakdown.",
        media_assets=[make_test_media_asset()],
        citations=[]
    )
    cand = make_qualifying_candidate()
    scorecard = make_qualifying_scorecard()

    disclosure = disclosure_rev.review_post(post)
    assert disclosure.risk_level == DisclosureRisk.HIGH
    assert disclosure.passed is False

    evaluation = policy_engine.evaluate(post, cand, scorecard, disclosure)
    assert evaluation.decision == AutonomyDecision.REQUIRE_HUMAN_APPROVAL


def test_private_repository_disclosure_requires_human_approval():
    ws = Path(__file__).resolve().parent.parent
    disclosure_rev = DisclosureReviewer(ws)

    post = Post(
        post_id="post_priv_disclosure",
        pillar="pillar_software_infrastructure",
        author="Serhat",
        title="Under NDA client contract",
        content_text="We signed an unannounced partnership with a confidential client under NDA.",
        citations=[]
    )

    disclosure = disclosure_rev.review_post(post)
    assert disclosure.risk_level == DisclosureRisk.HIGH
    assert "CONFIDENTIAL_OR_PROPRIETARY" in disclosure.prohibited_classes_detected


def test_payload_mutation_invalidates_auto_approval():
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    ae.set_killswitch_mode("AUTONOMY_ENABLED", "Testing")

    policy_engine = AutonomyPolicyEngine(ws)
    signer = PolicySigner(ws)
    disclosure_rev = DisclosureReviewer(ws)

    post = Post(
        post_id="post_auto_mutate",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Original Title",
        content_text="Original content text for verification.",
        media_assets=[make_test_media_asset()],
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="c++")]
    )
    scorecard = make_qualifying_scorecard()
    req = ae.create_approval_request(post, scorecard)
    cand = make_qualifying_candidate()
    disclosure = disclosure_rev.review_post(post)
    eval_res = policy_engine.evaluate(post, cand, scorecard, disclosure, recent_posts=[])

    token = signer.sign_auto_approval(post, req, eval_res)

    # Mutate post text
    post.content_text = "MUTATED content text after policy token was signed!"

    valid, reason = ae.verify_token_for_post(token, post)
    assert valid is False
    assert "E_PAYLOAD_MUTATED" in reason


def test_duplicate_dispatch_is_blocked():
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    ae.set_killswitch_mode("AUTONOMY_ENABLED", "Testing")

    dispatcher = PublisherDispatcher(ws, ae)

    tag = uuid.uuid4().hex[:8]
    post = Post(
        post_id=f"post_dispatch_{tag}",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title=f"Unique Dispatch Title {tag}",
        content_text=f"Content text for duplicate dispatch test {tag}.",
        media_assets=[make_test_media_asset()],
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="c++")]
    )
    scorecard = make_qualifying_scorecard()
    req = ae.create_approval_request(post, scorecard)
    cand = make_qualifying_candidate()
    disclosure = DisclosureReviewer(ws).review_post(post)
    eval_res = AutonomyPolicyEngine(ws).evaluate(post, cand, scorecard, disclosure, recent_posts=[])
    token = PolicySigner(ws).sign_auto_approval(post, req, eval_res)
    post.lifecycle_state = LifecycleState.AUTO_APPROVED

    # First dispatch passes in SHADOW_MODE
    res1 = dispatcher.dispatch(post, token, mode="SHADOW_MODE")
    assert res1.status == "SHADOW_SUCCESS"

    # Second dispatch with identical token must be BLOCKED as duplicate
    with pytest.raises(ValueError, match="E_DUPLICATE_DISPATCH"):
        dispatcher.dispatch(post, token, mode="SHADOW_MODE")


def test_killswitch_prevents_dispatch():
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    # Pause autonomy
    ae.set_killswitch_mode("AUTONOMY_PAUSED", "Paused for safety")

    dispatcher = PublisherDispatcher(ws, ae)

    tag = uuid.uuid4().hex[:8]
    post = Post(
        post_id=f"post_ks_{tag}",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title=f"Title {tag}",
        content_text=f"Unique text for killswitch dispatch test {tag}.",
        media_assets=[make_test_media_asset()],
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="c++")]
    )
    scorecard = make_qualifying_scorecard()
    req = ae.create_approval_request(post, scorecard)
    cand = make_qualifying_candidate()
    disclosure = DisclosureReviewer(ws).review_post(post)

    # Temporarily enable to sign
    ae.set_killswitch_mode("AUTONOMY_ENABLED", "signing")
    eval_res = AutonomyPolicyEngine(ws).evaluate(post, cand, scorecard, disclosure, recent_posts=[])
    token = PolicySigner(ws).sign_auto_approval(post, req, eval_res)
    post.lifecycle_state = LifecycleState.AUTO_APPROVED

    # Now pause autonomy
    ae.set_killswitch_mode("AUTONOMY_PAUSED", "Paused by operator")

    with pytest.raises(PermissionError, match="Autonomy is paused"):
        dispatcher.dispatch(post, token, mode="SHADOW_MODE")


def test_cooldown_and_weekly_ceiling():
    ws = Path(__file__).resolve().parent.parent
    pe = AutonomyPolicyEngine(ws)

    post = Post(
        post_id="post_rate_check",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Rate Test",
        content_text="Text",
        citations=[]
    )

    # Isolated empty backlog passes both cooldown and ceiling
    pass_cd, reason_cd = pe._check_cooldown_24h(post, recent_posts=[])
    assert pass_cd is True

    pass_wk, reason_wk = pe._check_weekly_ceiling(post, recent_posts=[])
    assert pass_wk is True

    # Cooldown fails when a post was scheduled within last 24h
    now = datetime.now(timezone.utc)
    recent_post = Post(
        post_id="post_recent",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Recent",
        content_text="Recent text",
        scheduled_publish_time=(now - timedelta(hours=6)).isoformat(),
        citations=[]
    )
    pass_cd_fail, reason_cd_fail = pe._check_cooldown_24h(post, recent_posts=[recent_post])
    assert pass_cd_fail is False
    assert "Cooldown violation" in reason_cd_fail

    # Weekly ceiling fails when 3 posts were scheduled within last 7d
    posts_7d = [
        Post(
            post_id=f"post_wk_{i}",
            pillar="pillar_ai_agent_architectures",
            author="Serhat",
            title=f"T{i}",
            content_text="C",
            scheduled_publish_time=(now - timedelta(days=i+1)).isoformat(),
            citations=[]
        )
        for i in range(3)
    ]
    pass_wk_fail, reason_wk_fail = pe._check_weekly_ceiling(post, recent_posts=posts_7d)
    assert pass_wk_fail is False
    assert "Weekly ceiling reached" in reason_wk_fail


def test_no_op_is_valid_when_backlog_empty():
    ws = Path(__file__).resolve().parent.parent
    from core.scheduler_engine import AgencyScheduler
    scheduler = AgencyScheduler(ws)
    briefing = scheduler.run_morning_intelligence()
    assert briefing["cycle"] == "MORNING_INTELLIGENCE"
    assert briefing["decision"] in ["NO_OP", "PIPELINE_READY"]


def test_universal_asset_rule_enforced_across_all_channels():
    """Verify text-only posts are held across LinkedIn, Instagram, and Twitter."""
    ws = Path(__file__).resolve().parent.parent
    pe = AutonomyPolicyEngine(ws)
    cand = make_qualifying_candidate()
    scorecard = make_qualifying_scorecard()

    text_only_post = Post(
        post_id="post_text_only_test",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Universal Asset Mandate Test",
        content_text="Post with zero media assets.",
        media_assets=[],
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="c++")]
    )
    disclosure = DisclosureReviewer(ws).review_post(text_only_post)

    for platform in ["linkedin", "instagram", "twitter"]:
        eval_res = pe.evaluate(text_only_post, cand, scorecard, disclosure, recent_posts=[], target_platform=platform)
        assert eval_res.decision in [AutonomyDecision.HOLD_FOR_ASSET, AutonomyDecision.REQUEST_ASSET_FROM_USER]
        assert any("Universal Asset Policy violation" in r or "strictly requires" in r for r in eval_res.reasons)


def test_anti_fake_evidence_rule_rejects_synthetic_benchmarks():
    """Verify AI-generated synthetic assets claiming to be empirical benchmarks are instantly REJECTED."""
    ws = Path(__file__).resolve().parent.parent
    pe = AutonomyPolicyEngine(ws)
    cand = make_qualifying_candidate()
    scorecard = make_qualifying_scorecard()

    fake_benchmark_asset = MediaAsset(
        asset_type="benchmark_chart",
        asset_path="assets/fake_chart.png",
        asset_sha256="1111111111111111111111111111111111111111111111111111111111111111",
        caption="Fake AI Benchmark",
        source_priority="AI_GENERATED_FALLBACK",
        archetype="benchmark_chart",
        is_synthetic=True,
        synthetic_purpose="benchmark_simulation"
    )

    post_with_fake = Post(
        post_id="post_fake_benchmark",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Benchmarking MediaCodec",
        content_text="Post claiming empirical benchmark from synthetic image.",
        media_assets=[fake_benchmark_asset],
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="c++")]
    )
    disclosure = DisclosureReviewer(ws).review_post(post_with_fake)
    eval_res = pe.evaluate(post_with_fake, cand, scorecard, disclosure, recent_posts=[], target_platform="linkedin")

    assert eval_res.decision == AutonomyDecision.REJECTED
    assert any("Anti-Fake Visual Rule violation" in r for r in eval_res.reasons)


def test_human_asset_request_generation():
    """Verify candidate requiring physical setup creates actionable HumanAssetRequest."""
    ws = Path(__file__).resolve().parent.parent
    from core.asset_planner import AssetPlanner
    planner = AssetPlanner(ws)

    hw_cand = Candidate(
        candidate_id="cand_usb_display_bench",
        idea_id="idea_usb",
        pillar="pillar_low_level_systems_and_graphics",
        target_audience=["Hardware Engineers"],
        angle="Dual-screen NVENC streaming demo",
        mvts_evaluation=MVTSEvaluation(
            grounding_score=3.0,
            technical_artifact_score=3.0,
            engineering_tradeoff_score=2.0,
            actionable_takeaway_score=1.5,
            total_score=9.5
        ),
        decision=CandidateDecision.PROCEED_TO_DRAFT
    )

    res = planner.evaluate_asset_availability(hw_cand, "instagram")
    assert res["status"] == "HOLD_FOR_ASSET"
    assert res["human_request_needed"] is True
    assert "human_asset_request" in res

    req = res["human_asset_request"]
    assert req.candidate_id == "cand_usb_display_bench"
    assert "Lenovo tablet" in req.specific_instructions
    assert len(req.recommended_shots) > 0


def test_human_asset_multiplatform_deduplication_and_cascading_fulfillment(tmp_path):
    """Verify that multi-platform evaluations share a single request and one upload unlocks all platforms."""
    ws = Path(__file__).resolve().parent.parent
    from core.asset_planner import AssetPlanner
    planner = AssetPlanner(ws)

    cand_id = "cand_test_dedup_flow"
    # Ensure clean state
    for p in planner.requests_dir.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("candidate_id") == cand_id:
                p.unlink()
        except Exception:
            pass

    cand = Candidate(
        candidate_id=cand_id,
        idea_id="idea_3dprinter_firmware",
        pillar="pillar_hardware_and_mechatronics",
        target_audience=["Firmware Engineers"],
        angle="Distributed 3-MCU board assembly with TMC2209",
        mvts_evaluation=MVTSEvaluation(
            grounding_score=3.0,
            technical_artifact_score=3.0,
            engineering_tradeoff_score=2.0,
            actionable_takeaway_score=1.5,
            total_score=9.5
        ),
        decision=CandidateDecision.PROCEED_TO_DRAFT
    )

    # 1. Evaluate for Instagram -> creates unified request
    res_ig = planner.evaluate_asset_availability(cand, "instagram")
    assert res_ig["status"] == "HOLD_FOR_ASSET"
    req_ig = res_ig["human_asset_request"]
    assert req_ig.candidate_id == cand_id
    assert "instagram" in req_ig.target_platforms

    # 2. Evaluate for Twitter -> reuses existing request, appends twitter
    res_tw = planner.evaluate_asset_availability(cand, "twitter")
    assert res_tw["status"] == "HOLD_FOR_ASSET"
    req_tw = res_tw["human_asset_request"]
    assert req_tw.request_id == req_ig.request_id
    assert "instagram" in req_tw.target_platforms
    assert "twitter" in req_tw.target_platforms

    # 3. Evaluate for LinkedIn -> reuses existing request, appends linkedin
    res_li = planner.evaluate_asset_availability(cand, "linkedin")
    assert res_li["status"] == "HOLD_FOR_ASSET"
    req_li = res_li["human_asset_request"]
    assert req_li.request_id == req_ig.request_id
    assert "linkedin" in req_li.target_platforms

    # Verify only ONE request file exists on disk for this candidate
    matching_files = [p for p in planner.requests_dir.glob("*.json") if json.loads(p.read_text(encoding="utf-8")).get("candidate_id") == cand_id]
    assert len(matching_files) == 1

    # 4. Fulfill request ONCE with a test image
    test_img = tmp_path / "workbench_test.png"
    test_img.write_bytes(b"TEST_WORKBENCH_IMAGE_BYTES_12345")
    fulfilled_req = planner.fulfill_request(req_ig.request_id, test_img)
    assert fulfilled_req.status == "FULFILLED"

    # 5. Re-evaluating ANY platform now returns ASSET_READY without asking again!
    res_ig_after = planner.evaluate_asset_availability(cand, "instagram")
    assert res_ig_after["status"] == "ASSET_READY"
    assert res_ig_after["human_request_needed"] is False

    res_tw_after = planner.evaluate_asset_availability(cand, "twitter")
    assert res_tw_after["status"] == "ASSET_READY"
    assert res_tw_after["human_request_needed"] is False

    res_li_after = planner.evaluate_asset_availability(cand, "linkedin")
    assert res_li_after["status"] == "ASSET_READY"
    assert res_li_after["human_request_needed"] is False

    # Cleanup test files
    for p in matching_files:
        if p.exists():
            p.unlink()
    user_sub = ws / "assets" / "user_submissions" / f"{cand_id}_{test_img.name}"
    if user_sub.exists():
        user_sub.unlink()

