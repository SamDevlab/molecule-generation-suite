"""Service boundary used by a chat-first client.

The service coordinates typed Oracle objects and recorded stores. It does not
expose Lab internals to the frontend and never executes free-form model text.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Iterable

from research_os.candidates import CandidateRanking
from research_os.bundles import ResearchBundle
from research_os.core.types import EvidenceLevel, RunLineage
from research_os.environment import capture_environment
from research_os.oracle import OracleAnswer, OracleAnswerStatus, OraclePlanner, PlanningResult, ResearchMemory
from research_os.orchestration import ResearchOrchestrator, default_registry
from research_os.orchestration.runner import PlanStep as RunnerPlanStep
from research_os.service.contracts import ResearchJob, ResearchJobStatus


@dataclass(frozen=True)
class ServiceResponse:
    job: ResearchJob
    planning: PlanningResult
    answer: OracleAnswer
    execution: Any | None = None
    bundle: ResearchBundle | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job": self.job.to_dict(),
            "planning": self.planning.to_dict(),
            "execution": self.execution.to_dict() if self.execution is not None and hasattr(self.execution, "to_dict") else None,
            "bundle": self.bundle.root if self.bundle is not None else None,
            "answer": self.answer.to_dict(),
        }


class OracleService:
    """Chat-first facade for ask/continue/plan/result/evidence operations."""

    def __init__(self, planner: OraclePlanner | None = None, *, memory: ResearchMemory | None = None, ledger: Any | None = None, registry: Any | None = None, bundle_root: str | Path | None = None, knowledge_retriever: Any | None = None, environment: Any | None = None):
        self.planner = planner or OraclePlanner()
        self.memory = memory or ResearchMemory(ledger)
        self.ledger = ledger
        self.registry = registry or default_registry()
        self.orchestrator = ResearchOrchestrator(self.registry)
        self.bundle_root = Path(bundle_root) if bundle_root is not None else None
        self.knowledge_retriever = knowledge_retriever
        self.environment = environment
        self._responses: dict[str, ServiceResponse] = {}

    def ask(self, text: str) -> ServiceResponse:
        planning = self.planner.ask(text, memory=[item.to_dict() for item in self.memory.search(text)])
        job = ResearchJob(planning.question.question_id, plan_id=planning.plan.plan_id, status=ResearchJobStatus.PLANNING, started_at=datetime.now(timezone.utc).isoformat())
        job.emit("question_interpreted", "ResearchQuestion created", completed=True, question_id=planning.question.question_id)
        job.emit("knowledge_retrieved", "Research memory consulted", completed=True)
        job.emit("plan_created", "ResearchPlan materialized", completed=True, plan_id=planning.plan.plan_id)
        job.status = ResearchJobStatus.VALIDATING
        job.emit("plan_validated", f"plan validation status: {planning.validation.status}", completed=True, status=planning.validation.status)
        execution = None
        bundle = None
        if planning.reformulated_from or planning.validation.status == "FAIL":
            answer = self.planner.answer_from_plan(planning)
        else:
            job.status = ResearchJobStatus.RUNNING
            job.emit("execution_started", "validated plan submitted to ResearchOrchestrator", completed=False)
            execution = self._execute(planning)
            bundle = self._persist_execution(execution)
            answer = self._answer_from_execution(planning, execution, bundle=bundle)
            job.emit("execution_completed", f"execution status: {answer.status.value}", completed=True, workflow_id=execution.plan_id)
            if answer.status is OracleAnswerStatus.INDETERMINATE:
                job.emit("evidence_gaps", "required engine, evidence or downstream dependency is unavailable", completed=True)
        if answer.status is OracleAnswerStatus.REJECTED:
            job.status = ResearchJobStatus.FAILED
        elif answer.status is OracleAnswerStatus.INDETERMINATE:
            job.status = ResearchJobStatus.INDETERMINATE
        else:
            job.status = ResearchJobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc).isoformat()
        response = ServiceResponse(job, planning, answer, execution, bundle)
        self._responses[job.job_id] = response
        self.memory.remember("question", planning.question.question_id, planning.question.to_dict())
        self.memory.remember("plan", planning.plan.plan_id, planning.plan.to_dict())
        return response

    def continue_research(self, job_id: str) -> ServiceResponse:
        previous = self._responses[job_id]
        question, plan = self.memory.continue_research(previous.planning.plan)
        planning = PlanningResult(question, plan, self.planner.validator.validate(plan, question=question), previous.planning.audits, previous.planning.plan.plan_id)
        job = ResearchJob(question.question_id, plan_id=plan.plan_id, status=ResearchJobStatus.VALIDATING, started_at=datetime.now(timezone.utc).isoformat())
        job.emit("plan_created", "new continuation plan created; previous plan remains immutable", completed=True, rerun_of=plan.rerun_of)
        job.emit("plan_validated", f"plan validation status: {planning.validation.status}", completed=True)
        execution = None
        bundle = None
        if planning.validation.status != "FAIL":
            job.status = ResearchJobStatus.RUNNING
            job.emit("execution_started", "continuation plan submitted to ResearchOrchestrator", completed=False)
            execution = self._execute(planning)
            previous_runs = previous.execution.runs if previous.execution is not None else {}
            ledger_parent = previous.execution.plan_id if previous.execution is not None else previous.planning.plan.plan_id
            bundle = self._persist_execution(execution, rerun_of=ledger_parent, parent_runs=previous_runs)
            answer = self._answer_from_execution(planning, execution, bundle=bundle)
            job.emit("execution_completed", f"execution status: {answer.status.value}", completed=True, workflow_id=execution.plan_id)
        else:
            answer = self.planner.answer_from_plan(planning)
        job.status = ResearchJobStatus.INDETERMINATE if answer.status is OracleAnswerStatus.INDETERMINATE else ResearchJobStatus.COMPLETED if answer.status is not OracleAnswerStatus.REJECTED else ResearchJobStatus.FAILED
        job.completed_at = datetime.now(timezone.utc).isoformat()
        response = ServiceResponse(job, planning, answer, execution, bundle)
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
        result = {"job_id": job_id, "question_id": response.planning.question.question_id, "plan_id": response.planning.plan.plan_id, "rerun_of": response.planning.plan.rerun_of, "run_ids": list(response.answer.run_ids), "workflow_ids": list(response.answer.workflow_ids)}
        if self.ledger is not None:
            result["ledger"] = {run_id: self.ledger.get_lineage(run_id).to_dict() for run_id in response.answer.run_ids if self._ledger_has_run(run_id)}
        return result

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

    def _execute(self, planning: PlanningResult) -> Any:
        steps = tuple(
            RunnerPlanStep(
                step_id=step.step_id,
                lab=step.lab,
                inputs=dict(step.inputs),
                experiment=step.experiment,
                requires=tuple(step.requires),
                consumed_evidence_ids=tuple(step.consumes),
            )
            for step in planning.plan.steps
        )
        return self.orchestrator.run(steps)

    def _persist_execution(self, execution: Any, *, rerun_of: str | None = None, parent_runs: dict[str, Any] | None = None) -> ResearchBundle | None:
        if self.ledger is None and self.bundle_root is None:
            return None
        environment = self.environment or capture_environment()
        for step_id, run in execution.runs.items():
            parent = (parent_runs or {}).get(step_id)
            if parent is not None:
                object.__setattr__(run, "lineage", RunLineage(parent_run_id=parent.run_id, rerun_of=parent.run_id, derived_from=(parent.run_id,)))
            run.attach_environment(environment)
            if run.lifecycle.value in {"COMPLETED", "FAILED", "INDETERMINATE"}:
                run.seal()
        root = self.bundle_root or (Path(self.ledger.root) / "bundles")
        bundle = ResearchBundle.create(execution, root, environment=environment)
        if self.ledger is not None:
            self.ledger.register_run(bundle, rerun_of=rerun_of)
        return bundle

    def _ledger_has_run(self, run_id: str) -> bool:
        try:
            self.ledger.get_run(run_id)
        except KeyError:
            return False
        return True

    def _answer_from_execution(self, planning: PlanningResult, execution: Any, *, bundle: ResearchBundle | None = None) -> OracleAnswer:
        evidence_items = [_evidence_to_dict(evidence) for run in execution.runs.values() for evidence in run.evidence]
        records = list(execution.steps.values())
        first_record = execution.first_loss
        first_loss = None
        if first_record is not None and first_record.first_loss is not None:
            first_loss = {
                "step_id": first_record.step_id,
                "rule_id": first_record.first_loss.rule_id,
                "status": first_record.first_loss.status.value,
                "message": first_record.first_loss.reason,
                "diagnostics": dict(first_record.first_loss.diagnostics),
            }
        if first_loss is None and planning.validation.status == "INSUFFICIENT_EVIDENCE" and planning.validation.first_loss is not None:
            first_loss = {"rule_id": planning.validation.first_loss.rule_id, "status": planning.validation.first_loss.status, "message": planning.validation.first_loss.message, "diagnostics": dict(planning.validation.first_loss.diagnostics)}

        if any(record.status == "FAIL" for record in records):
            status = OracleAnswerStatus.REJECTED
        elif any(record.status in {"INDETERMINATE", "SKIPPED"} for record in records):
            status = OracleAnswerStatus.INDETERMINATE
        else:
            observed = max((_evidence_rank(item.get("level")) for item in evidence_items), default=-1)
            required = _evidence_rank(planning.question.required_evidence_level)
            status = OracleAnswerStatus.INSUFFICIENT_EVIDENCE if required > observed else OracleAnswerStatus.SUPPORTED

        retrieved = self._retrieve(planning.question.text)
        provider = self.planner.provider
        summary_payload = execution.to_dict()
        summary_payload.update({"status": status.value, "evidence": evidence_items})
        try:
            generated = provider.summarize_results(summary_payload)
        except Exception:
            generated = {"summary": "Recorded execution result; provider narration was unavailable."}
        summary = str(generated.get("summary", "Recorded execution result."))
        summary += f" Status={status.value}; steps=" + ", ".join(f"{record.step_id}:{record.status}" for record in records) + "."
        if first_loss is not None:
            summary += f" FIRST_LOSS={first_loss.get('rule_id')} at {first_loss.get('step_id', 'validation')}."
        if retrieved:
            summary += " Reviewed knowledge sources were attached as citations; they do not increase computational evidence level."
        limitations = list(planning.plan.risk_flags)
        if first_loss is not None:
            limitations.append(str(first_loss.get("message", "execution stopped at the first loss")))
        if status is OracleAnswerStatus.INDETERMINATE:
            limitations.append("downstream steps remain SKIPPED after the first unavailable or indeterminate dependency")
        if status in {OracleAnswerStatus.SUPPORTED, OracleAnswerStatus.INSUFFICIENT_EVIDENCE}:
            limitations.append("computational and curated knowledge records do not prove experiment, efficacy, safety, cure or clinical outcome")
        run_ids = tuple(run.run_id for run in execution.runs.values())
        metadata = {
            "grounded": True,
            "provider": getattr(provider, "provider_id", type(provider).__name__),
            "provider_metadata": dict(getattr(provider, "audit_metadata", {}) or {}),
            "workflow_id": execution.plan_id,
        }
        return OracleAnswer(
            status=status,
            summary=summary,
            evidence=tuple(evidence_items),
            limitations=tuple(dict.fromkeys(limitations)),
            first_loss=first_loss,
            sources=tuple(item["source_id"] for item in retrieved if item.get("source_id")),
            run_ids=run_ids,
            workflow_ids=(execution.plan_id,),
            bundle_ids=(bundle.bundle_id,) if bundle is not None else (),
            metadata=metadata,
        )

    def _retrieve(self, query: str) -> list[dict[str, Any]]:
        if self.knowledge_retriever is None:
            return []
        try:
            results = list(self.knowledge_retriever.search(query, limit=20))
            # SQLite FTS treats punctuation as query syntax.  Retry with a
            # single meaningful token so chat punctuation cannot turn a
            # retrieval miss into a fabricated citation.
            if not results:
                for token in re.findall(r"[\wÀ-ÿ]+", query, flags=re.UNICODE):
                    if len(token) < 4:
                        continue
                    results = list(self.knowledge_retriever.search(token, limit=20))
                    if results:
                        break
            return [item.to_dict() if hasattr(item, "to_dict") else dict(item) for item in results]
        except Exception:
            # Retrieval failure is recorded as an absent citation, never as
            # scientific evidence and never as a reason to invent a source.
            return []


def _evidence_rank(value: Any) -> int:
    try:
        level = value if isinstance(value, EvidenceLevel) else EvidenceLevel(str(value))
    except (TypeError, ValueError):
        return -1
    return {level: index for index, level in enumerate((EvidenceLevel.E0_HEURISTIC, EvidenceLevel.E1_ML, EvidenceLevel.E2_COMPUTATIONAL, EvidenceLevel.E3_PHYSICS, EvidenceLevel.E4_CURATED_EXPERIMENTAL, EvidenceLevel.E5_VALIDATED_EXPERIMENTAL))}.get(level, -1)


def _evidence_to_dict(evidence: Any) -> dict[str, Any]:
    data = asdict(evidence)
    level = data.get("level")
    data["level"] = level.value if hasattr(level, "value") else str(level)
    return data


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
