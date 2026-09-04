from __future__ import annotations

import pytest

from research_os.programs import (
    KnowledgeGainAssessment,
    ResearchProgram,
    ResearchProgramController,
    ResearchProgramStatus,
    ResearchStepUtilityAssessment,
    UtilityRecommendation,
)


def _program() -> ResearchProgram:
    return ResearchProgram(
        "PROG-TEST",
        "bounded test program",
        "general",
        "test a bounded research state transition",
        "the state machine needs an auditable gap",
        "an unresolved test gap",
        max_campaigns=1,
        max_iterations=3,
        max_runs=1,
        max_sources=1,
        max_candidates=2,
        max_failures=1,
    )


def test_questions_require_an_explicit_gap() -> None:
    with pytest.raises(ValueError, match="gap_it_attempts_to_resolve"):
        ResearchProgram(
            "PROG-BAD",
            "invalid",
            "general",
            "objective",
            "motivation",
            "problem",
            research_questions=({"question": "missing gap"},),
        )

    with pytest.raises(ValueError, match="gap_it_attempts_to_resolve"):
        ResearchProgramController(_program()).add_question({"question_id": "Q-1", "question": "missing gap"})


def test_resource_limits_are_immutable() -> None:
    controller = ResearchProgramController(_program())
    with pytest.raises(PermissionError, match="max_runs"):
        controller.transition(max_runs=2)


def test_utility_contract_rejects_universal_numeric_gain() -> None:
    with pytest.raises(ValueError, match="universal numeric score"):
        ResearchStepUtilityAssessment(
            "UTIL-1",
            "PROG-TEST",
            "STEP-1",
            "test gap",
            "test question",
            (),
            {"score": 0.9},
            "low",
            (),
            (),
            (),
            None,
            "bounded",
            "low",
            UtilityRecommendation.EXECUTE,
            "registered evidence can answer the gap",
        )


def test_two_non_progress_iterations_stop_the_program() -> None:
    controller = ResearchProgramController(_program())
    controller = controller.add_question({"question_id": "Q-1", "question": "first", "gap_it_attempts_to_resolve": "gap"})
    controller = controller.record_iteration()
    controller = controller.add_question({"question_id": "Q-2", "question": "second", "gap_it_attempts_to_resolve": "gap"})
    controller = controller.record_iteration()
    assert controller.consecutive_no_progress == 2
    assert controller.program.status is ResearchProgramStatus.NO_PROGRESS
    assert controller.program.stop_reason == "two_consecutive_iterations_without_scientific_progress"


def test_knowledge_gain_is_qualitative_and_auditable() -> None:
    gain = KnowledgeGainAssessment(
        "PROG-TEST",
        new_partial_claim_ids=("CLAIM-1",),
        new_evidence_ids=("EVD-1",),
        unresolved_uncertainty=("external validation remains absent",),
        summary="The bounded run added one partial claim and preserved the open uncertainty.",
    )
    assert gain.has_positive_gain
    assert gain.to_dict()["new_partial_claim_ids"] == ["CLAIM-1"]
