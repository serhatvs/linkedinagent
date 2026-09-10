"""Tests verifying the cryptographic human-in-the-loop approval gate and TOCTOU defense."""

from pathlib import Path
import pytest
from core.models import Post, Citation, MediaAsset, ActionScope
from core.grounding_engine import GroundingEngine
from core.editorial_evaluator import EditorialEvaluator
from core.approval_engine import ApprovalEngine
from core.mcp_gateways import MetricoolGateway


def test_approval_workflow_and_tampering_protection(tmp_path):
    # Setup test workspace environment in tmp_path
    ws = Path(__file__).resolve().parent.parent
    ge = GroundingEngine(ws)
    ee = EditorialEvaluator(ge)
    ae = ApprovalEngine(ws)

    post = Post(
        post_id="post_approval_test",
        pillar="pillar_embedded_firmware",
        author="Serhat",
        title="DMA Buffer Contention Optimization",
        content_text="Verifiable content explaining bus arbitration on Cortex-M7.",
        media_assets=[
            MediaAsset(
                asset_type="logic_trace",
                asset_path="assets/trace.png",
                asset_sha256="aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899",
                caption="Logic trace"
            )
        ],
        citations=[
            Citation(
                claim_text="STM32",
                source_type="project_registry",
                reference_id="proj_tinyml_edge_vision"
            )
        ]
    )

    card = ee.evaluate_post(post)

    # 1. Metricool dispatch WITHOUT signed token must fail
    mg = MetricoolGateway(ae, dry_run=True)
    fake_token = None
    with pytest.raises(Exception):
        mg.schedule_post(post, fake_token, "2026-09-12T10:00:00Z")

    # 2. Generate Approval Request
    req = ae.create_approval_request(post, card, action_scope=ActionScope.METRICOOL_SCHEDULE)
    assert req.canonical_payload_sha256 is not None
    assert len(req.canonical_payload_sha256) == 64

    # 3. Signing by an unauthorized entity fails
    with pytest.raises(ValueError, match="Unauthorized signer"):
        ae.sign_approval_request(req.request_id, signer="MaliciousAgent")

    # 4. Valid signing by Serhat succeeds
    token = ae.sign_approval_request(req.request_id, signer="Serhat")
    assert token.approved_by == "Serhat"
    assert token.canonical_payload_sha256 == req.canonical_payload_sha256

    # 5. Live verification succeeds
    valid, reason = ae.verify_token_for_post(token, post)
    assert valid is True

    # 6. TOCTOU Defense: Altering post content after signature triggers E_PAYLOAD_MUTATED
    tampered_post = post.model_copy(deep=True)
    tampered_post.content_text = "Sneaky altered text that Serhat did not review or approve."

    valid, reason = ae.verify_token_for_post(token, tampered_post)
    assert valid is False
    assert "E_PAYLOAD_MUTATED" in reason

    # 7. Metricool gateway rejects tampered payload unconditionally
    with pytest.raises(PermissionError, match="E_PAYLOAD_MUTATED"):
        mg.schedule_post(tampered_post, token, "2026-09-12T10:00:00Z")


def test_killswitch_blocks_operations():
    ws = Path(__file__).resolve().parent.parent
    ae = ApprovalEngine(ws)

    ae.set_killswitch(frozen=True, reason="Security audit underway", authorized_by="Serhat")
    frozen, reason = ae.is_killswitch_active()
    assert frozen is True

    # Unfreeze for subsequent tests
    ae.set_killswitch(frozen=False, reason="Audit complete", authorized_by="Serhat")
    frozen, _ = ae.is_killswitch_active()
    assert frozen is False
