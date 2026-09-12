"""Constrained PolicySigner for Serhat's Personal Media Agency.

Issues machine-signed AUTO_APPROVAL tokens ONLY when all deterministic
AutonomyPolicyEngine rules pass and autonomy is enabled.
MediaDirector is strictly forbidden from directly signing tokens.
"""

from __future__ import annotations
import hmac
import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from core.models import (
    Post,
    ApprovalRequest,
    ApprovalToken,
    AutonomyEvaluation,
    AutonomyDecision,
    DisclosureRisk,
    LifecycleState
)
from core.approval_engine import ApprovalEngine, compute_canonical_payload_sha256, resolve_signing_secret
from core.lifecycle_manager import LifecycleManager


def compute_evaluation_hash(evaluation: AutonomyEvaluation) -> str:
    """Calculates a deterministic SHA-256 digest over the policy evaluation predicates."""
    eval_dict = {
        "candidate_id": evaluation.candidate_id or "",
        "cooldown_passed": evaluation.cooldown_passed,
        "decision": evaluation.decision.value,
        "disclosure_risk": evaluation.disclosure_risk.value,
        "drc_passed": evaluation.drc_passed,
        "editorial_score": evaluation.editorial_score,
        "grounding_percentage": evaluation.grounding_percentage,
        "mvts_score": evaluation.mvts_score,
        "payload_sha256": evaluation.canonical_payload_sha256 or "",
        "policy_version": evaluation.policy_version,
        "post_id": evaluation.post_id or "",
        "slop_score": evaluation.slop_score,
        "weekly_ceiling_passed": evaluation.weekly_ceiling_passed
    }
    canonical_bytes = json.dumps(eval_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(canonical_bytes).hexdigest()


class PolicySigner:
    def __init__(self, workspace_root: Path, signing_key: Optional[bytes] = None):
        self.workspace_root = workspace_root
        self.signing_key = signing_key if signing_key is not None else resolve_signing_secret()
        self.approval_engine = ApprovalEngine(workspace_root, self.signing_key)
        self.lifecycle_manager = LifecycleManager(workspace_root)
        self.audit_log_path = workspace_root / "approvals" / "audit_log.jsonl"

    def sign_auto_approval(
        self,
        post: Post,
        request: ApprovalRequest,
        evaluation: AutonomyEvaluation,
        ttl_hours: Optional[int] = None,
        shadow_mode: bool = False
    ) -> ApprovalToken:
        """Issues an AUTO_APPROVAL token only after independently verifying all policy predicates."""
        # 1. Check autonomy killswitch status (unless simulated in shadow mode)
        if not shadow_mode:
            autonomy_ok, reason = self.approval_engine.is_autonomy_enabled()
            if not autonomy_ok:
                raise PermissionError(f"PolicySigner refused: {reason}")

        # 2. Check policy decision is AUTO_APPROVE or AUTO_PUBLISH_ELIGIBLE
        valid_auto_decisions = [AutonomyDecision.AUTO_APPROVE, AutonomyDecision.AUTO_PUBLISH_ELIGIBLE]
        if evaluation.decision not in valid_auto_decisions:
            raise PermissionError(
                f"PolicySigner refused: Decision was '{evaluation.decision.value}'. "
                f"Reasons: {evaluation.reasons}"
            )

        # 3. Independent predicate verification (never trust a bare boolean)
        target_platform = request.target_platform.lower() if hasattr(request, "target_platform") and request.target_platform else "linkedin"
        if target_platform in ["twitter", "x"]:
            min_mvts = 6.5
            max_ceiling = 3
        elif target_platform == "instagram":
            min_mvts = 7.5
            max_ceiling = 1
        else:
            min_mvts = 9.0
            max_ceiling = 2

        if evaluation.mvts_score < min_mvts:
            raise PermissionError(f"PolicySigner rejected altered evaluation: MVTS score {evaluation.mvts_score} is below {min_mvts} threshold.")

        # Universal Asset Requirement (Text-only posts prohibited across all channels)
        if len(post.media_assets) == 0:
            raise PermissionError(f"PolicySigner rejected: All posts on {target_platform.upper()} strictly require at least one verified asset. Text-only posts are prohibited.")

        # Anti-Fake Evidence Check: AI-generated assets must NEVER pretend to be real evidence
        for a in post.media_assets:
            if getattr(a, "is_synthetic", False):
                fake_evidence_types = ["benchmark_chart", "hardware_photo", "screenshot", "terminal_output", "app_ui"]
                arch = (getattr(a, "archetype", "") or getattr(a, "asset_type", "")).lower()
                if arch in fake_evidence_types:
                    raise PermissionError(f"PolicySigner rejected fake evidence: AI-generated asset claiming to be real {arch} is strictly prohibited.")

        if evaluation.editorial_score < 90.0:
            raise PermissionError(f"PolicySigner rejected altered evaluation: Editorial score {evaluation.editorial_score} is below 90.0 threshold.")
        if evaluation.grounding_percentage < 98.0:
            raise PermissionError(f"PolicySigner rejected altered evaluation: Grounding coverage {evaluation.grounding_percentage}% is below 98.0% threshold.")
        if evaluation.slop_score > 0.0:
            raise PermissionError(f"PolicySigner rejected altered evaluation: Slop score {evaluation.slop_score} exceeds 0.0.")
        if not evaluation.drc_passed:
            raise PermissionError("PolicySigner rejected altered evaluation: Domain DRC checks failed.")
        if evaluation.disclosure_risk != DisclosureRisk.LOW:
            raise PermissionError(f"PolicySigner rejected altered evaluation: Disclosure risk is {evaluation.disclosure_risk.value} (must be LOW).")
        if not evaluation.cooldown_passed:
            raise PermissionError("PolicySigner rejected altered evaluation: 24-hour publication cooldown not satisfied.")
        if not evaluation.weekly_ceiling_passed:
            raise PermissionError(f"PolicySigner rejected altered evaluation: Weekly publication ceiling ({max_ceiling} posts/7d) not satisfied.")

        # 4. Verify evaluation artifact integrity hash if present
        if evaluation.evaluation_hash:
            expected_eval_hash = compute_evaluation_hash(evaluation)
            if evaluation.evaluation_hash != expected_eval_hash:
                raise PermissionError(
                    f"PolicySigner rejected altered evaluation: Evaluation hash mismatch. "
                    f"Expected {expected_eval_hash}, found {evaluation.evaluation_hash}."
                )

        # 5. Verify identity bindings (post_id, request_id)
        if evaluation.post_id and evaluation.post_id != post.post_id:
            raise ValueError(f"Evaluation post_id '{evaluation.post_id}' does not match post '{post.post_id}'.")
        if request.post_id != post.post_id:
            raise ValueError(f"Request post_id '{request.post_id}' does not match post '{post.post_id}'.")

        # 6. Verify live payload SHA-256 matches request canonical payload SHA-256
        media_hashes = [a.asset_sha256 for a in post.media_assets]
        live_sha256 = compute_canonical_payload_sha256(
            post_id=post.post_id,
            action_scope=request.action_scope.value,
            target_platform=request.target_platform,
            content_text=post.content_text,
            media_asset_hashes=media_hashes
        )
        if live_sha256 != request.canonical_payload_sha256:
            raise PermissionError(
                f"PolicySigner refused: Live payload hash {live_sha256} does not match "
                f"request payload hash {request.canonical_payload_sha256}. Content was mutated."
            )

        now = datetime.now(timezone.utc)
        # 7. Initial TTL enforcement: maximum 7 days (168h), allow shorter if requested
        effective_ttl = min(ttl_hours or evaluation.ttl_hours or 168, 168)
        if effective_ttl <= 0:
            effective_ttl = 168
        expires = now + timedelta(hours=effective_ttl)
        nonce = uuid.uuid4().hex
        signer_identity = "PolicySigner"

        # HMAC digest covering canonical payload hash, request ID, nonce, and PolicySigner identity
        sig_message = f"{request.canonical_payload_sha256}:{request.request_id}:{nonce}:{signer_identity}".encode('utf-8')
        signature_digest = hmac.new(self.signing_key, sig_message, hashlib.sha256).hexdigest()

        token = ApprovalToken(
            token_id=f"token_auto_{uuid.uuid4().hex[:10]}",
            request_id=request.request_id,
            post_id=post.post_id,
            approved_by=signer_identity,
            approval_type="AUTO_APPROVAL",
            autonomy_policy_version=evaluation.policy_version,
            signed_at=now.isoformat(),
            expires_at=expires.isoformat(),
            ttl_hours=effective_ttl,
            nonce=nonce,
            action_scope=request.action_scope,
            target_platform=request.target_platform,
            canonical_payload_sha256=request.canonical_payload_sha256,
            signature_digest=signature_digest
        )

        signed_file = self.approval_engine.signed_dir / f"{request.request_id}.approved.json"
        with open(signed_file, "w", encoding="utf-8") as f:
            f.write(token.model_dump_json(indent=2))

        # Log audit entry
        self._append_audit_log({
            "event": "AUTO_APPROVAL_TOKEN_ISSUED",
            "token_id": token.token_id,
            "request_id": request.request_id,
            "post_id": post.post_id,
            "policy_version": evaluation.policy_version,
            "mvts_score": evaluation.mvts_score,
            "editorial_score": evaluation.editorial_score,
            "grounding_percentage": evaluation.grounding_percentage,
            "timestamp": now.isoformat()
        })

        return token

    def _append_audit_log(self, entry: dict):
        with open(self.audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
