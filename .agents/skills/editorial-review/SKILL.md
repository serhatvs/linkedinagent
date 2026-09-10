---
name: editorial-review
description: >-
  Runs rigorous editorial review, slop detection, domain Design Rule Checks (DRC), and calculates the 5-point quality scorecard before allowing a post to be reviewed.
---

# Editorial Review Skill: Quality & Safety Reviewer

The **Editorial Review** skill acts as the unyielding quality gatekeeper of the agency. It ruthlessly enforces high technical standards, eliminates LinkedIn slop, and executes domain-specific Design Rule Checks (DRC).

---

## The 5-Point Quality Scorecard (0 - 100)

1. **Technical Rigor (25 pts)**:
   - Does the post explain the underlying mechanism or root cause accurately?
   - Are the concepts mathematically and physically sound?
   - Minimum threshold: 22 pts.

2. **Clarity & Flow (25 pts)**:
   - Is the writing clear, concise, and logically organized?
   - Does it avoid gratuitous jargon while retaining precision?
   - Minimum threshold: 21 pts.

3. **Visual Utility (25 pts)**:
   - Is the attached visual asset informative, legible, and directly tied to the claims?
   - (Schematic, logic trace, CAD render, architecture diagram).
   - Minimum threshold: 20 pts.

4. **Reader ROI & Actionability (25 pts)**:
   - Does an engineering reader walk away with tangible, reusable technical knowledge?
   - Minimum threshold: 22 pts.

**Composite Score Threshold**: $\ge 85 / 100$ required to pass.

---

## Strict Anti-Slop Lexical Engine

The reviewer runs a hard regex scan for banned terms and tone patterns:
- **Banned Buzzwords**: *"game-changer", "groundbreaking", "revolutionary", "supercharge", "unleash", "delve", "testament", "paradigm shift", "thrilled to share", "let that sink in", "agree?"*.
- **Emoji Limit**: Maximum 2 functional emojis (e.g. 🛠️, ⚠️, 📊). Zero decorative bullet emojis (🚀, 💡, 🔥, 👉).
- **Formatting**: Flags posts with single-sentence artificial line breaks designed to artificially stretch mobile screen space.
- **Slop Score**: Must be exactly **0.0**. Any positive slop score triggers an immediate `REJECTED_SLOP_OR_DRC` or `REVISE_REQUIRED`.

---

## Domain Design Rule Checks (DRC)

1. **Embedded Systems DRC**:
   - **Mains AC Safety**: If the project touches mains voltage, does it explicitly mention galvanic isolation (optocouplers, relays, creepage distance)?
   - **LiPo Protection**: If powered by LiPo/Li-ion, does it specify BMS / PCM protection?
   - **Logic Level Check**: Are 5V and 3.3V interfaces properly matched with level shifters?

2. **Robotics & 3D Engineering DRC**:
   - **Sim-vs-Real Transparency**: Are simulations explicitly identified as simulations? (No passing off PyBullet/Gazebo/Isaac as real-world hardware).
   - **3D Print Structural Feasibility**: Are FDM print orientations acknowledged for tensile loads along layer lines?

3. **AI Agents DRC**:
   - **Benchmark Integrity**: Are benchmark claims accompanied by dataset, baseline, hardware, and exact metric?

---

## Review Verdicts
- **`PASSED_EDITORIAL`**: Persists post with attached scorecard to `lifecycle/04_reviewed/<post_id>.json`.
- **`REVISE_REQUIRED`**: Generates a detailed revision critique and returns post to `lifecycle/03_drafts/`.
- **`REJECTED_SLOP_OR_DRC`**: Fails the post permanently due to unresolvable safety or integrity violations.
