"""Tests verifying that models and JSON schemas are valid and properly constrained."""

import json
from pathlib import Path
import pytest
from core.models import (
    Idea, Candidate, CandidateDecision, MVTSEvaluation,
    Post, LifecycleState, MediaAsset, Citation,
    ApprovalRequest, ApprovalToken, ActionScope, MetricoolPayload
)


def test_idea_schema_validation():
    idea = Idea(
        idea_id="idea_20260910_stm32",
        source_type="github_commit",
        title="STM32H7 DMA ping-pong buffer optimization",
        raw_notes="Cut memory bus contention by 24% using dual SRAM bank allocation.",
        pillar_affinity="pillar_embedded_firmware",
        project_id="proj_tinyml_edge_vision"
    )
    assert idea.idea_id == "idea_20260910_stm32"
    assert idea.pillar_affinity == "pillar_embedded_firmware"


def test_invalid_idea_id_raises():
    with pytest.raises(Exception):
        Idea(
            idea_id="INVALID_ID_FORMAT",
            source_type="github_commit",
            title="Short",
            raw_notes="Too short",
            pillar_affinity="unknown_pillar"
        )


def test_candidate_schema_validation():
    cand = Candidate(
        candidate_id="cand_20260910_01",
        idea_id="idea_20260910_stm32",
        pillar="pillar_embedded_firmware",
        target_audience=["Embedded Engineers"],
        angle="Root-Cause Analysis",
        mvts_evaluation=MVTSEvaluation(
            grounding_score=3.0,
            technical_artifact_score=3.0,
            engineering_tradeoff_score=2.0,
            actionable_takeaway_score=1.5,
            total_score=9.5
        ),
        decision=CandidateDecision.PROCEED_TO_DRAFT
    )
    assert cand.decision == CandidateDecision.PROCEED_TO_DRAFT
    assert cand.mvts_evaluation.total_score >= 8.0


def test_post_lifecycle_defaults():
    post = Post(
        post_id="post_20260910_test",
        pillar="pillar_embedded_firmware",
        author="Serhat",
        title="Test Post Title",
        content_text="This is a sufficiently long body explaining an engineering mechanism.",
        citations=[Citation(claim_text="fact", source_type="knowledge_fact", reference_id="c++17/20")]
    )
    assert post.lifecycle_state == LifecycleState.DRAFT
    assert post.state_version == 1
    assert post.author == "Serhat"
