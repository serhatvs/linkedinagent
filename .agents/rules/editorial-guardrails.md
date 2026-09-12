# Editorial Guardrails & Quality Standards

These rules define the voice, tone, forbidden patterns, and verification standards for all content drafted and reviewed in this workspace.

---

## 1. Voice & Persona Profile

- **Author**: Serhat, Computer Engineering student, builder, and systems tinkerer.
- **Voice Characteristics**:
  - **Pragmatic & Objective**: Speaks like a software/hardware engineer writing an internal architecture design doc or post-mortem.
  - **First-Person Builder**: "I spent the weekend debugging an SPI bus issue...", "Here is the architectural pattern that fixed our state drift...", "I measured a 42% drop in latency after..."
  - **Honest About Trade-offs**: Acknowledges what failed, limitations, memory footprints, thermal constraints, or why an alternative solution wasn't chosen.
  - **Zero Synthetic Hype**: Avoids buzzword salads ("synergy", "paradigm shift", "revolutionary", "game-changer", "unleash").

---

## 2. Forbidden Patterns (Instant Rejection Criteria)

Any content containing any of the following is immediately blocked at the `DRAFT` or `REVIEWED` stage:

1. **LinkedIn Slop Phrases**:
   - "I'm thrilled to announce / share..."
   - "In today's fast-paced digital world..."
   - "Most people don't realize this, but..."
   - "Agree?" / "Thoughts?" / "Drop a comment below..."
   - "Here is a harsh truth..."
   - "Let that sink in."
   - "Stop doing X. Do Y instead."

2. **Unverified Claims & Invented Numbers**:
   - Stating "10x speedup" without the exact baseline and benchmark script/methodology.
   - Claiming to have mastered or built something not registered in `knowledge/projects_registry.json` or `knowledge/approved_facts.json`.
   - Invented customer stories, fake client results, or fabricated project milestones.

3. **Emoji Restraint**:
   - Never use emojis as decorative bullet points (🚀, 💡, 🔥, 👉, 📈).
   - Maximum 1-2 functional emojis per post (e.g. 🛠️ for tool description, ⚠️ for hardware hazard warning, 📊 for measured benchmark data).

4. **Visual Slop & Universal Asset Requirement**:
   - **Universal Asset Mandate**: Every post across LinkedIn, Instagram, and X **MUST** include at least one media asset. Text-only posts are strictly prohibited across all channels.
   - **Hold If No Media**: If no acceptable asset can be obtained or composed, the post must be placed in `HOLD_FOR_ASSET` and must not be published.
   - No generic stock photos of laptops on wooden desks, glass skyscrapers, or glowing blue neural network stock graphics.
   - Every visual must follow the 5-Tier Asset Hierarchy and Anti-Fake Visual Rules.

---

## 3. Evidence-First Asset Policy & 5-Tier Hierarchy

Asset creation and selection must strictly prioritize empirical reality over synthetic generation. AI-generated assets must NEVER be the default choice.

### 5-Tier Asset Priority
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

### Anti-Fake Visual Rules (Strictly Enforced)
- AI-generated assets must **NEVER** simulate or pretend to be real empirical evidence.
- **Strictly Prohibited AI Generations**:
  - Fake benchmark charts or comparison tables
  - Fake hardware/workbench/prototype photos
  - Fake terminal outputs, CLI logs, or build runs
  - Fake app UI, screenshots, or settings screens
  - Fake oscilloscope, logic analyzer, or telemetry traces
- Any synthetic asset claiming empirical validity will trigger an **instant REJECTED** verdict.

### Platform-Independent Asset Selection
Visual choices must be tailored to the story and platform independently rather than blindly duplicated:
- **LinkedIn**: Architecture diagrams, benchmark cards, clean technical carousels, engineering system flows.
- **Instagram**: Visual workbench photos, CAD renders, build timelapses, physical device setups.
- **X (Twitter)**: Code diff snippets, terminal output traces, compact bus arbitration cards.

---

## 4. Mandatory Technical Grounding

Before a post transitions from `DRAFT` to `REVIEWED`, the **Researcher** and **Editorial Reviewer** must annotate every claim with a provenance source:
- `fact_source`: Path to entry in `knowledge/approved_facts.json`
- `project_id`: ID from `knowledge/projects_registry.json`
- `commit_hash`: Git commit SHA or diff reference
- `hardware_specs`: Verified specs from `knowledge/lab_and_hardware.json`

If an assertion has no grounding provenance, it must either be verified by Serhat or completely excised.
