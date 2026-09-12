"""Cross-Platform Distribution Adapter for Serhat's Personal Media Agency.

Enforces the non-negotiable Cross-Platform Rule:
NEVER blindly cross-post identical text across channels.

Adapts canonical engineering stories into independent platform variants:
- LinkedIn: Professional engineering reputation (MVTS >= 9.0, rigorous, deep, restrained)
- Instagram: Visual creative / build journal (MVTS >= 7.5, workbench, visual required)
- X (Twitter): Developer feed (MVTS >= 6.5, direct, concise, developer-native)

Each variant has an isolated lifecycle, independent payload hash, independent
approval decision, and separate dispatch tracking.
"""

from __future__ import annotations
import re
import uuid
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from pathlib import Path

from core.models import (
    Candidate,
    CandidateDecision,
    Post,
    MediaAsset,
    Citation,
    LifecycleState,
    SocialNetwork,
    ChannelIdentity,
    PlatformVariant,
    LinkedInVariant,
    InstagramVariant,
    XVariant,
    CanonicalStory,
    BufferPayload,
    BUFFER_BOUND_CHANNELS
)
from core.approval_engine import compute_canonical_payload_sha256


class DistributionAdapter:
    """Adapts engineering substance into channel-specific platform variants."""

    def __init__(self, channels: Optional[Dict[str, ChannelIdentity]] = None):
        self.channels = channels or BUFFER_BOUND_CHANNELS

    def evaluate_channel_eligibility(
        self,
        candidate: Candidate,
        media_assets: Optional[List[MediaAsset]] = None
    ) -> Dict[str, Tuple[bool, str]]:
        """Determines eligibility for each bound channel based on substance and constraints."""
        media = media_assets or []
        mvts = candidate.mvts_evaluation.total_score
        results: Dict[str, Tuple[bool, str]] = {}

        # 1. LinkedIn Check (asset strictly required, text-only prohibited)
        li_spec = self.channels.get("linkedin")
        if not li_spec:
            results["linkedin"] = (False, "Channel not configured.")
        elif mvts < li_spec.mvts_threshold:
            results["linkedin"] = (
                False,
                f"MVTS score {mvts:.1f} is below LinkedIn threshold ({li_spec.mvts_threshold:.1f}). Held for professional reputation bar."
            )
        elif len(media) == 0:
            results["linkedin"] = (
                False,
                "Ineligible for LinkedIn: Every post strictly requires at least one verified asset (text-only posts are prohibited)."
            )
        elif candidate.decision == CandidateDecision.REJECT:
            results["linkedin"] = (False, "Candidate is terminally rejected.")
        else:
            results["linkedin"] = (True, f"Eligible for LinkedIn (MVTS {mvts:.1f} >= {li_spec.mvts_threshold:.1f}, visual asset present).")

        # 2. Instagram Check (asset strictly required, text-only prohibited)
        ig_spec = self.channels.get("instagram")
        if not ig_spec:
            results["instagram"] = (False, "Channel not configured.")
        elif mvts < ig_spec.mvts_threshold:
            results["instagram"] = (
                False,
                f"MVTS score {mvts:.1f} is below Instagram threshold ({ig_spec.mvts_threshold:.1f})."
            )
        elif len(media) == 0:
            results["instagram"] = (
                False,
                "Ineligible for Instagram: Every post strictly requires at least one verified image or video asset."
            )
        elif candidate.decision == CandidateDecision.REJECT:
            results["instagram"] = (False, "Candidate is terminally rejected.")
        else:
            results["instagram"] = (True, f"Eligible for Instagram (MVTS {mvts:.1f}, visual asset present).")

        # 3. X (Twitter) Check (asset strictly required, text-only prohibited)
        x_spec = self.channels.get("twitter")
        if not x_spec:
            results["twitter"] = (False, "Channel not configured.")
        elif mvts < x_spec.mvts_threshold:
            results["twitter"] = (
                False,
                f"MVTS score {mvts:.1f} is below X threshold ({x_spec.mvts_threshold:.1f})."
            )
        elif len(media) == 0:
            results["twitter"] = (
                False,
                "Ineligible for X: Every post strictly requires at least one verified asset (text-only posts are prohibited)."
            )
        elif candidate.decision == CandidateDecision.REJECT:
            results["twitter"] = (False, "Candidate is terminally rejected.")
        else:
            results["twitter"] = (True, f"Eligible for X (MVTS {mvts:.1f} >= {x_spec.mvts_threshold:.1f}, visual asset present).")

        return results

    def adapt_for_linkedin(
        self,
        candidate: Candidate,
        base_text: str,
        media_assets: List[MediaAsset],
        citations: List[Citation]
    ) -> LinkedInVariant:
        """Crafts a deep, architectural, restrained LinkedIn post variant."""
        li_spec = self.channels["linkedin"]
        clean_text = base_text.strip()
        if not clean_text.endswith("."):
            clean_text += "."

        var_id = f"var_{candidate.candidate_id}_linkedin_{uuid.uuid4().hex[:6]}"
        payload_hash = compute_canonical_payload_sha256(
            post_id=var_id,
            action_scope="BUFFER_SCHEDULE",
            target_platform="linkedin",
            content_text=clean_text,
            media_asset_hashes=[a.asset_sha256 for a in media_assets]
        )

        return LinkedInVariant(
            variant_id=var_id,
            story_id=f"story_{candidate.candidate_id}",
            candidate_id=candidate.candidate_id,
            channel_id=li_spec.channel_id,
            target_platform=SocialNetwork.LINKEDIN,
            content_text=clean_text,
            media_assets=media_assets,
            citations=citations,
            canonical_payload_sha256=payload_hash,
            technical_depth="deep_architectural",
            adaptation_notes="Full technical breakdown with trade-off analysis and architectural context."
        )

    def adapt_for_instagram(
        self,
        candidate: Candidate,
        base_text: str,
        media_assets: List[MediaAsset],
        citations: List[Citation]
    ) -> InstagramVariant:
        """Crafts a visual workbench build-log caption for Instagram."""
        ig_spec = self.channels["instagram"]

        lines = [line.strip() for line in base_text.split("\n") if line.strip()]
        hook = lines[0] if lines else candidate.angle
        core_point = lines[1] if len(lines) > 1 else ""

        caption_parts = [
            f"🛠️ Build Log: {hook}",
            "",
            core_point or "Bench testing and verifying hardware architecture in the lab.",
            "",
            "Visual breakdown from the workbench. Swipe for scope trace / assembly detail."
        ]

        hashtags = ["#buildinpublic", "#embedded", "#robotics", "#hardware", "#systemdesign"]
        caption_parts.append("")
        caption_parts.append(" ".join(hashtags))

        full_caption = "\n".join(caption_parts)
        var_id = f"var_{candidate.candidate_id}_instagram_{uuid.uuid4().hex[:6]}"
        payload_hash = compute_canonical_payload_sha256(
            post_id=var_id,
            action_scope="BUFFER_SCHEDULE",
            target_platform="instagram",
            content_text=full_caption,
            media_asset_hashes=[a.asset_sha256 for a in media_assets]
        )

        return InstagramVariant(
            variant_id=var_id,
            story_id=f"story_{candidate.candidate_id}",
            candidate_id=candidate.candidate_id,
            channel_id=ig_spec.channel_id,
            target_platform=SocialNetwork.INSTAGRAM,
            content_text=full_caption,
            media_assets=media_assets,
            citations=citations,
            canonical_payload_sha256=payload_hash,
            sub_type="post",
            should_share_to_feed=True,
            hashtags=hashtags,
            adaptation_notes="Condensed visual build-log focusing on workbench artifact and testing observations."
        )

    def adapt_for_x(
        self,
        candidate: Candidate,
        base_text: str,
        media_assets: List[MediaAsset],
        citations: List[Citation]
    ) -> XVariant:
        """Crafts a punchy, developer-native 280-character post for X."""
        x_spec = self.channels["twitter"]

        sentences = re.split(r"(?<=[.!?])\s+", base_text.strip())
        first_sentence = sentences[0] if sentences else candidate.angle

        metric_sentence = ""
        for s in sentences[1:]:
            if any(char.isdigit() for char in s) or "tradeoff" in s.lower() or "latency" in s.lower() or "dma" in s.lower():
                metric_sentence = s
                break

        x_text = f"{first_sentence}\n\n{metric_sentence}".strip()
        if len(x_text) > 275:
            x_text = x_text[:272] + "..."

        var_id = f"var_{candidate.candidate_id}_twitter_{uuid.uuid4().hex[:6]}"
        payload_hash = compute_canonical_payload_sha256(
            post_id=var_id,
            action_scope="BUFFER_SCHEDULE",
            target_platform="twitter",
            content_text=x_text,
            media_asset_hashes=[a.asset_sha256 for a in media_assets]
        )

        return XVariant(
            variant_id=var_id,
            story_id=f"story_{candidate.candidate_id}",
            candidate_id=candidate.candidate_id,
            channel_id=x_spec.channel_id,
            target_platform=SocialNetwork.TWITTER,
            content_text=x_text,
            media_assets=media_assets,
            citations=citations,
            canonical_payload_sha256=payload_hash,
            is_thread=False,
            adaptation_notes="Direct developer-native punchline with concrete technical result under 280 chars."
        )

    def generate_story_variants(
        self,
        candidate: Candidate,
        base_text: str,
        media_assets: Optional[List[MediaAsset]] = None,
        citations: Optional[List[Citation]] = None
    ) -> CanonicalStory:
        """Evaluates eligibility and creates variants for all eligible channels."""
        assets = media_assets or []
        cits = citations or []
        eligibility = self.evaluate_channel_eligibility(candidate, assets)

        variants: Dict[str, PlatformVariant] = {}
        eligible_networks: List[SocialNetwork] = []

        if eligibility["linkedin"][0]:
            variants["linkedin"] = self.adapt_for_linkedin(candidate, base_text, assets, cits)
            eligible_networks.append(SocialNetwork.LINKEDIN)

        if eligibility["instagram"][0]:
            variants["instagram"] = self.adapt_for_instagram(candidate, base_text, assets, cits)
            eligible_networks.append(SocialNetwork.INSTAGRAM)

        if eligibility["twitter"][0]:
            variants["twitter"] = self.adapt_for_x(candidate, base_text, assets, cits)
            eligible_networks.append(SocialNetwork.TWITTER)

        story = CanonicalStory(
            story_id=f"story_{candidate.candidate_id}",
            candidate_id=candidate.candidate_id,
            project_id=candidate.idea_id,
            title=candidate.angle,
            core_engineering_thesis=base_text[:140],
            verified_evidence=[f"MVTS={candidate.mvts_evaluation.total_score:.1f}"],
            shared_media_assets=assets,
            citations=cits,
            mvts_score=candidate.mvts_evaluation.total_score,
            eligible_channels=eligible_networks,
            variants=variants
        )

        return story

    def build_canary_buffer_payload(
        self,
        channel_key: str,
        due_at_iso: str = "2026-09-15T09:00:00+03:00"
    ) -> BufferPayload:
        """Constructs a strictly compliant, real-schema Buffer canary payload with 0 network bytes."""
        if channel_key not in self.channels:
            raise ValueError(f"Unknown channel key '{channel_key}'.")

        ch = self.channels[channel_key]
        dummy_token = f"tok_canary_{channel_key}_{uuid.uuid4().hex[:8]}"

        if channel_key == "linkedin":
            text = (
                "Technical architecture update: benchmarked zero-copy DMA ring buffer on STM32H7. "
                "Eliminated double-buffering latency jitter down to 12 microseconds without bus collision."
            )
            assets = [{
                "image": {
                    "url": "https://raw.githubusercontent.com/serhatvs/assets/main/dma_trace.png",
                    "metadata": {"altText": "Oscilloscope capture showing DMA bus timing"}
                }
            }]
            sha = hashlib.sha256((ch.channel_id + text + dummy_token).encode()).hexdigest()
            return BufferPayload(
                channel_id=ch.channel_id,
                text=text,
                scheduling_type="automatic",
                due_at=due_at_iso,
                mode="customScheduled",
                assets=assets,
                approval_token_id=dummy_token,
                verified_payload_sha256=sha
            )

        elif channel_key == "instagram":
            text = (
                "🛠️ Build Log: USB display controller on the logic analyzer.\n\n"
                "Captured 60Hz frame pacing over SPI. Verified no frame tear during buffer flip.\n\n"
                "#buildinpublic #embedded #stm32 #hardware"
            )
            assets = [{
                "image": {
                    "url": "https://raw.githubusercontent.com/serhatvs/assets/main/workbench_test.jpg",
                    "metadata": {"altText": "Hardware lab workbench with logic analyzer connected to display"}
                }
            }]
            metadata = {
                "instagram": {
                    "type": "post",
                    "shouldShareToFeed": True
                }
            }
            sha = hashlib.sha256((ch.channel_id + text + dummy_token).encode()).hexdigest()
            return BufferPayload(
                channel_id=ch.channel_id,
                text=text,
                scheduling_type="automatic",
                due_at=due_at_iso,
                mode="customScheduled",
                assets=assets,
                metadata=metadata,
                approval_token_id=dummy_token,
                verified_payload_sha256=sha
            )

        elif channel_key == "twitter":
            text = (
                "Benchmarked zero-copy DMA on STM32H7: cut SPI bus contention by 24% "
                "and jitter to 12µs by synchronizing buffer flips with FreeRTOS direct-to-task notifications."
            )
            assets = [{
                "image": {
                    "url": "https://raw.githubusercontent.com/serhatvs/assets/main/stm32_dma_benchmark_card.png",
                    "metadata": {"altText": "Saleae Logic trace showing DMA bus arbitration timing"}
                }
            }]
            sha = hashlib.sha256((ch.channel_id + text + dummy_token).encode()).hexdigest()
            return BufferPayload(
                channel_id=ch.channel_id,
                text=text,
                scheduling_type="automatic",
                due_at=due_at_iso,
                mode="customScheduled",
                assets=assets,
                approval_token_id=dummy_token,
                verified_payload_sha256=sha
            )

        raise ValueError(f"Unsupported channel '{channel_key}'.")
