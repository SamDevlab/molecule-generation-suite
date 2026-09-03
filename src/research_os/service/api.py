"""Service boundary used by a chat-first client.

The service coordinates typed Oracle objects and recorded stores. It does not
expose Lab internals to the frontend and never executes free-form model text.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from research_os.candidates import CandidateRanking
from research_os.oracle import OracleAnswer, OraclePlanner, PlanningResult, ResearchMemory
from research_os.service.contracts import ResearchJob, ResearchJobStatus


@dataclass(frozen=True)
class ServiceResponse:
    job: ResearchJob
    planning: PlanningResult
    answer: OracleAnswer

    def to_dict(self) -> dict[str, Any]:
        return {"job": self.job.to_dict(), "planning": self.planning.to_dict(), "answer": self.answer.to_dict()}


class OracleService:
    """Chat-first facade for ask/continue/plan/result/evidence operations."""

    def __init__(self, planner: OraclePlanner | None = None, *, memory: ResearchMemory | None = None, ledger: Any | None = None):
        self.planner = planner or OraclePlanner()
        self.memory = memory or ResearchMemory(ledger)
        self.ledger = ledger
        self._responses: dict[str, ServiceResponse] = {}

    def ask(self, text: str) -> ServiceResponse:
        planning = self.planner.ask(text, memory=[item.to_dict() for item in self.memory.search(text)])
        job = ResearchJob(planning.question.question_id, plan_id=planning.plan.plan_id, status=ResearchJobStatus.PLANNING, started_at=datetime.now(timezone.utc).isoformat())
        job.emit("question_interpreted", "ResearchQuestion created", completed=True, question_id=planning.question.question_id)
        job.emit("knowledge_retrieved", "Research memory consulted", completed=True)
        job.emit("plan_created", "ResearchPlan materialized", completed=True, plan_id=planning.plan.plan_id)
        job.status = ResearchJobStatus.VALIDATING
        job.emit("plan_validated", f"plan validation status: {planning.validation.status}", completed=True, status=planning.validation.status)
        answer = self.planner.answer_from_plan(planning)
        if answer.status.value in {"REJECTED"}:
            job.status = ResearchJobStatus.FAILED
        elif answer.status.value == "INDETERMINATE":
            job.status = ResearchJobStatus.INDETERMINATE
            job.emit("evidence_gaps", "required engine or evidence is unavailable", completed=True)
        else:
            job.status = ResearchJobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc).isoformat()
        response = ServiceResponse(job, planning, answer)
        self._responses[job.job_id] = response
        self.memory.remember("question", planning.question.question_id, planning.question.to_dict())
        self.memory.remember("plan", planning.plan.plan_id, planning.plan.to_dict())
        return response

    def continue_research(self, job_id: str) -> ServiceResponse:
        previous = self._responses[job_id]
        question, plan = self.memory.continue_research(previous.planning.plan)
        planning = PlanningResult(question, plan, self.planner.validator.validate(plan), previous.planning.audits, previous.planning.plan.plan_id)
        job = ResearchJob(question.question_id, plan_id=plan.plan_id, status=ResearchJobStatus.VALIDATING, started_at=datetime.now(timezone.utc).isoformat())
        job.emit("plan_created", "new continuation plan created; previous plan remains immutable", completed=True, rerun_of=plan.rerun_of)
        job.emit("plan_validated", f"plan validation status: {planning.validation.status}", completed=True)
        answer = self.planner.answer_from_plan(planning)
        job.status = ResearchJobStatus.INDETERMINATE if answer.status.value == "INDETERMINATE" else ResearchJobStatus.COMPLETED if answer.status.value != "REJECTED" else ResearchJobStatus.FAILED
        job.completed_at = datetime.now(timezone.utc).isoformat()
        response = ServiceResponse(job, planning, answer)
        self._responses[job.job_id] = response
        self.memory.remember("plan", plan.plan_id, plan.to_dict(), rerun_of=plan.rerun_of)
        return response

    def get_plan(self, job_id: str) -> dict[str, Any]:
        return self._responses[job_id].planning.plan.to_dict()

    def get_results(self, job_id: str) -> dict[str, Any]:
        return self._responses[job_id].answer.to_dict()

    def get_evidence(self, job_id: str) -> list[dict[str, Any]]:
        return list(self._responses[job_id].answer.evidence)

    def get_sources(self, job_id: str) -> list[str]:
        return list(self._responses[job_id].answer.sources)

    def get_runs(self, job_id: str) -> list[str]:
        return list(self._responses[job_id].answer.run_ids)

    def get_lineage(self, job_id: str) -> dict[str, Any]:
        response = self._responses[job_id]
        return {"job_id": job_id, "question_id": response.planning.question.question_id, "plan_id": response.planning.plan.plan_id, "rerun_of": response.planning.plan.rerun_of}

    def compare_runs(self, original_run_id: str, rerun_run_id: str) -> dict[str, Any]:
        if self.ledger is None:
            return {"status": "INDETERMINATE", "reason": "no Ledger configured"}
        return self.ledger.compare_runs(original_run_id, rerun_run_id).to_dict()

    def explain_ranking(self, ranking: CandidateRanking, candidate_a: str, candidate_b: str) -> dict[str, Any]:
        left = next((item for item in ranking.ranked if item.candidate_id == candidate_a), None)
        right = next((item for item in ranking.ranked if item.candidate_id == candidate_b), None)
        if left is None or right is None:
            return {"status": "INSUFFICIENT_EVIDENCE", "reason": "one or both candidates are not in the auditable ranking"}
        return {"status": "SUPPORTED", "metric": ranking.metric, "direction": ranking.direction, "winner": candidate_a if (left.value >= right.value if ranking.direction == "max" else left.value <= right.value) else candidate_b, "comparison": {candidate_a: left.to_dict(), candidate_b: right.to_dict()}, "reason": "comparison is derived only from recorded metric, evidence, status, OOD, uncertainty and conditions"}


class ResearchService(OracleService):
    pass


class RunService:
    def __init__(self, ledger: Any):
        self.ledger = ledger

    def get_runs(self, **filters: Any) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.ledger.search_runs(**filters)]

    def get_lineage(self, run_id: str) -> dict[str, Any]:
        return self.ledger.get_lineage(run_id).to_dict()

    def compare_runs(self, original_run_id: str, rerun_run_id: str) -> dict[str, Any]:
        return self.ledger.compare_runs(original_run_id, rerun_run_id).to_dict()


class DatasetService:
    def __init__(self, registry: Any):
        self.registry = registry

    def get_datasets(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.registry.list()]


class KnowledgeService:
    def __init__(self, retriever: Any):
        self.retriever = retriever

    def get_sources(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.retriever.search(query, limit=limit)]

