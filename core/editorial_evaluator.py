"""Editorial evaluation engine for Serhat's personal media agency.

Performs lexical slop analysis, domain Design Rule Checks (DRC),
substance scoring, and generates formal Editorial Scorecards.
"""

from __future__ import annotations
import re
import uuid
from typing import List, Dict, Any, Tuple
from core.models import (
    Post,
    EditorialScorecard,
    EditorialVerdict,
    Scores,
    SlopAnalysis,
    DomainDRCChecks,
    GroundingVerification
)
from core.grounding_engine import GroundingEngine


BANNED_BUZZWORDS = [
    r"thrilled to announce",
    r"thrilled to share",
    r"super excited",
    r"excited to share",
    r"in today'?s (?:fast-paced|rapidly evolving) (?:world|tech|market)",
    r"game-?changer",
    r"revolutionary",
    r"paradigm shift",
    r"supercharge",
    r"unleash",
    r"delve into",
    r"a testament to",
    r"let that sink in",
    r"here'?s what nobody tells you",
    r"agree\??\s*$",
    r"thoughts\??\s*$",
    r"drop a comment below",
    r"type ['\"]?[a-z]+['\"]? to get",
    r"comment ['\"]?[a-z]+['\"]? below",
]

DECORATIVE_EMOJIS = ["🚀", "💡", "🔥", "👉", "📈", "✨", "🎯", "💥", "👇"]
EMOJI_PATTERN = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)


class EditorialEvaluator:
    def __init__(self, grounding_engine: GroundingEngine):
        self.grounding_engine = grounding_engine

    def analyze_slop(self, text: str) -> SlopAnalysis:
        text_lower = text.lower()
        detected_buzzwords: List[str] = []

        for pattern in BANNED_BUZZWORDS:
            matches = re.findall(pattern, text_lower)
            if matches:
                detected_buzzwords.extend(matches)

        # Count emojis
        emojis_found = EMOJI_PATTERN.findall(text)
        emoji_count = len(emojis_found)

        # Check decorative emojis
        has_decorative = any(e in text for e in DECORATIVE_EMOJIS)
        if has_decorative:
            detected_buzzwords.append("decorative_clickbait_emojis")

        # Slop score calculation
        slop_score = float(len(detected_buzzwords))
        if emoji_count > 2:
            slop_score += (emoji_count - 2) * 1.5

        return SlopAnalysis(
            slop_score=round(slop_score, 2),
            detected_buzzwords=detected_buzzwords,
            emoji_count=emoji_count,
            slop_detected=slop_score > 0
        )

    def run_domain_drc(self, post: Post) -> DomainDRCChecks:
        text_lower = post.content_text.lower()
        checks_run: List[str] = []
        violations: List[str] = []

        # 1. Embedded: Mains AC Safety Check
        if any(w in text_lower for w in ["mains", "110v", "220v", "230v", "ac circuit"]):
            checks_run.append("embedded_mains_ac_isolation")
            if not any(w in text_lower for w in ["isolation", "optocoupler", "relay", "galvanic", "isolated"]):
                violations.append("DRC VIOLATION: Project mentions mains AC voltage without documenting galvanic isolation or safety barriers.")

        # 2. Embedded: LiPo / Battery Safety Check
        if any(w in text_lower for w in ["lipo", "li-ion", "18650", "lithium polymer"]):
            checks_run.append("embedded_lipo_protection")
            if not any(w in text_lower for w in ["bms", "protection circuit", "pcm", "undervoltage", "cutoff"]):
                violations.append("DRC VIOLATION: LiPo battery usage mentioned without documenting BMS or over-discharge protection.")

        # 3. Embedded: Logic Level Matching
        if "esp32" in text_lower and "5v" in text_lower:
            checks_run.append("embedded_esp32_5v_level_matching")
            if not any(w in text_lower for w in ["level shifter", "divider", "shifter", "3.3v tolerant"]):
                violations.append("DRC WARNING: ESP32 paired with 5V logic without explicit reference to level shifting.")

        # 4. Robotics: Sim-vs-Real Transparency
        if any(w in text_lower for w in ["gazebo", "isaac sim", "pybullet", "simulation"]):
            checks_run.append("robotics_sim_transparency")
            if not any(w in text_lower for w in ["in simulation", "simulated", "virtual", "physics engine"]):
                violations.append("DRC VIOLATION: Simulation environment mentioned but results are ambiguous regarding physical hardware implementation.")

        # 5. AI Agents: Benchmark Integrity
        if any(w in text_lower for w in ["faster", "speedup", "latency", "accuracy", "benchmarked"]):
            checks_run.append("ai_benchmark_integrity")
            # Should have explicit metric units
            if not any(w in text_lower for w in ["ms", "fps", "tokens/s", "%", "microseconds", "kb"]):
                violations.append("DRC VIOLATION: Benchmark claims made without specific quantitative units (ms, fps, tokens/s, etc.).")

        passed = len(violations) == 0
        return DomainDRCChecks(
            passed=passed,
            checks_run=checks_run,
            violations=violations
        )

    def calculate_scores(self, post: Post, slop: SlopAnalysis, drc: DomainDRCChecks, grounding: GroundingVerification) -> Scores:
        # Technical Rigor: (0-25)
        rigor = 24.0
        if len(post.citations) < 2:
            rigor -= 2.0
        if drc.violations:
            rigor -= 10.0
        rigor = max(0.0, min(25.0, rigor))

        # Clarity & Flow: (0-25)
        clarity = 23.0
        words = len(post.content_text.split())
        if words < 120:
            clarity -= 3.0
        elif words > 450:
            clarity -= 2.0
        clarity = max(0.0, min(25.0, clarity))

        # Visual Utility: (0-25)
        if not post.media_assets:
            visual = 10.0  # severely penalized for missing technical visual
        else:
            visual = 24.0
        visual = max(0.0, min(25.0, visual))

        # Reader ROI: (0-25)
        roi = 23.0
        if slop.slop_detected:
            roi -= (slop.slop_score * 3.0)
        roi = max(0.0, min(25.0, roi))

        composite = round(rigor + clarity + visual + roi, 1)

        return Scores(
            technical_rigor=round(rigor, 1),
            clarity_and_flow=round(clarity, 1),
            visual_utility=round(visual, 1),
            reader_roi=round(roi, 1),
            composite_score=composite
        )

    def evaluate_post(self, post: Post) -> EditorialScorecard:
        slop = self.analyze_slop(post.content_text)
        drc = self.run_domain_drc(post)
        grounding = self.grounding_engine.verify_post_grounding(post)
        scores = self.calculate_scores(post, slop, drc, grounding)

        # Verdict logic
        if slop.slop_detected or not drc.passed:
            verdict = EditorialVerdict.REJECTED_SLOP_OR_DRC
        elif scores.composite_score < 85.0 or grounding.grounding_percentage < 100.0:
            verdict = EditorialVerdict.REVISE_REQUIRED
        else:
            verdict = EditorialVerdict.PASSED_EDITORIAL

        return EditorialScorecard(
            evaluation_id=f"eval_{uuid.uuid4().hex[:12]}",
            post_id=post.post_id,
            scores=scores,
            slop_analysis=slop,
            domain_drc_checks=drc,
            grounding_verification=grounding,
            verdict=verdict
        )
