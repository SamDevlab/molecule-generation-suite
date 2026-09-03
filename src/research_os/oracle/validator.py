"""Fail-closed research plan validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from research_os.core.types import EvidenceLevel
from research_os.core.units import UnitError, quantity
from research_os.oracle.capabilities import LabCapability, default_capabilities
from research_os.oracle.models import ClaimTarget, PlanStatus, ResearchPlan, ResearchQuestion


CANONICAL_EVIDENCE_LEVELS = (
    EvidenceLevel.E0_HEURISTIC,
    EvidenceLevel.E1_ML,
    EvidenceLevel.E2_COMPUTATIONAL,
    EvidenceLevel.E3_PHYSICS,
    EvidenceLevel.E4_CURATED_EXPERIMENTAL,
    EvidenceLevel.E5_VALIDATED_EXPERIMENTAL,
)
_LEVEL_ORDER = {level: index for index, level in enumerate(CANONICAL_EVIDENCE_LEVELS)}


@dataclass(frozen=True)
class ValidationIssue:
    rule_id: str
    status: str
    message: str
    step_id: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "status": self.status, "message": self.message, "step_id": self.step_id, "diagnostics": dict(self.diagnostics)}


@dataclass(frozen=True)
class PlanValidationResult:
    status: str
    plan_id: str
    issues: tuple[ValidationIssue, ...] = ()
    normalized_plan: ResearchPlan | None = None
    attempts: int = 1
    repairs: int = 0

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    @property
    def first_loss(self) -> ValidationIssue | None:
        return self.issues[0] if self.issues else None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "plan_id": self.plan_id, "issues": [item.to_dict() for item in self.issues], "normalized_plan": self.normalized_plan.to_dict() if self.normalized_plan else None, "attempts": self.attempts, "repairs": self.repairs}


class PlanValidator:
    def __init__(self, capabilities: Iterable[LabCapability] | None = None, *, engine_registry: Any | None = None, dataset_registry: Any | None = None, model_registry: Any | None = None, source_registry: Any | None = None):
        self.capabilities = {item.lab: item for item in (capabilities or default_capabilities())}
        self.engine_registry = engine_registry
        self.dataset_registry = dataset_registry
        self.model_registry = model_registry
        self.source_registry = source_registry

    def validate(self, plan: ResearchPlan, *, question: ResearchQuestion | None = None) -> PlanValidationResult:
        issues: list[ValidationIssue] = []
        if not plan.steps:
            issues.append(ValidationIssue("ORACLE-PLAN-SCHEMA-002", "FAIL", "a research plan must contain at least one typed step"))
        known = {step.step_id for step in plan.steps}
        if len(known) != len(plan.steps):
            issues.append(ValidationIssue("ORACLE-PLAN-SCHEMA-001", "FAIL", "plan step IDs must be unique"))
        for step in plan.steps:
            capability = self.capabilities.get(step.lab)
            if capability is None:
                issues.append(ValidationIssue("ORACLE-LAB-001", "FAIL", f"unknown Lab: {step.lab}", step.step_id))
                continue
            if question is not None:
                if question.allowed_tools and step.lab not in question.allowed_tools and step.experiment not in question.allowed_tools:
                    issues.append(ValidationIssue("ORACLE-TOOL-001", "FAIL", f"step is outside the question allowlist: {step.lab}/{step.experiment}", step.step_id))
                if step.lab in question.forbidden_tools or step.experiment in question.forbidden_tools:
                    issues.append(ValidationIssue("ORACLE-TOOL-002", "FAIL", f"forbidden tool requested: {step.lab}/{step.experiment}", step.step_id))
            if step.experiment not in capability.experiments:
                issues.append(ValidationIssue("ORACLE-EXPERIMENT-001", "FAIL", f"unknown experiment {step.experiment} for {step.lab}", step.step_id))
            missing = [name for name in capability.required_inputs if name not in step.inputs or step.inputs.get(name) in (None, "", "REQUIRED")]
            if missing:
                issues.append(ValidationIssue("ORACLE-CONFIG-001", "FAIL", "required plan inputs are missing", step.step_id, {"missing": missing}))
            if _LEVEL_ORDER[step.minimum_evidence_level] > _LEVEL_ORDER[capability.evidence_ceiling]:
                issues.append(ValidationIssue("ORACLE-EVIDENCE-001", "FAIL", "step requests evidence above Lab ceiling", step.step_id, {"requested": step.minimum_evidence_level.value, "ceiling": capability.evidence_ceiling.value}))
            for engine_id in capability.required_engines:
                if self._engine_unavailable(engine_id):
                    issues.append(ValidationIssue("ORACLE-ENGINE-001", "INDETERMINATE", f"required engine unavailable: {engine_id}", step.step_id))
            self._validate_units(step.inputs, step.step_id, issues)
            self._validate_references(step.inputs, step.step_id, issues)
            unknown = sorted(set(step.requires) - known)
            if unknown:
                issues.append(ValidationIssue("ORACLE-DEPENDENCY-001", "FAIL", "plan references unknown dependencies", step.step_id, {"unknown": unknown}))
        if self._has_cycle(plan):
            issues.append(ValidationIssue("ORACLE-DEPENDENCY-002", "FAIL", "plan dependency graph contains a cycle"))
        self._validate_claims(plan.claim_targets, plan, issues)
        if question is not None:
            plan_ceiling = max(
                (_LEVEL_ORDER[self.capabilities[step.lab].evidence_ceiling] for step in plan.steps if step.lab in self.capabilities),
                default=-1,
            )
            required = _LEVEL_ORDER[question.required_evidence_level]
            if required > plan_ceiling:
                issues.append(ValidationIssue(
                    "ORACLE-EVIDENCE-002",
                    "INSUFFICIENT_EVIDENCE",
                    "question requires evidence above the proposed Lab ceiling",
                    diagnostics={"required": question.required_evidence_level.value, "plan_ceiling": CANONICAL_EVIDENCE_LEVELS[plan_ceiling].value if plan_ceiling >= 0 else None},
                ))
        if any(issue.status == "FAIL" for issue in issues):
            status = "FAIL"
        elif any(issue.status == "INDETERMINATE" for issue in issues):
            status = "INDETERMINATE"
        elif any(issue.status == "INSUFFICIENT_EVIDENCE" for issue in issues):
            status = "INSUFFICIENT_EVIDENCE"
        else:
            status = "PASS"
        normalized_status = {
            "PASS": PlanStatus.VALIDATED,
            "INDETERMINATE": PlanStatus.INDETERMINATE,
            "INSUFFICIENT_EVIDENCE": PlanStatus.INSUFFICIENT_EVIDENCE,
        }.get(status, PlanStatus.INVALID)
        normalized = ResearchPlan(plan.question_id, plan.steps, plan.assumptions, plan.required_sources, plan.expected_outputs, plan.risk_flags, plan.claim_targets, normalized_status, plan.plan_id, plan.created_at, plan.rerun_of)
        return PlanValidationResult(status, plan.plan_id, tuple(issues), normalized)

    def _engine_unavailable(self, engine_id: str) -> bool:
        if self.engine_registry is None:
            return True
        try:
            manifest = self.engine_registry.get_engine(engine_id)
        except (KeyError, AttributeError):
            return True
        return str(getattr(manifest, "readiness", "NOT_READY")) not in {"AVAILABLE", "EngineReadiness.AVAILABLE", "PROTOCOL_READY", "EngineReadiness.PROTOCOL_READY", "REFERENCE_VALIDATED", "EngineReadiness.REFERENCE_VALIDATED"} or str(getattr(manifest, "status", "")) not in {"AVAILABLE_BUT_NOT_EXECUTED", "SUPPORTED_AND_EXECUTED", "EXECUTED", "REFERENCE_VALIDATED", "EngineStatus.AVAILABLE_BUT_NOT_EXECUTED", "EngineStatus.SUPPORTED_AND_EXECUTED", "EngineStatus.EXECUTED", "EngineStatus.REFERENCE_VALIDATED"}

    @staticmethod
    def _validate_units(inputs: dict[str, Any], step_id: str, issues: list[ValidationIssue]) -> None:
        for key, value in inputs.items():
            if isinstance(value, dict) and "value" in value and "unit" in value:
                try:
                    quantity(value["value"], value["unit"])
                except (UnitError, TypeError, ValueError) as exc:
                    issues.append(ValidationIssue("ORACLE-UNITS-001", "FAIL", f"invalid units for {key}", step_id, {"error": str(exc)}))

    def _validate_references(self, inputs: dict[str, Any], step_id: str, issues: list[ValidationIssue]) -> None:
        for key, registry in (("dataset_id", self.dataset_registry), ("model_id", self.model_registry), ("source_id", self.source_registry)):
            value = inputs.get(key)
            if value is not None and registry is not None:
                try:
                    registry.get(str(value))
                except (KeyError, ValueError):
                    issues.append(ValidationIssue("ORACLE-REFERENCE-001", "FAIL", f"unknown {key}: {value}", step_id))

    @staticmethod
    def _has_cycle(plan: ResearchPlan) -> bool:
        graph = {step.step_id: set(step.requires) for step in plan.steps}
        visited: set[str] = set()
        active: set[str] = set()
        def visit(node: str) -> bool:
            if node in active:
                return True
            if node in visited:
                return False
            active.add(node)
            if any(visit(dep) for dep in graph.get(node, ())):
                return True
            active.remove(node)
            visited.add(node)
            return False
        return any(visit(node) for node in graph)

    def _validate_claims(self, targets: Iterable[ClaimTarget], plan: ResearchPlan, issues: list[ValidationIssue]) -> None:
        labs = {step.lab for step in plan.steps}
        for target in targets:
            text = target.statement.lower()
            if any(term in text for term in ("cure", "cura", "treat", "trata", "clinical efficacy", "eficácia clínica")) and "DockingLab" in labs:
                issues.append(ValidationIssue("ORACLE-CLAIM-001", "FAIL", "docking cannot support a clinical cure/efficacy claim; reformulate as a computational hypothesis"))
            ceiling = max((_LEVEL_ORDER[self.capabilities[lab].evidence_ceiling] for lab in labs if lab in self.capabilities), default=0)
            if _LEVEL_ORDER[target.required_evidence_level] > ceiling:
                issues.append(ValidationIssue("ORACLE-CLAIM-002", "FAIL", "claim requires evidence above the proposed plan ceiling", diagnostics={"claim": target.statement, "required": target.required_evidence_level.value}))
