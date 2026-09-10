"""Model Context Protocol (MCP) gateways for GitHub and Metricool.

Enforces zero external writes without a validated cryptographic approval token,
sanitizes untrusted input, and provides dry-run simulation mode.
"""

from __future__ import annotations
import os
import re
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from core.models import Post, ApprovalToken, ActionScope, MetricoolPayload
from core.approval_engine import ApprovalEngine, compute_canonical_payload_sha256


class GitHubGateway:
    """Read-only GitHub intelligence gateway."""
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")

    def sanitize_input(self, raw_text: str) -> str:
        """Strips injection delimiters and quarantines third-party text."""
        cleaned = re.sub(r"[<>{}\[\]\\]", " ", raw_text)
        return f"<untrusted_source_data>{cleaned.strip()}</untrusted_source_data>"

    def fetch_recent_commits(self, repo: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Simulates or fetches recent commits in read-only mode."""
        return [
            {
                "commit_hash": "8f3b1a2c4e5d6",
                "message": self.sanitize_input("optimize DMA ping-pong buffer on STM32H7, cut bus contention by 24%"),
                "author": "Serhat",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "files_changed": ["src/dma_manager.c", "include/stm32h7_conf.h"]
            },
            {
                "commit_hash": "9e2a1b3c5d7f8",
                "message": self.sanitize_input("add FreeRTOS semaphore synchronization to prevent I2C bus collision with display driver"),
                "author": "Serhat",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "files_changed": ["src/i2c_bus.c", "src/display_task.c"]
            }
        ]


class MetricoolGateway:
    """Metricool social publishing and analytics gateway with strict verification gates."""
    def __init__(self, approval_engine: ApprovalEngine, dry_run: bool = True):
        self.approval_engine = approval_engine
        self.dry_run = dry_run
        self.user_token = os.getenv("METRICOOL_USER_TOKEN", "")
        self.blog_id = os.getenv("METRICOOL_BLOG_ID", "")

    def schedule_post(
        self,
        post: Post,
        token: ApprovalToken,
        publish_time: str
    ) -> Dict[str, Any]:
        """Dispatches a schedule request to Metricool MCP after rigorous cryptographic verification."""
        # 1. Action scope check
        if token.action_scope not in [ActionScope.METRICOOL_SCHEDULE, ActionScope.METRICOOL_PUBLISH_NOW]:
            raise PermissionError(f"Token action scope {token.action_scope} does not allow scheduling.")

        # 2. Cryptographic token verification against live post state
        is_valid, reason = self.approval_engine.verify_token_for_post(token, post)
        if not is_valid:
            raise PermissionError(f"Security Gate Blocked: {reason}")

        # 3. Payload Construction
        media_items = [
            {"url_or_path": a.asset_path, "type": "image", "sha256": a.asset_sha256}
            for a in post.media_assets
        ]

        payload = MetricoolPayload(
            platform="linkedin",
            text=post.content_text,
            dateTime=publish_time,
            media=media_items,
            approval_token_id=token.token_id,
            verified_payload_sha256=token.canonical_payload_sha256
        )

        # 4. Dispatch (Dry Run or Live)
        if self.dry_run or not self.user_token:
            simulated_id = f"metricool_mock_{hashlib.sha256(token.token_id.encode()).hexdigest()[:12]}"
            return {
                "status": "SUCCESS",
                "mode": "DRY_RUN",
                "message": "Validated cryptographic signature. Scheduled in Metricool simulation mode.",
                "metricool_post_id": simulated_id,
                "scheduled_time": publish_time,
                "verified_hash": token.canonical_payload_sha256
            }

        # Real HTTP dispatch logic would execute here using standard authenticated requests
        raise NotImplementedError("Live publishing mode is locked in v1 safety boundaries.")

    def fetch_post_analytics(self, metricool_post_id: str) -> Dict[str, Any]:
        """Fetches post analytics in read-only mode."""
        return {
            "metricool_post_id": metricool_post_id,
            "impressions": 1840,
            "clicks": 142,
            "reactions": 68,
            "comments": 19,
            "shares": 8,
            "profile_visits": 37,
            "inbound_messages": 2,
            "technical_commenters": [
                {"title": "Staff Firmware Engineer", "company": "Aerospace Systems"},
                {"title": "Robotics Researcher", "company": "Autonomous Systems Lab"}
            ]
        }

    def fetch_comments(self, metricool_post_id: str) -> List[Dict[str, Any]]:
        """Fetches comments in read-only mode with sanitization."""
        return [
            {
                "comment_id": "comm_901",
                "author": "Dr. E. Miller (Robotics Lead)",
                "text": "<untrusted_comment_data>What clock frequency was the SPI bus running at when you hit the DMA contention?</untrusted_comment_data>",
                "is_high_signal": True
            },
            {
                "comment_id": "comm_902",
                "author": "LinkedIn User",
                "text": "<untrusted_comment_data>CFBR</untrusted_comment_data>",
                "is_high_signal": False
            }
        ]
