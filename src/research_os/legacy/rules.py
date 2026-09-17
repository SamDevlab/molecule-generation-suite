"""Named migration safety rules applied to historical artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


LEGACY_ML_RESUBSTITUTION_RULE = "LEGACY-ML-RESUBSTITUTION-001"
LEGACY_TARGET_SPECIES_RULE = "LEGACY-TARGET-SPECIES-001"


@dataclass(frozen=True)
class LegacyRuleFinding:
    rule_id: str
    status: str
    message: str
    component_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "status": self.status, "message": self.message, "component_ids": list(self.component_ids)}


def resubstitution_finding(component_ids: tuple[str, ...] = ()) -> LegacyRuleFinding:
    return LegacyRuleFinding(LEGACY_ML_RESUBSTITUTION_RULE, "REVIEW_REQUIRED", "training-set scoring or model.score is not independent validation", component_ids)


def species_finding(component_ids: tuple[str, ...] = ()) -> LegacyRuleFinding:
    return LegacyRuleFinding(LEGACY_TARGET_SPECIES_RULE, "REVIEW_REQUIRED", "species must be explicit; unknown species remains UNKNOWN", component_ids)

