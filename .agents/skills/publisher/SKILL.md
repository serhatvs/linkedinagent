---
name: publisher
description: >-
  Interfaces with Buffer MCP via SocialPublisher for scheduling and publishing approved LinkedIn, Instagram, and X content, strictly validating signed approval tokens and payload hashes before dispatch.
---

# Publisher Skill: Buffer Multi-Channel Gateway & Dispatcher

The **Publisher** skill is the only component in the agency that communicates with external publishing infrastructure via the SocialPublisher interface and official Buffer Model Context Protocol (MCP) server across **LinkedIn**, **Instagram**, and **X (Twitter)**.

---

## Multi-Channel Bound Channels

The agency binds 3 verified social channels via Buffer MCP:
- **LinkedIn Personal Profile** (`6aa34050cd8b9c702c48769e`): Serhat Yavuz (MVTS >= 9.0, architectural, restrained)
- **Instagram Professional Account** (`6aa340c6cd8b9c702c487833`): @serhatyvz_38 (MVTS >= 7.5, visual build-log, image/video mandatory)
- **X Developer Profile** (`6aa340e1cd8b9c702c487894`): @Arkhino_DEV (MVTS >= 6.5, developer-native, <= 280 chars)

## Cross-Platform Rule (Non-Negotiable)

**NEVER blindly cross-post identical text.**
Every outbound post must pass through `DistributionAdapter` which adapts the core engineering substance into channel-specific variants with independent payloads, hashes, approval decisions, and dispatch states.

---

## Defensive Execution Rules

Before ANY call is made to the Buffer MCP server:

1. **Verify Signed Approval Token**:
   - Locate `approvals/signed/<request_id>.approved.json`.
   - Check that the token exists and is cryptographically verified by `approval_engine`.

2. **Recompute Outbound Payload Hash**:
   - Build the exact Buffer MCP payload matching the channel specification:
     ```json
     {
       "channel_id": "<channel_id>",
       "text": "<adapted_post_text>",
       "scheduling_type": "automatic",
       "due_at": "<scheduled_iso_time_with_offset>",
       "mode": "customScheduled",
       "assets": [...]
     }
     ```
   - Calculate live SHA-256 of the payload.
   - If `live_sha256 != token.canonical_payload_sha256`:
     - **HARD ABORT**: Raise `E_PAYLOAD_MUTATED`.
     - Log incident to security audit log.
     - Demote post back to `lifecycle/03_drafts/`.

3. **Dry-Run Mode Enforcement**:
   - In development, staging, or canary evaluation, the publisher runs in simulation mode (`--dry-run` or `SHADOW_MODE`), producing an exact mock response with `buffer_mock_<id>` and zero external network calls.
   - For live production calls, explicit environment confirmation is required.

4. **Lifecycle Transition**:
   - For scheduled posts: transitions post to `lifecycle/07_scheduled/<post_id>.json`.
   - For live posts (after Buffer status confirmation): transitions post to `lifecycle/08_published/<post_id>.json`.
