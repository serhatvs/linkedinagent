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

4. **Visual Slop**:
   - No generic stock photos of laptops on wooden desks, glass skyscrapers, or glowing blue neural network stock graphics.
   - Every visual must be a real artifact: a schematic, a logic analyzer trace, a CAD cross-section, a code diff, a clean terminal log, or an architecture block diagram.

---

## 3. Mandatory Technical Grounding

Before a post transitions from `DRAFT` to `REVIEWED`, the **Researcher** and **Editorial Reviewer** must annotate every claim with a provenance source:
- `fact_source`: Path to entry in `knowledge/approved_facts.json`
- `project_id`: ID from `knowledge/projects_registry.json`
- `commit_hash`: Git commit SHA or diff reference
- `hardware_specs`: Verified specs from `knowledge/lab_and_hardware.json`

If an assertion has no grounding provenance, it must either be verified by Serhat or completely excised.
