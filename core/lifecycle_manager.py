"""Lifecycle state machine manager for Serhat's personal media agency.

Enforces valid sequential state transitions, atomic file persistence,
optimistic concurrency control (state_version), and NO-OP recording.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from core.models import LifecycleState, Post, Idea, Candidate


VALID_TRANSITIONS: Dict[LifecycleState, List[LifecycleState]] = {
    LifecycleState.IDEA: [LifecycleState.CANDIDATE],
    LifecycleState.CANDIDATE: [LifecycleState.DRAFT],
    LifecycleState.DRAFT: [LifecycleState.REVIEWED, LifecycleState.DRAFT],
    LifecycleState.REVIEWED: [LifecycleState.AWAITING_APPROVAL, LifecycleState.DRAFT],
    LifecycleState.AWAITING_APPROVAL: [LifecycleState.APPROVED, LifecycleState.DRAFT],
    LifecycleState.APPROVED: [LifecycleState.SCHEDULED, LifecycleState.DRAFT],
    LifecycleState.SCHEDULED: [LifecycleState.PUBLISHED, LifecycleState.DRAFT],
    LifecycleState.PUBLISHED: [LifecycleState.ANALYZED],
    LifecycleState.ANALYZED: []
}

STAGE_DIR_MAP: Dict[LifecycleState, str] = {
    LifecycleState.IDEA: "01_ideas",
    LifecycleState.CANDIDATE: "02_candidates",
    LifecycleState.DRAFT: "03_drafts",
    LifecycleState.REVIEWED: "04_reviewed",
    LifecycleState.AWAITING_APPROVAL: "05_awaiting_approval",
    LifecycleState.APPROVED: "06_approved",
    LifecycleState.SCHEDULED: "07_scheduled",
    LifecycleState.PUBLISHED: "08_published",
    LifecycleState.ANALYZED: "09_analyzed"
}


class LifecycleManager:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.lifecycle_dir = workspace_root / "lifecycle"
        self._ensure_directories()

    def _ensure_directories(self):
        for folder_name in STAGE_DIR_MAP.values():
            (self.lifecycle_dir / folder_name).mkdir(parents=True, exist_ok=True)

    def _atomic_write_json(self, target_path: Path, data: Dict[str, Any]):
        tmp_path = target_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        # os.replace is atomic on both POSIX and Windows
        os.replace(tmp_path, target_path)

    def save_idea(self, idea: Idea) -> Path:
        path = self.lifecycle_dir / "01_ideas" / f"{idea.idea_id}.json"
        self._atomic_write_json(path, idea.model_dump())
        return path

    def save_candidate(self, candidate: Candidate) -> Path:
        path = self.lifecycle_dir / "02_candidates" / f"{candidate.candidate_id}.json"
        self._atomic_write_json(path, candidate.model_dump())
        return path

    def create_initial_draft(self, post: Post) -> Path:
        post.lifecycle_state = LifecycleState.DRAFT
        post.state_version = 1
        post.created_at = datetime.now(timezone.utc).isoformat()
        post.updated_at = post.created_at

        path = self.lifecycle_dir / STAGE_DIR_MAP[LifecycleState.DRAFT] / f"{post.post_id}.json"
        self._atomic_write_json(path, post.model_dump())
        return path

    def get_post(self, post_id: str, state: Optional[LifecycleState] = None) -> Optional[Post]:
        """Finds post across lifecycle folders."""
        states_to_check = [state] if state else list(LifecycleState)[2:]  # Draft onwards
        for st in states_to_check:
            folder = self.lifecycle_dir / STAGE_DIR_MAP[st]
            p_file = folder / f"{post_id}.json"
            if p_file.exists():
                with open(p_file, "r", encoding="utf-8") as f:
                    return Post.model_validate(json.load(f))
        return None

    def transition(self, post_id: str, target_state: LifecycleState, expected_version: int) -> Post:
        """Executes a valid state transition with optimistic concurrency control."""
        current_post = self.get_post(post_id)
        if not current_post:
            raise FileNotFoundError(f"Post with ID {post_id} not found in lifecycle.")

        # Optimistic concurrency check
        if current_post.state_version != expected_version:
            raise ValueError(
                f"Concurrency conflict on {post_id}: expected version {expected_version}, found {current_post.state_version}"
            )

        current_state = current_post.lifecycle_state
        allowed_targets = VALID_TRANSITIONS.get(current_state, [])
        if target_state not in allowed_targets:
            raise ValueError(
                f"Illegal state transition for {post_id}: cannot transition from {current_state.value} to {target_state.value}."
            )

        # Remove from old directory
        old_folder = self.lifecycle_dir / STAGE_DIR_MAP[current_state]
        old_file = old_folder / f"{post_id}.json"

        # Update post attributes
        current_post.lifecycle_state = target_state
        current_post.state_version += 1
        current_post.updated_at = datetime.now(timezone.utc).isoformat()

        # Write to new directory
        new_folder = self.lifecycle_dir / STAGE_DIR_MAP[target_state]
        new_file = new_folder / f"{post_id}.json"
        self._atomic_write_json(new_file, current_post.model_dump())

        # Clean up old file
        if old_file.exists() and old_file != new_file:
            old_file.unlink()

        return current_post

    def save_post_in_place(self, post: Post) -> Post:
        """Saves post metadata (scorecard_id, approval_request_id, etc.) without
        changing lifecycle state or bumping state_version. Use for attaching
        review results, approval IDs, or scheduling metadata to a post that
        should stay in its current lifecycle stage."""
        post.updated_at = datetime.now(timezone.utc).isoformat()
        target_file = self.lifecycle_dir / STAGE_DIR_MAP[post.lifecycle_state] / f"{post.post_id}.json"
        self._atomic_write_json(target_file, post.model_dump())
        return post

    def update_post_content(self, post: Post, expected_version: int) -> Post:
        """Updates post copy/assets and revokes approvals if previously approved.

        This method is for *content-altering* changes (text, media). It bumps
        state_version and demotes the post back to DRAFT if it had already
        passed editorial review or approval — because the approved hash is now
        invalid.

        For metadata-only writes (scorecard_id, approval_request_id, etc.),
        use ``save_post_in_place`` instead.
        """
        existing = self.get_post(post.post_id)
        if not existing:
            raise FileNotFoundError(f"Post {post.post_id} not found.")

        if existing.state_version != expected_version:
            raise ValueError(f"Version mismatch: expected {expected_version}, found {existing.state_version}")

        # Content-altering change while in a post-review state → demote to DRAFT
        if existing.lifecycle_state in [LifecycleState.REVIEWED, LifecycleState.AWAITING_APPROVAL, LifecycleState.APPROVED]:
            old_folder = self.lifecycle_dir / STAGE_DIR_MAP[existing.lifecycle_state]
            old_file = old_folder / f"{post.post_id}.json"
            if old_file.exists():
                old_file.unlink()
            post.lifecycle_state = LifecycleState.DRAFT
            post.scorecard_id = None
            post.approval_request_id = None

        post.state_version += 1
        post.updated_at = datetime.now(timezone.utc).isoformat()

        target_file = self.lifecycle_dir / STAGE_DIR_MAP[post.lifecycle_state] / f"{post.post_id}.json"
        self._atomic_write_json(target_file, post.model_dump())
        return post

    def list_posts_in_state(self, state: LifecycleState) -> List[Post]:
        folder = self.lifecycle_dir / STAGE_DIR_MAP[state]
        posts = []
        for file in folder.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    posts.append(Post.model_validate(json.load(f)))
            except Exception:
                pass
        return posts
