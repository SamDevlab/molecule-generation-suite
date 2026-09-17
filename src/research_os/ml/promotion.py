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
    require_applicability_domain: bool = False
    require_calibration: bool = False
    max_ood_score: float | None = None
    max_uncertainty: float | None = None


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

        for name, rule_id, comparator, label in (("mae", "ML-PROMO-MAE-THRESHOLD-001", lambda value, threshold: value <= threshold, "MAE"), ("rmse", "ML-PROMO-RMSE-001", lambda value, threshold: value <= threshold, "RMSE"), ("r2", "ML-PROMO-R2-001", lambda value, threshold: value >= threshold, "R2")):
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

        if policy.require_applicability_domain:
            domain = validation.applicability_domain if validation is not None else None
            if domain is None:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-AD-001", GateStatus.INSUFFICIENT_EVIDENCE, "applicability-domain assessment is required for promotion"))
            elif domain.in_domain:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-AD-001", GateStatus.PASS, "declared validation set is inside the applicability domain", diagnostics={"method": domain.method, "score": domain.score}))
            else:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-AD-001", GateStatus.OUT_OF_DOMAIN, "declared validation set contains out-of-domain observations", diagnostics={"method": domain.method, "score": domain.score}))

        if policy.require_calibration:
            calibration = validation.calibration if validation is not None else None
            if isinstance(calibration, dict) and calibration.get("method") and int(calibration.get("calibration_count", 0)) > 0:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-CAL-001", GateStatus.PASS, "explicit residual-calibrated prediction interval is recorded; it is not a certainty claim", diagnostics={"method": calibration.get("method"), "calibration_count": calibration.get("calibration_count")}))
            else:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-CAL-001", GateStatus.INSUFFICIENT_EVIDENCE, "an explicit uncertainty calibration record is required for promotion"))

        if policy.max_ood_score is not None:
            observed_ood = validation.out_of_domain_score if validation is not None else None
            if observed_ood is None:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-OOD-001", GateStatus.INSUFFICIENT_EVIDENCE, "an applicability-domain OOD score is required by policy"))
            elif observed_ood <= policy.max_ood_score:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-OOD-001", GateStatus.PASS, "OOD score is within the explicit promotion threshold", diagnostics={"value": observed_ood, "threshold": policy.max_ood_score}))
            else:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-OOD-001", GateStatus.OUT_OF_DOMAIN, "OOD score exceeds the explicit promotion threshold", diagnostics={"value": observed_ood, "threshold": policy.max_ood_score}))

        if policy.max_uncertainty is not None:
            interval = validation.prediction_interval if validation is not None else None
            observed_uncertainty = interval.get("radius") if isinstance(interval, dict) else None
            if observed_uncertainty is None:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-UNCERTAINTY-001", GateStatus.INSUFFICIENT_EVIDENCE, "an uncertainty radius is required by policy"))
            elif float(observed_uncertainty) <= policy.max_uncertainty:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-UNCERTAINTY-001", GateStatus.PASS, "residual-calibrated uncertainty is within the explicit threshold", diagnostics={"value": observed_uncertainty, "threshold": policy.max_uncertainty}))
            else:
                gates.append(GateResult("GATE-ML-PROMOTION", "ML-PROMO-UNCERTAINTY-001", GateStatus.FAIL, "residual-calibrated uncertainty exceeds the explicit threshold", diagnostics={"value": observed_uncertainty, "threshold": policy.max_uncertainty}))

        promoted = bool(gates) and all(gate.status == GateStatus.PASS for gate in gates)
        status = PromotionStatus.PROMOTED if promoted else PromotionStatus.REJECTED
        rule_ids = [gate.rule_id for gate in gates]
        evidence = Evidence(
            evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}",
            kind="model_promotion_decision",
            level=EvidenceLevel.E1_ML,
            source="Research OS ModelPromotionEngine",
            payload={"status": status.value, "model_id": candidate.model_id, "training_run_id": candidate.training_run_id, "candidate_model_id": candidate.model_id, "champion_model_id": champion.model_id if champion else None, "candidate_model": {"model_id": candidate.model_id, "training_run_id": candidate.training_run_id}, "champion_model": {"model_id": champion.model_id, "training_run_id": champion.training_run_id} if champion else None, "rule_ids": rule_ids, "gates": [{"rule_id": gate.rule_id, "status": gate.status.value, "reason": gate.reason, "diagnostics": gate.diagnostics} for gate in gates], "validation_metrics": dict(validation.metrics) if validation is not None else {}, "external_test_acceptable": external, "applicability_domain": validation.applicability_domain.to_dict() if validation is not None and validation.applicability_domain else None, "calibration": validation.calibration if validation is not None else None, "uncertainty": validation.prediction_interval if validation is not None else None, "regression_check": {"candidate_mae": candidate_mae, "champion_mae": champion_mae, "status": "compared" if champion is not None else "no_champion_baseline"}},
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
