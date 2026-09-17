"""Typed, read-only legacy inventory and migration assessment.

The scanner treats the historical directories as evidence to be inventoried,
never as an importable execution surface. It records uncertain provenance
instead of silently promoting historical outputs to datasets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from pathlib import Path
from typing import Any, Iterable

from research_os.core.hashing import sha256_file


class MigrationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MIGRATING = "MIGRATING"
    REPLACED = "REPLACED"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class ParityType(str, Enum):
    NONE = "NONE"
    INPUT = "INPUT"
    SCHEMA = "SCHEMA"
    BEHAVIORAL = "BEHAVIORAL"
    NUMERICAL = "NUMERICAL"
    SCIENTIFIC = "SCIENTIFIC"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class LegacyDataClass(str, Enum):
    HEURISTIC = "HEURISTIC"
    SYNTHETIC = "SYNTHETIC"
    UNVERIFIED = "UNVERIFIED"
    UNKNOWN_PROVENANCE = "UNKNOWN_PROVENANCE"


@dataclass(frozen=True)
class LegacyComponent:
    component_id: str
    path: str
    kind: str
    status: MigrationStatus = MigrationStatus.ACTIVE
    size_bytes: int = 0
    sha256: str | None = None
    flags: tuple[str, ...] = ()
    data_class: LegacyDataClass | None = None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["flags"] = list(self.flags)
        data["notes"] = list(self.notes)
        if self.data_class is not None:
            data["data_class"] = self.data_class.value
        return data


@dataclass(frozen=True)
class LegacyFlow:
    flow_id: str
    entrypoint: str
    components: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    targets: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    status: MigrationStatus = MigrationStatus.MIGRATING

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for name in ("components", "inputs", "outputs", "targets", "flags"):
            data[name] = list(data[name])
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class LegacyReplacement:
    legacy_component_id: str
    replacement: str
    parity: ParityType
    status: MigrationStatus
    evidence: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["parity"] = self.parity.value
        data["status"] = self.status.value
        data["evidence"] = list(self.evidence)
        data["limitations"] = list(self.limitations)
        return data


@dataclass(frozen=True)
class ParityAssessment:
    subject: str
    parity: ParityType
    equivalent: bool | None
    protocol: str
    legacy_values: dict[str, Any] = field(default_factory=dict)
    replacement_values: dict[str, Any] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["parity"] = self.parity.value
        data["diagnostics"] = list(self.diagnostics)
        return data


@dataclass(frozen=True)
class MigrationDecision:
    component_id: str
    status: MigrationStatus
    action: str
    reason: str
    gate_id: str = "LEGACY-MIGRATION-001"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class QuarantineManifest:
    quarantine_id: str
    source_path: str
    source_kind: str
    data_class: LegacyDataClass
    eligible_for_training: bool = False
    content_hash: str | None = None
    reason: str = "provenance has not been independently verified"
    required_review: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["data_class"] = self.data_class.value
        data["required_review"] = list(self.required_review)
        return data


@dataclass(frozen=True)
class LegacyInventory:
    repo_root: str
    components: tuple[LegacyComponent, ...]
    flows: tuple[LegacyFlow, ...]
    replacements: tuple[LegacyReplacement, ...]
    quarantine: tuple[QuarantineManifest, ...]
    findings: tuple[dict[str, Any], ...] = ()
    generated_by: str = "research_os.legacy.migration.scan_legacy"

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_root": self.repo_root,
            "generated_by": self.generated_by,
            "components": [item.to_dict() for item in self.components],
            "flows": [item.to_dict() for item in self.flows],
            "replacements": [item.to_dict() for item in self.replacements],
            "quarantine": [item.to_dict() for item in self.quarantine],
            "findings": [dict(item) for item in self.findings],
            "counts": {"components": len(self.components), "flows": len(self.flows), "quarantine": len(self.quarantine)},
        }


_TEXT_SUFFIXES = {".py", ".txt", ".csv", ".json", ".yaml", ".yml", ".md", ".log", ".ini", ".cfg"}
_TARGET_SUFFIXES = {".pdb", ".pdbqt", ".cif", ".mol", ".sdf"}
_DATA_SUFFIXES = {".csv", ".parquet", ".json", ".jsonl", ".tsv"}
_MODEL_SUFFIXES = {".pkl", ".joblib", ".onnx", ".pt", ".h5"}
_CONFIG_SUFFIXES = {".yaml", ".yml", ".toml", ".ini", ".cfg", ".txt"}
_OUTPUT_SUFFIXES = {".png", ".pdf", ".html", ".log", ".out"}


def _kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "script"
    if suffix in _DATA_SUFFIXES:
        return "dataset"
    if suffix in _MODEL_SUFFIXES:
        return "model"
    if suffix in _TARGET_SUFFIXES:
        return "target_or_structure"
    if suffix in _CONFIG_SUFFIXES or "config" in path.name.lower():
        return "config"
    if suffix in _OUTPUT_SUFFIXES:
        return "output_or_report"
    return "artifact"


def _classify_text(text: str, path: Path) -> tuple[tuple[str, ...], LegacyDataClass | None, tuple[str, ...]]:
    lower = text.lower()
    flags: list[str] = []
    notes: list[str] = []
    if any(token in lower for token in ("xgboost", "randomforest", "train_test_split", "joblib.dump", "model.fit")):
        flags.append("ML_PIPELINE")
    if any(token in lower for token in ("vina", "autodock", "obabel", "openbabel")):
        flags.append("EXTERNAL_ENGINE")
    if any(token in lower for token in ("bonus", "random.choice", "sqrt(nova_energia", "indice_eficiencia", "impulso_espec")):
        flags.append("HEURISTIC")
    if any(token in lower for token in ("synthetic", "synthetic_feedback", "geracao", "mutante", "evolut")):
        flags.append("SYNTHETIC_FEEDBACK")
    if re.search(r"r2\s*[*=]|r2_.*confian|confiabilidade.*r2", lower):
        flags.append("R2_OVERCLAIM")
        notes.append("R² is a model metric, not a confidence percentage or clinical evidence")
    if any(token in lower for token in ("alzheimer", "ache", "4ey7", "5w8k")):
        flags.append("ALZHEIMER_RELATED")
    if any(token in lower for token in ("c:\\", "./", "../", "base_dir", "os.path.join")):
        flags.append("HARDCODED_PATH_OR_RELATIVE_PATH")
    if "HEURISTIC" in flags:
        return tuple(sorted(set(flags))), LegacyDataClass.HEURISTIC, tuple(notes)
    if "SYNTHETIC_FEEDBACK" in flags:
        return tuple(sorted(set(flags))), LegacyDataClass.SYNTHETIC, tuple(notes)
    if path.suffix.lower() in _DATA_SUFFIXES or path.suffix.lower() in _MODEL_SUFFIXES:
        return tuple(sorted(set(flags))), LegacyDataClass.UNKNOWN_PROVENANCE, tuple(notes)
    return tuple(sorted(set(flags))), None, tuple(notes)


def _component(path: Path, root: Path, ordinal: int) -> LegacyComponent:
    relative = str(path.relative_to(root)).replace("\\", "/")
    data_class = None
    flags: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    if path.suffix.lower() in _TEXT_SUFFIXES:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:2_000_000]
        except OSError:
            text = ""
        flags, data_class, notes = _classify_text(text, path)
    elif path.suffix.lower() in _DATA_SUFFIXES or path.suffix.lower() in _MODEL_SUFFIXES:
        data_class = LegacyDataClass.UNKNOWN_PROVENANCE
    return LegacyComponent(component_id=f"LEG-{ordinal:05d}", path=relative, kind=_kind(path), size_bytes=path.stat().st_size, sha256=sha256_file(path), flags=flags, data_class=data_class, notes=notes)


def _flows(components: Iterable[LegacyComponent]) -> tuple[LegacyFlow, ...]:
    by_path = {component.path: component for component in components}
    pharma = tuple(path for path in by_path if path.endswith("formolecular/g_oraculo_farma.py") or path.endswith("Biolab/fabrica_g2.py"))
    aero = tuple(path for path in by_path if path.endswith("formolecular/g_oraculo_aeroespacial.py") or path.endswith("formolecular/t_aero.py") or path.endswith("formolecular/t_aero2.py"))
    flows = []
    if pharma:
        flows.append(LegacyFlow("LEGACY-FLOW-PHARMA", pharma[0], pharma, ("SMILES", "receptor", "config"), ("rankings", "reports", "docking outputs"), ("1cx2", "4cox", "6cox", "4EY7", "5W8K"), ("ML_PIPELINE", "EXTERNAL_ENGINE", "HARDCODED_PATH_OR_RELATIVE_PATH")))
    if aero:
        flows.append(LegacyFlow("LEGACY-FLOW-AERO", aero[0], aero, ("SMILES", "energy-like columns"), ("Isp", "energy rankings"), ("AERO_Impulso_Espec_Teorico",), ("ML_PIPELINE", "HEURISTIC", "SYNTHETIC_FEEDBACK")))
    return tuple(flows)


def _replacements() -> tuple[LegacyReplacement, ...]:
    return (
        LegacyReplacement("formolecular/g_oraculo_farma.py", "MoleculeLab + deterministic RDKit properties + PharmaLab", ParityType.SCIENTIFIC, MigrationStatus.MIGRATING, ("QED/MW/LogP/TPSA side-by-side parity",), ("ADMET/clinical efficacy remains outside deterministic parity",)),
        LegacyReplacement("formolecular/g_oraculo_aeroespacial.py", "FuelLab -> CombustionLab -> PropulsionLab", ParityType.NONE, MigrationStatus.MIGRATING, (), ("AERO_Impulso_Espec_Teorico remains HEURISTIC_REVIEW; no numerical parity target",)),
        LegacyReplacement("Biolab/fabrica_g2.py", "MoleculeLab -> preparation -> DockingLab -> Campaign -> PharmaLab -> Evidence -> Bundle -> Ledger", ParityType.BEHAVIORAL, MigrationStatus.MIGRATING, (), ("requires real Vina/Open Babel execution and target-specific validated protocols",)),
        LegacyReplacement("formolecular/t_aero.py", "FuelLab/CombustionLab with explicit conditions and units", ParityType.NONE, MigrationStatus.MIGRATING, (), ("heuristic rankings are quarantined, not numerically reproduced",)),
        LegacyReplacement("formolecular/t_aero2.py", "physics engine boundary with no synthetic energy feedback", ParityType.NONE, MigrationStatus.MIGRATING, (), ("legacy mutation/energy feedback is not scientific evidence",)),
    )


def scan_legacy(repo_root: str | Path = ".") -> LegacyInventory:
    root = Path(repo_root).resolve()
    components: list[LegacyComponent] = []
    ordinal = 1
    for directory in ("Biolab", "formolecular"):
        path = root / directory
        if not path.is_dir():
            continue
        for item in sorted(path.rglob("*")):
            if not item.is_file() or item.suffix.lower() == ".pyc" or "__pycache__" in item.parts:
                continue
            components.append(_component(item, root, ordinal))
            ordinal += 1
    quarantine = tuple(QuarantineManifest(quarantine_id=f"Q-{component.component_id}", source_path=component.path, source_kind=component.kind, data_class=component.data_class, content_hash=component.sha256, reason="legacy provenance, split, licensing and independent validation are not established", required_review=("source provenance", "license", "units and conditions", "independent validation")) for component in components if component.data_class in {LegacyDataClass.HEURISTIC, LegacyDataClass.SYNTHETIC, LegacyDataClass.UNKNOWN_PROVENANCE} and component.kind in {"dataset", "model", "output_or_report"})
    findings = []
    if any("ML_PIPELINE" in component.flags for component in components):
        findings.append({"rule_id": "LEGACY-ML-RESUBSTITUTION-001", "status": "REVIEW_REQUIRED", "message": "historical ML scripts require an explicit holdout/independent validation audit; resubstitution scoring is not validation"})
    if any("ALZHEIMER_RELATED" in component.flags for component in components):
        findings.append({"rule_id": "LEGACY-TARGET-SPECIES-001", "status": "REVIEW_REQUIRED", "message": "species is not globally inferable from filenames; use HUMAN only where explicitly documented, otherwise UNKNOWN"})
    return LegacyInventory(str(root), tuple(components), _flows(components), _replacements(), quarantine, tuple(findings))


def migration_decisions(inventory: LegacyInventory) -> tuple[MigrationDecision, ...]:
    return tuple(MigrationDecision(component.component_id, MigrationStatus.MIGRATING, "wrap_or_replace_without_editing_legacy", "legacy path remains preserved while Research OS parity and provenance gates are built") for component in inventory.components)


def legacy_datasets(inventory: LegacyInventory) -> tuple[QuarantineManifest, ...]:
    return inventory.quarantine


def write_inventory(inventory: LegacyInventory, path: str | Path) -> Path:
    import json
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(inventory.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def legacy_target_species(target: str) -> str:
    """Return only species explicitly supported by legacy text evidence."""
    return "HUMAN" if str(target).strip().upper() == "4EY7" else "UNKNOWN"


class LegacyDatasetAuditor:
    """Read-only auditor for training eligibility and provenance risks."""

    def audit(self, inventory: LegacyInventory) -> dict[str, Any]:
        return {
            "rule_id": "LEGACY-DATASET-AUDIT-001",
            "eligible_for_training": [item.to_dict() for item in inventory.quarantine if item.eligible_for_training],
            "ineligible_for_training": [item.to_dict() for item in inventory.quarantine if not item.eligible_for_training],
            "findings": list(inventory.findings),
            "policy": "unknown provenance defaults to eligible_for_training=false",
        }
