---
name: approval-gate
description: >-
  Prepares immutable approval requests, canonicalizes payload hashes, and validates human-signed approval tokens before allowing any post to become APPROVED.
---

# Approval Gate Skill: Cryptographic Human-in-the-Loop Verification

The **Approval Gate** skill enforces the zero-trust boundary separating autonomous agency operations from external-facing actions.

---

## The Core Protocol

1. **Compilation of Approval Request**:
   - The skill ingests a post from `lifecycle/04_reviewed/<post_id>.json`.
   - Generates a unique `request_id`: `appr_req_<timestamp>_<slug>`.
   - Constructs the canonical text representation and collects all pinned media asset hashes.
   - Computes the canonical payload hash:
     $$\text{canonical\_payload\_sha256} = \text{SHA256}(\text{CanonicalJSON}(\text{post\_id}, \text{action\_scope}, \text{platform}, \text{content\_text}, \text{media\_asset\_hashes}))$$
   - Writes the request to `approvals/pending/<request_id>.json`.
   - Transitions post to `lifecycle/05_awaiting_approval/<post_id>.json`.

2. **Presenting to Serhat**:
   - The MediaDirector presents the approval request summary directly to Serhat in the chat:
     - Post title and summary
     - Full post copy
     - Linked media assets
     - Pinned SHA-256 digest
     - Proposed publishing window
     - Instructions on how to approve via CLI (`python -m core.approval_engine approve <request_id>`).

3. **Verifying the Human Sign-Off**:
   - When Serhat signs the token, a signed file is created at `approvals/signed/<request_id>.approved.json`.
   - The Approval Gate verifies:
     - Signer is explicitly `"Serhat"`.
     - `canonical_payload_sha256` matches the pending request payload hash byte-for-byte.
     - Token has not expired (`expires_at > current_time`).
     - Token has not been replayed (`nonce` check).
     - Target action scope matches (`METRICOOL_SCHEDULE` or `METRICOOL_PUBLISH_NOW`).

4. **Transition to APPROVED**:
   - On successful verification, the post is atomically moved to `lifecycle/06_approved/<post_id>.json` with `approval_token_id` recorded.
   - An immutable audit log entry is appended to `approvals/audit_log.jsonl`.
