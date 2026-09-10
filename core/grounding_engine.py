"""Grounding verification engine for Serhat's personal media agency.

Validates that every claim and citation resolves to verified project context,
approved facts, git commits, or lab hardware specifications.
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple
from core.models import Citation, GroundingVerification, Post


class GroundingEngine:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.knowledge_dir = workspace_root / "knowledge"
        self._load_knowledge()

    def _load_knowledge(self):
        projects_file = self.knowledge_dir / "projects_registry.json"
        facts_file = self.knowledge_dir / "approved_facts.json"
        lab_file = self.knowledge_dir / "lab_and_hardware.json"

        self.projects: Dict[str, Any] = {}
        if projects_file.exists():
            with open(projects_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for p in data.get("projects", []):
                    self.projects[p["project_id"]] = p

        self.approved_facts: Dict[str, Any] = {}
        if facts_file.exists():
            with open(facts_file, "r", encoding="utf-8") as f:
                self.approved_facts = json.load(f).get("approved_author_facts", {})

        self.lab_hardware: Dict[str, Any] = {}
        if lab_file.exists():
            with open(lab_file, "r", encoding="utf-8") as f:
                self.lab_hardware = json.load(f)

    def verify_post_grounding(self, post: Post) -> GroundingVerification:
        unverified_claims: List[str] = []
        cited_sources: List[str] = []

        # 1. Check for explicitly prohibited claims
        prohibited_rules = self.approved_facts.get("unapproved_or_prohibited_claims", [])
        text_lower = post.content_text.lower()

        phd_patterns = [r"\bph\.?d\b", r"doctorate", r"master'?s\s+degree"]
        for pattern in phd_patterns:
            if re.search(pattern, text_lower):
                unverified_claims.append(f"Prohibited educational claim detected matching '{pattern}'. Author is an undergraduate student.")

        years_exp = re.search(r"(\d+)\+?\s*years?\s+of\s+experience", text_lower)
        if years_exp:
            val = int(years_exp.group(1))
            if val > 4:
                unverified_claims.append(f"Exaggerated experience claim: '{val} years of experience'.")

        # 2. Verify all attached citations
        if not post.citations:
            unverified_claims.append("Post contains zero citations. At least one grounded citation is required.")

        for citation in post.citations:
            valid, reason = self.verify_citation(citation)
            if valid:
                cited_sources.append(f"{citation.source_type}:{citation.reference_id}")
            else:
                unverified_claims.append(f"Invalid citation for claim '{citation.claim_text[:40]}...': {reason}")

        # 3. Verify project consistency if mentioned
        for project_id, project in self.projects.items():
            if project["name"].lower() in text_lower or project_id in text_lower:
                # Ensure post is tied to this pillar or cites this project
                if post.pillar != project["pillar"] and not any(c.reference_id == project_id for c in post.citations):
                    unverified_claims.append(f"Post mentions project '{project['name']}' but does not cite it in citations.")

        # Calculate grounding percentage
        total_checks = len(post.citations) + len(unverified_claims)
        if total_checks == 0:
            grounding_percentage = 0.0
        else:
            valid_citations_count = len(cited_sources)
            grounding_percentage = max(0.0, min(100.0, (valid_citations_count / (valid_citations_count + len(unverified_claims))) * 100.0))

        return GroundingVerification(
            grounding_percentage=round(grounding_percentage, 1),
            unverified_claims=unverified_claims,
            cited_sources=cited_sources
        )

    def verify_citation(self, citation: Citation) -> Tuple[bool, str]:
        src = citation.source_type
        ref = citation.reference_id

        if src == "project_registry":
            if ref in self.projects:
                return True, "Valid project reference."
            return False, f"Project ID '{ref}' not found in knowledge/projects_registry.json"

        elif src == "knowledge_fact":
            # Check verified technical skills or experience claims
            skills = self.approved_facts.get("verified_technical_skills", {})
            flat_skills = [s.lower() for sublist in skills.values() for s in sublist]
            claims = [c.lower() for c in self.approved_facts.get("verifiable_experience_claims", [])]

            if any(ref.lower() in s for s in flat_skills) or any(ref.lower() in c for c in claims) or ref in self.approved_facts.get("identity", {}):
                return True, "Valid knowledge fact reference."
            return False, f"Fact reference '{ref}' not found in knowledge/approved_facts.json"

        elif src == "lab_spec":
            instruments = [i["model"].lower() for i in self.lab_hardware.get("lab_instruments", [])]
            mcus = [m["board"].lower() for m in self.lab_hardware.get("microcontrollers_and_devboards", [])]
            tools = [t.get("machine", t.get("tool", "")).lower() for t in self.lab_hardware.get("manufacturing_and_rapid_prototyping", [])]

            all_lab = instruments + mcus + tools
            if any(ref.lower() in item for item in all_lab):
                return True, "Valid lab specification reference."
            return False, f"Lab reference '{ref}' not found in knowledge/lab_and_hardware.json"

        elif src == "git_commit":
            # Valid git commit format (7 to 40 hex chars)
            if re.match(r"^[0-9a-f]{7,40}$", ref.lower()):
                return True, "Valid git commit hash format."
            return False, f"Invalid git commit SHA format: '{ref}'"

        return False, f"Unknown citation source type: '{src}'"
