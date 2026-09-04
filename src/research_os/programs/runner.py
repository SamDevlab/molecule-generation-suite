"""Bounded controller primitives for autonomous Research Programs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from research_os.programs.models import ResearchProgram, ResearchProgramStatus, ResearchStepUtilityAssessment, UtilityRecommendation


_LIMIT_FIELDS = ("max_campaigns", "max_iterations", "max_runs", "max_sources", "max_candidates", "max_failures")


def _rebuild(program: ResearchProgram, **changes: Any) -> ResearchProgram:
    payload = program._hash_payload()
    payload.update(changes)
    return ResearchProgram(**payload)


@dataclass(frozen=True)
class ResearchProgramController:
    """Immutable state machine; limits are copied and cannot be enlarged."""

    program: ResearchProgram
    consecutive_no_progress: int = 0
    iteration_count: int = 0
    run_count: int = 0
    failure_count: int = 0

    def add_question(self, question: Mapping[str, Any]) -> "ResearchProgramController":
        if not str(question.get("gap_it_attempts_to_resolve") or "").strip():
            raise ValueError("question rejected: gap_it_attempts_to_resolve is required")
        if len(self.program.research_questions) >= self.program.max_iterations:
            return self
        question_id = str(question.get("question_id") or f"Q-{len(self.program.research_questions) + 1:03d}")
        item = {**dict(question), "question_id": question_id}
        program = _rebuild(self.program, research_questions=(*self.program.research_questions, item), current_question_id=question_id, open_question_ids=tuple(dict.fromkeys((*self.program.open_question_ids, question_id))), status=ResearchProgramStatus.RUNNING)
        return replace(self, program=program)

    def assess_step(self, assessment: ResearchStepUtilityAssessment) -> "ResearchProgramController":
        if assessment.program_id != self.program.program_id:
            raise ValueError("utility assessment belongs to another program")
        if assessment.recommendation == UtilityRecommendation.EXECUTE and self.run_count >= self.program.max_runs:
            return replace(self, program=self.program.with_status(ResearchProgramStatus.INDETERMINATE, stop_reason="max_runs"))
        return self

    def record_iteration(self, *, evidence_ids: tuple[str, ...] = (), source_ids: tuple[str, ...] = (), dataset_ids: tuple[str, ...] = (), claim_revision_ids: tuple[str, ...] = (), resolved_gap_ids: tuple[str, ...] = (), resolved_question_ids: tuple[str, ...] = (), improved_uncertainty: bool = False, improved_comparability: bool = False, new_decision_ids: tuple[str, ...] = (), runs: int = 0, failures: int = 0) -> "ResearchProgramController":
        positive = any((evidence_ids, source_ids, dataset_ids, claim_revision_ids, resolved_gap_ids, improved_uncertainty, improved_comparability, new_decision_ids))
        no_progress = 0 if positive else self.consecutive_no_progress + 1
        iterations = self.iteration_count + 1
        total_runs = self.run_count + int(runs)
        total_failures = self.failure_count + int(failures)
        if total_runs > self.program.max_runs or iterations > self.program.max_iterations or total_failures > self.program.max_failures:
            status = ResearchProgramStatus.INDETERMINATE
            reason = "hard_resource_limit"
        elif no_progress >= 2:
            status = ResearchProgramStatus.NO_PROGRESS
            reason = "two_consecutive_iterations_without_scientific_progress"
        else:
            status = self.program.status
            reason = self.program.stop_reason
        resolved_questions = tuple(dict.fromkeys((*self.program.resolved_question_ids, *resolved_question_ids)))
        program = _rebuild(self.program, status=status, stop_reason=reason, resolved_question_ids=resolved_questions, open_question_ids=tuple(item for item in self.program.open_question_ids if item not in set(resolved_questions)))
        return replace(self, program=program, consecutive_no_progress=no_progress, iteration_count=iterations, run_count=total_runs, failure_count=total_failures)

    def transition(self, **changes: Any) -> "ResearchProgramController":
        for field in _LIMIT_FIELDS:
            if field in changes and changes[field] != getattr(self.program, field):
                raise PermissionError(f"ResearchProgram limit {field} is immutable")
        return replace(self, program=_rebuild(self.program, **changes))


__all__ = ["ResearchProgramController"]
