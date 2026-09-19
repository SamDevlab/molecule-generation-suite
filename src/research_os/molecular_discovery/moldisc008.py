"""MOLDISC-008: characterize the MOLDISC-007-selected JE2 seed before generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from research_os.core.hashing import sha256_json
from research_os.molecular_discovery.aqsoldb_coverage import (
    AqSolDBCoverageReport,
    CandidateCoverage,
    run_public_aqsoldb_coverage,
)
from research_os.molecular_discovery.moldisc003 import (
    RCSBChemicalIdentity,
    fetch_rcsb_identity,
)
from research_os.molecular_discovery.solubility import FrozenESOLSolubilityPredictor
from research_os.molecular_discovery.workflow import (
    CandidateAssessment,
    MolecularDiscoveryWorkflow,
)


PROGRAM_ID = "MOLDISC-008"
SEED_CANDIDATE_ID = "MOLDISC-008-SEED-JE2"
COVERAGE_BOUNDARY = 0.4
EXPECTED_PARENT_PROGRAM_HASH = "92ca1d06d3d1c01466d284910854f36f35949bf4ce8031cf10f869373ed419de"
EXPECTED_ESOL_DATASET_HASH = "6de39771743dc4f15b191cffc27e1e02eb474457cc841afda565f31aff198e85"
EXPECTED_ESOL_TRAINING_HASH = "300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b"
EXPECTED_ESOL_AD_THRESHOLD = 0.26684684684684684
EXPECTED_AQSOLDB_PARSED_HASH = "2c6e56f56389f0fd99fa2a3c843446f98b6b068a3f93aaab71a08822caa085f4"
EXPECTED_PARENT_AQSOLDB_SIMILARITY = 0.569620253164557


class MOLDISC008Error(RuntimeError):
    """Fail-closed error for JE2 seed, source or frozen capability drift."""


@dataclass(frozen=True)
class JE2EvidenceProfile:
    candidate_id: str
    canonical_smiles: str
    inchikey: str
    chemistry_status: str
    esol_status: str
    predicted_log_s_mol_l: float
    esol_max_training_tanimoto: float
    esol_applicability_threshold: float
    aqsoldb_nearest_similarity: float
    aqsoldb_similarity_bin: str
    aqsoldb_neighbors_ge_0_4: int
    aqsoldb_neighbors_ge_0_6: int
    aqsoldb_neighbors_ge_0_8: int
    exact_aqsoldb_match: bool
    top_neighbor_canonical_smiles: str | None
    top_neighbor_inchikey: str | None
    top_neighbor_observation_count: int | None
    top_neighbor_median_log_s_mol_l: float | None
    top_neighbor_minimum_log_s_mol_l: float | None
    top_neighbor_maximum_log_s_mol_l: float | None
    generation_source_ready: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MOLDISC008Result:
    program_id: str
    config_hash: str
    rcsb_identity: RCSBChemicalIdentity
    rcsb_identity_hash: str
    assessment: CandidateAssessment
    coverage: AqSolDBCoverageReport
    profile: JE2EvidenceProfile
    workflow_scientific_summary_hash: str
    program_scientific_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "config_hash": self.config_hash,
            "rcsb_identity": self.rcsb_identity.scientific_dict(),
            "rcsb_identity_hash": self.rcsb_identity_hash,
            "assessment": self.assessment.to_dict(),
            "coverage": self.coverage.to_dict(),
            "profile": self.profile.to_dict(),
            "workflow_scientific_summary_hash": self.workflow_scientific_summary_hash,
            "program_scientific_hash": self.program_scientific_hash,
        }


def load_program_config_v8(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != "1.0":
        raise MOLDISC008Error("MOLDISC-008 requires frozen program_id/version 1.0")

    parent = config.get("parent_program") or {}
    if parent.get("program_scientific_hash") != EXPECTED_PARENT_PROGRAM_HASH:
        raise MOLDISC008Error("MOLDISC-008 parent MOLDISC-007 hash drifted")
    if (
        parent.get("selected_case_id") != "ATX-007"
        or parent.get("selected_pdb_id") != "1KZK"
        or parent.get("selected_chem_comp_id") != "JE2"
    ):
        raise MOLDISC008Error("MOLDISC-008 parent selection drifted from ATX-007 / 1KZK / JE2")

    seed = config.get("seed") or {}
    if (
        seed.get("case_id") != "ATX-007"
        or seed.get("pdb_id") != "1KZK"
        or seed.get("chem_comp_id") != "JE2"
    ):
        raise MOLDISC008Error("MOLDISC-008 seed identity drifted")

    predictor = config.get("predictor") or {}
    if predictor.get("dataset_hash") != EXPECTED_ESOL_DATASET_HASH:
        raise MOLDISC008Error("MOLDISC-008 frozen ESOL dataset hash drifted")
    if predictor.get("training_hash") != EXPECTED_ESOL_TRAINING_HASH:
        raise MOLDISC008Error("MOLDISC-008 frozen ESOL training hash drifted")
    if abs(float(predictor.get("applicability_threshold", -1)) - EXPECTED_ESOL_AD_THRESHOLD) > 1e-12:
        raise MOLDISC008Error("MOLDISC-008 frozen ESOL AD threshold drifted")
    if predictor.get("model_change_allowed") is not False:
        raise MOLDISC008Error("MOLDISC-008 forbids model changes")
    if predictor.get("prediction_used_as_selection_score") is not False:
        raise MOLDISC008Error("MOLDISC-008 forbids using ESOL prediction as a selection score")

    coverage = config.get("measured_source_coverage") or {}
    if coverage.get("parsed_source_hash") != EXPECTED_AQSOLDB_PARSED_HASH:
        raise MOLDISC008Error("MOLDISC-008 AqSolDB parsed-source hash drifted")
    if abs(float(coverage.get("coverage_boundary", -1)) - COVERAGE_BOUNDARY) > 1e-12:
        raise MOLDISC008Error("MOLDISC-008 AqSolDB coverage boundary drifted")
    if abs(
        float(coverage.get("expected_parent_nearest_similarity", -1))
        - EXPECTED_PARENT_AQSOLDB_SIMILARITY
    ) > 1e-12:
        raise MOLDISC008Error("MOLDISC-008 parent AqSolDB similarity drifted")

    execution = config.get("execution") or {}
    if any(bool(execution.get(key)) for key in ("molecule_generation", "docking", "model_training", "hyperparameter_tuning")):
        raise MOLDISC008Error("MOLDISC-008 is characterization-only and must not generate, dock or train")

    gate = config.get("followup_gate") or {}
    if gate.get("esol_in_domain_required") is not False or gate.get("no_automatic_generation") is not True:
        raise MOLDISC008Error("MOLDISC-008 follow-up gate drifted")
    return config


def _seed_case(config: Mapping[str, Any]) -> dict[str, Any]:
    seed = config["seed"]
    return {
        "case_id": seed["case_id"],
        "pdb_id": seed["pdb_id"],
        "chem_comp_id": seed["chem_comp_id"],
        "target": seed["target"],
    }


def _verify_predictor(
    predictor: FrozenESOLSolubilityPredictor,
) -> None:
    manifest = predictor.evidence_manifest()
    training = manifest["training"]
    if training["dataset_hash"] != EXPECTED_ESOL_DATASET_HASH:
        raise MOLDISC008Error("active frozen ESOL dataset identity drifted")
    if training["training_hash"] != EXPECTED_ESOL_TRAINING_HASH:
        raise MOLDISC008Error("active frozen ESOL training identity drifted")
    if abs(float(manifest["applicability_domain"]["threshold"]) - EXPECTED_ESOL_AD_THRESHOLD) > 1e-12:
        raise MOLDISC008Error("active frozen ESOL applicability threshold drifted")


def _profile(
    assessment: CandidateAssessment,
    local: CandidateCoverage,
) -> JE2EvidenceProfile:
    if assessment.solubility is None:
        raise MOLDISC008Error("frozen ESOL capability returned no JE2 solubility result")
    if local.candidate_id != assessment.candidate_id:
        raise MOLDISC008Error("JE2 workflow/coverage candidate identity mismatch")
    if local.canonical_smiles != assessment.smiles:
        # CandidateAssessment stores the submitted canonical RCSB SMILES. If the
        # active runtime canonicalizes it differently, that is identity drift.
        raise MOLDISC008Error("JE2 workflow and AqSolDB canonical structure identities differ")

    solubility = assessment.solubility
    top = local.top_neighbors[0] if local.top_neighbors else None
    exact = bool(top is not None and abs(top.similarity - 1.0) <= 1e-12)
    ready = assessment.chemistry_status == "PASS" and local.nearest_similarity >= COVERAGE_BOUNDARY
    return JE2EvidenceProfile(
        candidate_id=assessment.candidate_id,
        canonical_smiles=local.canonical_smiles,
        inchikey=local.inchikey,
        chemistry_status=assessment.chemistry_status,
        esol_status=assessment.solubility_status,
        predicted_log_s_mol_l=float(solubility["predicted_log_s_mol_l"]),
        esol_max_training_tanimoto=float(solubility["max_training_tanimoto"]),
        esol_applicability_threshold=float(solubility["applicability_threshold"]),
        aqsoldb_nearest_similarity=local.nearest_similarity,
        aqsoldb_similarity_bin=local.similarity_bin,
        aqsoldb_neighbors_ge_0_4=local.neighbors_ge_0_4,
        aqsoldb_neighbors_ge_0_6=local.neighbors_ge_0_6,
        aqsoldb_neighbors_ge_0_8=local.neighbors_ge_0_8,
        exact_aqsoldb_match=exact,
        top_neighbor_canonical_smiles=(top.canonical_smiles if top else None),
        top_neighbor_inchikey=(top.inchikey if top else None),
        top_neighbor_observation_count=(top.observation_count if top else None),
        top_neighbor_median_log_s_mol_l=(top.median_measured_log_s_mol_l if top else None),
        top_neighbor_minimum_log_s_mol_l=(top.minimum_measured_log_s_mol_l if top else None),
        top_neighbor_maximum_log_s_mol_l=(top.maximum_measured_log_s_mol_l if top else None),
        generation_source_ready=ready,
    )


def run_moldisc_008(
    *,
    config_path: str | Path,
    output_root: str | Path,
    predictor: FrozenESOLSolubilityPredictor | None = None,
    timeout: float = 60.0,
) -> MOLDISC008Result:
    config = load_program_config_v8(config_path)
    config_hash = sha256_json(config)

    identity = fetch_rcsb_identity(_seed_case(config), timeout=min(timeout, 30.0))
    if identity.case_id != "ATX-007" or identity.pdb_id != "1KZK" or identity.chem_comp_id != "JE2":
        raise MOLDISC008Error("active RCSB JE2 identity drifted from frozen seed")
    rcsb_identity_hash = sha256_json(identity.scientific_dict())

    model = predictor or FrozenESOLSolubilityPredictor.from_public_source(timeout=timeout)
    _verify_predictor(model)

    candidate = {
        "id": SEED_CANDIDATE_ID,
        "name": "JE2 / ATX-007 / PDB 1KZK",
        "smiles": identity.canonical_smiles,
        "origin": {
            "source_type": "RCSB_crystallographic_chemical_component",
            "evidence_level": "E4_CURATED_EXPERIMENTAL",
            "case_id": identity.case_id,
            "pdb_id": identity.pdb_id,
            "chem_comp_id": identity.chem_comp_id,
            "rdkit_inchikey": identity.rdkit_inchikey,
            "source_url": identity.source_url,
            "selection_parent": "MOLDISC-007",
        },
    }

    workflow_report = MolecularDiscoveryWorkflow(solubility_predictor=model).run([candidate])
    if len(workflow_report.candidates) != 1:
        raise MOLDISC008Error("MOLDISC-008 expected exactly one JE2 workflow assessment")
    assessment = workflow_report.candidates[0]
    if assessment.chemistry_status != "PASS":
        raise MOLDISC008Error("MOLDISC-008 JE2 seed failed molecular validation")

    coverage = run_public_aqsoldb_coverage([candidate], timeout=timeout)
    if coverage.parsed_source_hash != EXPECTED_AQSOLDB_PARSED_HASH:
        raise MOLDISC008Error("active AqSolDB parsed-source identity drifted")
    if len(coverage.candidates) != 1:
        raise MOLDISC008Error("MOLDISC-008 expected exactly one JE2 coverage assessment")
    local = coverage.candidates[0]
    if abs(local.nearest_similarity - EXPECTED_PARENT_AQSOLDB_SIMILARITY) > 1e-12:
        raise MOLDISC008Error(
            "JE2 AqSolDB nearest similarity no longer reproduces the MOLDISC-007 parent evidence"
        )

    profile = _profile(assessment, local)
    scientific = {
        "program_id": PROGRAM_ID,
        "config_hash": config_hash,
        "rcsb_identity": identity.scientific_dict(),
        "rcsb_identity_hash": rcsb_identity_hash,
        "profile": profile.to_dict(),
        "workflow_scientific_summary_hash": workflow_report.scientific_summary_hash,
        "aqsoldb_coverage_scientific_hash": coverage.scientific_hash,
        "predictor_model_identity": model.model_identity,
    }
    result = MOLDISC008Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        rcsb_identity=identity,
        rcsb_identity_hash=rcsb_identity_hash,
        assessment=assessment,
        coverage=coverage,
        profile=profile,
        workflow_scientific_summary_hash=workflow_report.scientific_summary_hash,
        program_scientific_hash=sha256_json(scientific),
    )

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=False)
    (root / "program_manifest.json").write_text(
        json.dumps(
            {
                "program_id": PROGRAM_ID,
                "program_version": config["program_version"],
                "config_hash": config_hash,
                "rcsb_identity": identity.scientific_dict(),
                "rcsb_identity_hash": rcsb_identity_hash,
                "profile": profile.to_dict(),
                "workflow_scientific_summary_hash": workflow_report.scientific_summary_hash,
                "aqsoldb_coverage_scientific_hash": coverage.scientific_hash,
                "predictor_model_identity": model.model_identity,
                "program_scientific_hash": result.program_scientific_hash,
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
    (root / "coverage.json").write_text(
        json.dumps(coverage.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "program_report.md").write_text(_markdown(config, result), encoding="utf-8")
    return result


def _markdown(config: Mapping[str, Any], result: MOLDISC008Result) -> str:
    profile = result.profile
    lines = [
        "# MOLDISC-008 — JE2 source-backed solubility evidence profile",
        "",
        f"- seed: {result.rcsb_identity.case_id} / {result.rcsb_identity.pdb_id} / {result.rcsb_identity.chem_comp_id}",
        f"- RCSB canonical SMILES: {result.rcsb_identity.canonical_smiles}",
        f"- RCSB/RDKit InChIKey: {result.rcsb_identity.rdkit_inchikey}",
        f"- chemistry: {profile.chemistry_status}",
        f"- frozen ESOL status: {profile.esol_status}",
        f"- frozen ESOL predicted logS: {profile.predicted_log_s_mol_l:.6f}",
        f"- ESOL max-training Tanimoto: {profile.esol_max_training_tanimoto:.6f}",
        f"- ESOL AD threshold: {profile.esol_applicability_threshold:.6f}",
        f"- AqSolDB nearest similarity: {profile.aqsoldb_nearest_similarity:.6f}",
        f"- AqSolDB similarity bin: {profile.aqsoldb_similarity_bin}",
        f"- exact AqSolDB canonical match: {'YES' if profile.exact_aqsoldb_match else 'NO'}",
        f"- generation-source ready: {'YES' if profile.generation_source_ready else 'NO'}",
        f"- workflow scientific hash: {result.workflow_scientific_summary_hash}",
        f"- AqSolDB coverage hash: {result.coverage.scientific_hash}",
        f"- program scientific hash: {result.program_scientific_hash}",
        "",
        "## Top measured-source neighbor",
        "",
    ]
    if profile.top_neighbor_canonical_smiles is None:
        lines.append("No measured-source neighbor was available.")
    else:
        lines.extend(
            [
                f"- canonical SMILES: {profile.top_neighbor_canonical_smiles}",
                f"- InChIKey: {profile.top_neighbor_inchikey}",
                f"- observation count: {profile.top_neighbor_observation_count}",
                f"- median measured logS: {profile.top_neighbor_median_log_s_mol_l}",
                f"- range: {profile.top_neighbor_minimum_log_s_mol_l} to {profile.top_neighbor_maximum_log_s_mol_l}",
            ]
        )
    lines.extend(["", "## Interpretation boundaries", ""])
    lines.extend(f"- {item}" for item in config["interpretation_boundaries"])
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "COVERAGE_BOUNDARY",
    "JE2EvidenceProfile",
    "MOLDISC008Error",
    "MOLDISC008Result",
    "PROGRAM_ID",
    "SEED_CANDIDATE_ID",
    "load_program_config_v8",
    "run_moldisc_008",
]
