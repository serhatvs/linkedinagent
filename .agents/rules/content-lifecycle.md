# Content Lifecycle & State Machine Rules

All content artifacts managed by this agency are statefully tracked through 9 canonical stages.

```
IDEA ➔ CANDIDATE ➔ DRAFT ➔ REVIEWED ➔ AWAITING_APPROVAL ➔ APPROVED ➔ SCHEDULED ➔ PUBLISHED ➔ ANALYZED
```

---

## 1. Lifecycle State Definitions

1. **`IDEA`** (`lifecycle/01_ideas/`):
   - Unstructured spark, raw bug fix note, interesting benchmark snippet, or hardware discovery.
   - Sourced autonomously by `scout` or logged directly by Serhat.

2. **`CANDIDATE`** (`lifecycle/02_candidates/`):
   - Evaluated by `strategist`.
   - Has an assigned content pillar, technical angle, target audience, and novelty score.
   - If the idea is deemed trivial or premature, it is rejected or archived as a `HOLD / NO-OP`.

3. **`DRAFT`** (`lifecycle/03_drafts/`):
   - Fully fleshed out technical post by `writer`.
   - Structured with hook, technical problem, architecture/mechanism, benchmark/code proof, and key takeaway.
   - Cites concrete sources in `knowledge/`.

4. **`REVIEWED`** (`lifecycle/04_reviewed/`):
   - Evaluated by `editorial-review`.
   - Contains a formal Scorecard across 5 dimensions (Technical Rigor, Grounding, Slop Index, Visual Utility, Reader ROI).
   - Must achieve a score of ≥ 85/100 and a Slop Index of 0 to pass.

5. **`AWAITING_APPROVAL`** (`lifecycle/05_awaiting_approval/`):
   - Packaging stage. An Approval Request package is compiled and placed in `approvals/pending/`.
   - Ready for Serhat's review.

6. **`APPROVED`** (`lifecycle/06_approved/`):
   - Human sign-off granted by Serhat via signed approval token.
   - The SHA-256 hash of the content payload is permanently locked.

7. **`SCHEDULED`** (`lifecycle/07_scheduled/`):
   - Queued in Metricool with an assigned publishing datetime.
   - Verified against the Metricool MCP scheduling queue.

8. **`PUBLISHED`** (`lifecycle/08_published/`):
   - Confirmed live on LinkedIn via Metricool webhook/status check.
   - Stored in persistent archive with live post URL and timestamp.

9. **`ANALYZED`** (`lifecycle/09_analyzed/`):
   - Post-performance data ingested 7 days and 30 days post-publish.
   - Qualitative learnings extracted to `memory/lessons_learned.json`.

---

## 2. Invariant Rules
- **No Skipping**: A post cannot jump directly from `DRAFT` to `APPROVED` or `SCHEDULED`. Every gate must execute and produce its audit log.
- **Immutability After Approval**: Once approved, any edit to the content invalidates the hash and requires re-approval.
- **Explicit NO-OP**: If the strategist finds no worthy candidate during a cycle, the lifecycle engine records a formal `NO-OP_RECORD` explaining the reasoning and halts the cycle safely.
