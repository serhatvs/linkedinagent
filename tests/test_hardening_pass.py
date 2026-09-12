import json
import uuid
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from core.models import (
    Post,
    Candidate,
    CandidateDecision,
    MVTSEvaluation,
    LifecycleState,
    Citation,
    MediaAsset,
    ApprovalToken,
    ActionScope,
    AutonomyDecision,
    DisclosureRisk,
    EditorialScorecard,
    EditorialVerdict,
    Scores,
    SlopAnalysis,
    DomainDRCChecks,
    GroundingVerification
)
from core.lifecycle_manager import LifecycleManager
from core.approval_engine import ApprovalEngine, resolve_signing_secret, compute_canonical_payload_sha256
from core.autonomy_policy_engine import AutonomyPolicyEngine, AUTONOMY_POLICY_VERSION
from core.policy_signer import PolicySigner, compute_evaluation_hash
from core.publisher_dispatcher import PublisherDispatcher
from core.scheduler_engine import AgencyScheduler
from core.editorial_evaluator import EditorialEvaluator
from core.disclosure_reviewer import DisclosureReviewer
from core.mcp_gateways import MetricoolGateway

@pytest.fixture(autouse=True)
def reset_agency_state():
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    yield
    ae.set_killswitch_mode("AUTONOMY_PAUSED", "Restored after test")


def make_test_scorecard(composite: float = 94.0, slop: float = 0.0, drc: bool = True, grounding: float = 100.0) -> EditorialScorecard:
    return EditorialScorecard(
        evaluation_id="eval_test",
        post_id="post_test",
        scores=Scores(
            technical_rigor=24.0,
            clarity_and_flow=23.0,
            visual_utility=24.0,
            reader_roi=23.0,
            composite_score=composite
        ),
        slop_analysis=SlopAnalysis(
            detected_buzzwords=[],
            emoji_count=0,
            slop_score=slop,
            slop_detected=slop > 0
        ),
        domain_drc_checks=DomainDRCChecks(
            passed=drc,
            checks_run=["domain_test"],
            violations=[] if drc else ["Test DRC violation"]
        ),
        grounding_verification=GroundingVerification(
            grounding_percentage=grounding,
            unverified_claims=[],
            cited_sources=["source_1", "source_2"]
        ),
        verdict=EditorialVerdict.PASSED_EDITORIAL if drc and slop == 0 and composite >= 90.0 else EditorialVerdict.REJECTED_SLOP_OR_DRC
    )


def make_test_media_asset() -> MediaAsset:
    return MediaAsset(
        asset_type="architecture_diagram",
        asset_path="assets/diagram.png",
        asset_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        caption="Architecture Diagram",
        source_priority="DETERMINISTIC_COMPOSED_ASSET",
        archetype="architecture_diagram"
    )


def test_terminal_rejected_candidates_never_auto_approve_or_require_human_approval():
    ws = Path(__file__).resolve().parent.parent
    policy_engine = AutonomyPolicyEngine(ws)
    disclosure_rev = DisclosureReviewer(ws)

    cand_rejected = Candidate(
        candidate_id="cand_rejected_01",
        idea_id="idea_rej_01",
        pillar="pillar_low_level_systems_and_graphics",
        target_audience=["General"],
        angle="Opinion",
        mvts_evaluation=MVTSEvaluation(grounding_score=1.0, technical_artifact_score=1.0, engineering_tradeoff_score=0.1, actionable_takeaway_score=0.0, total_score=2.1),
        decision=CandidateDecision.REJECT
    )

    post = Post(
        post_id="post_rejected_01",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Why C++ is better than Python",
        content_text="Pure opinion without code.",
        media_assets=[make_test_media_asset()],
        citations=[Citation(claim_text="skill", source_type="knowledge_fact", reference_id="c++")]
    )

    scorecard = make_test_scorecard(composite=65.0, slop=2.0, drc=False)
    disclosure = disclosure_rev.review_post(post)

    eval_res = policy_engine.evaluate(post, cand_rejected, scorecard, disclosure, recent_posts=[])
    assert eval_res.decision == AutonomyDecision.REJECTED
    assert eval_res.decision != AutonomyDecision.REQUIRE_HUMAN_APPROVAL
    assert eval_res.decision != AutonomyDecision.AUTO_APPROVE
    assert any("Candidate is in terminal REJECTED state" in r for r in eval_res.reasons)


def test_below_threshold_mvts_becomes_hold_quality_not_human_approval():
    ws = Path(__file__).resolve().parent.parent
    policy_engine = AutonomyPolicyEngine(ws)
    disclosure_rev = DisclosureReviewer(ws)

    cand_held = Candidate(
        candidate_id="cand_hardware_01",
        idea_id="idea_hw_01",
        pillar="pillar_distributed_embedded_hardware",
        target_audience=["Embedded Engineers"],
        angle="Trade-off",
        mvts_evaluation=MVTSEvaluation(grounding_score=2.6, technical_artifact_score=2.6, engineering_tradeoff_score=1.8, actionable_takeaway_score=1.8, total_score=8.8),
        decision=CandidateDecision.HOLD_QUALITY
    )

    post = Post(
        post_id="post_hardware_01",
        pillar="pillar_distributed_embedded_hardware",
        author="Serhat",
        title="Arduino Mega as a 24V auxiliary I/O co-processor",
        content_text="Why include an Arduino Mega 2560 alongside high-speed ESP32-S3s? Because the Mega has 54 digital pins, 5V logic tolerances, and handles slow ADC sampling.",
        media_assets=[make_test_media_asset()],
        citations=[Citation(claim_text="Firmware", source_type="project_registry", reference_id="proj_3dprinter_firmware")]
    )

    scorecard = make_test_scorecard(composite=94.0)
    disclosure = disclosure_rev.review_post(post)

    eval_res = policy_engine.evaluate(post, cand_held, scorecard, disclosure, recent_posts=[])
    assert eval_res.decision == AutonomyDecision.HOLD_QUALITY
    assert eval_res.decision != AutonomyDecision.REQUIRE_HUMAN_APPROVAL
    assert eval_res.decision != AutonomyDecision.AUTO_APPROVE
    assert any("below autonomous threshold (9.0)" in r for r in eval_res.reasons)


def test_revive_candidate_creates_valid_new_revision():
    ws = Path(__file__).resolve().parent.parent
    now_iso = datetime.now(timezone.utc).isoformat()

    revived = Candidate(
        candidate_id="cand_rejected_01_rev1",
        idea_id="idea_rejected_01",
        pillar="pillar_low_level_systems_and_graphics",
        target_audience=["Systems Engineers"],
        angle="Technical Analysis",
        mvts_evaluation=MVTSEvaluation(grounding_score=3.0, technical_artifact_score=3.0, engineering_tradeoff_score=2.0, actionable_takeaway_score=2.0, total_score=9.5),
        decision=CandidateDecision.PROCEED_TO_DRAFT,
        parent_candidate_id="cand_rejected_01",
        revival_reason="Refocused with rigorous x86-64 calling convention disassembly and benchmark setup.",
        revived_by="Serhat",
        revived_at=now_iso
    )

    assert revived.parent_candidate_id == "cand_rejected_01"
    assert revived.revival_reason is not None
    assert revived.decision == CandidateDecision.PROCEED_TO_DRAFT

    post = Post(
        post_id="post_rejected_01_rev1",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Assembly calling conventions: Why C++ outperforms Python ctypes",
        content_text="Detailed register allocation and frame pointer benchmark analysis.",
        media_assets=[make_test_media_asset()],
        citations=[Citation(claim_text="skill", source_type="knowledge_fact", reference_id="c++")]
    )
    scorecard = make_test_scorecard(composite=94.0)
    disclosure = DisclosureReviewer(ws).review_post(post)
    eval_res = AutonomyPolicyEngine(ws).evaluate(post, revived, scorecard, disclosure, recent_posts=[])
    assert eval_res.decision == AutonomyDecision.AUTO_APPROVE


def test_override_hold_routes_to_human_approval_queue():
    ws = Path(__file__).resolve().parent.parent
    policy_engine = AutonomyPolicyEngine(ws)
    disclosure_rev = DisclosureReviewer(ws)

    cand_overridden = Candidate(
        candidate_id="cand_chronos_01",
        idea_id="idea_chronos_01",
        pillar="pillar_local_infra_and_tooling",
        target_audience=["Developers"],
        angle="Teardown",
        mvts_evaluation=MVTSEvaluation(grounding_score=2.6, technical_artifact_score=2.6, engineering_tradeoff_score=1.7, actionable_takeaway_score=1.8, total_score=8.7),
        decision=CandidateDecision.PROCEED_TO_DRAFT,
        override_reason="Strategic importance for establishing local RAG architecture authority.",
        overridden_by="Serhat",
        overridden_at=datetime.now(timezone.utc).isoformat()
    )

    post = Post(
        post_id="post_chronos_01",
        pillar="pillar_local_infra_and_tooling",
        author="Serhat",
        title="Zero-budget RAG: Deterministic heading-aware Markdown chunking",
        content_text="Most RAG tutorials split documents into fixed 500-token chunks with 50-token overlap.",
        media_assets=[make_test_media_asset()],
        citations=[Citation(claim_text="skill", source_type="knowledge_fact", reference_id="python")]
    )

    scorecard = make_test_scorecard(composite=92.0)
    disclosure = disclosure_rev.review_post(post)

    eval_res = policy_engine.evaluate(post, cand_overridden, scorecard, disclosure, recent_posts=[])
    assert eval_res.decision == AutonomyDecision.REQUIRE_HUMAN_APPROVAL
    assert any("Deliberate manual override active" in r for r in eval_res.reasons)


def test_domain_drc_scope_passes_architectural_claims():
    ws = Path(__file__).resolve().parent.parent
    evaluator = EditorialEvaluator(ws)

    safe_post = Post(
        post_id="post_arch_safe",
        pillar="pillar_distributed_embedded_hardware",
        author="Serhat",
        title="Distributed MCUs: ESP32-S3 and Arduino Mega",
        content_text="The system uses an ESP32-S3 for motion control and an Arduino Mega for 5V auxiliary heaters and thermistor sampling over isolated UART.",
        citations=[]
    )
    drc_safe = evaluator.run_domain_drc(safe_post)
    assert drc_safe.passed is True

    unsafe_post = Post(
        post_id="post_arch_unsafe",
        pillar="pillar_distributed_embedded_hardware",
        author="Serhat",
        title="Direct connection without shifters",
        content_text="We connected 5V directly to ESP32 GPIO pins without level shifters or isolation.",
        citations=[]
    )
    drc_unsafe = evaluator.run_domain_drc(unsafe_post)
    assert drc_unsafe.passed is False
    assert any("level shift" in v.lower() for v in drc_unsafe.violations)


def test_auto_approval_ttl_and_expiration():
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    ae.set_killswitch_mode("AUTONOMY_ENABLED", "Testing TTL")
    signer = PolicySigner(ws)

    post = Post(
        post_id="post_ttl_test",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="TTL Test Title",
        content_text="Testing TTL enforcement on auto approval tokens.",
        media_assets=[make_test_media_asset()],
        citations=[Citation(claim_text="skill", source_type="knowledge_fact", reference_id="c++")]
    )
    scorecard = make_test_scorecard(composite=95.0)
    req = ae.create_approval_request(post, scorecard)
    cand = Candidate(
        candidate_id="cand_ttl_test",
        idea_id="idea_ttl",
        pillar="pillar_low_level_systems_and_graphics",
        target_audience=["Engineers"],
        angle="Test",
        mvts_evaluation=MVTSEvaluation(grounding_score=3.0, technical_artifact_score=3.0, engineering_tradeoff_score=2.0, actionable_takeaway_score=2.0, total_score=10.0),
        decision=CandidateDecision.PROCEED_TO_DRAFT
    )
    disclosure = DisclosureReviewer(ws).review_post(post)
    eval_res = AutonomyPolicyEngine(ws).evaluate(post, cand, scorecard, disclosure, recent_posts=[])

    token = signer.sign_auto_approval(post, req, eval_res, ttl_hours=200)
    assert token.ttl_hours == 168

    token_short = signer.sign_auto_approval(post, req, eval_res, ttl_hours=48)
    assert token_short.ttl_hours == 48


def test_expired_approval_returns_post_to_revalidation_required():
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    lm = LifecycleManager(ws)
    ae.set_killswitch_mode("AUTONOMY_ENABLED", "Testing expiration")
    dispatcher = PublisherDispatcher(ws, ae)

    tag = uuid.uuid4().hex[:8]
    test_asset = make_test_media_asset()
    post = Post(
        post_id=f"post_expired_{tag}",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title=f"Expired Post Test {tag}",
        content_text=f"Content for expired post test {tag}.",
        media_assets=[test_asset],
        citations=[Citation(claim_text="skill", source_type="knowledge_fact", reference_id="c++")]
    )
    lm.save_post_in_place(post)
    post = lm.transition(post.post_id, LifecycleState.DRAFT, post.state_version)
    post = lm.transition(post.post_id, LifecycleState.REVIEWED, post.state_version)
    post = lm.transition(post.post_id, LifecycleState.AUTO_APPROVED, post.state_version)

    past_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    sig_key = resolve_signing_secret()
    nonce = uuid.uuid4().hex
    canonical_hash = compute_canonical_payload_sha256(
        post_id=post.post_id,
        action_scope=ActionScope.METRICOOL_SCHEDULE.value,
        target_platform="linkedin",
        content_text=post.content_text,
        media_asset_hashes=[test_asset.asset_sha256]
    )
    sig_msg = f"{canonical_hash}:req_exp:{nonce}:PolicySigner".encode('utf-8')
    sig_digest = hmac.new(sig_key, sig_msg, hashlib.sha256).hexdigest()

    expired_token = ApprovalToken(
        token_id="token_expired_999",
        request_id="req_exp",
        post_id=post.post_id,
        approved_by="PolicySigner",
        approval_type="AUTO_APPROVAL",
        autonomy_policy_version=AUTONOMY_POLICY_VERSION,
        signed_at=(datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
        expires_at=past_iso,
        ttl_hours=168,
        nonce=nonce,
        action_scope=ActionScope.METRICOOL_SCHEDULE,
        target_platform="linkedin",
        canonical_payload_sha256=canonical_hash,
        signature_digest=sig_digest
    )

    with pytest.raises(PermissionError, match="E_APPROVAL_EXPIRED"):
        dispatcher.dispatch(post, expired_token, mode="SHADOW_MODE")

    updated_post = lm.get_post(post.post_id)
    assert updated_post.lifecycle_state == LifecycleState.REVALIDATION_REQUIRED


def test_scheduling_horizon_enforces_7_day_window_and_max_3_posts():
    ws = Path(__file__).resolve().parent.parent
    scheduler = AgencyScheduler(ws)

    now = datetime.now(timezone.utc)
    simulated_posts = [
        Post(post_id="post_p1", pillar="pillar_low_level_systems_and_graphics", author="Serhat", title="T1", content_text="C1", scheduled_publish_time=(now + timedelta(days=1)).isoformat()),
        Post(post_id="post_p2", pillar="pillar_low_level_systems_and_graphics", author="Serhat", title="T2", content_text="C2", scheduled_publish_time=(now + timedelta(days=3)).isoformat()),
        Post(post_id="post_p3", pillar="pillar_low_level_systems_and_graphics", author="Serhat", title="T3", content_text="C3", scheduled_publish_time=(now + timedelta(days=5)).isoformat()),
    ]

    new_post = Post(post_id="post_p4", pillar="pillar_low_level_systems_and_graphics", author="Serhat", title="T4", content_text="C4")
    sched_time, rationale, within_horizon = scheduler.calculate_best_publication_time(new_post, existing_posts=simulated_posts)

    assert within_horizon is False
    assert sched_time is None
    assert "Scheduling horizon saturated" in rationale


def test_policysigner_rejects_altered_evaluation_hash_and_predicates():
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    ae.set_killswitch_mode("AUTONOMY_ENABLED", "Testing policy signer integrity")
    signer = PolicySigner(ws)

    post = Post(
        post_id="post_tamper_test",
        pillar="pillar_low_level_systems_and_graphics",
        author="Serhat",
        title="Tamper Test",
        content_text="Integrity verification content.",
        media_assets=[make_test_media_asset()],
        citations=[Citation(claim_text="skill", source_type="knowledge_fact", reference_id="c++")]
    )
    scorecard = make_test_scorecard(composite=95.0)
    req = ae.create_approval_request(post, scorecard)
    cand = Candidate(
        candidate_id="cand_tamper_test",
        idea_id="idea_tamper",
        pillar="pillar_low_level_systems_and_graphics",
        target_audience=["Engineers"],
        angle="Test",
        mvts_evaluation=MVTSEvaluation(grounding_score=3.0, technical_artifact_score=3.0, engineering_tradeoff_score=2.0, actionable_takeaway_score=2.0, total_score=9.5),
        decision=CandidateDecision.PROCEED_TO_DRAFT
    )
    disclosure = DisclosureReviewer(ws).review_post(post)
    eval_res = AutonomyPolicyEngine(ws).evaluate(post, cand, scorecard, disclosure, recent_posts=[])

    eval_res.editorial_score = 85.0
    with pytest.raises(PermissionError, match="below 90.0 threshold"):
        signer.sign_auto_approval(post, req, eval_res)

    eval_res.editorial_score = 95.0
    eval_res.evaluation_hash = "f" * 64
    with pytest.raises(PermissionError, match="Evaluation hash mismatch"):
        signer.sign_auto_approval(post, req, eval_res)


def test_secret_storage_isolated_from_git_and_repo():
    secret = resolve_signing_secret()
    assert isinstance(secret, bytes)
    assert len(secret) >= 32

    ws = Path(__file__).resolve().parent.parent
    py_files = list((ws / "core").glob("*.py"))
    for pyf in py_files:
        content = pyf.read_text(encoding="utf-8")
        assert "DEFAULT_SIGNING_KEY = b\"" not in content


def test_metricool_unauthenticated_returns_blocked_metricool_auth():
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    mg = MetricoolGateway(ae)

    cap = mg.verify_authenticated_capability()
    assert cap["status"] == "BLOCKED_METRICOOL_AUTH"
    assert cap["authenticated"] is False
    assert cap["blocker_code"] == "BLOCKED_METRICOOL_AUTH"
    assert cap["schedule_post_available"] is True
