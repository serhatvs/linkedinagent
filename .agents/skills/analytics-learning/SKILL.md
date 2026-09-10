---
name: analytics-learning
description: >-
  Ingests post metrics from Metricool MCP, evaluates technical resonance over vanity metrics, generates analytical reports, and updates persistent learning memory.
---

# Analytics & Learning Skill: Empirical Feedback Loop

The **Analytics & Learning** skill closes the loop of the agency. By rigorously evaluating what technical narratives resonate with senior engineers and founders, it guides the continuous evolution of Serhat's personal brand strategy.

---

## Metric Philosophy: Quality Over Vanity

| Vanity Metrics (Ignored) | High-Signal Quality Metrics (Optimized) |
| :--- | :--- |
| Raw impression counts | **Technical Comment Density**: In-depth questions from verified engineers |
| Clickbait CTR | **Meaningful Profile Visits**: Visits from founders, staff engineers, recruiters |
| Superficial emoji reactions | **Inbound Opportunities**: DMs proposing collaboration, jobs, or research |
| Generic comment pods | **Repository Traffic**: Direct referral clicks to Serhat's GitHub projects |

---

## Analytical Cadence

1. **Snapshot Ingestion (T+48h & T+7d)**:
   - Ingest post metrics via Metricool MCP: `get_post_analytics(post_id)`.
   - Store raw snapshot in `analytics/snapshots/<post_id>_<timestamp>.json`.

2. **Quality Metric Calculation**:
   $$\text{Quality Engagement Ratio} = \frac{\text{Technical Comments} + \text{Saves} + \text{Sends}}{\text{Total Impressions}} \times 100$$
   $$\text{Conversion Score} = \text{Inbound Inquiries} \times 10 + \text{Target Profile Visits}$$

3. **Synthesis & Learning**:
   - Compile weekly report adhering to [analytics_report.schema.json](../../../schemas/analytics_report.schema.json) in `analytics/reports/`.
   - Identify what technical angle, hook, or visual artifact drove outsized signal.
   - Append concrete heuristics to `memory/lessons_learned.json`.
   - Update hook templates and recommended word counts in `memory/editorial_insights.json`.
   - Transition post to final state `lifecycle/09_analyzed/<post_id>.json`.
