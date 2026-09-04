from __future__ import annotations

import pytest

from research_os.prioritization import PriorityRecommendation, ResearchPriorityAssessment, ResearchPriorityQueue


def _assessment(assessment_id: str, recommendation: PriorityRecommendation) -> ResearchPriorityAssessment:
    return ResearchPriorityAssessment(
        assessment_id,
        "Q-1",
        "GAP-1",
        "HIGH",
        ("E1_ML",),
        ("E4_CURATED_EXPERIMENTAL",),
        "actionable",
        "high: could change a decision",
        "LOW",
        ("engine",),
        ("dataset",),
        ("source",),
        None,
        "bounded search",
        "SAFE",
        recommendation,
        "explicit current evidence and gap state determine this recommendation",
    )


def test_priority_queue_is_traceable_and_not_a_magic_score() -> None:
    queue = ResearchPriorityQueue.from_assessments((_assessment("PRI-1", PriorityRecommendation.PRIORITIZE_NOW), _assessment("PRI-2", PriorityRecommendation.LOW_INFORMATION_GAIN)))
    assert queue.valid
    assert queue.entries[0].assessment_id == "PRI-1"
    assert all(entry.reason_for_order for entry in queue.entries)
    assert "score" not in queue.to_dict()


def test_priority_assessment_rejects_universal_score() -> None:
    with pytest.raises(ValueError, match="universal hidden score"):
        ResearchPriorityAssessment(
            "PRI-BAD",
            "Q-1",
            "GAP-1",
            "HIGH",
            (),
            (),
            "actionable",
            {"score": 0.8},
            "LOW",
            (),
            (),
            (),
            None,
            "bounded",
            "SAFE",
            PriorityRecommendation.PRIORITIZE_NOW,
            "structured rationale",
        )


def test_reorder_keeps_prior_assessment_history() -> None:
    old = _assessment("PRI-OLD", PriorityRecommendation.BLOCKED)
    new = ResearchPriorityAssessment(**{**old.to_dict(), "assessment_id": "PRI-NEW", "recommendation": PriorityRecommendation.SECONDARY, "supersedes_assessment_id": old.assessment_id})
    queue = ResearchPriorityQueue.from_assessments((new,), history=(old,))
    assert len(queue.assessment_history) == 2
    assert queue.assessment_history[0].assessment_id == "PRI-OLD"
    assert queue.entries[0].assessment_id == "PRI-NEW"
