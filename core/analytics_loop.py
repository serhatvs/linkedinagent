"""Post-publish Analytics Loop and Checkpoints Engine for Serhat's Personal Media Agency.

Executes post-publish evaluations at ~24h, ~72h, and 7d checkpoints.
Maintains version tracking:
- editorial_policy_version
- autonomy_policy_version
- analytics_model_version
Updates persistent memory/lessons_learned.json with verified qualitative takeaways.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from core.models import Post, LifecycleState


ANALYTICS_MODEL_VERSION = "v1.0.0-phase3"
EDITORIAL_POLICY_VERSION = "v1.0.0-phase3"
AUTONOMY_POLICY_VERSION = "v1.0.0-phase3"


class AnalyticsFeedbackLoop:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.reports_dir = workspace_root / "analytics" / "reports"
        self.lessons_path = workspace_root / "memory" / "lessons_learned.json"
        self.editorial_insights_path = workspace_root / "memory" / "editorial_insights.json"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def record_checkpoint(
        self,
        post: Post,
        checkpoint_window: str,  # "24H", "72H", "7D"
        metrics: Dict[str, Any],
        qualitative_notes: str
    ) -> Dict[str, Any]:
        """Records an evaluation checkpoint for a published post."""
        report_id = f"eval_{post.post_id}_{checkpoint_window.lower()}"
        report = {
            "report_id": report_id,
            "post_id": post.post_id,
            "title": post.title,
            "pillar": post.pillar,
            "checkpoint": checkpoint_window,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "versions": {
                "editorial_policy_version": EDITORIAL_POLICY_VERSION,
                "autonomy_policy_version": AUTONOMY_POLICY_VERSION,
                "analytics_model_version": ANALYTICS_MODEL_VERSION
            },
            "metrics": metrics,
            "qualitative_notes": qualitative_notes
        }

        out_path = self.reports_dir / f"{report_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        return report

    def update_lessons_learned(self, new_lesson: str, evidence: str) -> None:
        """Appends an empirical lesson learned to persistent memory."""
        lessons = []
        if self.lessons_path.exists():
            try:
                with open(self.lessons_path, "r", encoding="utf-8") as f:
                    lessons = json.load(f)
            except Exception:
                lessons = []

        lessons.append({
            "lesson": new_lesson,
            "evidence": evidence,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "model_version": ANALYTICS_MODEL_VERSION
        })

        with open(self.lessons_path, "w", encoding="utf-8") as f:
            json.dump(lessons, f, indent=2)
