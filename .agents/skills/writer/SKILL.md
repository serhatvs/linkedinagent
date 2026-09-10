---
name: writer
description: >-
  Crafts high-signal, authentic technical LinkedIn post drafts in Serhat's builder voice, adhering strictly to anti-slop rules and grounding citations.
---

# Writer Skill: Technical LinkedIn Copywriting

The **Writer** skill transforms validated candidate topics and research into crisp, compelling, and intellectually substantive LinkedIn posts written in Serhat's authentic voice.

---

## The 4 Authentic Post Archetypes

### 1. The Hard Bug & Root-Cause Post-Mortem
- **Hook**: The anomaly observed on the instrument or console (e.g. "Our STM32 DMA buffer was dropping 12% of frames only when the SPI display refreshed concurrently...").
- **Investigation**: Hypotheses tested, instruments used (logic analyzer, oscilloscope, memory profiler).
- **The Root Cause**: The physical or architectural reason (e.g. bus matrix arbitration, priority inversion, missing pull-up).
- **The Fix**: The exact code change or hardware modification.
- **The Heuristic**: What other engineers should check when facing similar symptoms.

### 2. The Architecture Teardown
- **Hook**: A design trade-off in building an agentic system or distributed service.
- **System Diagram**: Walkthrough of components, state machines, and boundaries.
- **Why Standard Approaches Failed**: Why naive solutions (e.g. standard LLM loops without state persistence) failed under production stress.
- **The Measured Result**: Latency, reliability, or memory impact.

### 3. The Hardware-Software Integration Bridge
- **Hook**: Bridging the physical mechanism (3D printed linkage / motor) with the control software (ROS2 / FOC).
- **Constraints**: Mechanical tolerances, current limits, thermal dissipation.
- **Implementation**: The algorithm and the hardware interface.
- **Key Takeaway**: Practical tips on rapid prototyping and design for manufacturing (DFM).

### 4. The Empirical Benchmark Reality Check
- **Hook**: Challenging common hype with real laboratory numbers.
- **Test Setup**: Exact hardware, compiler flags, dataset, methodology.
- **Data Table / Breakdown**: Honest comparison of results.
- **Nuance & Limitations**: Where the approach struggles.

---

## Linguistic & Stylistic Rules
- **No Cringe Openers**: Never start with "I am thrilled...", "Super excited...", "Ever wondered...", "Here's a hard truth...".
- **No Fake Engagement Bait**: Never end with "Agree?", "Thoughts?", "Drop your email below", or "Comment 'AI' for the code".
- **Formatting**: Short, readable paragraphs (2-3 sentences max). Use monospace or code formatting for variable names and register addresses.
- **Length**: 150 to 350 words. Every word must carry technical weight.
- **Output**: Writes initial post object to `lifecycle/03_drafts/<post_id>.json` matching [post.schema.json](../../../schemas/post.schema.json).
