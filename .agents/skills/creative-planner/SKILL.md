---
name: creative-planner
description: >-
  Plans, specifies, and prepares authentic technical visual assets (schematics, CAD renders, logic analyzer traces, code diffs) and calculates immutable asset hashes for the approval envelope.
---

# Creative Planner Skill: Technical Visual Media

The **Creative Planner** skill designs and verifies the visual artifacts that accompany Serhat's technical posts. High-caliber engineers judge posts primarily by the fidelity of their visual evidence.

---

## Allowed Visual Asset Archetypes

1. **System & Architecture Diagrams**:
   - Clean, high-contrast block diagrams detailing data flow, state machines, or agent communication graphs.
   - No stock iconography. Use formal engineering notation.

2. **Instrument Captures & Oscilloscope Traces**:
   - Screen exports from Saleae Logic Pro or Rigol digital oscilloscopes.
   - Must include channel labels, timebase (e.g. 50ns/div), and protocol decode overlays.

3. **Code Diffs & Carbon Snippets**:
   - Focused syntax-highlighted diffs (max 20 lines) isolating the exact bug fix or optimization.
   - Monospace font with clear line numbering.

4. **Parametric CAD Renders & Cross-Sections**:
   - Exploded views or cutaway sections from Fusion 360 showing internal clearances, gasket compression grooves, or heat-set insert pockets.

5. **Annotated Workbench Photos**:
   - High-resolution bench photos showing real circuits, wiring harnesses, or 3D printed assemblies, annotated with callout arrows for key ICs or test points.

---

## Hash Pinning & Security Envelope

To prevent Time-of-Check to Time-of-Use (TOCTOU) visual tampering:
1. Every asset intended for publication is stored locally with an absolute path.
2. The Creative Planner calculates the SHA-256 hash of the exact file bytes:
   $$\text{asset\_sha256} = \text{SHA256}(\text{asset\_file\_bytes})$$
3. These hashes are embedded directly into the post object in `media_assets` and pinned in the **Approval Request**.
4. If an image or diagram is modified after Serhat grants approval, the hash mismatch causes the **Publisher Gateway** to abort immediately.
