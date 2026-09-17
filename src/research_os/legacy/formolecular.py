from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class LegacyTargetClass(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    MODEL_CANDIDATE = "MODEL_CANDIDATE"
    HEURISTIC_REVIEW = "HEURISTIC_REVIEW"
    UNKNOWN = "UNKNOWN"


_DETERMINISTIC = {
    "peso_molar", "molecular_weight", "mw", "logp", "tpsa", "score_qed", "qed",
    "fractioncsp3", "rotatablebonds", "aromaticrings", "hdonors", "hacceptors",
}
_HEURISTIC = {"aero_impulso_espec_teorico", "indice_eficiencia", "ob%", "oxygen_balance"}


@dataclass(frozen=True)
class TargetMigration:
    target: str
    target_class: LegacyTargetClass
    action: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        data = asdict(self)
        data["target_class"] = self.target_class.value
        return data


def _key(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def classify_legacy_target(name: str) -> TargetMigration:
    key = _key(name)
    if key in _DETERMINISTIC:
        return TargetMigration(name, LegacyTargetClass.DETERMINISTIC, "replace_ml_with_deterministic_calculation", "target is directly computable from molecular structure by RDKit/descriptors and should not be learned as a surrogate without a separate reason")
    if key in _HEURISTIC or "impulso" in key or "eficiencia" in key:
        return TargetMigration(name, LegacyTargetClass.HEURISTIC_REVIEW, "quarantine_and_rederive_from_physics_or_experiment", "target appears heuristic/derived and must not be promoted as physical truth or recycled into training without independent evidence")
    if any(token in key for token in ("experimental", "tox", "solub", "clearance", "permeab", "bioactiv", "affinity", "ic50", "ec50", "yield_strength", "creep", "fatigue")):
        return TargetMigration(name, LegacyTargetClass.MODEL_CANDIDATE, "retain_for_ml_after_provenance_and_split_audit", "target can plausibly represent an empirical property where statistical learning may add value")
    return TargetMigration(name, LegacyTargetClass.UNKNOWN, "manual_review", "target semantics are not explicit enough for automatic migration")


def migration_plan_for_targets(targets: list[str]) -> list[dict[str, str]]:
    return [classify_legacy_target(target).to_dict() for target in targets]
