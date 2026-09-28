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


def test_approved_to_published_direct_transition_strictly_forbidden():
    """Regression test: Direct APPROVED -> PUBLISHED transition must be rejected."""
    ws = Path(__file__).resolve().parent.parent
    lm = LifecycleManager(ws)

    tag = "inv_check_tag"
    post = Post(
        post_id=f"post_{tag}",
        pillar="pillar_embedded_firmware",
        author="Serhat",
        title="Direct Transition Check",
        content_text="Verifying direct approved to published is rejected.",
        citations=[Citation(claim_text="c", source_type="knowledge_fact", reference_id="sqlite")]
    )

    lm.create_initial_draft(post)
    post = lm.transition(f"post_{tag}", LifecycleState.REVIEWED, expected_version=1)
    post = lm.transition(f"post_{tag}", LifecycleState.AWAITING_APPROVAL, expected_version=2)
    post = lm.transition(f"post_{tag}", LifecycleState.APPROVED, expected_version=3)
    assert post.lifecycle_state == LifecycleState.APPROVED

    # Attempt direct transition APPROVED -> PUBLISHED: must be strictly forbidden
    with pytest.raises(ValueError, match="(?i)Illegal state transition.*cannot transition from approved to published"):
        lm.transition(f"post_{tag}", LifecycleState.PUBLISHED, expected_version=4)

    # Must follow sequential path: APPROVED -> SCHEDULED -> PUBLISHED
    post = lm.transition(f"post_{tag}", LifecycleState.SCHEDULED, expected_version=4)
    assert post.lifecycle_state == LifecycleState.SCHEDULED
    assert post.state_version == 5

    post = lm.transition(f"post_{tag}", LifecycleState.PUBLISHED, expected_version=5)
    assert post.lifecycle_state == LifecycleState.PUBLISHED
    assert post.state_version == 6

    # Clean up test post file
    pub_file = ws / "lifecycle" / "08_published" / f"post_{tag}.json"
    if pub_file.exists():
        pub_file.unlink()


def test_publisher_dispatcher_executes_sequential_lifecycle_transitions():
    """Verify PublisherDispatcher automatically transitions APPROVED -> SCHEDULED -> PUBLISHED."""
    import uuid
    from core.models import MediaAsset, ActionScope, AssetSourcePriority
    from core.approval_engine import ApprovalEngine
    from core.publisher_dispatcher import PublisherDispatcher
    from core.mcp_gateways import BufferGateway
    from core.editorial_evaluator import EditorialEvaluator

    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)
    ae.set_killswitch_mode("AUTONOMY_ENABLED", "Testing sequential dispatch transitions")
    lm = LifecycleManager(ws)
    dispatcher = PublisherDispatcher(ws, ae, publisher=BufferGateway(ae, dry_run=True))

    tag = f"seq_{uuid.uuid4().hex[:6]}"
    post = Post(
        post_id=f"post_{tag}",
        pillar="pillar_embedded_firmware",
        author="Serhat",
        title=f"Sequential Dispatch Test {tag}",
        content_text=f"Testing sequential lifecycle progression during dispatch {tag}.",
        media_assets=[
            MediaAsset(
                asset_type="code_snippet",
                asset_path="assets/test.png",
                asset_sha256="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                caption="Test asset",
                source_priority=AssetSourcePriority.EXISTING_PROJECT_ASSET
            )
        ],
        citations=[Citation(claim_text="test", source_type="knowledge_fact", reference_id="sqlite")]
    )

    # Walk through lifecycle up to APPROVED
    lm.create_initial_draft(post)
    post = lm.transition(f"post_{tag}", LifecycleState.REVIEWED, expected_version=1)
    post = lm.transition(f"post_{tag}", LifecycleState.AWAITING_APPROVAL, expected_version=2)
    post = lm.transition(f"post_{tag}", LifecycleState.APPROVED, expected_version=3)
    assert post.lifecycle_state == LifecycleState.APPROVED
    assert post.state_version == 4

    scorecard = EditorialEvaluator(ws).evaluate_post(post)
    req = ae.create_approval_request(post, scorecard, action_scope=ActionScope.BUFFER_SCHEDULE)
    token = ae.sign_approval_request(req.request_id, signer="Serhat")

    # Dispatch: must automatically advance APPROVED -> SCHEDULED (v5) -> PUBLISHED (v6)
    res = dispatcher.dispatch(post, token, mode="DRY_RUN")
    assert res.status == "SUCCESS"

    final_post = lm.get_post(f"post_{tag}")
    assert final_post is not None
    assert final_post.lifecycle_state == LifecycleState.PUBLISHED
    assert final_post.state_version == 6

    # Verify intermediate file does not linger in scheduled
    assert not (ws / "lifecycle" / "07_scheduled" / f"post_{tag}.json").exists()
    assert (ws / "lifecycle" / "08_published" / f"post_{tag}.json").exists()

    # Clean up
    pub_f = ws / "lifecycle" / "08_published" / f"post_{tag}.json"
    if pub_f.exists():
        pub_f.unlink()

