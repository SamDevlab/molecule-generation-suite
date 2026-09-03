"""Oracle planner: language interpretation ends at a validated plan schema."""

from __future__ import annotations

from dataclasses import dataclass, field
import uuid
from typing import Any

from research_os.core.types import EvidenceLevel
from research_os.oracle.models import ClaimTarget, OracleAnswer, OracleAnswerStatus, PlanStep, ResearchPlan, ResearchQuestion
from research_os.oracle.provider import LLMProvider, RuleBasedLLMProvider, audit_llm_call, parse_structured_output
from research_os.oracle.validator import PlanValidationResult, PlanValidator


@dataclass(frozen=True)
class PlanningResult:
    question: ResearchQuestion
    plan: ResearchPlan
    validation: PlanValidationResult
    audits: tuple[Any, ...] = ()
    reformulated_from: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"question": self.question.to_dict(), "plan": self.plan.to_dict(), "validation": self.validation.to_dict(), "audits": [item.to_dict() for item in self.audits], "reformulated_from": self.reformulated_from}


class OraclePlanner:
    def __init__(self, provider: LLMProvider | None = None, *, validator: PlanValidator | None = None, max_plan_repair_attempts: int = 1):
        self.provider = provider or RuleBasedLLMProvider()
        self.validator = validator or PlanValidator()
        if max_plan_repair_attempts < 0:
            raise ValueError("max_plan_repair_attempts must be non-negative")
        self.max_plan_repair_attempts = max_plan_repair_attempts

    def interpret(self, text: str) -> ResearchQuestion:
        raw = parse_structured_output(self.provider.interpret_question(text))
        return ResearchQuestion(text=str(raw.get("text", text)), domain=str(raw.get("domain", "general")), objective=str(raw.get("objective", text)), constraints=dict(raw.get("constraints") or {}), required_evidence_level=raw.get("required_evidence_level", EvidenceLevel.E2_COMPUTATIONAL.value), allowed_tools=tuple(raw.get("allowed_tools") or ()), forbidden_tools=tuple(raw.get("forbidden_tools") or ()))

    def propose(self, question: ResearchQuestion, *, memory: list[dict[str, Any]] | None = None) -> PlanningResult:
        planning_run_id = f"PLANRUN-{uuid.uuid4().hex[:12].upper()}"
        raw = parse_structured_output(self.provider.generate_plan(question.to_dict(), memory))
        audits: list[Any] = [audit_llm_call(self.provider, "generate_plan", question.to_dict(), raw, planning_run_id)]
        plan = self._plan_from_raw(question, raw)
        validation = self.validator.validate(plan, question=question)
        repairs = 0
        attempts = 1
        # Repair is deliberately bounded and never attempts to repair an
        # unsupported scientific claim or a missing external engine.
        while (
            validation.status == "FAIL"
            and repairs < self.max_plan_repair_attempts
            and not any(issue.rule_id == "ORACLE-CLAIM-001" for issue in validation.issues)
            and not any(issue.rule_id == "ORACLE-ENGINE-001" for issue in validation.issues)
        ):
            repaired_raw = parse_structured_output(self.provider.repair_plan(raw, [issue.to_dict() for issue in validation.issues]))
            audits.append(audit_llm_call(self.provider, "repair_plan", {"plan": raw, "issues": [issue.to_dict() for issue in validation.issues]}, repaired_raw, planning_run_id))
            raw = repaired_raw
            plan = self._plan_from_raw(question, raw)
            validation = self.validator.validate(plan, question=question)
            repairs += 1
            attempts += 1
        validation = PlanValidationResult(validation.status, validation.plan_id, validation.issues, validation.normalized_plan, attempts, repairs)
        return PlanningResult(question, plan, validation, tuple(audits))

    def ask(self, text: str, *, memory: list[dict[str, Any]] | None = None) -> PlanningResult:
        planning_run_id = f"PLANRUN-{uuid.uuid4().hex[:12].upper()}"
        question = self.interpret(text)
        audit = audit_llm_call(self.provider, "interpret_question", {"text": text}, question.to_dict(), planning_run_id)
        proposed = self.propose(question, memory=memory)
        if any(issue.rule_id == "ORACLE-CLAIM-001" for issue in proposed.validation.issues):
            safe_targets = tuple(ClaimTarget(f"Computational docking hypothesis for: {target.statement}", EvidenceLevel.E2_COMPUTATIONAL) for target in proposed.plan.claim_targets)
            safe_plan = ResearchPlan(proposed.plan.question_id, proposed.plan.steps, proposed.plan.assumptions, proposed.plan.required_sources, proposed.plan.expected_outputs, (*proposed.plan.risk_flags, "OVERCLAIM_REFORMULATED"), safe_targets)
            safe_validation = self.validator.validate(safe_plan)
            return PlanningResult(question, safe_plan, safe_validation, (audit, *proposed.audits), proposed.plan.plan_id)
        return PlanningResult(proposed.question, proposed.plan, proposed.validation, (audit, *proposed.audits), proposed.reformulated_from)

    def answer_from_plan(self, result: PlanningResult) -> OracleAnswer:
        validation = result.validation
        if result.reformulated_from:
            return OracleAnswer(OracleAnswerStatus.REJECTED, "A solicitação de eficácia clínica foi rejeitada e reformulada como hipótese computacional.", limitations=("docking has an E2 computational ceiling", "no clinical or cure claim was executed"), first_loss={"rule_id": "ORACLE-CLAIM-001", "status": "FAIL", "message": "unsupported clinical claim"})
        if any(issue.rule_id == "ORACLE-CLAIM-001" for issue in validation.issues):
            return OracleAnswer(OracleAnswerStatus.REJECTED, "A claim de eficácia clínica/cura não pode ser executada como docking.", limitations=("docking has an E2 computational ceiling", "plan requires reformulation as a computational hypothesis"), first_loss=validation.first_loss.to_dict() if validation.first_loss else None)
        if validation.status == "INDETERMINATE":
            return OracleAnswer(OracleAnswerStatus.INDETERMINATE, "O plano foi estruturado, mas depende de recursos externos indisponíveis.", limitations=("required engine is unavailable",), first_loss=validation.first_loss.to_dict() if validation.first_loss else None)
        if validation.status == "INSUFFICIENT_EVIDENCE":
            return OracleAnswer(OracleAnswerStatus.INSUFFICIENT_EVIDENCE, "O plano não pode atender ao nível de evidência solicitado com os Labs disponíveis.", limitations=("requested evidence level exceeds the plan ceiling",), first_loss=validation.first_loss.to_dict() if validation.first_loss else None)
        if validation.status == "FAIL":
            return OracleAnswer(OracleAnswerStatus.REJECTED, "O plano não passou pela validação tipada e não foi executado.", limitations=("structured plan validation failed",), first_loss=validation.first_loss.to_dict() if validation.first_loss else None)
        return OracleAnswer(OracleAnswerStatus.INSUFFICIENT_EVIDENCE, "Plano validado; nenhuma execução científica foi realizada por esta etapa de planejamento.", limitations=("planning is not execution",))

    @staticmethod
    def _plan_from_raw(question: ResearchQuestion, raw: dict[str, Any]) -> ResearchPlan:
        steps = tuple(OraclePlanner._step(item) for item in raw.get("steps") or ())
        targets = tuple(ClaimTarget(str(item.get("statement", "")), item.get("required_evidence_level", EvidenceLevel.E2_COMPUTATIONAL.value), str(item.get("claim_id")) if item.get("claim_id") else ClaimTarget.__dataclass_fields__["claim_id"].default_factory()) for item in raw.get("claim_targets") or () if item.get("statement"))
        lower_objective = question.objective.lower()
        if not targets and "DockingLab" in {step.lab for step in steps} and any(term in lower_objective for term in ("cure", "cura", "clinical", "clínica", "treat", "trata")):
            targets = (ClaimTarget(question.objective, EvidenceLevel.E4_CURATED_EXPERIMENTAL),)
        return ResearchPlan(question.question_id, steps, tuple(raw.get("assumptions") or ()), tuple(raw.get("required_sources") or ()), tuple(raw.get("expected_outputs") or ()), tuple(raw.get("risk_flags") or ()), targets)

    @staticmethod
    def _step(raw: dict[str, Any]) -> PlanStep:
        return PlanStep(str(raw.get("step_id", "step")), str(raw.get("lab", "")), str(raw.get("experiment", "")), dict(raw.get("inputs") or {}), tuple(raw.get("requires") or ()), tuple(raw.get("consumes") or ()), tuple(raw.get("produces") or ()), raw.get("minimum_evidence_level", EvidenceLevel.E0_HEURISTIC.value), str(raw.get("failure_policy", "STOP_DOWNSTREAM")))
