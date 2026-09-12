---
name: creative-planner
description: >-
  Plans, specifies, and prepares authentic technical visual assets (schematics, CAD renders, logic analyzer traces, code diffs) and calculates immutable asset hashes for the approval envelope.
---

# Creative Planner Skill: Technical Visual Media

The **Creative Planner** skill designs and verifies the visual artifacts that accompany Serhat's technical posts. High-caliber engineers judge posts primarily by the fidelity of their visual evidence.

---

# Creative Planner Skill: Technical Visual Media

The **Creative Planner** skill designs, sources, and verifies the visual artifacts that accompany Serhat's technical posts. High-caliber engineers judge posts primarily by the fidelity of their visual evidence.

---

## 1. Universal Asset Requirement

- **Mandate**: Every post across LinkedIn, Instagram, and X **MUST** include at least one visual asset. Text-only posts are strictly prohibited across all three networks.
- **Hold If No Media**: If no acceptable asset can be created, captured, or composed, the post is automatically placed in `HOLD_FOR_ASSET` and must not proceed to scheduling or publishing.

---

## 2. 5-Tier Asset Source Priority Hierarchy

Asset selection must strictly prioritize empirical reality over synthetic generation. AI-generated assets are NEVER the default choice.

1. **Priority 1: Existing Real Project Assets**
   - Screenshots, app UI, controls/settings screens, demo frames, prototype/product photos, video recordings, benchmark captures, real data charts, terminal outputs, CAD renders, architecture diagrams already in the project repository.
2. **Priority 2: Automatically Captured Real Assets**
   - Newly captured directly from local repository builds, test runs, profiler outputs, or live device logs.
3. **Priority 3: User-Requested Real Assets (Human-Asset Request Protocol)**
   - When a strong physical or real asset is realistically obtainable from Serhat (workbench photos, multi-device physical setups, hardware harnesses, 3D printer in action), the system must NOT settle for inferior synthetic visuals. It must issue a `REQUEST_ASSET_FROM_USER` -> `HOLD_FOR_ASSET` state with clear, actionable shooting instructions.
4. **Priority 4: Deterministic Composed Assets Built from Real Evidence**
   - Screenshot composites, annotated technical visuals, benchmark cards, architecture diagrams, before/after comparisons, and carousels assembled deterministically from verified data.
5. **Priority 5: AI-Generated Assets as Final Fallback Only**
   - Strictly reserved for conceptual visuals, abstract support, cover graphics, or stylistic explanatory backdrops.

---

## 3. Anti-Fake Visual Rules (Strictly Enforced)

- AI-generated assets must **NEVER** simulate or pretend to be real empirical evidence.
- **Strictly Prohibited AI Generations**:
  - Fake benchmark charts or comparison tables
  - Fake hardware/workbench/prototype photos
  - Fake terminal outputs, CLI logs, or build runs
  - Fake app UI, screenshots, or settings screens
  - Fake oscilloscope, logic analyzer, or telemetry traces
- Any synthetic asset claiming empirical validity will trigger an **instant REJECTED** verdict.

---

## 4. Platform-Independent Asset Archetypes

Visual choices must be tailored to the story and platform independently rather than blindly duplicated:
- **LinkedIn**: Architecture diagrams, benchmark cards, clean technical carousels, engineering system flows.
- **Instagram**: Visual workbench photos, CAD renders, build timelapses, physical device setups.
- **X (Twitter)**: Code diff snippets, terminal output traces, compact bus arbitration cards.

---

## 5. Human-Asset Request Protocol

When a physical or real asset is obtainable from Serhat:
1. `AssetPlanner` creates a persistent `HumanAssetRequest` record in `lifecycle/human_asset_requests/<request_id>.json`.
2. The request specifies:
   - `candidate_id` and `target_platforms`
   - `requested_asset_title`
   - `specific_instructions` (exact framing, lighting, elements to show)
   - `why_needed` (engineering rationale)
   - `recommended_shots` (specific angles or test conditions)
3. The candidate/post transitions to `HOLD_FOR_ASSET` (decision: `REQUEST_ASSET_FROM_USER`).
4. Once Serhat provides the photo via `agency_cli submit-asset <request_id> <path>`, the request is marked `FULFILLED` and the post transitions to ready state.

---

## 6. Hash Pinning & Security Envelope

To prevent Time-of-Check to Time-of-Use (TOCTOU) visual tampering:
1. Every asset intended for publication is stored locally with an absolute or workspace-relative path.
2. The Creative Planner calculates the SHA-256 hash of the exact file bytes:
   $$\text{asset\_sha256} = \text{SHA256}(\text{asset\_file\_bytes})$$
3. These hashes are embedded directly into the post object in `media_assets` and pinned in the **Approval Request**.
4. If an image or diagram is modified after Serhat grants approval, the hash mismatch causes the **Publisher Gateway** to abort immediately.
