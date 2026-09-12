"""Deterministic Disclosure Reviewer for Serhat's Personal Media Agency.

Audits candidate posts and drafts to ensure zero unauthorized disclosure of:
- Security vulnerabilities, exploits, bug bounty findings, CVEs
- Client, employer, or startup confidential information / NDAs
- Private repository contents not certified public-safe
- Credentials, tokens, keys, secrets
- Legal, medical, political claims or accusations
- Contractual commitments or sensitive personal life details
"""

from __future__ import annotations
import re
from typing import List, Tuple
from pathlib import Path
from core.models import Post, DisclosureRisk, DisclosureCheck


# Prohibited phrases and regex patterns that trigger MANDATORY HUMAN APPROVAL
DISCLOSURE_PATTERNS = {
    "SECURITY_VULNERABILITY_OR_EXPLOIT": [
        r"\bcve-\d{4}-\d{4,7}\b",
        r"\bzero-day\b",
        r"\b0-day\b",
        r"\bexploit\s+payload\b",
        r"\bproof\s+of\s+concept\s+exploit\b",
        r"\bbug\s+bounty\s+reward\b",
        r"\bresponsible\s+disclosure\b",
        r"\bvulnerability\s+disclosure\b",
        r"\brce\s+vulnerability\b",
        r"\bprivilege\s+escalation\s+exploit\b"
    ],
    "CONFIDENTIAL_OR_PROPRIETARY": [
        r"\bunder\s+nda\b",
        r"\bconfidential\s+client\b",
        r"\bclient\s+contract\b",
        r"\bnon-disclosure\b",
        r"\bproprietary\s+codebase\b",
        r"\binternal\s+slack\b",
        r"\bconfidential\s+financials\b",
        r"\bmonthly\s+recurring\s+revenue\b",
        r"\bunannounced\s+partnership\b"
    ],
    "SECRETS_AND_CREDENTIALS": [
        r"\bghp_[a-zA-Z0-9]{36}\b",
        r"\bgho_[a-zA-Z0-9]{36}\b",
        r"\bsk-[a-zA-Z0-9]{32,}\b",
        r"\bpassword\s*=\s*['\"].+?['\"]",
        r"\bapi_key\s*=\s*['\"].+?['\"]",
        r"\bsecret_key\s*=\s*['\"].+?['\"]",
        r"\.env\s+file\b"
    ],
    "LEGAL_OR_MEDICAL_OR_POLITICAL": [
        r"\blawsuit\b",
        r"\blitigation\b",
        r"\bbreach\s+of\s+contract\b",
        r"\bcease\s+and\s+desist\b",
        r"\bprescribed\s+medication\b",
        r"\bclinical\s+diagnosis\b",
        r"\belection\s+campaign\b",
        r"\bvote\s+for\b",
        r"\bpolitical\s+party\b"
    ],
    "CONTRACTUAL_OR_JOB_DISCLOSURES": [
        r"\bsigned\s+an\s+offer\b",
        r"\baccepted\s+an\s+offer\b",
        r"\brejected\s+an\s+offer\b",
        r"\bcontractually\s+obligated\b",
        r"\bsigned\s+a\s+contract\s+with\b",
        r"\bour\s+investors\b"
    ],
    "ACCUSATIONS_AND_CONTROVERSY": [
        r"\bdefrauded\b",
        r"\bscammed\b",
        r"\bstole\s+my\s+code\b",
        r"\bmalicious\s+intent\b",
        r"\blie\s+about\b",
        r"\bincompetent\s+engineer\b"
    ]
}


class DisclosureReviewer:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def review_post(self, post: Post) -> DisclosureCheck:
        """Audits a post for disclosure risks. Any match fails closed to HIGH risk."""
        full_text = f"{post.title}\n{post.content_text}".lower()
        detected_classes: List[str] = []

        for category, patterns in DISCLOSURE_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, full_text, re.IGNORECASE):
                    detected_classes.append(category)
                    break

        # Check citations for references to unapproved private sources
        for cit in post.citations:
            if cit.source_type == "unapproved_private":
                detected_classes.append("PRIVATE_UNAPPROVED_SOURCE")

        if detected_classes:
            return DisclosureCheck(
                passed=False,
                risk_level=DisclosureRisk.HIGH,
                prohibited_classes_detected=list(set(detected_classes)),
                public_safe_verification=False,
                rationale=f"Disclosure check failed: detected sensitive/prohibited classes: {', '.join(set(detected_classes))}. Mandatory human review required."
            )

        return DisclosureCheck(
            passed=True,
            risk_level=DisclosureRisk.LOW,
            prohibited_classes_detected=[],
            public_safe_verification=True,
            rationale="Disclosure audit passed. No credentials, exploits, NDAs, or sensitive categories detected."
        )
