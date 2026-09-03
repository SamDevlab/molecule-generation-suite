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
from research_os.oracle import ClaimTarget, OracleAnswer, OracleAnswerStatus, OraclePlanner, PlanStatus, PlanningResult, ResearchMemory, ResearchPlan, ResearchQuestion
from research_os.oracle.models import PlanStep
from research_os.oracle.validator import PlanValidationResult, ValidationIssue
from research_os.orchestration import ResearchOrchestrator, default_registry
from research_os.orchestration.runner import PlanStep as RunnerPlanStep
from research_os.service.contracts import ResearchJob, ResearchJobStatus, ResearchMessage, ResearchSession
from research_os.service.persistence import ResearchStore


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

    def __init__(self, planner: OraclePlanner | None = None, *, memory: ResearchMemory | None = None, ledger: Any | None = None, registry: Any | None = None, bundle_root: str | Path | None = None, knowledge_retriever: Any | None = None, source_registry: Any | None = None, environment: Any | None = None, store: ResearchStore | None = None, engine_registry: Any | None = None):
        self.planner = planner or OraclePlanner()
        self.memory = memory or ResearchMemory(ledger)
        self.ledger = ledger
        self.registry = registry or default_registry()
        self.orchestrator = ResearchOrchestrator(self.registry)
        self.bundle_root = Path(bundle_root) if bundle_root is not None else None
        self.knowledge_retriever = knowledge_retriever
        self.source_registry = source_registry
        self.environment = environment
        self.store = store
        self.engine_registry = engine_registry
        self._responses: dict[str, ServiceResponse] = {}
        self._sessions: dict[str, ResearchSession] = {}
        self._hydrate_memory()

    def ask(self, text: str, *, session_id: str | None = None) -> ServiceResponse:
        session = self._get_or_create_session(session_id, text)
        if session.active_job_id and _is_continue_request(text):
            return self.continue_research(session.active_job_id, prompt=text)
        planning = self.planner.ask(text, memory=[item.to_dict() for item in self.memory.search(text)])
        job = ResearchJob(planning.question.question_id, session_id=session.session_id, plan_id=planning.plan.plan_id, status=ResearchJobStatus.PLANNING, started_at=datetime.now(timezone.utc).isoformat())
        self._record_user_message(session, text, question_id=planning.question.question_id, job_id=job.job_id)
        self._save_job(job)
        job.emit("question_interpreted", "ResearchQuestion created", completed=True, question_id=planning.question.question_id)
        job.emit("knowledge_retrieved", "Research memory consulted", completed=True)
        job.emit("plan_created", "ResearchPlan materialized", completed=True, plan_id=planning.plan.plan_id)
        job.status = ResearchJobStatus.VALIDATING
        job.emit("plan_validated", f"plan validation status: {planning.validation.status}", completed=True, status=planning.validation.status)
        self._save_job(job)
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
            job.workflow_id = execution.plan_id
            job.emit("execution_completed", f"execution status: {answer.status.value}", completed=True, workflow_id=execution.plan_id)
            if answer.status is OracleAnswerStatus.INDETERMINATE:
                job.emit("evidence_gaps", "required engine, evidence or downstream dependency is unavailable", completed=True)
        if answer.status is OracleAnswerStatus.REJECTED:
            job.status = ResearchJobStatus.FAILED
            job.error_code = answer.first_loss.get("rule_id") if answer.first_loss else "ORACLE-ANSWER-REJECTED"
        elif answer.status is OracleAnswerStatus.INDETERMINATE:
            job.status = ResearchJobStatus.INDETERMINATE
            job.error_code = answer.first_loss.get("rule_id") if answer.first_loss else "ORACLE-EXECUTION-INDETERMINATE"
        else:
            job.status = ResearchJobStatus.COMPLETED
        job.first_loss = answer.first_loss
        job.current_step = answer.first_loss.get("step_id") if answer.first_loss else None
        job.completed_at = datetime.now(timezone.utc).isoformat()
        response = ServiceResponse(job, planning, answer, execution, bundle)
        self._responses[job.job_id] = response
        self._finalize_session(session, response)
        self._save_job(job)
        self._save_response(response)
        self.memory.remember("question", planning.question.question_id, planning.question.to_dict())
        self.memory.remember("plan", planning.plan.plan_id, planning.plan.to_dict())
        return response

    def continue_research(self, job_id: str, *, prompt: str = "Continue essa pesquisa.") -> ServiceResponse:
        previous = self._get_response(job_id)
        session = self._get_or_create_session(previous.job.session_id, "Continue research")
        question, plan = self.memory.continue_research(previous.planning.plan)
        planning = PlanningResult(question, plan, self.planner.validator.validate(plan, question=question), previous.planning.audits, previous.planning.plan.plan_id)
        job = ResearchJob(question.question_id, session_id=session.session_id, plan_id=plan.plan_id, status=ResearchJobStatus.VALIDATING, started_at=datetime.now(timezone.utc).isoformat())
        self._record_user_message(session, prompt, question_id=question.question_id, job_id=job.job_id)
        self._save_job(job)
        job.emit("plan_created", "new continuation plan created; previous plan remains immutable", completed=True, rerun_of=plan.rerun_of)
        job.emit("plan_validated", f"plan validation status: {planning.validation.status}", completed=True)
        execution = None
        bundle = None
        if planning.validation.status != "FAIL":
            job.status = ResearchJobStatus.RUNNING
            job.emit("execution_started", "continuation plan submitted to ResearchOrchestrator", completed=False)
            execution = self._execute(planning)
            previous_runs = previous.execution.runs if previous.execution is not None else self._stored_parent_runs(previous)
            ledger_parent = previous.execution.plan_id if previous.execution is not None else (previous.job.workflow_id or previous.planning.plan.plan_id or None)
            bundle = self._persist_execution(execution, rerun_of=ledger_parent, parent_runs=previous_runs)
            answer = self._answer_from_execution(planning, execution, bundle=bundle)
            job.workflow_id = execution.plan_id
            job.emit("execution_completed", f"execution status: {answer.status.value}", completed=True, workflow_id=execution.plan_id)
        else:
            answer = self.planner.answer_from_plan(planning)
        job.status = ResearchJobStatus.INDETERMINATE if answer.status is OracleAnswerStatus.INDETERMINATE else ResearchJobStatus.COMPLETED if answer.status is not OracleAnswerStatus.REJECTED else ResearchJobStatus.FAILED
        job.error_code = answer.first_loss.get("rule_id") if answer.first_loss and job.status is not ResearchJobStatus.COMPLETED else None
        job.first_loss = answer.first_loss
        job.current_step = answer.first_loss.get("step_id") if answer.first_loss else None
        job.completed_at = datetime.now(timezone.utc).isoformat()
        response = ServiceResponse(job, planning, answer, execution, bundle)
        self._responses[job.job_id] = response
        self._finalize_session(session, response)
        self._save_job(job)
        self._save_response(response)
        self.memory.remember("plan", plan.plan_id, plan.to_dict(), rerun_of=plan.rerun_of)
        return response

    def create_session(self, title: str = "New research", *, tags: list[str] | None = None) -> ResearchSession:
        session = self.store.create_session(title, tags=tags) if self.store is not None else ResearchSession(title=title, tags=list(tags or []))
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> dict[str, Any]:
        return (self.store.get_session(session_id) if self.store is not None else self._sessions[session_id]).to_dict()

    def list_sessions(self, *, limit: int = 100) -> list[dict[str, Any]]:
        sessions = self.store.list_sessions(limit=limit) if self.store is not None else list(self._sessions.values())[:limit]
        return [item.to_dict() for item in sessions]

    def list_jobs(self, session_id: str | None = None, *, limit: int = 100) -> list[dict[str, Any]]:
        if self.store is not None:
            return self.store.list_jobs(session_id, limit=limit)
        values = [item.job.to_dict() for item in self._responses.values() if session_id is None or item.job.session_id == session_id]
        return values[-limit:][::-1]

    def get_plan(self, job_id: str) -> dict[str, Any]:
        return self._response_payload(job_id)["planning"]["plan"]

    def get_results(self, job_id: str) -> dict[str, Any]:
        return self._response_payload(job_id)["answer"]

    def get_evidence(self, job_id: str) -> list[dict[str, Any]]:
        return list(self._response_payload(job_id)["answer"].get("evidence") or [])

    def filter_evidence(self, job_id: str, minimum: str | EvidenceLevel) -> dict[str, Any]:
        required = minimum if isinstance(minimum, EvidenceLevel) else EvidenceLevel(str(minimum))
        evidence = [item for item in self.get_evidence(job_id) if _evidence_rank(item.get("level")) >= _evidence_rank(required)]
        return {"minimum_evidence": required.value, "status": "SUPPORTED" if evidence else "INSUFFICIENT_EVIDENCE", "evidence": evidence, "message": "No recorded evidence meets the requested minimum level." if not evidence else "Evidence is filtered from recorded runs only."}

    def get_sources(self, job_id: str) -> list[str]:
        return list(self._response_payload(job_id)["answer"].get("sources") or [])

    def get_source_records(self, job_id: str) -> list[dict[str, Any]]:
        ids = self.get_sources(job_id)
        if self.source_registry is None:
            return [{"source_id": source_id} for source_id in ids]
        records = []
        for source_id in ids:
            try:
                records.append(self.source_registry.get(source_id).to_dict())
            except (KeyError, AttributeError):
                records.append({"source_id": source_id})
        return records

    def get_runs(self, job_id: str) -> list[str]:
        return list(self._response_payload(job_id)["answer"].get("run_ids") or [])

    def get_lineage(self, job_id: str) -> dict[str, Any]:
        response = self._get_response(job_id)
        result = {"job_id": job_id, "question_id": response.planning.question.question_id, "plan_id": response.planning.plan.plan_id, "rerun_of": response.planning.plan.rerun_of, "run_ids": list(response.answer.run_ids), "workflow_ids": list(response.answer.workflow_ids)}
        if self.ledger is not None:
            result["ledger"] = {run_id: self.ledger.get_lineage(run_id).to_dict() for run_id in response.answer.run_ids if self._ledger_has_run(run_id)}
        return result

    def get_response(self, job_id: str) -> dict[str, Any]:
        return self._response_payload(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        if job_id in self._responses:
            return self._responses[job_id].job.to_dict()
        if self.store is not None:
            try:
                return self.store.get_response(job_id)["job"]
            except KeyError:
                return self.store.get_job(job_id)
        raise KeyError(job_id)

    def get_engine_status(self) -> list[dict[str, Any]]:
        from research_os.engines import EngineRegistry
        registry = self.engine_registry or EngineRegistry()
        return [item.to_dict() for item in registry.probe_all()]

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
        if status is OracleAnswerStatus.INSUFFICIENT_EVIDENCE:
            metadata["research_gap"] = {
                "what_we_know": [item.get("kind") for item in evidence_items],
                "current_evidence": max((item.get("level") for item in evidence_items), default=None),
                "required_evidence": planning.question.required_evidence_level.value,
                "missing_information": ["independent evidence at the requested level"],
                "recommended_next_steps": ["add a reviewed experimental source or validated experiment"],
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
        # SQLite FTS treats punctuation such as a hyphen as query syntax. Try
        # the complete query first, then meaningful tokens independently so a
        # syntax error cannot suppress a valid citation fallback.
        queries = [query, *(token for token in re.findall(r"[\wÀ-ÿ]+", query, flags=re.UNICODE) if len(token) >= 4)]
        for candidate in dict.fromkeys(queries):
            try:
                results = list(self.knowledge_retriever.search(candidate, limit=20))
            except Exception:
                continue
            if results:
                return [item.to_dict() if hasattr(item, "to_dict") else dict(item) for item in results]
        # Retrieval failure is recorded as an absent citation, never as
        # scientific evidence and never as a reason to invent a source.
        return []

    def _get_or_create_session(self, session_id: str | None, text: str) -> ResearchSession:
        if session_id:
            try:
                session = self.store.get_session(session_id) if self.store is not None else self._sessions[session_id]
            except KeyError:
                session = self.create_session(text[:80] or "New research")
        else:
            session = self.create_session(text[:80] or "New research")
        self._sessions[session.session_id] = session
        return session

    def _record_user_message(self, session: ResearchSession, text: str, *, question_id: str, job_id: str) -> None:
        message = session.add_user_message(text, question_id=question_id, job_id=job_id)
        if self.store is not None:
            self.store.append_message(session.session_id, message)

    def _finalize_session(self, session: ResearchSession, response: ServiceResponse) -> None:
        session.active_question_id = response.planning.question.question_id
        session.active_workflow_id = response.job.workflow_id
        session.active_job_id = response.job.job_id
        session.related_run_ids = list(dict.fromkeys([*session.related_run_ids, *response.answer.run_ids]))
        session.related_bundle_ids = list(dict.fromkeys([*session.related_bundle_ids, *response.answer.bundle_ids]))
        session.status = "INDETERMINATE" if response.answer.status is OracleAnswerStatus.INDETERMINATE else "ACTIVE"
        message = session.add_oracle_message(response.answer.summary, job_id=response.job.job_id, references={"run_ids": list(response.answer.run_ids), "evidence_ids": [item.get("evidence_id") for item in response.answer.evidence], "bundle_ids": list(response.answer.bundle_ids)})
        if self.store is not None:
            self.store.append_message(session.session_id, message)
            self.store.save_session(session)
        self._sessions[session.session_id] = session

    def _save_job(self, job: ResearchJob) -> None:
        if self.store is not None:
            self.store.save_job(job)

    def _save_response(self, response: ServiceResponse) -> None:
        if self.store is not None:
            self.store.save_response(response.job.job_id, response.job.session_id, response.to_dict(), created_at=response.job.completed_at or response.job.created_at)

    def _hydrate_memory(self) -> None:
        """Restore searchable immutable context after a web-process restart."""
        if self.store is None:
            return
        for payload in self.store.list_responses(limit=10000):
            try:
                question = payload["planning"]["question"]
                plan = payload["planning"]["plan"]
                self.memory.remember("question", question["question_id"], question)
                self.memory.remember("plan", plan["plan_id"], plan, rerun_of=plan.get("rerun_of"))
            except (KeyError, TypeError):
                # A malformed historical payload must not make the whole UI
                # unavailable; its response remains inspectable in storage.
                continue

    def _response_payload(self, job_id: str) -> dict[str, Any]:
        if job_id in self._responses:
            return self._responses[job_id].to_dict()
        if self.store is not None:
            return self.store.get_response(job_id)
        raise KeyError(job_id)

    def _get_response(self, job_id: str) -> ServiceResponse:
        if job_id in self._responses:
            return self._responses[job_id]
        payload = self.store.get_response(job_id) if self.store is not None else None
        if payload is None:
            raise KeyError(job_id)
        question = _question_from_dict(payload["planning"]["question"])
        plan = _plan_from_dict(payload["planning"]["plan"])
        validation = _validation_from_dict(payload["planning"]["validation"])
        planning = PlanningResult(question, plan, validation, (), payload["planning"].get("reformulated_from"))
        answer = _answer_from_dict(payload["answer"])
        job_data = payload["job"]
        job = ResearchJob(question.question_id, session_id=job_data.get("session_id"), plan_id=job_data.get("plan_id"), workflow_id=job_data.get("workflow_id"), status=ResearchJobStatus(job_data["status"]), progress=[], current_step=job_data.get("current_step"), started_at=job_data.get("started_at"), completed_at=job_data.get("completed_at"), job_id=job_data["job_id"], created_at=job_data.get("created_at") or datetime.now(timezone.utc).isoformat(), error_code=job_data.get("error_code"), first_loss=job_data.get("first_loss"))
        response = ServiceResponse(job, planning, answer, None, None)
        self._responses[job_id] = response
        return response

    def _stored_parent_runs(self, response: ServiceResponse) -> dict[str, Any]:
        if self.ledger is None or self.store is None:
            return {}
        payload = self.store.get_response(response.job.job_id)
        runs = ((payload.get("execution") or {}).get("runs") or {})
        parents = {}
        for step_id, run_payload in runs.items():
            run_id = run_payload.get("run_id") if isinstance(run_payload, dict) else None
            if run_id:
                try:
                    parents[step_id] = self.ledger.get_run(run_id)
                except KeyError:
                    pass
        return parents
def _evidence_rank(value: Any) -> int:
    try:
        level = value if isinstance(value, EvidenceLevel) else EvidenceLevel(str(value))
    except (TypeError, ValueError):
        return -1
    return {level: index for index, level in enumerate((EvidenceLevel.E0_HEURISTIC, EvidenceLevel.E1_ML, EvidenceLevel.E2_COMPUTATIONAL, EvidenceLevel.E3_PHYSICS, EvidenceLevel.E4_CURATED_EXPERIMENTAL, EvidenceLevel.E5_VALIDATED_EXPERIMENTAL))}.get(level, -1)


def _is_continue_request(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    return any(phrase in normalized for phrase in ("continue essa pesquisa", "continue a pesquisa", "continue research", "continue esta pesquisa"))


def _evidence_to_dict(evidence: Any) -> dict[str, Any]:
    data = asdict(evidence)
    level = data.get("level")
    data["level"] = level.value if hasattr(level, "value") else str(level)
    return data


def _question_from_dict(raw: dict[str, Any]) -> ResearchQuestion:
    return ResearchQuestion(
        text=str(raw["text"]), domain=str(raw["domain"]), objective=str(raw["objective"]), constraints=dict(raw.get("constraints") or {}), required_evidence_level=raw.get("required_evidence_level", EvidenceLevel.E2_COMPUTATIONAL.value), allowed_tools=tuple(raw.get("allowed_tools") or ()), forbidden_tools=tuple(raw.get("forbidden_tools") or ()), question_id=str(raw["question_id"]), created_at=str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
    )


def _plan_from_dict(raw: dict[str, Any]) -> ResearchPlan:
    steps = tuple(
        PlanStep(
            step_id=str(item["step_id"]), lab=str(item["lab"]), experiment=str(item["experiment"]), inputs=dict(item.get("inputs") or {}), requires=tuple(item.get("requires") or ()), consumes=tuple(item.get("consumes") or ()), produces=tuple(item.get("produces") or ()), minimum_evidence_level=item.get("minimum_evidence_level", EvidenceLevel.E0_HEURISTIC.value), failure_policy=str(item.get("failure_policy", "STOP_DOWNSTREAM")),
        )
        for item in raw.get("steps") or ()
    )
    targets = tuple(ClaimTarget(str(item["statement"]), item.get("required_evidence_level", EvidenceLevel.E2_COMPUTATIONAL.value), str(item.get("claim_id") or "")) for item in raw.get("claim_targets") or ())
    return ResearchPlan(
        question_id=str(raw["question_id"]), steps=steps, assumptions=tuple(raw.get("assumptions") or ()), required_sources=tuple(raw.get("required_sources") or ()), expected_outputs=tuple(raw.get("expected_outputs") or ()), risk_flags=tuple(raw.get("risk_flags") or ()), claim_targets=targets, status=raw.get("status", PlanStatus.PROPOSED.value), plan_id=str(raw["plan_id"]), created_at=str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()), rerun_of=raw.get("rerun_of"),
    )


def _validation_from_dict(raw: dict[str, Any]) -> PlanValidationResult:
    issues = tuple(ValidationIssue(str(item["rule_id"]), str(item["status"]), str(item["message"]), item.get("step_id"), dict(item.get("diagnostics") or {})) for item in raw.get("issues") or ())
    normalized = _plan_from_dict(raw["normalized_plan"]) if raw.get("normalized_plan") else None
    return PlanValidationResult(str(raw["status"]), str(raw["plan_id"]), issues, normalized, int(raw.get("attempts", 1)), int(raw.get("repairs", 0)))


def _answer_from_dict(raw: dict[str, Any]) -> OracleAnswer:
    return OracleAnswer(
        status=OracleAnswerStatus(str(raw["status"])), summary=str(raw.get("summary", "")), claims=tuple(raw.get("claims") or ()), evidence=tuple(raw.get("evidence") or ()), limitations=tuple(raw.get("limitations") or ()), conditions=dict(raw.get("conditions") or {}), uncertainty=dict(raw.get("uncertainty") or {}), first_loss=raw.get("first_loss"), first_divergence=raw.get("first_divergence"), sources=tuple(raw.get("sources") or ()), datasets=tuple(raw.get("datasets") or ()), models=tuple(raw.get("models") or ()), run_ids=tuple(raw.get("run_ids") or ()), workflow_ids=tuple(raw.get("workflow_ids") or ()), bundle_ids=tuple(raw.get("bundle_ids") or ()), metadata=dict(raw.get("metadata") or {}),
    )


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
