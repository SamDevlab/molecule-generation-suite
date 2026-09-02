from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Callable
import uuid

from research_os.artifacts import ModelArtifactManifest
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus
from research_os.ml.metrics import metric_value
from research_os.ml.registry import ModelRegistry, ModelStage
from research_os.ml.schema import ValidationReport


class PromotionStatus(str, Enum):
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PromotionPolicy:
    require_validation_pass: bool = True
    require_external_test: bool = True
    max_mae: float | None = None
    max_rmse: float | None = None
    min_r2: float | None = None


@dataclass(frozen=True)
class PromotionDecision:
    status: PromotionStatus
    candidate_model_id: str
    champion_model_id: str | None
    gates: tuple[GateResult, ...]
    evidence: Evidence
    reason: str

    @property
    def promoted(self) -> bool:
        return self.status == PromotionStatus.PROMOTED

    @property
    def first_loss(self) -> GateResult | None:
        return next((gate for gate in self.gates if gate.status != GateStatus.PASS), None)


class ModelPromotionEngine:
    """Apply explicit candidate-vs-champion gates and emit an audit artifact."""

    def __init__(self, policy: PromotionPolicy | None = None, registry: ModelRegistry | None = None):
        self.policy = policy or PromotionPolicy()
        self.registry = registry

    def evaluate(self, candidate: ModelArtifactManifest, champion: ModelArtifactManifest | None = None, *, validation: ValidationReport | None = None, external_test_acceptable: bool | None = None) -> PromotionDecision:
        policy = self.policy
        gates: list[GateResult] = []
        if policy.require_validation_pass:
            if validation is None:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-VAL-001", GateStatus.INSUFFICIENT_EVIDENCE, "candidate validation report is required for promotion"))
            elif validation.passed:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-VAL-001", GateStatus.PASS, "candidate passed all validation gates", evidence_ids=tuple(evidence_id for gate in validation.gates for evidence_id in gate.evidence_ids)))
            else:
                loss = validation.first_loss
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-VAL-001", loss.status if loss else GateStatus.FAIL, "candidate did not pass all validation gates", diagnostics={"first_loss": loss.rule_id if loss else None}))

        candidate_mae = metric_value(candidate.metrics, "mae")
        champion_mae = metric_value(champion.metrics, "mae") if champion else None
        if candidate_mae is None or not isfinite(candidate_mae):
            gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-METRIC-001", GateStatus.INSUFFICIENT_EVIDENCE, "candidate MAE is required for comparison"))
        elif champion is not None and (champion_mae is None or not candidate_mae < champion_mae):
            gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-MAE-001", GateStatus.FAIL, "candidate MAE is not lower than champion MAE", diagnostics={"candidate_mae": candidate_mae, "champion_mae": champion_mae}))
        else:
            gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-MAE-001", GateStatus.PASS, "candidate MAE is better than the champion or no champion exists", diagnostics={"candidate_mae": candidate_mae, "champion_mae": champion_mae}))

        for name, rule_id, comparator, label in (("rmse", "ML-PROMO-RMSE-001", lambda value, threshold: value <= threshold, "RMSE"), ("r2", "ML-PROMO-R2-001", lambda value, threshold: value >= threshold, "R2")):
            threshold = getattr(policy, f"min_{name}" if name == "r2" else f"max_{name}")
            if threshold is None:
                continue
            value = metric_value(candidate.metrics, name)
            if value is None:
                gates.append(GateResult("GATE-ML-PROMOTION", rule_id, GateStatus.INSUFFICIENT_EVIDENCE, f"candidate {label} is required by policy"))
            elif isfinite(value) and comparator(value, threshold):
                gates.append(GateResult("GATE-ML-PROMOTION", rule_id, GateStatus.PASS, f"candidate {label} satisfies explicit policy threshold", diagnostics={"value": value, "threshold": threshold}))
            else:
                gates.append(GateResult("GATE-ML-PROMOTION", rule_id, GateStatus.FAIL, f"candidate {label} does not satisfy explicit policy threshold", diagnostics={"value": value, "threshold": threshold}))

        external = validation.external_test_acceptable if external_test_acceptable is None and validation is not None else external_test_acceptable
        if policy.require_external_test:
            if external is True:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-EXT-001", GateStatus.PASS, "external test was explicitly marked acceptable"))
            elif external is False:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-EXT-001", GateStatus.FAIL, "external test was explicitly rejected"))
            else:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-EXT-001", GateStatus.INSUFFICIENT_EVIDENCE, "external test acceptability is required for promotion"))

        promoted = bool(gates) and all(gate.status == GateStatus.PASS for gate in gates)
        status = PromotionStatus.PROMOTED if promoted else PromotionStatus.REJECTED
        rule_ids = [gate.rule_id for gate in gates]
        evidence = Evidence(
            evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}",
            kind="model_promotion_decision",
            level=EvidenceLevel.E1_ML,
            source="Research OS ModelPromotionEngine",
            payload={"status": status.value, "candidate_model_id": candidate.model_id, "champion_model_id": champion.model_id if champion else None, "rule_ids": rule_ids, "gates": [{"rule_id": gate.rule_id, "status": gate.status.value, "reason": gate.reason, "diagnostics": gate.diagnostics} for gate in gates]},
        )
        reason = "candidate passed explicit promotion gates" if promoted else f"candidate rejected at {next((gate.rule_id for gate in gates if gate.status != GateStatus.PASS), 'unknown gate')}"
        decision = PromotionDecision(status, candidate.model_id, champion.model_id if champion else None, tuple(gates), evidence, reason)
        if self.registry is not None:
            if candidate.model_id not in {record.model_id for record in self.registry.candidates()}:
                try:
                    self.registry.register(candidate, stage=ModelStage.CANDIDATE)
                except ValueError:
                    pass
            if promoted and champion is not None:
                try:
                    self.registry.set_stage(champion.model_id, ModelStage.RETIRED)
                except KeyError:
                    pass
            self.registry.set_stage(candidate.model_id, ModelStage.CHAMPION if promoted else ModelStage.REJECTED)
        return decision

    promote = evaluate


def promote_candidate(
    candidate: ModelArtifactManifest,
    champion: ModelArtifactManifest | None = None,
    *,
    validation: ValidationReport | None = None,
    external_test_acceptable: bool | None = None,
    policy: PromotionPolicy | None = None,
) -> PromotionDecision:
    return ModelPromotionEngine(policy=policy).evaluate(candidate, champion, validation=validation, external_test_acceptable=external_test_acceptable)
