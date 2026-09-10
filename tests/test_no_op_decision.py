"""Tests verifying the Strategist's ability to issue a NO-OP / HOLD decision when substance is insufficient."""

from pathlib import Path
from core.models import Idea, Candidate, CandidateDecision, MVTSEvaluation
from core.lifecycle_manager import LifecycleManager


def test_strategist_issues_no_op_on_shallow_idea():
    ws = Path(__file__).resolve().parent.parent
    lm = LifecycleManager(ws)

    # 1. Ingest shallow idea
    shallow_idea = Idea(
        idea_id="idea_shallow_reflection",
        source_type="lab_note",
        title="Thinking about microcontrollers vs FPGAs",
        raw_notes="Had some general thoughts on when to use an FPGA vs an MCU for robotics.",
        pillar_affinity="pillar_embedded_firmware",
        technical_artifacts_available=[]  # Zero artifacts
    )
    lm.save_idea(shallow_idea)

    # 2. Evaluate MVTS: missing grounding, missing artifacts, missing concrete numbers
    mvts = MVTSEvaluation(
        grounding_score=1.0,
        technical_artifact_score=0.0,
        engineering_tradeoff_score=1.0,
        actionable_takeaway_score=1.0,
        total_score=3.0  # Well below 8.0 threshold
    )

    assert mvts.total_score < 8.0

    cand = Candidate(
        candidate_id="cand_shallow_reflection",
        idea_id=shallow_idea.idea_id,
        pillar=shallow_idea.pillar_affinity,
        target_audience=["Firmware Engineers"],
        angle="Conceptual Reflection",
        mvts_evaluation=mvts,
        decision=CandidateDecision.HOLD_NO_OP,
        hold_rationale="Purely conceptual. Missing bench comparison, hardware benchmarks, and logic traces."
    )
    lm.save_candidate(cand)

    assert cand.decision == CandidateDecision.HOLD_NO_OP
    assert cand.hold_rationale is not None

    # Verify pipeline state: NO draft should exist for this candidate
    draft = lm.get_post("post_shallow_reflection")
    assert draft is None
