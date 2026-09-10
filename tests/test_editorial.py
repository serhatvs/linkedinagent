"""Tests for editorial review, slop detection, and domain Design Rule Checks (DRC)."""

from pathlib import Path
from core.models import Post, Citation, MediaAsset, EditorialVerdict
from core.grounding_engine import GroundingEngine
from core.editorial_evaluator import EditorialEvaluator


def test_slop_buzzword_triggers_rejection():
    ws = Path(__file__).resolve().parent.parent
    ge = GroundingEngine(ws)
    ee = EditorialEvaluator(ge)

    post = Post(
        post_id="post_slop_sample",
        pillar="pillar_ai_agents",
        author="Serhat",
        title="AI Breakthrough",
        content_text="I'm thrilled to announce a revolutionary game-changer in AI agent orchestration! Agree?",
        citations=[
            Citation(
                claim_text="AI agents",
                source_type="project_registry",
                reference_id="proj_antigravity_agency"
            )
        ]
    )

    card = ee.evaluate_post(post)
    assert card.slop_analysis.slop_detected is True
    assert card.slop_analysis.slop_score > 0
    assert card.verdict == EditorialVerdict.REJECTED_SLOP_OR_DRC


def test_decorative_emoji_bullet_points_rejected():
    ws = Path(__file__).resolve().parent.parent
    ge = GroundingEngine(ws)
    ee = EditorialEvaluator(ge)

    post = Post(
        post_id="post_emoji_slop",
        pillar="pillar_ai_agents",
        author="Serhat",
        title="Agent Architecture",
        content_text="Here is our stack:\n🚀 Antigravity engine\n💡 Deterministic guards\n🔥 Fast execution",
        citations=[
            Citation(
                claim_text="AI agents",
                source_type="project_registry",
                reference_id="proj_antigravity_agency"
            )
        ]
    )

    card = ee.evaluate_post(post)
    assert card.slop_analysis.slop_detected is True
    assert card.verdict == EditorialVerdict.REJECTED_SLOP_OR_DRC


def test_mains_ac_without_isolation_violates_drc():
    ws = Path(__file__).resolve().parent.parent
    ge = GroundingEngine(ws)
    ee = EditorialEvaluator(ge)

    post = Post(
        post_id="post_mains_hazard",
        pillar="pillar_embedded_firmware",
        author="Serhat",
        title="Direct Mains AC Dimmer Circuit",
        content_text="I hooked up a 220V mains AC circuit directly to my bench breadboard with a triac switch to dim our lab lights.",
        citations=[
            Citation(
                claim_text="Embedded skills",
                source_type="knowledge_fact",
                reference_id="c++17/20"
            )
        ]
    )

    card = ee.evaluate_post(post)
    assert card.domain_drc_checks.passed is False
    assert any("galvanic isolation" in v for v in card.domain_drc_checks.violations)
    assert card.verdict == EditorialVerdict.REJECTED_SLOP_OR_DRC


def test_clean_technical_post_passes():
    ws = Path(__file__).resolve().parent.parent
    ge = GroundingEngine(ws)
    ee = EditorialEvaluator(ge)

    post_text = (
        "While testing INT8 MobileNetV2 on an STM32H743ZI at 480 MHz, we hit an unexpected 28ms frame drop.\n\n"
        "The DCMI camera interface and the SPI display driver were competing for the same AXI SRAM bank, stalling the Cortex-M7 core on bus arbitration.\n\n"
        "Here is the architectural pattern that resolved it:\n"
        "1. Relocated camera DMA rx buffers to SRAM1 (D2 domain).\n"
        "2. Kept the model tensor arena in AXI SRAM (D1 domain).\n"
        "3. Configured ping-pong double buffering with circular DMA interrupts.\n\n"
        "Result: Memory bus contention dropped by 24%, restoring a sustained 20 FPS inference pipeline without frame jitter.\n\n"
        "When designing high-throughput vision on Cortex-M7, never treat internal RAM as a homogeneous pool. Domain bus matrix boundaries matter."
    )

    post = Post(
        post_id="post_clean_firmware",
        pillar="pillar_embedded_firmware",
        author="Serhat",
        title="Fixing STM32H7 DMA Bus Contention Under 20 FPS Edge Vision",
        content_text=post_text,
        media_assets=[
            MediaAsset(
                asset_type="logic_trace",
                asset_path="assets/stm32h7_dma_trace.png",
                asset_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                caption="Saleae Logic Pro 16 capture"
            )
        ],
        citations=[
            Citation(
                claim_text="STM32H743ZI edge vision tracker",
                source_type="project_registry",
                reference_id="proj_tinyml_edge_vision"
            ),
            Citation(
                claim_text="STM32 ARM Cortex-M7 hardware",
                source_type="knowledge_fact",
                reference_id="stm32 (arm cortex-m4/m7)"
            )
        ]
    )

    card = ee.evaluate_post(post)
    assert card.slop_analysis.slop_detected is False
    assert card.domain_drc_checks.passed is True
    assert card.grounding_verification.grounding_percentage == 100.0
    assert card.scores.composite_score >= 85.0
    assert card.verdict == EditorialVerdict.PASSED_EDITORIAL
