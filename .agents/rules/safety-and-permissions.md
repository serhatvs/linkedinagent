# Safety & Permission Boundaries

This document defines the security model and permission boundaries enforced across all agents, subagents, and automated tools operating in this workspace.

---

## 1. Autonomous Scope vs Restricted Scope

| Capability / Action | Autonomous Allowed? | Enforcement Mechanism |
| :--- | :--- | :--- |
| Read local git repositories, diffs, commits | **YES** | Read-only local filesystem tools |
| Query GitHub MCP (repos, commits, issues, PRs) | **YES** | Read-only tool scopes |
| Fetch Metricool analytics, audience metrics | **YES** | Read-only analytics endpoints |
| Ideate, Scout, Draft, and Score content | **YES** | Workspace internal state writes |
| Transition to `AWAITING_APPROVAL` | **YES** | Approval package compilation |
| **Publishing to LinkedIn (Metricool MCP)** | **STRICT NO** | Blocked without valid cryptographic/hash receipt signed by Serhat |
| **Scheduling content on Metricool** | **STRICT NO** | Blocked without valid signed approval |
| **Replying to comments or sending DMs** | **STRICT NO** | Blocked without explicit human review & approval |
| **Editing public profile details** | **STRICT NO** | Completely disabled in v1 |

---

## 2. Cryptographic / Hash Approval Verification Protocol

1. When a post reaches the `AWAITING_APPROVAL` stage, the agency creates an **Approval Request Package** in `approvals/pending/<request_id>.json`.
2. The package includes:
   - Complete final post text
   - Attached media descriptors
   - Citations and provenance audit
   - Intended scheduling window
   - `content_sha256`: SHA-256 hash of the exact canonical text and media descriptors
3. Serhat reviews the request and issues a signed approval token in `approvals/signed/<request_id>.approved.json`.
4. The **Publisher Gateway**:
   - Computes the SHA-256 hash of the post content to be published.
   - Verifies that `approvals/signed/<request_id>.approved.json` exists and that its `content_sha256` matches the payload exactly.
   - Verifies the approval timestamp and signer identity (`approved_by: "Serhat"`).
   - If any character of the post was altered after approval, the hash mismatch **immediately aborts** the publish call.

---

## 3. Ban on Unofficial Automation & Scraping

- **No Selenium / Puppeteer / Playwright**: No browser emulation or simulated DOM interactions against LinkedIn.
- **No Unofficial APIs**: Only official, sanctioned MCP interfaces (Metricool for scheduling/analytics, GitHub for code intelligence) are allowed.
- **No Stored Plaintext Credentials**: All MCP connections leverage local environment secrets or standard MCP authorization configs.
