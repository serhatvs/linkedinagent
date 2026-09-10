"""Approval engine and cryptographic gatekeeper for Serhat's personal media agency.

Ensures zero unauthorized external write actions can occur without explicit,
canonical hash-verified human approval from Serhat.
"""

from __future__ import annotations
import hmac
import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from core.models import (
    Post,
    ApprovalRequest,
    ApprovalToken,
    ActionScope,
    EditorialScorecard
)

# Standard default secret key for local development/simulation if not provided in environment
DEFAULT_SIGNING_KEY = b"serhat_secure_local_airgap_signing_key_v1"


def compute_canonical_payload_sha256(
    post_id: str,
    action_scope: str,
    target_platform: str,
    content_text: str,
    media_asset_hashes: list[str]
) -> str:
    """Creates a deterministic, canonical JSON representation and returns its SHA-256."""
    canonical_dict = {
        "action_scope": action_scope,
        "content_text": content_text.strip(),
        "media_asset_hashes": sorted(media_asset_hashes),
        "post_id": post_id,
        "target_platform": target_platform
    }
    canonical_bytes = json.dumps(canonical_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(canonical_bytes).hexdigest()


class ApprovalEngine:
    def __init__(self, workspace_root: Path, signing_key: bytes = DEFAULT_SIGNING_KEY):
        self.workspace_root = workspace_root
        self.approvals_dir = workspace_root / "approvals"
        self.pending_dir = self.approvals_dir / "pending"
        self.signed_dir = self.approvals_dir / "signed"
        self.revoked_dir = self.approvals_dir / "revoked"
        self.audit_log_path = self.approvals_dir / "audit_log.jsonl"
        self.killswitch_path = self.approvals_dir / "killswitch_state.json"
        self.signing_key = signing_key

        self._ensure_directories()

    def _ensure_directories(self):
        for d in [self.pending_dir, self.signed_dir, self.revoked_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def is_killswitch_active(self) -> Tuple[bool, str]:
        if self.killswitch_path.exists():
            try:
                with open(self.killswitch_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("agency_frozen", False):
                        return True, data.get("reason", "Agency is frozen by emergency killswitch.")
            except Exception:
                return True, "Killswitch state file corrupted. Halting defensively."
        return False, "Operational"

    def set_killswitch(self, frozen: bool, reason: str, authorized_by: str = "Serhat") -> None:
        state = {
            "agency_frozen": frozen,
            "reason": reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "authorized_by": authorized_by
        }
        with open(self.killswitch_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        self._append_audit_log({
            "event": "KILLSWITCH_STATE_CHANGED",
            "frozen": frozen,
            "reason": reason,
            "authorized_by": authorized_by,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def create_approval_request(
        self,
        post: Post,
        scorecard: EditorialScorecard,
        action_scope: ActionScope = ActionScope.METRICOOL_SCHEDULE,
        proposed_schedule_time: Optional[str] = None
    ) -> ApprovalRequest:
        frozen, reason = self.is_killswitch_active()
        if frozen:
            raise PermissionError(f"Cannot create approval request: {reason}")

        request_id = f"appr_req_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        media_hashes = [a.asset_sha256 for a in post.media_assets]

        payload_sha256 = compute_canonical_payload_sha256(
            post_id=post.post_id,
            action_scope=action_scope.value,
            target_platform="linkedin",
            content_text=post.content_text,
            media_asset_hashes=media_hashes
        )

        sched_time = proposed_schedule_time or (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        req = ApprovalRequest(
            request_id=request_id,
            post_id=post.post_id,
            action_scope=action_scope,
            target_platform="linkedin",
            proposed_schedule_time=sched_time,
            canonical_payload_sha256=payload_sha256,
            content_summary=post.title,
            content_full_text=post.content_text,
            media_asset_hashes=media_hashes,
            scorecard_summary={
                "composite_score": scorecard.scores.composite_score,
                "slop_detected": scorecard.slop_analysis.slop_detected,
                "grounding_percentage": scorecard.grounding_verification.grounding_percentage
            }
        )

        req_path = self.pending_dir / f"{request_id}.json"
        with open(req_path, "w", encoding="utf-8") as f:
            f.write(req.model_dump_json(indent=2))

        self._append_audit_log({
            "event": "APPROVAL_REQUEST_CREATED",
            "request_id": request_id,
            "post_id": post.post_id,
            "payload_sha256": payload_sha256,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        return req

    def sign_approval_request(
        self,
        request_id: str,
        signer: str = "Serhat"
    ) -> ApprovalToken:
        """Simulates or executes Serhat's human approval signing action."""
        if signer != "Serhat":
            raise ValueError(f"Unauthorized signer '{signer}'. Only Serhat can sign approval requests.")

        req_file = self.pending_dir / f"{request_id}.json"
        if not req_file.exists():
            raise FileNotFoundError(f"Pending approval request {request_id} does not exist.")

        with open(req_file, "r", encoding="utf-8") as f:
            req_data = json.load(f)
            req = ApprovalRequest.model_validate(req_data)

        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=7)
        nonce = uuid.uuid4().hex

        sig_message = f"{req.canonical_payload_sha256}:{req.request_id}:{nonce}:{signer}".encode('utf-8')
        signature_digest = hmac.new(self.signing_key, sig_message, hashlib.sha256).hexdigest()

        token = ApprovalToken(
            token_id=f"token_{uuid.uuid4().hex[:12]}",
            request_id=req.request_id,
            post_id=req.post_id,
            approved_by=signer,
            signed_at=now.isoformat(),
            expires_at=expires.isoformat(),
            nonce=nonce,
            action_scope=req.action_scope,
            target_platform=req.target_platform,
            canonical_payload_sha256=req.canonical_payload_sha256,
            signature_digest=signature_digest
        )

        signed_file = self.signed_dir / f"{request_id}.approved.json"
        with open(signed_file, "w", encoding="utf-8") as f:
            f.write(token.model_dump_json(indent=2))

        self._append_audit_log({
            "event": "APPROVAL_REQUEST_SIGNED",
            "token_id": token.token_id,
            "request_id": request_id,
            "post_id": req.post_id,
            "approved_by": signer,
            "timestamp": now.isoformat()
        })

        return token

    def verify_token_for_post(
        self,
        token: ApprovalToken,
        post: Post
    ) -> Tuple[bool, str]:
        """Validates that a signed token matches the current live state of the post."""
        frozen, reason = self.is_killswitch_active()
        if frozen:
            return False, f"Verification failed: {reason}"

        # 1. Signer check
        if token.approved_by != "Serhat":
            return False, f"Invalid approver '{token.approved_by}'. Must be Serhat."

        # 2. Expiration check
        now = datetime.now(timezone.utc)
        expires = datetime.fromisoformat(token.expires_at)
        if now > expires:
            return False, "Approval token has expired."

        # 3. Signature digest verification
        sig_message = f"{token.canonical_payload_sha256}:{token.request_id}:{token.nonce}:{token.approved_by}".encode('utf-8')
        expected_digest = hmac.new(self.signing_key, sig_message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(token.signature_digest, expected_digest):
            return False, "HMAC signature digest verification failed."

        # 4. Live payload hash match
        media_hashes = [a.asset_sha256 for a in post.media_assets]
        live_sha256 = compute_canonical_payload_sha256(
            post_id=post.post_id,
            action_scope=token.action_scope.value,
            target_platform=token.target_platform,
            content_text=post.content_text,
            media_asset_hashes=media_hashes
        )

        if live_sha256 != token.canonical_payload_sha256:
            return False, "E_PAYLOAD_MUTATED: Content or media modified after approval was granted."

        return True, "Approval token verified successfully."

    def _append_audit_log(self, entry: Dict[str, Any]):
        with open(self.audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
