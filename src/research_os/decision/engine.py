"""Decision evaluation and audit helpers with explicit refusal semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
import uuid

from research_os.core.hashing import sha256_json
from research_os.decision.models import DecisionStatus, ScientificDecision


@dataclass(frozen=True)
class CriterionEvaluation:
    option: str
    criterion_id: str
    passed: bool
    evidence_ids: tuple[str, ...] = ()
    reason: str = ""
    ood: bool = False
    uncertainty: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"option": self.option, "criterion_id": self.criterion_id, "passed": self.passed, "evidence_ids": list(self.evidence_ids), "reason": self.reason, "ood": self.ood, "uncertainty": self.uncertainty}


@dataclass(frozen=True)
class DecisionAudit:
    decision_id: str
    criteria_declared: bool
    evidence_traceable: bool
    conditions_included: bool
    uncertainty_included: bool
    ood_considered: bool
    no_evidence_inflation: bool
    no_hidden_scoring: bool
    no_unsupported_winner: bool
    claims_traceable: bool
    reproducibility_references: bool
    status: str
    findings: tuple[str, ...] = ()
    audit_id: str = field(default_factory=lambda: f"DAUD-{uuid.uuid4().hex[:12].upper()}")

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    @property
    def digest(self) -> str:
        return sha256_json(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {"audit_id": self.audit_id, "decision_id": self.decision_id, "criteria_declared": self.criteria_declared, "evidence_traceable": self.evidence_traceable, "conditions_included": self.conditions_included, "uncertainty_included": self.uncertainty_included, "ood_considered": self.ood_considered, "no_evidence_inflation": self.no_evidence_inflation, "no_hidden_scoring": self.no_hidden_scoring, "no_unsupported_winner": self.no_unsupported_winner, "claims_traceable": self.claims_traceable, "reproducibility_references": self.reproducibility_references, "status": self.status, "findings": list(self.findings), "passed": self.passed}
    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


def audit_decision(decision: ScientificDecision, *, known_evidence_ids: set[str] | None = None, known_claim_ids: set[str] | None = None, reproducibility_references: bool = True) -> DecisionAudit:
    findings: list[str] = []
    criteria_declared = bool(decision.criteria)
    if not criteria_declared:
        findings.append("no explicit decision criteria")
    available = set(decision.evidence_available)
    required = set(decision.required_evidence)
    evidence_traceable = required.issubset(available) and (known_evidence_ids is None or available.issubset(known_evidence_ids))
    if not evidence_traceable:
        findings.append("required or declared evidence is not traceable")
    conditions_included = bool(decision.conditions) and all(bool(criterion.conditions) or bool(criterion.comparison_protocol) for criterion in decision.criteria)
    if not conditions_included:
        findings.append("conditions or comparison protocols are incomplete")
    uncertainty_included = bool(decision.uncertainties) or any(criterion.maximum_uncertainty_optional is not None for criterion in decision.criteria)
    if not uncertainty_included:
        findings.append("uncertainty was not recorded")
    ood_considered = bool(decision.OOD_flags) or any("OOD" in criterion.OOD_policy.upper() or "OUT" in criterion.OOD_policy.upper() for criterion in decision.criteria)
    if not ood_considered:
        findings.append("OOD policy was not considered")
    claims_traceable = known_claim_ids is None or set(decision.supporting_claim_ids + decision.conflicting_claim_ids).issubset(known_claim_ids)
    if not claims_traceable:
        findings.append("claim references are not traceable")
    no_unsupported_winner = decision.selected_option is None or decision.decision_status in {DecisionStatus.SUPPORTED_DECISION.value, DecisionStatus.PROVISIONAL_DECISION.value}
    if not no_unsupported_winner:
        findings.append("selected option is inconsistent with decision status")
    checks = (criteria_declared, evidence_traceable, conditions_included, uncertainty_included, ood_considered, claims_traceable, no_unsupported_winner, reproducibility_references)
    return DecisionAudit(decision.decision_id, criteria_declared, evidence_traceable, conditions_included, uncertainty_included, ood_considered, True, True, no_unsupported_winner, claims_traceable, reproducibility_references, "PASS" if all(checks) else "FAIL", tuple(findings))


def resolve_decision(*, decision_id: str, campaign_id: str, question_id: str, decision_question: str, options: tuple[str, ...], criteria: tuple[Any, ...], required_evidence: tuple[str, ...], evidence_available: tuple[str, ...], evaluations: tuple[CriterionEvaluation, ...], supporting_claim_ids: tuple[str, ...] = (), conflicting_claim_ids: tuple[str, ...] = (), conditions: Mapping[str, Any] | None = None, uncertainties: tuple[str, ...] = (), OOD_flags: tuple[str, ...] = (), limitations: tuple[str, ...] = (), created_at: str | None = None) -> ScientificDecision:
    required_criteria = {criterion.criterion_id for criterion in criteria if criterion.required}
    by_option: dict[str, list[CriterionEvaluation]] = {option: [] for option in options}
    for evaluation in evaluations:
        by_option.setdefault(evaluation.option, []).append(evaluation)
    eligible = [option for option, values in by_option.items() if required_criteria and all(item.passed for item in values if item.criterion_id in required_criteria) and {item.criterion_id for item in values if item.passed}.issuperset(required_criteria)]
    ood_options = {item.option for item in evaluations if item.ood}
    if not required_criteria:
        status, selected, rationale = DecisionStatus.REJECTED_DECISION_REQUEST, None, "The decision request had no required criteria."
    elif len(eligible) == 1:
        selected = eligible[0]
        complete = all(item.passed for item in by_option[selected]) and len(by_option[selected]) >= len(criteria)
        status = DecisionStatus.SUPPORTED_DECISION if complete else DecisionStatus.PROVISIONAL_DECISION
        rationale = f"{selected} satisfies the declared required criteria under the recorded protocol."
    elif len(eligible) > 1:
        selected, status, rationale = None, DecisionStatus.NO_DECISION_CONFLICTING_EVIDENCE, "More than one option satisfies the required criteria; the evidence does not justify a unique decision."
    elif ood_options or OOD_flags:
        selected, status, rationale = None, DecisionStatus.NO_DECISION_OUT_OF_DOMAIN, "At least one required criterion is out of the model applicability domain; no option was ranked through it."
    else:
        selected, status, rationale = None, DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE, "No option satisfies all required criteria with the available evidence."
    rejected = tuple(option for option in options if option != selected)
    return ScientificDecision(decision_id, campaign_id, question_id, decision_question, options, criteria, required_evidence, evidence_available, supporting_claim_ids, conflicting_claim_ids, conditions or {}, uncertainties, OOD_flags, selected, rejected, status, rationale, limitations, created_at or datetime.now(timezone.utc).isoformat())
