"""Tests verifying lifecycle state transitions, concurrency control, and atomic persistence."""

from pathlib import Path
import pytest
from core.models import Post, LifecycleState, Citation
from core.lifecycle_manager import LifecycleManager


def test_valid_and_invalid_lifecycle_transitions(tmp_path):
    ws = Path(__file__).resolve().parent.parent
    lm = LifecycleManager(ws)

    post = Post(
        post_id="post_lifecycle_test",
        pillar="pillar_embedded_firmware",
        author="Serhat",
        title="Bus Matrix Architecture",
        content_text="Detailed explanation of SRAM domains on STM32H7.",
        citations=[Citation(claim_text="STM32", source_type="project_registry", reference_id="proj_tinyml_edge_vision")]
    )

    # 1. Create initial draft (version 1)
    lm.create_initial_draft(post)
    saved = lm.get_post("post_lifecycle_test")
    assert saved is not None
    assert saved.lifecycle_state == LifecycleState.DRAFT
    assert saved.state_version == 1

    # 2. Illegal transition: DRAFT -> SCHEDULED must fail
    with pytest.raises(ValueError, match="Illegal state transition"):
        lm.transition("post_lifecycle_test", LifecycleState.SCHEDULED, expected_version=1)

    # 3. Concurrency conflict check
    with pytest.raises(ValueError, match="Concurrency conflict"):
        lm.transition("post_lifecycle_test", LifecycleState.REVIEWED, expected_version=99)

    # 4. Valid transition: DRAFT -> REVIEWED
    post = lm.transition("post_lifecycle_test", LifecycleState.REVIEWED, expected_version=1)
    assert post.lifecycle_state == LifecycleState.REVIEWED
    assert post.state_version == 2

    # 5. Valid transition: REVIEWED -> AWAITING_APPROVAL
    post = lm.transition("post_lifecycle_test", LifecycleState.AWAITING_APPROVAL, expected_version=2)
    assert post.lifecycle_state == LifecycleState.AWAITING_APPROVAL
    assert post.state_version == 3

    # 6. Valid transition: AWAITING_APPROVAL -> APPROVED
    post = lm.transition("post_lifecycle_test", LifecycleState.APPROVED, expected_version=3)
    assert post.lifecycle_state == LifecycleState.APPROVED
    assert post.state_version == 4

    # 7. Valid transition: APPROVED -> SCHEDULED
    post = lm.transition("post_lifecycle_test", LifecycleState.SCHEDULED, expected_version=4)
    assert post.lifecycle_state == LifecycleState.SCHEDULED
    assert post.state_version == 5

    # 8. Valid transition: SCHEDULED -> PUBLISHED
    post = lm.transition("post_lifecycle_test", LifecycleState.PUBLISHED, expected_version=5)
    assert post.lifecycle_state == LifecycleState.PUBLISHED
    assert post.state_version == 6

    # 9. Valid transition: PUBLISHED -> ANALYZED
    post = lm.transition("post_lifecycle_test", LifecycleState.ANALYZED, expected_version=6)
    assert post.lifecycle_state == LifecycleState.ANALYZED
    assert post.state_version == 7


def test_content_mutation_demotes_to_draft():
    ws = Path(__file__).resolve().parent.parent
    lm = LifecycleManager(ws)

    post = Post(
        post_id="post_demote_test",
        pillar="pillar_embedded_firmware",
        author="Serhat",
        title="Original Title",
        content_text="Original content text.",
        citations=[Citation(claim_text="STM32", source_type="project_registry", reference_id="proj_tinyml_edge_vision")]
    )

    lm.create_initial_draft(post)
    post = lm.transition("post_demote_test", LifecycleState.REVIEWED, expected_version=1)
    assert post.lifecycle_state == LifecycleState.REVIEWED

    # Mutate content
    post.content_text = "Updated content text requiring re-review."
    updated = lm.update_post_content(post, expected_version=2)

    # Must be demoted back to DRAFT
    assert updated.lifecycle_state == LifecycleState.DRAFT
    assert updated.state_version == 3
