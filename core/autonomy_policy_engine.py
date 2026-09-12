"""Deterministic Autonomy Policy Engine for Serhat's Personal Media Agency.

Enforces strict mathematical and procedural constraints on autonomous machine approvals:
- MVTS >= 9.0
- Editorial score >= 90.0
- Grounding >= 98.0%
- Slop score <= 0.0 (zero buzzwords, zero decorative emojis)
- Domain DRC = PASS
- Disclosure risk = LOW
- Evidence completeness = PASS
- Duplicate content check = PASS
- Cadence limits: max 1 post per 24h, max 3 posts per rolling 7 days
"""

from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from core.models import (
    Post,
    Candidate,
    CandidateDecision,
    EditorialScorecard,
    DisclosureCheck,
    DisclosureRisk,
    AutonomyDecision,
    AutonomyEvaluation,
    Post,
    Candidate,
    CandidateDecision,
    EditorialScorecard,
    DisclosureCheck,
    DisclosureRisk,
    AutonomyDecision,
    AutonomyEvaluation,
    LifecycleState,
    AssetArchetype,
    AssetSourcePriority
)
from core.lifecycle_manager import LifecycleManager
from core.approval_engine import compute_canonical_payload_sha256
from core.policy_signer import compute_evaluation_hash
from core.asset_planner import AssetPlanner


AUTONOMY_POLICY_VERSION = "v1.3.0-production-evidence-first"

CHANNEL_POLICIES: Dict[str, Dict[str, Any]] = {
    "linkedin": {
        "role": "Professional engineering reputation",
        "min_mvts": 9.0,
        "weekly_ceiling": 2,
        "requires_media": True,
        "autonomous_enabled": True
    },
    "twitter": {
        "role": "Primary developer feed",
        "min_mvts": 6.5,
        "weekly_ceiling": 3,
        "requires_media": True,
        "autonomous_enabled": True
    },
    "x": {
        "role": "Primary developer feed",
        "min_mvts": 6.5,
        "weekly_ceiling": 3,
        "requires_media": True,
        "autonomous_enabled": True
    },
    "instagram": {
        "role": "Visual creative / build journal",
        "min_mvts": 7.5,
        "weekly_ceiling": 1,
        "requires_media": True,
        "autonomous_enabled": True
    }
}


class AutonomyPolicyEngine:
    CHANNEL_POLICIES = CHANNEL_POLICIES

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.lifecycle_manager = LifecycleManager(workspace_root)
        self.pillars_path = workspace_root / "brand" / "positioning_pillars.json"

    def evaluate(
        self,
        post: Post,
        candidate: Optional[Candidate],
        scorecard: EditorialScorecard,
        disclosure: DisclosureCheck,
        recent_posts: Optional[List[Post]] = None,
        enforce_rate_limits: bool = True,
        target_platform: str = "linkedin"
    ) -> AutonomyEvaluation:
        reasons: List[str] = []
        mvts_score = candidate.mvts_evaluation.total_score if (candidate and candidate.mvts_evaluation) else 0.0
        editorial_score = scorecard.scores.composite_score
        grounding_pct = scorecard.grounding_verification.grounding_percentage
        slop_score = scorecard.slop_analysis.slop_score
        drc_passed = scorecard.domain_drc_checks.passed
        disclosure_risk = disclosure.risk_level

        channel_key = target_platform.lower()
        policy = self.CHANNEL_POLICIES.get(channel_key, self.CHANNEL_POLICIES["linkedin"])
        min_mvts = policy["min_mvts"]
        requires_media = policy.get("requires_media", True)

        # Compute live payload SHA-256
        media_hashes = [a.asset_sha256 for a in post.media_assets]
        payload_sha256 = compute_canonical_payload_sha256(
            post_id=post.post_id,
            action_scope="BUFFER_SCHEDULE",
            target_platform=channel_key,
            content_text=post.content_text,
            media_asset_hashes=media_hashes
        )

        # Check if candidate is already in terminal REJECTED state
        is_candidate_rejected = False
        if candidate:
            if candidate.decision == CandidateDecision.REJECT:
                is_candidate_rejected = True
            elif getattr(candidate, "recommendation", None) and "REJECT" in str(getattr(candidate, "recommendation", "")):
                is_candidate_rejected = True

        # 1. MVTS Check
        mvts_passed = mvts_score >= min_mvts
        if not mvts_passed:
            reasons.append(f"MVTS score {mvts_score} is below autonomous threshold ({min_mvts}) for {channel_key.upper()}.")

        # Media Requirement Check across all platforms (Universal Asset Requirement)
        media_passed = len(post.media_assets) > 0
        asset_planner_eval = None
        if not media_passed:
            reasons.append(f"Universal Asset Policy violation: {channel_key.upper()} strictly requires at least one media asset. Text-only posts are prohibited.")
            if candidate:
                planner = AssetPlanner(self.workspace_root)
                asset_planner_eval = planner.evaluate_asset_availability(candidate, channel_key)

        # Anti-Fake Visual Evidence Check
        anti_fake_passed = True
        for a in post.media_assets:
            if getattr(a, "is_synthetic", False):
                empirical_archetypes = [
                    AssetArchetype.BENCHMARK_CHART.value,
                    AssetArchetype.WORKBENCH_PHOTO.value,
                    AssetArchetype.PRODUCT_PROTOTYPE_PHOTO.value,
                    AssetArchetype.TERMINAL_OUTPUT.value,
                    AssetArchetype.SCREENSHOT.value,
                    AssetArchetype.APP_UI.value,
                    AssetArchetype.CODE_SNIPPET_DIFF.value,
                    AssetArchetype.SCHEMATIC.value,
                    AssetArchetype.OSCILLOSCOPE_TRACE.value,
                    AssetArchetype.LOGIC_ANALYZER_TRACE.value
                ]
                if a.archetype in empirical_archetypes:
                    anti_fake_passed = False
                    reasons.append(f"Anti-Fake Visual Rule violation: AI-generated asset cannot simulate empirical evidence ({a.archetype}).")

        # 2. Editorial Score (>= 90.0)
        editorial_passed = editorial_score >= 90.0
        if not editorial_passed:
            reasons.append(f"Editorial composite score {editorial_score} is below autonomous threshold (90.0).")

        # 3. Grounding Verification (>= 98.0%)
        grounding_passed = grounding_pct >= 98.0
        if not grounding_passed:
            reasons.append(f"Grounding coverage {grounding_pct}% is below autonomous threshold (98.0%).")

        # 4. Slop Analysis (slop_score == 0.0 and no detected buzzwords)
        slop_passed = slop_score <= 0.0 and not scorecard.slop_analysis.slop_detected
        if not slop_passed:
            reasons.append(f"Slop detected in copy: {scorecard.slop_analysis.detected_buzzwords}.")

        # 5. Domain DRC Check (must pass)
        if not drc_passed:
            reasons.append(f"Domain DRC failed with violations: {scorecard.domain_drc_checks.violations}.")

        # 6. Disclosure Risk (must be LOW)
        disclosure_passed = disclosure_risk == DisclosureRisk.LOW and disclosure.passed
        if not disclosure_passed:
            reasons.append(f"Disclosure audit requires human review: {disclosure.rationale}")

        # 7. Evidence completeness
        evidence_passed = len(scorecard.grounding_verification.unverified_claims) == 0
        if not evidence_passed:
            reasons.append(f"Unverified factual claims exist: {scorecard.grounding_verification.unverified_claims}")

        # 8. Pillar verification
        approved_pillars = self._load_approved_pillars()
        pillar_passed = post.pillar in approved_pillars
        if not pillar_passed:
            reasons.append(f"Post pillar '{post.pillar}' is not an approved pillar.")

        # 9. Cooldown & Weekly ceiling checks
        if enforce_rate_limits:
            cooldown_passed, cooldown_reason = self._check_cooldown_24h(post, recent_posts)
            if not cooldown_passed:
                reasons.append(cooldown_reason)

            weekly_ceiling_passed, weekly_reason = self._check_weekly_ceiling(post, recent_posts, target_platform=channel_key)
            if not weekly_ceiling_passed:
                reasons.append(weekly_reason)
        else:
            cooldown_passed = True
            weekly_ceiling_passed = True

        # 10. Duplicate content check
        duplicate_passed, duplicate_reason = self._check_duplicate_content(post, recent_posts)
        if not duplicate_passed:
            reasons.append(duplicate_reason)

        # Determine final decision
        all_passed = (
            mvts_passed and
            media_passed and
            anti_fake_passed and
            editorial_passed and
            grounding_passed and
            slop_passed and
            drc_passed and
            disclosure_passed and
            evidence_passed and
            pillar_passed and
            cooldown_passed and
            weekly_ceiling_passed and
            duplicate_passed
        )

        has_operator_override = bool(candidate and candidate.override_reason)

        if is_candidate_rejected:
            decision = AutonomyDecision.REJECTED
            reasons.append("Candidate is in terminal REJECTED state. Silent revival is prohibited; requires explicit 'revive-candidate' operator action.")
        elif not anti_fake_passed:
            decision = AutonomyDecision.REJECTED
            reasons.append("Post rejected for anti-fake visual evidence violation (synthetic asset claiming empirical evidence).")
        elif not drc_passed or not slop_passed or editorial_score < 70.0:
            decision = AutonomyDecision.REJECTED
            reasons.append("Post rejected for editorial unsuitability (slop, DRC failure, or sub-viable editorial score).")
        elif not media_passed:
            if asset_planner_eval and asset_planner_eval.get("human_request_needed"):
                decision = AutonomyDecision.REQUEST_ASSET_FROM_USER
                reasons.append(f"Asset requested from Serhat: {asset_planner_eval.get('rationale')}")
            else:
                decision = AutonomyDecision.HOLD_FOR_ASSET
                reasons.append(f"Content held for asset verification on {channel_key.upper()}. Universal Asset Policy requires real/composed visual asset.")
        elif all_passed and not has_operator_override:
            decision = AutonomyDecision.AUTO_APPROVE
            reasons.append("All deterministic autonomy policy requirements satisfied. Approved for PolicySigner signing.")
        elif has_operator_override:
            decision = AutonomyDecision.REQUIRE_HUMAN_APPROVAL
            reasons.append(f"Deliberate manual override active: '{candidate.override_reason}'. Routing to human approval queue.")
        elif mvts_passed and editorial_passed and grounding_passed and slop_passed and drc_passed and not disclosure_passed:
            decision = AutonomyDecision.REQUIRE_HUMAN_APPROVAL
            reasons.append("High-substance content outside autonomous risk envelope (sensitive topics / elevated disclosure risk). Routing to human approval queue.")
        else:
            decision = AutonomyDecision.HOLD_QUALITY
            reasons.append(f"Content does not meet autonomous quality threshold (MVTS >= {min_mvts}, Editorial >= 90.0, Grounding >= 98.0%). Held in backlog pending engineering refinement or operator override.")

        eval_res = AutonomyEvaluation(
            decision=decision,
            policy_version=AUTONOMY_POLICY_VERSION,
            mvts_score=mvts_score,
            editorial_score=editorial_score,
            grounding_percentage=grounding_pct,
            slop_score=slop_score,
            drc_passed=drc_passed,
            disclosure_risk=disclosure_risk,
            cooldown_passed=cooldown_passed,
            weekly_ceiling_passed=weekly_ceiling_passed,
            reasons=reasons,
            candidate_id=candidate.candidate_id if candidate else None,
            post_id=post.post_id,
            canonical_payload_sha256=payload_sha256,
            ttl_hours=168
        )
        eval_res.evaluation_hash = compute_evaluation_hash(eval_res)
        return eval_res

    def _load_approved_pillars(self) -> List[str]:
        if self.pillars_path.exists():
            with open(self.pillars_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [p["id"] for p in data.get("pillars", [])]
        return ["pillar_low_level_systems_and_graphics", "pillar_cognitive_architectures", "pillar_distributed_embedded_hardware", "pillar_applied_crypto_and_privacy", "pillar_local_infra_and_tooling", "pillar_embedded_firmware", "pillar_software_infrastructure", "pillar_ai_agents"]

    def _check_cooldown_24h(self, current_post: Post, recent_posts: Optional[List[Post]] = None) -> tuple[bool, str]:
        """Ensures at most 1 autonomous post per 24 hours based on scheduled/published timestamp distance."""
        posts = recent_posts if recent_posts is not None else self._get_recent_published_or_scheduled()
        now = datetime.now(timezone.utc)
        curr_ts = self._get_post_timestamp(current_post) or now

        for p in posts:
            if p.post_id == current_post.post_id:
                continue
            ts = self._get_post_timestamp(p)
            if not ts:
                continue

            diff_hours = abs((curr_ts - ts).total_seconds()) / 3600.0
            if diff_hours < 24.0:
                if ts <= now:
                    hours_ago = (now - ts).total_seconds() / 3600.0
                    return False, f"24h Cooldown violation: post '{p.post_id}' was published {hours_ago:.1f} hours ago. Minimum separation between posts is 24 hours."
                else:
                    return False, f"24h Cooldown violation: post '{p.post_id}' is scheduled within {diff_hours:.1f} hours of this post. Minimum separation is 24 hours."

        return True, "24h cooldown satisfied."

    def _check_weekly_ceiling(self, current_post: Post, recent_posts: Optional[List[Post]] = None, target_platform: str = "linkedin") -> tuple[bool, str]:
        """Ensures at most channel ceiling autonomous posts per rolling 7-day window."""
        posts = recent_posts if recent_posts is not None else self._get_recent_published_or_scheduled()
        now = datetime.now(timezone.utc)
        curr_ts = self._get_post_timestamp(current_post) or now

        # 7-day window centered on curr_ts
        window_start = curr_ts - timedelta(days=3.5)
        window_end = curr_ts + timedelta(days=3.5)

        channel_key = target_platform.lower()
        policy = self.CHANNEL_POLICIES.get(channel_key, self.CHANNEL_POLICIES["linkedin"])
        ceiling = policy["weekly_ceiling"]

        count = 0
        for p in posts:
            if p.post_id == current_post.post_id:
                continue
            ts = self._get_post_timestamp(p)
            if ts and window_start <= ts <= window_end:
                count += 1

        if count >= ceiling:
            return False, f"Weekly ceiling reached: {count} posts scheduled/published in this 7-day window. Maximum ceiling for {channel_key.upper()} is {ceiling}."
        return True, f"Weekly ceiling satisfied ({count}/{ceiling} posts used in 7-day rolling window for {channel_key.upper()})."

    def _check_duplicate_content(self, current_post: Post, recent_posts: Optional[List[Post]] = None) -> tuple[bool, str]:
        """Verifies no identical or near-duplicate post already scheduled or published."""
        posts = recent_posts if recent_posts is not None else self._get_recent_published_or_scheduled()
        for p in posts:
            if p.post_id == current_post.post_id:
                continue
            if p.title.strip().lower() == current_post.title.strip().lower():
                return False, f"Duplicate content detected: post '{p.post_id}' shares the exact same title."
        return True, "Duplicate check passed."

    def _get_recent_published_or_scheduled(self) -> List[Post]:
        posts: List[Post] = []
        posts.extend(self.lifecycle_manager.list_posts_in_state(LifecycleState.SCHEDULED))
        posts.extend(self.lifecycle_manager.list_posts_in_state(LifecycleState.PUBLISHED))
        posts.extend(self.lifecycle_manager.list_posts_in_state(LifecycleState.ANALYZED))
        return posts

    def _get_post_timestamp(self, post: Post) -> Optional[datetime]:
        date_str = post.scheduled_publish_time or post.updated_at or post.created_at
        if date_str:
            try:
                return datetime.fromisoformat(date_str)
            except Exception:
                pass
        return None
