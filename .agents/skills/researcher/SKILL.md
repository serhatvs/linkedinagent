---
name: researcher
description: >-
  Conducts deep technical verification, checks code repositories and datasheets, validates numerical metrics, and grounds every factual claim before or during drafting.
---

# Researcher Skill: Technical Grounding & Fact Verification

The **Researcher** skill is the agency's rigorous fact-checker and technical depth investigator. It ensures that every post draft is anchored in absolute engineering reality.

## Responsibilities
1. **Source Citation & Provenance**:
   - For every technical claim (e.g. clock speed, latency, current draw, gear ratio, model size), find the authoritative reference:
     - Project entry in `knowledge/projects_registry.json`
     - Verified author facts in `knowledge/approved_facts.json`
     - Lab equipment and safety specs in `knowledge/lab_and_hardware.json`
     - Git commit hashes and diffs in code repositories.

2. **Benchmark & Numerical Integrity**:
   - Verify that any benchmark metric defines:
     - Baseline system
     - Workload / dataset
     - Specific hardware (CPU/GPU/MCU, clock frequency, RAM)
     - Metric definition (e.g. latency p95 in ms, not just "faster")
   - Disallow unsubstantiated comparative claims ("10x faster than standard").

3. **Datasheet & Protocol Accuracy**:
   - For embedded topics: verify SPI/I2C clock limits, voltage levels (3.3V vs 5V), pull-up resistor requirements, DMA channel limitations.
   - For robotics topics: verify motor stall torque, continuous torque, gear reduction ratios, and bus bandwidth limits.
   - For AI agent topics: verify token contexts, framework versions, deterministic constraints, and tool schemas.

## Output
Produces a structured Grounding Report containing:
- List of verified claims with direct citations.
- List of unverified or suspicious claims requiring removal or confirmation.
- Grounding coverage percentage ($100\%$ required for publishing).
