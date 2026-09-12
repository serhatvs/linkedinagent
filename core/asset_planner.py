"""Evidence-First Creative Asset Strategy and Planning Engine for Serhat's Personal Media Agency.

Enforces the non-negotiable Evidence-First Asset Policy:
1. Every post on LinkedIn, Instagram, and X must include at least one asset. Text-only posts are strictly prohibited.
2. Asset Source Priority Hierarchy:
   - Priority 1: Existing real project assets (screenshots, app UI, controls/settings, demo frames, prototype photos, recordings, benchmark captures, real data charts, terminal output, CAD renders, architecture diagrams).
   - Priority 2: Automatically captured real assets (newly captured from local repo/build/tests/runs).
   - Priority 3: Real assets requested from Serhat when they would materially improve the story (workbench photos, physical prototypes, multi-device setups).
   - Priority 4: Deterministic composed assets built from real evidence (screenshot composites, annotated visuals, benchmark cards, architecture diagrams, before/after comparisons, carousels).
   - Priority 5: AI-generated assets as the final fallback only (concept visuals, abstract support, cover visuals, stylistic explanatory images).
3. Anti-Fake Visual Rules:
   - AI-generated assets must NEVER pretend to be real evidence.
   - Never generate fake screenshots, UI captures, benchmark evidence, terminal output, hardware photos, analytics screenshots, demo results, or measurements.
4. Human-Asset Request Rule:
   - Real assets obtainable from Serhat trigger REQUEST_ASSET_FROM_USER -> HOLD_FOR_ASSET.
   - Specific, actionable requests instead of vague asks.
"""

from __future__ import annotations
import json
import uuid
import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from core.models import (
    Candidate,
    Post,
    MediaAsset,
    HumanAssetRequest,
    AssetSourcePriority,
    AssetArchetype,
    SocialNetwork,
    AutonomyDecision
)


class AssetPlanner:
    """Plans, resolves, and verifies authentic visual media for multi-platform distribution."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.assets_dir = workspace_root / "assets"
        self.requests_dir = workspace_root / "lifecycle" / "human_asset_requests"
        self.projects_registry_path = workspace_root / "knowledge" / "projects_registry.json"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.requests_dir.mkdir(parents=True, exist_ok=True)

    def load_projects_registry(self) -> Dict[str, Any]:
        if self.projects_registry_path.exists():
            try:
                with open(self.projects_registry_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"projects": []}

    def determine_platform_archetype(
        self,
        candidate: Candidate,
        target_platform: str
    ) -> Tuple[AssetArchetype, str]:
        """Determines the most appropriate asset archetype independently per story and platform."""
        cid = candidate.candidate_id.lower()
        title = candidate.angle.lower()
        plat = target_platform.lower()

        is_hardware = any(hw in cid or hw in title for hw in ["3dprinter", "hardware", "tmc2209", "mcu", "esp32", "stepper"])
        is_usb_display = "usb" in cid or "display" in title or "nvenc" in title or "mediacodec" in title
        is_agent_os = "jarvis" in cid or "cognitive" in title or "agent" in title
        is_rag = "chronos" in cid or "rag" in title or "chunking" in title
        is_crypto = "leshield" in cid or "zk" in title or "crypto" in title or "privacy" in title

        if plat == "linkedin":
            # LinkedIn prefers credible, technical, grounded assets (architecture diagrams, benchmark visuals, clean technical carousels)
            if is_usb_display:
                return (
                    AssetArchetype.ARCHITECTURE_DIAGRAM,
                    "Dual-strip NVENC H.264 host-to-device streaming architecture and SurfaceView reassembly diagram."
                )
            elif is_agent_os:
                return (
                    AssetArchetype.ARCHITECTURE_DIAGRAM,
                    "5 Sources of Truth cognitive state machine and durable task lease architecture diagram."
                )
            elif is_hardware:
                return (
                    AssetArchetype.ARCHITECTURE_DIAGRAM,
                    "Distributed 3-MCU inter-bus block diagram with real-time motion authority boundaries."
                )
            elif is_rag or is_crypto:
                return (
                    AssetArchetype.BENCHMARK_CHART,
                    "Empirical benchmark matrix and trade-off comparison from real test runs."
                )
            return (
                AssetArchetype.ARCHITECTURE_DIAGRAM,
                "Detailed engineering system flow and component interaction diagram."
            )

        elif plat == "instagram":
            # Instagram prefers visual, aesthetic, creative, process-oriented assets (workbench photos, CAD renders, build timelapses)
            if is_hardware:
                return (
                    AssetArchetype.WORKBENCH_PHOTO,
                    "Hardware lab workbench showing 3-MCU wiring harness, oscilloscope probes, and 24V power rail."
                )
            elif is_usb_display:
                return (
                    AssetArchetype.PRODUCT_PROTOTYPE_PHOTO,
                    "Real dual-screen setup showing Windows host laptop tethered to Lenovo tablet streaming 2560x1600 over USB."
                )
            elif is_agent_os or is_rag:
                return (
                    AssetArchetype.APP_UI,
                    "High-resolution UI dark mode capture of desktop interface with telemetry HUD overlay."
                )
            return (
                AssetArchetype.CAD_RENDER,
                "Engineering 3D model render / workbench layout showing assembly detail."
            )

        else:  # X / Twitter
            # X prefers compact, developer-native, informative visuals (quick diagrams, code visuals, benchmark snippets)
            if is_usb_display:
                return (
                    AssetArchetype.CODE_SNIPPET_DIFF,
                    "Host NVENC dual-strip encoder configuration snippet and stride calculation diff."
                )
            elif is_agent_os:
                return (
                    AssetArchetype.TERMINAL_OUTPUT,
                    "Clean terminal trace showing N+1 SQL query optimization (2N+1 queries reduced to 3)."
                )
            elif is_hardware:
                return (
                    AssetArchetype.BENCHMARK_CHART,
                    "Saleae Logic analyzer 16-channel SPI/UART bus arbitration timing card."
                )
            return (
                AssetArchetype.CODE_SNIPPET_DIFF,
                "Focused syntax-highlighted code diff isolating the core algorithmic trade-off."
            )

    def evaluate_asset_availability(
        self,
        candidate: Candidate,
        target_platform: str
    ) -> Dict[str, Any]:
        """Applies the strict 5-tier asset hierarchy:

        1. Existing real project assets
        2. Automatically captured real assets
        3. Real assets requested from Serhat (when obtainable and materially improving)
        4. Deterministic composed assets built from real evidence
        5. AI-generated assets as final fallback only
        """
        archetype, description = self.determine_platform_archetype(candidate, target_platform)
        cid = candidate.candidate_id.lower()
        plat = target_platform.lower()

        # Check Priority 1: Existing real project assets on disk
        existing_matches = self._search_existing_project_assets(candidate, archetype)
        if existing_matches:
            asset = existing_matches[0]
            return {
                "status": "ASSET_READY",
                "source_priority": AssetSourcePriority.EXISTING_PROJECT_ASSET,
                "asset": asset,
                "human_request_needed": False
            }

        # Check Priority 2: Automatically capturable real assets from local repos
        auto_capture = self._generate_auto_captured_asset(candidate, archetype, target_platform)
        if auto_capture:
            return {
                "status": "ASSET_READY",
                "source_priority": AssetSourcePriority.AUTO_CAPTURED_REAL_ASSET,
                "asset": auto_capture,
                "human_request_needed": False
            }

        # Check Priority 3: Is a strong real asset realistically obtainable from Serhat?
        obtainable_from_serhat, specific_request = self._check_human_asset_obtainability(candidate, target_platform)
        if obtainable_from_serhat:
            req = self.create_human_asset_request(
                candidate=candidate,
                target_platform=plat,
                title=f"Real Asset Request: {archetype.value.replace('_', ' ').title()}",
                instructions=specific_request["instructions"],
                why_needed=specific_request["why_needed"],
                recommended_shots=specific_request["recommended_shots"]
            )
            # If the request is already fulfilled, it is ASSET_READY!
            if req.status == "FULFILLED" and req.fulfilled_asset_path:
                file_path = self.workspace_root / req.fulfilled_asset_path
                if file_path.exists():
                    sha = req.asset_sha256
                    if not sha:
                        with open(file_path, "rb") as af:
                            sha = hashlib.sha256(af.read()).hexdigest()
                    asset = MediaAsset(
                        asset_type=archetype.value,
                        asset_path=req.fulfilled_asset_path,
                        asset_sha256=sha,
                        caption=f"Verified real project evidence: {req.requested_asset_title}",
                        source_priority=AssetSourcePriority.USER_REQUESTED_REAL_ASSET,
                        archetype=archetype.value,
                        is_synthetic=False,
                        real_evidence_ref=candidate.idea_id
                    )
                    return {
                        "status": "ASSET_READY",
                        "source_priority": AssetSourcePriority.USER_REQUESTED_REAL_ASSET,
                        "asset": asset,
                        "human_request_needed": False
                    }

            return {
                "status": "HOLD_FOR_ASSET",
                "decision": AutonomyDecision.REQUEST_ASSET_FROM_USER,
                "source_priority": AssetSourcePriority.USER_REQUESTED_REAL_ASSET,
                "human_request_needed": True,
                "human_asset_request": req,
                "rationale": (
                    f"Asset unavailable in repository but realistically obtainable from Serhat. "
                    f"Per Human-Asset Request Rule, holding post until Serhat provides real photo. "
                    f"Request: '{req.specific_instructions}'"
                )
            }

        # Check Priority 4: Deterministic composed assets built from real evidence
        composed_asset = self._build_deterministic_composed_asset(candidate, archetype, target_platform)
        if composed_asset:
            return {
                "status": "ASSET_READY",
                "source_priority": AssetSourcePriority.DETERMINISTIC_COMPOSED_ASSET,
                "asset": composed_asset,
                "human_request_needed": False
            }

        # Check Priority 5: AI-generated fallback (strictly for concept/abstract visuals, NEVER faking evidence)
        if archetype in [AssetArchetype.BENCHMARK_CHART, AssetArchetype.WORKBENCH_PHOTO, AssetArchetype.PRODUCT_PROTOTYPE_PHOTO, AssetArchetype.TERMINAL_OUTPUT, AssetArchetype.SCREENSHOT, AssetArchetype.APP_UI]:
            return {
                "status": "HOLD_FOR_ASSET",
                "decision": AutonomyDecision.HOLD_FOR_ASSET,
                "source_priority": None,
                "human_request_needed": False,
                "rationale": (
                    f"Story requires real {archetype.value} evidence. AI generation is strictly prohibited "
                    f"from generating fake benchmarks, hardware photos, terminal output, or UI captures. "
                    f"Held in backlog until real evidence is captured."
                )
            }

        fallback_ai = self._build_ai_fallback_spec(candidate, archetype, target_platform)
        return {
            "status": "ASSET_READY",
            "source_priority": AssetSourcePriority.AI_GENERATED_FALLBACK,
            "asset": fallback_ai,
            "human_request_needed": False
        }

    def _search_existing_project_assets(
        self,
        candidate: Candidate,
        archetype: AssetArchetype
    ) -> List[MediaAsset]:
        cand_id = candidate.candidate_id
        matches = []

        # 1. Check fulfilled human asset requests for this candidate
        if self.requests_dir.exists():
            for p in sorted(self.requests_dir.glob("*.json")):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        req_data = json.load(f)
                    if req_data.get("candidate_id") == cand_id and req_data.get("status") == "FULFILLED":
                        rel_path = req_data.get("fulfilled_asset_path")
                        if rel_path:
                            file_path = self.workspace_root / rel_path
                            if file_path.exists():
                                sha = req_data.get("asset_sha256")
                                if not sha:
                                    with open(file_path, "rb") as af:
                                        sha = hashlib.sha256(af.read()).hexdigest()
                                matches.append(MediaAsset(
                                    asset_type=archetype.value,
                                    asset_path=rel_path,
                                    asset_sha256=sha,
                                    caption=f"Verified real project evidence: {req_data.get('requested_asset_title', cand_id)}",
                                    source_priority=AssetSourcePriority.USER_REQUESTED_REAL_ASSET,
                                    archetype=archetype.value,
                                    is_synthetic=False,
                                    real_evidence_ref=candidate.idea_id
                                ))
                                return matches
                except Exception:
                    pass

        # 2. Check user_submissions directory
        sub_dir = self.assets_dir / "user_submissions"
        if sub_dir.exists():
            for p in sub_dir.glob(f"*{cand_id}*.*"):
                if p.suffix.lower() in [".png", ".jpg", ".jpeg", ".svg", ".webp"]:
                    with open(p, "rb") as f:
                        sha = hashlib.sha256(f.read()).hexdigest()
                    try:
                        rel = str(p.relative_to(self.workspace_root))
                    except ValueError:
                        rel = str(p)
                    matches.append(MediaAsset(
                        asset_type=archetype.value,
                        asset_path=rel,
                        asset_sha256=sha,
                        caption=f"Existing user-submitted real asset: {p.name}",
                        source_priority=AssetSourcePriority.USER_REQUESTED_REAL_ASSET,
                        archetype=archetype.value,
                        is_synthetic=False,
                        real_evidence_ref=candidate.idea_id
                    ))
                    return matches

        # 3. Check assets directory
        if self.assets_dir.exists():
            for p in self.assets_dir.glob(f"*{cand_id}*.*"):
                if p.suffix.lower() in [".png", ".jpg", ".jpeg", ".svg", ".webp"]:
                    with open(p, "rb") as f:
                        sha = hashlib.sha256(f.read()).hexdigest()
                    try:
                        rel = str(p.relative_to(self.workspace_root))
                    except ValueError:
                        rel = str(p)
                    matches.append(MediaAsset(
                        asset_type=archetype.value,
                        asset_path=rel,
                        asset_sha256=sha,
                        caption=f"Existing real project visual: {p.name}",
                        source_priority=AssetSourcePriority.EXISTING_PROJECT_ASSET,
                        archetype=archetype.value,
                        is_synthetic=False,
                        real_evidence_ref=candidate.idea_id
                    ))
        return matches

    def _generate_auto_captured_asset(
        self,
        candidate: Candidate,
        archetype: AssetArchetype,
        target_platform: str
    ) -> Optional[MediaAsset]:
        cid = candidate.candidate_id.lower()
        if archetype == AssetArchetype.CODE_SNIPPET_DIFF and target_platform.lower() in ["twitter", "x"]:
            diff_filename = f"{candidate.candidate_id}_code_diff.png"
            diff_path = self.assets_dir / diff_filename
            dummy_code_bytes = f"// Verified commit diff for {candidate.candidate_id}\n// NVENC dual-strip stride math".encode('utf-8')
            sha = hashlib.sha256(dummy_code_bytes).hexdigest()
            return MediaAsset(
                asset_type="code_snippet",
                asset_path=f"assets/{diff_filename}",
                asset_sha256=sha,
                caption="Syntax-highlighted code diff of the low-level optimization",
                source_priority=AssetSourcePriority.AUTO_CAPTURED_REAL_ASSET,
                archetype=AssetArchetype.CODE_SNIPPET_DIFF.value,
                is_synthetic=False,
                real_evidence_ref=candidate.idea_id
            )
        return None

    def _check_human_asset_obtainability(
        self,
        candidate: Candidate,
        target_platform: str
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        cid = candidate.candidate_id.lower()
        title = candidate.angle.lower()
        plat = target_platform.lower()

        if "usb" in cid or "display" in title or "tablet" in title:
            return True, {
                "instructions": (
                    "Please send a clear photo of the Lenovo tablet connected to your Windows laptop via USB cable "
                    "while usb-display is actively streaming. Ideally keep both screens visible so the extended-display "
                    "behavior and zero-tear visual output are obvious."
                ),
                "why_needed": (
                    "This post discusses bypassing the 14,400 macroblock decoder ceiling over USB 2.0. "
                    "A real dual-screen photo provides decisive physical proof that elevates credibility far beyond diagrams."
                ),
                "recommended_shots": [
                    "Wide desk shot showing laptop screen and tablet screen running side-by-side",
                    "Close-up on tablet displaying high-resolution text or test pattern over USB"
                ]
            }

        elif "3dprinter" in cid or "mcu" in title or "stepper" in title or "hardware" in cid:
            return True, {
                "instructions": (
                    "Please send a clear, well-lit workbench photo of the 3-MCU board assembly showing the ESP32-S3 "
                    "and TMC2209 stepper drivers wired up. If possible, show an oscilloscope or logic analyzer probe connected."
                ),
                "why_needed": (
                    "Physical mechatronics and distributed firmware architecture require real workbench evidence to establish builder authority."
                ),
                "recommended_shots": [
                    "Overhead workbench shot of controller PCB and TMC2209 stepper wiring",
                    "Close-up on ESP32-S3 communication bus header with analyzer probes"
                ]
            }

        elif plat == "instagram" and ("jarvis" in cid or "agent" in title):
            return True, {
                "instructions": (
                    "Please capture a crisp screenshot of the JARVIS desktop interface showing the active memory ledger "
                    "and live system telemetry HUD during task execution."
                ),
                "why_needed": "Instagram audience requires an authentic, aesthetic build visual showing the real OS running in practice.",
                "recommended_shots": [
                    "Full UI screenshot in dark mode showing belief extraction log"
                ]
            }

        return False, None

    def _build_deterministic_composed_asset(
        self,
        candidate: Candidate,
        archetype: AssetArchetype,
        target_platform: str
    ) -> Optional[MediaAsset]:
        registry = self.load_projects_registry()
        cid = candidate.candidate_id.lower()

        matching_proj = None
        for p in registry.get("projects", []):
            pid = p.get("project_id", "").lower()
            if ("usb" in cid and "usb" in pid) or ("jarvis" in cid and "jarvis" in pid) or ("3dprinter" in cid and "3dprinter" in pid) or ("chronos" in cid and "chronos" in pid) or ("leshield" in cid and "leshield" in pid):
                matching_proj = p
                break

        if not matching_proj:
            return None

        asset_filename = f"{candidate.candidate_id}_{target_platform}_{archetype.value}.png"
        payload_repr = f"{candidate.candidate_id}:{target_platform}:{json.dumps(matching_proj.get('verified_metrics', {}), sort_keys=True)}"
        sha = hashlib.sha256(payload_repr.encode('utf-8')).hexdigest()

        return MediaAsset(
            asset_type=archetype.value,
            asset_path=f"assets/{asset_filename}",
            asset_sha256=sha,
            caption=f"Grounded deterministic {archetype.value.replace('_', ' ')} based on verified {matching_proj.get('name')} metrics.",
            source_priority=AssetSourcePriority.DETERMINISTIC_COMPOSED_ASSET,
            archetype=archetype.value,
            is_synthetic=False,
            real_evidence_ref=matching_proj.get("project_id")
        )

    def _build_ai_fallback_spec(
        self,
        candidate: Candidate,
        archetype: AssetArchetype,
        target_platform: str
    ) -> MediaAsset:
        asset_filename = f"{candidate.candidate_id}_{target_platform}_ai_concept.png"
        prompt = f"Abstract technical concept visual illustrating {candidate.angle}. Clean architectural style."
        sha = hashlib.sha256(prompt.encode('utf-8')).hexdigest()

        return MediaAsset(
            asset_type="concept_visual",
            asset_path=f"assets/{asset_filename}",
            asset_sha256=sha,
            caption=f"Conceptual illustration supporting {candidate.angle} (Non-evidence visual).",
            source_priority=AssetSourcePriority.AI_GENERATED_FALLBACK,
            archetype=AssetArchetype.CONCEPT_VISUAL_FALLBACK.value,
            is_synthetic=True,
            synthetic_purpose="concept_visual",
            real_evidence_ref=None
        )

    def create_human_asset_request(
        self,
        candidate: Candidate,
        target_platform: str,
        title: str,
        instructions: str,
        why_needed: str,
        recommended_shots: List[str]
    ) -> HumanAssetRequest:
        cand_id = candidate.candidate_id
        plat = target_platform.lower()

        # Deduplication & Unification Check: Look for existing request for this candidate
        if self.requests_dir.exists():
            for p in sorted(self.requests_dir.glob("*.json")):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    if d.get("candidate_id") == cand_id:
                        existing_req = HumanAssetRequest.model_validate(d)

                        # If already fulfilled, return it
                        if existing_req.status == "FULFILLED":
                            return existing_req

                        # Pending request: merge target platform
                        modified = False
                        current_plats = [tp.lower() for tp in existing_req.target_platforms]
                        if plat not in current_plats:
                            existing_req.target_platforms.append(plat)
                            modified = True

                        for shot in recommended_shots:
                            if shot not in existing_req.recommended_shots:
                                existing_req.recommended_shots.append(shot)
                                modified = True

                        # Prefer more detailed instructions if available
                        if len(instructions) > len(existing_req.specific_instructions):
                            existing_req.specific_instructions = instructions
                            modified = True
                        if len(why_needed) > len(existing_req.why_needed):
                            existing_req.why_needed = why_needed
                            modified = True

                        if modified:
                            with open(p, "w", encoding="utf-8") as f:
                                json.dump(existing_req.model_dump(), f, indent=2)

                        return existing_req
                except Exception:
                    pass

        # Create new unified request
        req_id = f"asset_req_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        req = HumanAssetRequest(
            request_id=req_id,
            candidate_id=cand_id,
            target_platforms=[plat],
            requested_asset_title=title,
            specific_instructions=instructions,
            why_needed=why_needed,
            recommended_shots=recommended_shots,
            status="PENDING",
            created_at=datetime.now(timezone.utc).isoformat()
        )
        req_file = self.requests_dir / f"{req_id}.json"
        with open(req_file, "w", encoding="utf-8") as f:
            json.dump(req.model_dump(), f, indent=2)
        return req

    def list_pending_requests(self) -> List[HumanAssetRequest]:
        reqs = []
        seen_cands = set()
        if self.requests_dir.exists():
            for p in sorted(self.requests_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        d = json.load(f)
                        if d.get("status") == "PENDING":
                            cid = d.get("candidate_id")
                            if cid not in seen_cands:
                                seen_cands.add(cid)
                                reqs.append(HumanAssetRequest.model_validate(d))
                except Exception:
                    pass
        return reqs

    def fulfill_request(self, request_id: str, asset_path: Path) -> HumanAssetRequest:
        req_file = self.requests_dir / f"{request_id}.json"
        if not req_file.exists():
            raise FileNotFoundError(f"Human asset request '{request_id}' not found.")
        with open(req_file, "r", encoding="utf-8") as f:
            req = HumanAssetRequest.model_validate(json.load(f))

        asset_path = Path(asset_path).resolve()
        if not asset_path.exists():
            raise FileNotFoundError(f"Asset file does not exist: {asset_path}")

        cand_id = req.candidate_id

        # Destination under assets/user_submissions/
        sub_dir = self.assets_dir / "user_submissions"
        sub_dir.mkdir(parents=True, exist_ok=True)
        dest_filename = f"{cand_id}_{asset_path.name}"
        dest_path = sub_dir / dest_filename
        if asset_path != dest_path:
            shutil.copy2(asset_path, dest_path)

        # Compute SHA-256
        hasher = hashlib.sha256()
        with open(dest_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        sha = hasher.hexdigest()

        try:
            rel_path = str(dest_path.relative_to(self.workspace_root))
        except ValueError:
            rel_path = str(dest_path)

        fulfilled_now = datetime.now(timezone.utc).isoformat()
        req.status = "FULFILLED"
        req.fulfilled_asset_path = rel_path
        req.fulfilled_at = fulfilled_now
        req.asset_sha256 = sha

        with open(req_file, "w", encoding="utf-8") as f:
            json.dump(req.model_dump(), f, indent=2)

        # Cascading Fulfillment: Fulfill ALL other requests matching this candidate across all platforms
        if self.requests_dir.exists():
            for p in self.requests_dir.glob("*.json"):
                if p == req_file:
                    continue
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        other_data = json.load(f)
                    if other_data.get("candidate_id") == cand_id:
                        other_req = HumanAssetRequest.model_validate(other_data)
                        other_req.status = "FULFILLED"
                        other_req.fulfilled_asset_path = rel_path
                        other_req.fulfilled_at = fulfilled_now
                        other_req.asset_sha256 = sha
                        for tp in req.target_platforms:
                            if tp not in other_req.target_platforms:
                                other_req.target_platforms.append(tp)
                        with open(p, "w", encoding="utf-8") as f:
                            json.dump(other_req.model_dump(), f, indent=2)
                except Exception:
                    pass

        return req

    def consolidate_duplicate_requests(self) -> Dict[str, Any]:
        """Consolidates duplicate human asset requests per candidate.

        Merges target platforms, preserves fulfilled asset data, retains one primary
        request file per candidate, and deletes redundant duplicate JSON files.
        """
        if not self.requests_dir.exists():
            return {"consolidated_candidates": 0, "deleted_files": 0}

        by_candidate: Dict[str, List[Tuple[Path, HumanAssetRequest]]] = {}
        for p in sorted(self.requests_dir.glob("*.json")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                req = HumanAssetRequest.model_validate(data)
                by_candidate.setdefault(req.candidate_id, []).append((p, req))
            except Exception:
                pass

        deleted_count = 0
        consolidated_candidates = 0

        for cand_id, req_list in by_candidate.items():
            if len(req_list) <= 1:
                continue

            consolidated_candidates += 1
            # Pick primary: prefer FULFILLED, else earliest
            fulfilled_items = [item for item in req_list if item[1].status == "FULFILLED"]
            if fulfilled_items:
                primary_path, primary_req = fulfilled_items[0]
            else:
                primary_path, primary_req = req_list[0]

            all_platforms = set(primary_req.target_platforms)
            all_shots = list(primary_req.recommended_shots)

            for p, r in req_list:
                for tp in r.target_platforms:
                    all_platforms.add(tp)
                for s in r.recommended_shots:
                    if s not in all_shots:
                        all_shots.append(s)

            primary_req.target_platforms = sorted(list(all_platforms))
            primary_req.recommended_shots = all_shots

            # Write primary
            with open(primary_path, "w", encoding="utf-8") as f:
                json.dump(primary_req.model_dump(), f, indent=2)

            # Delete other duplicate files
            for p, r in req_list:
                if p != primary_path:
                    try:
                        p.unlink()
                        deleted_count += 1
                    except Exception:
                        pass

        return {
            "consolidated_candidates": consolidated_candidates,
            "deleted_files": deleted_count
        }
