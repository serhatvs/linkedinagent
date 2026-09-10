"""End-to-end dry run scenario validating the entire agency lifecycle workflow."""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from core.models import (
    Idea, Candidate, CandidateDecision, MVTSEvaluation,
    Post, LifecycleState, MediaAsset, Citation, ActionScope, EditorialVerdict,
    AnalyticsReport
)
from core.lifecycle_manager import LifecycleManager
from core.grounding_engine import GroundingEngine
from core.editorial_evaluator import EditorialEvaluator
from core.approval_engine import ApprovalEngine
from core.mcp_gateways import GitHubGateway, MetricoolGateway


def test_end_to_end_agency_dry_run():
    ws = Path(__file__).resolve().parent.parent
    lm = LifecycleManager(ws)
    ge = GroundingEngine(ws)
    ee = EditorialEvaluator(ge)
    ae = ApprovalEngine(ws)
    gh = GitHubGateway()
    mg = MetricoolGateway(ae, dry_run=True)

    # -------------------------------------------------------------
    # STAGE 1: IDEA (Scouted from GitHub Commit Intelligence)
    # -------------------------------------------------------------
    commits = gh.fetch_recent_commits("serhat/stm32h7-tinyml-tracker")
    assert len(commits) > 0
    top_commit = commits[0]

    idea_id = "idea_e2e_stm32_dma"
    idea = Idea(
        idea_id=idea_id,
        source_type="github_commit",
        title="Optimizing DMA buffer contention on STM32H7",
        raw_notes=f"Observed 24% lower bus contention by partitioning SRAM banks during inference: {top_commit['message']}",
        pillar_affinity="pillar_embedded_firmware",
        project_id="proj_tinyml_edge_vision",
        technical_artifacts_available=["logic_analyzer_trace", "code_diff"]
    )
    lm.save_idea(idea)
    assert (ws / "lifecycle" / "01_ideas" / f"{idea_id}.json").exists()

    # -------------------------------------------------------------
    # STAGE 2: CANDIDATE (Strategist MVTS Evaluation)
    # -------------------------------------------------------------
    mvts = MVTSEvaluation(
        grounding_score=3.0,
        technical_artifact_score=3.0,
        engineering_tradeoff_score=2.0,
        actionable_takeaway_score=1.8,
        total_score=9.8
    )
    assert mvts.total_score >= 8.0

    cand_id = "cand_e2e_stm32_dma"
    candidate = Candidate(
        candidate_id=cand_id,
        idea_id=idea.idea_id,
        pillar=idea.pillar_affinity,
        target_audience=["Embedded Systems Engineers", "Firmware Architects"],
        angle="Memory Bus Matrix Architecture",
        mvts_evaluation=mvts,
        decision=CandidateDecision.PROCEED_TO_DRAFT
    )
    lm.save_candidate(candidate)
    assert (ws / "lifecycle" / "02_candidates" / f"{cand_id}.json").exists()

    # -------------------------------------------------------------
    # STAGE 3: DRAFT (Writer produces grounded technical post)
    # -------------------------------------------------------------
    post_id = "post_e2e_stm32_dma"
    post_body = (
        "While running INT8 MobileNetV2 on an STM32H743ZI at 480 MHz, we hit an unexpected 28ms frame drop.\n\n"
        "The DCMI camera interface and the SPI display driver were competing for the same AXI SRAM bank, stalling the Cortex-M7 core on bus arbitration.\n\n"
        "Here is the architectural pattern that resolved it:\n"
        "1. Relocated camera DMA rx buffers to SRAM1 (D2 domain).\n"
        "2. Kept the model tensor arena in AXI SRAM (D1 domain).\n"
        "3. Configured ping-pong double buffering with circular DMA interrupts.\n\n"
        "Result: Memory bus contention dropped by 24%, restoring a sustained 20 FPS inference pipeline without frame jitter.\n\n"
        "When designing high-throughput vision on Cortex-M7, never treat internal RAM as a homogeneous pool. Domain bus matrix boundaries matter."
    )

    post = Post(
        post_id=post_id,
        pillar="pillar_embedded_firmware",
        author="Serhat",
        title="Fixing STM32H7 DMA Bus Contention Under 20 FPS Edge Vision",
        content_text=post_body,
        media_assets=[
            MediaAsset(
                asset_type="logic_trace",
                asset_path="assets/stm32h7_dma_trace.png",
                asset_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                caption="Saleae Logic Pro 16 capture showing SPI display vs DCMI DMA bus arbitration."
            )
        ],
        citations=[
            Citation(
                claim_text="STM32H743ZI edge vision tracker",
                source_type="project_registry",
                reference_id="proj_tinyml_edge_vision"
            ),
            Citation(
                claim_text="STM32 Cortex-M7 hardware development",
                source_type="knowledge_fact",
                reference_id="stm32 (arm cortex-m4/m7)"
            )
        ]
    )
    lm.create_initial_draft(post)
    assert (ws / "lifecycle" / "03_drafts" / f"{post_id}.json").exists()

    # -------------------------------------------------------------
    # STAGE 4: REVIEWED (Editorial Review & Domain DRC)
    # -------------------------------------------------------------
    scorecard = ee.evaluate_post(post)
    assert scorecard.verdict == EditorialVerdict.PASSED_EDITORIAL
    assert scorecard.slop_analysis.slop_detected is False
    assert scorecard.domain_drc_checks.passed is True
    assert scorecard.grounding_verification.grounding_percentage == 100.0

    post.scorecard_id = scorecard.evaluation_id
    lm.save_post_in_place(post)  # metadata-only: attach scorecard ID
    post = lm.transition(post.post_id, LifecycleState.REVIEWED, expected_version=post.state_version)
    assert (ws / "lifecycle" / "04_reviewed" / f"{post_id}.json").exists()

    # -------------------------------------------------------------
    # STAGE 5: AWAITING_APPROVAL (Approval Gate Packaging)
    # -------------------------------------------------------------
    sched_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    appr_req = ae.create_approval_request(
        post=post,
        scorecard=scorecard,
        action_scope=ActionScope.METRICOOL_SCHEDULE,
        proposed_schedule_time=sched_time
    )
    assert appr_req.canonical_payload_sha256 is not None
    post.approval_request_id = appr_req.request_id
    lm.save_post_in_place(post)  # metadata-only: attach approval request ID
    post = lm.transition(post.post_id, LifecycleState.AWAITING_APPROVAL, expected_version=post.state_version)
    assert (ws / "lifecycle" / "05_awaiting_approval" / f"{post_id}.json").exists()
    assert (ws / "approvals" / "pending" / f"{appr_req.request_id}.json").exists()

    # -------------------------------------------------------------
    # STAGE 6: APPROVED (Serhat Human Sign-Off)
    # -------------------------------------------------------------
    token = ae.sign_approval_request(request_id=appr_req.request_id, signer="Serhat")
    assert token.approved_by == "Serhat"
    assert (ws / "approvals" / "signed" / f"{appr_req.request_id}.approved.json").exists()

    post = lm.transition(post.post_id, LifecycleState.APPROVED, expected_version=post.state_version)
    assert (ws / "lifecycle" / "06_approved" / f"{post_id}.json").exists()

    # -------------------------------------------------------------
    # STAGE 7: SCHEDULED (Metricool MCP Dry-Run Dispatch)
    # -------------------------------------------------------------
    dispatch_res = mg.schedule_post(post, token, sched_time)
    assert dispatch_res["status"] == "SUCCESS"
    assert dispatch_res["mode"] == "DRY_RUN"

    post.metricool_post_id = dispatch_res["metricool_post_id"]
    post.scheduled_publish_time = sched_time
    lm.save_post_in_place(post)  # metadata-only: attach metricool scheduling info
    post = lm.transition(post.post_id, LifecycleState.SCHEDULED, expected_version=post.state_version)
    assert (ws / "lifecycle" / "07_scheduled" / f"{post_id}.json").exists()

    # -------------------------------------------------------------
    # STAGE 8: PUBLISHED (Simulated Live Confirmation)
    # -------------------------------------------------------------
    post.linkedin_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{dispatch_res['metricool_post_id']}/"
    lm.save_post_in_place(post)  # metadata-only: attach linkedin URL
    post = lm.transition(post.post_id, LifecycleState.PUBLISHED, expected_version=post.state_version)
    assert (ws / "lifecycle" / "08_published" / f"{post_id}.json").exists()

    # -------------------------------------------------------------
    # STAGE 9: ANALYZED (Analytics Ingestion & Closed-Loop Learning)
    # -------------------------------------------------------------
    analytics = mg.fetch_post_analytics(post.metricool_post_id)
    assert analytics["impressions"] > 0
    assert analytics["profile_visits"] > 0

    # Calculate quality engagement ratio
    quality_ratio = round(((analytics["comments"] + analytics["shares"]) / analytics["impressions"]) * 100.0, 2)
    assert quality_ratio > 0

    report = AnalyticsReport(
        report_id=f"rep_{post.post_id}",
        period_start=datetime.now(timezone.utc).isoformat(),
        period_end=datetime.now(timezone.utc).isoformat(),
        total_posts_published=1,
        total_impressions=analytics["impressions"],
        quality_engagement_ratio=quality_ratio,
        inbound_technical_leads=analytics["inbound_messages"],
        top_performing_pillar=post.pillar,
        key_learnings=[
            "DMA memory domain partitioning posts generate outsized engagement from staff firmware engineers."
        ]
    )

    report_file = ws / "analytics" / "reports" / f"{report.report_id}.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))

    post = lm.transition(post.post_id, LifecycleState.ANALYZED, expected_version=post.state_version)
    assert (ws / "lifecycle" / "09_analyzed" / f"{post_id}.json").exists()
    assert report_file.exists()
