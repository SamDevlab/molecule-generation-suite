"""MOLDISC-004: calibrate the selected NCT seed against its exact measured anchor."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from research_os.core.hashing import sha256_json
from research_os.molecular_discovery.aqsoldb_coverage import (
    AqSolDBSourceRecord,
    download_aqsoldb,
)
from research_os.molecular_discovery.solubility import FrozenESOLSolubilityPredictor
from research_os.molecular_discovery.workflow import (
    CandidateAssessment,
    MolecularDiscoveryWorkflow,
)


PROGRAM_ID = "MOLDISC-004"


class MOLDISC004Error(RuntimeError):
    """Fail-closed error for selected-seed or measured-anchor identity drift."""


@dataclass(frozen=True)
class MeasuredSolubilityAnchor:
    dataset: str
    source_id: str
    canonical_smiles: str
    inchikey: str
    measured_log_s_mol_l: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SeedCalibration:
    measured_log_s_mol_l: float
    predicted_log_s_mol_l: float
    signed_error_predicted_minus_measured: float
    absolute_error: float
    max_training_tanimoto: float
    applicability_threshold: float
    applicability_domain_status: str
    predictor_model_identity: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MOLDISC004Result:
    program_id: str
    config_hash: str
    anchor: MeasuredSolubilityAnchor
    assessment: CandidateAssessment
    calibration: SeedCalibration
    workflow_scientific_summary_hash: str
    program_scientific_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "config_hash": self.config_hash,
            "anchor": self.anchor.to_dict(),
            "assessment": self.assessment.to_dict(),
            "calibration": self.calibration.to_dict(),
            "workflow_scientific_summary_hash": self.workflow_scientific_summary_hash,
            "program_scientific_hash": self.program_scientific_hash,
        }


def load_program_config_v4(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("program_id") != PROGRAM_ID:
        raise MOLDISC004Error(
            f"expected program_id {PROGRAM_ID}, got {config.get('program_id')!r}"
        )
    if config.get("program_version") != "1.0":
        raise MOLDISC004Error("MOLDISC-004 requires program_version 1.0")
    parent = config.get("parent_program") or {}
    if parent.get("selected_case_id") != "ATX-014":
        raise MOLDISC004Error("MOLDISC-004 parent selection drifted from ATX-014")
    seed = config.get("seed") or {}
    if (
        seed.get("pdb_id") != "1P2Y"
        or seed.get("chem_comp_id") != "NCT"
        or seed.get("inchikey") != "SNICXCGAKADSCV-UHFFFAOYSA-N"
    ):
        raise MOLDISC004Error("MOLDISC-004 NCT seed identity drifted")
    predictor = config.get("predictor") or {}
    if predictor.get("model_change_allowed") is not False:
        raise MOLDISC004Error("MOLDISC-004 forbids predictor changes")
    comparison = config.get("comparison") or {}
    if comparison.get("performance_threshold") is not None:
        raise MOLDISC004Error("MOLDISC-004 must not introduce a post-selection performance threshold")
    if comparison.get("post_result_model_tuning") is not False:
        raise MOLDISC004Error("MOLDISC-004 forbids post-result model tuning")
    return config


def _rdkit_identity(smiles: str) -> tuple[str, str]:
    try:
        from rdkit import Chem
        from rdkit.Chem import inchi
    except ImportError as exc:
        raise MOLDISC004Error(
            "MOLDISC-004 requires RDKit; install the 'discovery' extra"
        ) from exc
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise MOLDISC004Error(f"invalid or unsanitizable anchor SMILES: {smiles!r}")
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    return canonical, inchi.MolToInchiKey(molecule)


def verify_measured_anchor(
    config: Mapping[str, Any],
    records: Sequence[AqSolDBSourceRecord],
) -> MeasuredSolubilityAnchor:
    expected = config["measured_anchor"]
    source_id = str(expected["source_id"])
    matches = [record for record in records if record.source_id == source_id]
    if len(matches) != 1:
        raise MOLDISC004Error(
            f"expected exactly one AqSolDB source record {source_id}, found {len(matches)}"
        )
    record = matches[0]
    canonical, inchikey = _rdkit_identity(record.smiles)
    if canonical != expected["expected_canonical_smiles"]:
        raise MOLDISC004Error("NCT AqSolDB anchor canonical SMILES drifted")
    if inchikey != expected["expected_inchikey"]:
        raise MOLDISC004Error("NCT AqSolDB anchor InChIKey drifted")
    measured = float(record.measured_log_s_mol_l)
    if abs(measured - float(expected["expected_measured_log_s_mol_l"])) > 1e-12:
        raise MOLDISC004Error(
            f"NCT AqSolDB measured logS drifted: expected {expected['expected_measured_log_s_mol_l']}, got {measured}"
        )
    seed = config["seed"]
    seed_canonical, seed_inchikey = _rdkit_identity(str(seed["canonical_smiles"]))
    if seed_canonical != canonical or seed_inchikey != inchikey:
        raise MOLDISC004Error("selected NCT seed no longer matches the exact AqSolDB anchor")
    return MeasuredSolubilityAnchor(
        dataset=str(expected["dataset"]),
        source_id=source_id,
        canonical_smiles=canonical,
        inchikey=inchikey,
        measured_log_s_mol_l=measured,
    )


def run_moldisc_004(
    *,
    config_path: str | Path,
    output_root: str | Path,
    predictor: FrozenESOLSolubilityPredictor | None = None,
    aqsoldb_records: Sequence[AqSolDBSourceRecord] | None = None,
    timeout: float = 60.0,
) -> MOLDISC004Result:
    config = load_program_config_v4(config_path)
    config_hash = sha256_json(config)

    if aqsoldb_records is None:
        records, source_row_count, parsed_source_hash = download_aqsoldb(timeout=timeout)
        expected_hash = str(config["measured_anchor"]["parsed_source_hash"])
        if parsed_source_hash != expected_hash:
            raise MOLDISC004Error("MOLDISC-004 AqSolDB parsed-source identity drifted")
        if source_row_count != 9982:
            raise MOLDISC004Error("MOLDISC-004 AqSolDB source row-count identity drifted")
    else:
        records = tuple(aqsoldb_records)

    anchor = verify_measured_anchor(config, records)
    model = predictor or FrozenESOLSolubilityPredictor.from_public_source(timeout=timeout)

    predictor_config = config["predictor"]
    manifest = model.evidence_manifest()
    training = manifest["training"]
    if training["dataset_hash"] != predictor_config["dataset_hash"]:
        raise MOLDISC004Error("frozen ESOL dataset hash drifted")
    if training["training_hash"] != predictor_config["training_hash"]:
        raise MOLDISC004Error("frozen ESOL training hash drifted")
    if abs(
        float(manifest["applicability_domain"]["threshold"])
        - float(predictor_config["applicability_threshold"])
    ) > 1e-12:
        raise MOLDISC004Error("frozen ESOL applicability threshold drifted")

    seed = config["seed"]
    workflow = MolecularDiscoveryWorkflow(solubility_predictor=model)
    report = workflow.run(
        [
            {
                "id": "MOLDISC-004-SEED-NCT",
                "name": "NCT / ATX-014 / PDB 1P2Y",
                "smiles": seed["canonical_smiles"],
                "origin": {
                    "source_type": seed["source_type"],
                    "evidence_level": "E4_CURATED_EXPERIMENTAL",
                    "case_id": seed["case_id"],
                    "pdb_id": seed["pdb_id"],
                    "chem_comp_id": seed["chem_comp_id"],
                    "measured_anchor_source_id": anchor.source_id,
                },
            }
        ]
    )
    if len(report.candidates) != 1:
        raise MOLDISC004Error("MOLDISC-004 expected exactly one seed assessment")
    assessment = report.candidates[0]
    if assessment.chemistry_status != "PASS":
        raise MOLDISC004Error("selected NCT seed failed molecular validation")
    solubility = assessment.solubility
    if solubility is None:
        raise MOLDISC004Error("frozen ESOL predictor produced no NCT solubility result")

    predicted = float(solubility["predicted_log_s_mol_l"])
    measured = anchor.measured_log_s_mol_l
    signed_error = predicted - measured
    calibration = SeedCalibration(
        measured_log_s_mol_l=measured,
        predicted_log_s_mol_l=predicted,
        signed_error_predicted_minus_measured=signed_error,
        absolute_error=abs(signed_error),
        max_training_tanimoto=float(solubility["max_training_tanimoto"]),
        applicability_threshold=float(solubility["applicability_threshold"]),
        applicability_domain_status=str(solubility["domain_status"]),
        predictor_model_identity=model.model_identity,
    )

    program_hash = sha256_json(
        {
            "program_id": PROGRAM_ID,
            "config_hash": config_hash,
            "anchor": anchor.to_dict(),
            "calibration": calibration.to_dict(),
            "workflow_scientific_summary_hash": report.scientific_summary_hash,
        }
    )
    result = MOLDISC004Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        anchor=anchor,
        assessment=assessment,
        calibration=calibration,
        workflow_scientific_summary_hash=report.scientific_summary_hash,
        program_scientific_hash=program_hash,
    )

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=False)
    (root / "program_manifest.json").write_text(
        json.dumps(
            {
                "program_id": PROGRAM_ID,
                "program_version": config["program_version"],
                "config_hash": config_hash,
                "anchor": anchor.to_dict(),
                "calibration": calibration.to_dict(),
                "workflow_scientific_summary_hash": report.scientific_summary_hash,
                "program_scientific_hash": program_hash,
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "assessment.json").write_text(
        json.dumps(assessment.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "program_report.md").write_text(
        _markdown(config, result),
        encoding="utf-8",
    )
    return result


def _markdown(config: Mapping[str, Any], result: MOLDISC004Result) -> str:
    calibration = result.calibration
    lines = [
        "# MOLDISC-004 — NCT measured-anchor calibration",
        "",
        f"- PDB / ligand: {config['seed']['pdb_id']} / {config['seed']['chem_comp_id']}",
        f"- AqSolDB source: {result.anchor.source_id}",
        f"- measured logS: {calibration.measured_log_s_mol_l:.6f}",
        f"- frozen ESOL predicted logS: {calibration.predicted_log_s_mol_l:.6f}",
        f"- signed error (predicted - measured): {calibration.signed_error_predicted_minus_measured:.6f}",
        f"- absolute error: {calibration.absolute_error:.6f}",
        f"- max training Tanimoto: {calibration.max_training_tanimoto:.6f}",
        f"- AD threshold: {calibration.applicability_threshold:.6f}",
        f"- AD status: {calibration.applicability_domain_status}",
        f"- predictor model identity: {calibration.predictor_model_identity}",
        f"- workflow scientific hash: {result.workflow_scientific_summary_hash}",
        f"- program scientific hash: {result.program_scientific_hash}",
        "",
        "## Interpretation boundaries",
        "",
    ]
    lines.extend(f"- {item}" for item in config["interpretation_boundaries"])
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "MOLDISC004Error",
    "MOLDISC004Result",
    "MeasuredSolubilityAnchor",
    "PROGRAM_ID",
    "SeedCalibration",
    "load_program_config_v4",
    "run_moldisc_004",
    "verify_measured_anchor",
]
