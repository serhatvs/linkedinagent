---
name: publisher
description: >-
  Interfaces with Metricool MCP for scheduling and publishing approved LinkedIn content, strictly validating signed approval tokens and payload hashes before dispatch.
---

# Publisher Skill: Metricool Gateway & Dispatcher

The **Publisher** skill is the only component in the agency that communicates with external publishing infrastructure via the Metricool Model Context Protocol (MCP) server.

---

## Defensive Execution Rules

Before ANY call is made to the Metricool MCP server:

1. **Verify Signed Approval Token**:
   - Locate `approvals/signed/<request_id>.approved.json`.
   - Check that the token exists and is cryptographically verified by `approval_engine`.

2. **Recompute Outbound Payload Hash**:
   - Build the exact Metricool API payload:
     ```json
     {
       "platform": "linkedin",
       "text": "<final_post_text>",
       "dateTime": "<scheduled_iso_time>",
       "media": [...]
     }
     ```
   - Calculate live SHA-256 of the payload.
   - If `live_sha256 != token.canonical_payload_sha256`:
     - **HARD ABORT**: Raise `E_PAYLOAD_MUTATED`.
     - Log incident to security audit log.
     - Demote post back to `lifecycle/03_drafts/`.

3. **Dry-Run Mode Enforcement**:
   - In development, staging, or dry-run evaluation, the publisher runs in simulation mode (`--dry-run`), producing an exact mock response from Metricool with `mock_metricool_post_id` and zero external network calls.
   - For live production calls, explicit environment confirmation is required.

4. **Lifecycle Transition**:
   - For scheduled posts: transitions post to `lifecycle/07_scheduled/<post_id>.json`.
   - For live posts (after Metricool webhook / status confirmation): transitions post to `lifecycle/08_published/<post_id>.json`.
