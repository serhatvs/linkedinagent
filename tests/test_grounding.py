"""Tests verifying strict technical grounding and fact-checking."""

from pathlib import Path
from core.models import Post, Citation, MediaAsset
from core.grounding_engine import GroundingEngine


def test_grounded_post_passes():
    ws = Path(__file__).resolve().parent.parent
    ge = GroundingEngine(ws)

    post = Post(
        post_id="post_grounded_sample",
        pillar="pillar_embedded_firmware",
        author="Serhat",
        title="STM32H7 DMA ping-pong buffers",
        content_text="We reduced bus contention by 24% on the STM32H743ZI running INT8 MobileNetV2 with FreeRTOS.",
        citations=[
            Citation(
                claim_text="STM32H743ZI TinyML edge vision tracker",
                source_type="project_registry",
                reference_id="proj_tinyml_edge_vision"
            ),
            Citation(
                claim_text="FreeRTOS firmware skills",
                source_type="knowledge_fact",
                reference_id="stm32 (arm cortex-m4/m7)"
            )
        ]
    )

    res = ge.verify_post_grounding(post)
    assert res.grounding_percentage == 100.0
    assert len(res.unverified_claims) == 0


def test_prohibited_phd_claim_rejected():
    ws = Path(__file__).resolve().parent.parent
    ge = GroundingEngine(ws)

    post = Post(
        post_id="post_fake_credentials",
        pillar="pillar_ai_agents",
        author="Serhat",
        title="Autonomous Agents Overview",
        content_text="During my Ph.D. research on multi-agent cognitive architectures, I discovered...",
        citations=[
            Citation(
                claim_text="AI agents",
                source_type="project_registry",
                reference_id="proj_antigravity_agency"
            )
        ]
    )

    res = ge.verify_post_grounding(post)
    assert res.grounding_percentage < 100.0
    assert any("Prohibited educational claim" in claim for claim in res.unverified_claims)


def test_exaggerated_experience_rejected():
    ws = Path(__file__).resolve().parent.parent
    ge = GroundingEngine(ws)

    post = Post(
        post_id="post_exaggerated_exp",
        pillar="pillar_embedded_firmware",
        author="Serhat",
        title="Embedded C Reflections",
        content_text="With 15 years of experience designing real-time systems, here is what I recommend...",
        citations=[
            Citation(
                claim_text="Embedded skills",
                source_type="knowledge_fact",
                reference_id="c++17/20"
            )
        ]
    )

    res = ge.verify_post_grounding(post)
    assert res.grounding_percentage < 100.0
    assert any("Exaggerated experience claim" in claim for claim in res.unverified_claims)


def test_invalid_project_citation_rejected():
    ws = Path(__file__).resolve().parent.parent
    ge = GroundingEngine(ws)

    post = Post(
        post_id="post_invalid_citation",
        pillar="pillar_software_infrastructure",
        author="Serhat",
        title="Microservices Architecture",
        content_text="We achieved 100k events/sec in our production telemetry engine.",
        citations=[
            Citation(
                claim_text="Invented project",
                source_type="project_registry",
                reference_id="non_existent_project_id_xyz"
            )
        ]
    )

    res = ge.verify_post_grounding(post)
    assert res.grounding_percentage < 100.0
    assert any("not found in knowledge/projects_registry.json" in claim for claim in res.unverified_claims)
