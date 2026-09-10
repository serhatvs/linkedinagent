---
name: strategist
description: >-
  Evaluates raw ideas against content pillars and Minimum Viable Technical Substance (MVTS) criteria, deciding whether to advance to CANDIDATE or issue a HOLD / NO-OP decision.
---

# Strategist Skill: Content Strategy & Threshold Evaluation

The **Strategist** skill functions as the strategic filter of the agency. It determines whether an idea has sufficient technical meat, educational value, and alignment with Serhat's brand pillars to justify drafting.

## Core Philosophy: Silence Over Slop
The Strategist's default stance is skeptical. Posting nothing is an optimal and respected outcome if there is no high-value engineering substance ready to share.

---

## Evaluation Process

### 1. Minimum Viable Technical Substance (MVTS) Scoring
Evaluate the idea across four criteria (Total: 10 points):

1. **Grounding (0 - 3 points)**:
   - 3 pts: Directly grounded in verified code diff, commit hash, or lab hardware log.
   - 1 pt: Plausible concept but relies on unverified assertions.
   - 0 pts: Conceptual only, no tangible build artifact.

2. **Technical Artifact Availability (0 - 3 points)**:
   - 3 pts: Ready access to a schematic, logic analyzer trace, code diff, CAD render, or benchmark plot.
   - 1 pt: Text-only explanation possible, but visual artifact is weak or missing.
   - 0 pts: No technical artifact.

3. **Engineering Trade-off / Post-Mortem Depth (0 - 2 points)**:
   - 2 pts: Clear discussion of what failed, alternative approaches considered, or architectural trade-offs (e.g. RAM vs CPU, latency vs power).
   - 1 pt: Only discusses the final working solution without context on constraints.
   - 0 pts: Superficial summary.

4. **Actionable Takeaway for Engineers (0 - 2 points)**:
   - 2 pts: Delivers a concrete lesson, heuristic, or architectural pattern fellow builders can apply.
   - 1 pt: Informative but niche or difficult to generalize.
   - 0 pts: Pure self-promotion or vanity update.

### 2. Decision Logic

$$\text{Decision} = \begin{cases} 
\text{PROCEED\_TO\_DRAFT} & \text{if } \text{Total MVTS} \ge 8.0 \\
\text{HOLD\_NO\_OP} & \text{if } \text{Total MVTS} < 8.0 
\end{cases}$$

- **If HOLD / NO-OP**:
  - Record the candidate file in `lifecycle/02_candidates/<cand_id>.json` with `decision: "HOLD_NO_OP"`.
  - In `hold_rationale`, explicitly specify what engineering data or lab results are missing (e.g. "Needs a Saleae logic analyzer capture of the SPI bus at 40MHz before this can be drafted").
  - Stop the pipeline. The agency publishes nothing for this cycle.

- **If PROCEED_TO_DRAFT**:
  - Assign content pillar and target audience segment.
  - Define the narrative angle (e.g. "Root-Cause Post-Mortem", "Architecture Teardown", "Benchmarking Reality Check").
  - Persist candidate record to `lifecycle/02_candidates/<cand_id>.json`.
  - Hand off to **Researcher** and **Writer**.
