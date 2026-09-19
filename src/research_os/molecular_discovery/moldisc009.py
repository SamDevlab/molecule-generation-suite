"""MOLDISC-009: bounded JE2 single-terminal-methyl deletion series."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from research_os.core.hashing import sha256_json
from research_os.molecular_discovery.aqsoldb_coverage import (
    AqSolDBCoverageReport,
    CandidateCoverage,
    run_public_aqsoldb_coverage,
)
from research_os.molecular_discovery.solubility import FrozenESOLSolubilityPredictor
from research_os.molecular_discovery.workflow import CandidateAssessment, MolecularDiscoveryWorkflow


PROGRAM_ID = "MOLDISC-009"
GENERATOR_ID = "research-os.molecular-discovery.je2-single-terminal-methyl-deletion.v1"
SEED_CANDIDATE_ID = "MOLDISC-009-SEED-JE2"
SEED_SMILES = "Cc1ccccc1CNC(=O)[C@H]1N(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2C)CSC1(C)C"
SEED_INCHIKEY = "CUFQBQOBLVLKRF-RZDMPUFOSA-N"
PARENT_PROGRAM_HASH = "fd2adf5923ba0ad822d14ee8a4c1199aa3bf6732b8c70cb396940951126d2b90"
COVERAGE_BOUNDARY = 0.4
EXPECTED_TERMINAL_METHYL_SITES = 4
EXPECTED_UNIQUE_PRODUCTS = 3
VARIANT_IDS = ("DEMETHYL-01", "DEMETHYL-02", "DEMETHYL-03")


class MOLDISC009Error(RuntimeError):
    """Fail-closed error for JE2 demethyl generation or evidence drift."""


@dataclass(frozen=True)
class GeneratedJE2Analog:
    variant_id: str
    candidate_id: str
    smiles: str
    inchikey: str
    removed_seed_atom_indices: tuple[int, ...]
    generator_id: str = GENERATOR_ID
    evidence_level: str = "E0_HEURISTIC"
    operation: str = "delete_one_terminal_methyl"

    @property
    def generation_hash(self) -> str:
        return sha256_json(
            {
                "variant_id": self.variant_id,
                "candidate_id": self.candidate_id,
                "smiles": self.smiles,
                "inchikey": self.inchikey,
                "removed_seed_atom_indices": list(self.removed_seed_atom_indices),
                "generator_id": self.generator_id,
                "evidence_level": self.evidence_level,
                "operation": self.operation,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "removed_seed_atom_indices": list(self.removed_seed_atom_indices),
            "generation_hash": self.generation_hash,
        }

    def to_workflow_candidate(self) -> dict[str, Any]:
        return {
            "id": self.candidate_id,
            "name": f"JE2 {self.variant_id}",
            "smiles": self.smiles,
            "origin": {
                "source_type": "heuristic_generation",
                "evidence_level": self.evidence_level,
                "generator_id": self.generator_id,
                "parent_id": SEED_CANDIDATE_ID,
                "variant_id": self.variant_id,
                "operation": self.operation,
                "generation_hash": self.generation_hash,
            },
        }


@dataclass(frozen=True)
class JE2AnalogProfile:
    candidate_id: str
    variant_id: str
    source_role: str
    smiles: str
    chemistry_status: str
    esol_status: str
    predicted_log_s_mol_l: float | None
    esol_max_training_tanimoto: float | None
    aqsoldb_nearest_similarity: float
    aqsoldb_similarity_bin: str
    aqsoldb_neighbors_ge_0_4: int
    aqsoldb_neighbors_ge_0_6: int
    aqsoldb_neighbors_ge_0_8: int
    exact_aqsoldb_match: bool
    aqsoldb_top_neighbor_smiles: str | None
    aqsoldb_top_neighbor_inchikey: str | None
    aqsoldb_top_neighbor_measured_log_s_mol_l: float | None
    followup_eligible: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JE2AnalogSelection:
    selected_candidate_id: str | None
    selected_variant_id: str | None
    selected_nearest_similarity: float | None
    eligible_generated_candidate_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_candidate_id": self.selected_candidate_id,
            "selected_variant_id": self.selected_variant_id,
            "selected_nearest_similarity": self.selected_nearest_similarity,
            "eligible_generated_candidate_ids": list(self.eligible_generated_candidate_ids),
            "coverage_boundary": COVERAGE_BOUNDARY,
        }


@dataclass(frozen=True)
class MOLDISC009Result:
    program_id: str
    config_hash: str
    generation_scientific_hash: str
    workflow_scientific_summary_hash: str
    coverage_scientific_hash: str
    profiles: tuple[JE2AnalogProfile, ...]
    selection: JE2AnalogSelection
    program_scientific_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "config_hash": self.config_hash,
            "generation_scientific_hash": self.generation_scientific_hash,
            "workflow_scientific_summary_hash": self.workflow_scientific_summary_hash,
            "coverage_scientific_hash": self.coverage_scientific_hash,
            "profiles": [item.to_dict() for item in self.profiles],
            "selection": self.selection.to_dict(),
            "program_scientific_hash": self.program_scientific_hash,
        }


def _rdkit():
    try:
        from rdkit import Chem
        from rdkit.Chem import inchi
    except ImportError as exc:
        raise MOLDISC009Error("MOLDISC-009 requires RDKit; install the 'discovery' extra") from exc
    return Chem, inchi


def load_program_config_v9(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != "1.0":
        raise MOLDISC009Error("MOLDISC-009 requires frozen program_id/version 1.0")
    parent = config.get("parent_program") or {}
    if parent.get("program_scientific_hash") != PARENT_PROGRAM_HASH:
        raise MOLDISC009Error("MOLDISC-009 parent MOLDISC-008 hash drifted")
    if parent.get("generation_source_ready") is not True:
        raise MOLDISC009Error("MOLDISC-009 requires the frozen MOLDISC-008 source-ready gate")
    seed = config.get("seed") or {}
    if seed.get("canonical_smiles") != SEED_SMILES or seed.get("inchikey") != SEED_INCHIKEY:
        raise MOLDISC009Error("MOLDISC-009 JE2 seed identity drifted")
    generation = config.get("generation") or {}
    if generation.get("generator_id") != GENERATOR_ID:
        raise MOLDISC009Error("MOLDISC-009 generator identity drifted")
    if int(generation.get("expected_seed_terminal_methyl_sites", -1)) != EXPECTED_TERMINAL_METHYL_SITES:
        raise MOLDISC009Error("MOLDISC-009 frozen terminal-methyl site count drifted")
    if int(generation.get("expected_unique_generated_candidates", -1)) != EXPECTED_UNIQUE_PRODUCTS:
        raise MOLDISC009Error("MOLDISC-009 frozen unique-product count drifted")
    if tuple(generation.get("variant_ids_in_sorted_product_order") or ()) != VARIANT_IDS:
        raise MOLDISC009Error("MOLDISC-009 frozen variant IDs drifted")
    if generation.get("use_downstream_metrics_during_generation") is not False:
        raise MOLDISC009Error("MOLDISC-009 generation must stay upstream of evidence")
    evidence = config.get("evidence") or {}
    if abs(float(evidence.get("aqsoldb_coverage_boundary", -1)) - COVERAGE_BOUNDARY) > 1e-12:
        raise MOLDISC009Error("MOLDISC-009 AqSolDB coverage boundary drifted")
    if evidence.get("esol_used_for_selection") is not False:
        raise MOLDISC009Error("MOLDISC-009 forbids ESOL-based selection")
    if evidence.get("docking_in_v1") is not False:
        raise MOLDISC009Error("MOLDISC-009 v1 must not dock")
    return config


def _seed_identity() -> tuple[Any, str, str]:
    Chem, inchi = _rdkit()
    seed = Chem.MolFromSmiles(SEED_SMILES)
    if seed is None:
        raise MOLDISC009Error("frozen JE2 seed SMILES is not parseable")
    canonical = Chem.MolToSmiles(seed, canonical=True, isomericSmiles=True)
    key = inchi.MolToInchiKey(seed)
    if canonical != SEED_SMILES or key != SEED_INCHIKEY:
        raise MOLDISC009Error("active RDKit JE2 identity differs from the frozen seed")
    return seed, canonical, key


def _terminal_methyl_indices(seed: Any) -> tuple[int, ...]:
    indices = []
    for atom in seed.GetAtoms():
        if (
            atom.GetAtomicNum() == 6
            and atom.GetDegree() == 1
            and atom.GetTotalNumHs() == 3
        ):
            indices.append(atom.GetIdx())
    if len(indices) != EXPECTED_TERMINAL_METHYL_SITES:
        raise MOLDISC009Error(
            f"expected {EXPECTED_TERMINAL_METHYL_SITES} terminal methyl sites in JE2, found {len(indices)}"
        )
    return tuple(indices)


def generate_je2_single_demethyl_series() -> tuple[GeneratedJE2Analog, ...]:
    Chem, inchi = _rdkit()
    seed, canonical_seed, _ = _seed_identity()
    by_smiles: dict[str, dict[str, Any]] = {}
    for atom_index in _terminal_methyl_indices(seed):
        editable = Chem.RWMol(seed)
        editable.RemoveAtom(atom_index)
        product = editable.GetMol()
        try:
            Chem.SanitizeMol(product)
        except Exception as exc:
            raise MOLDISC009Error(
                f"frozen terminal-methyl deletion at seed atom {atom_index} did not sanitize"
            ) from exc
        smiles = Chem.MolToSmiles(product, canonical=True, isomericSmiles=True)
        if smiles == canonical_seed:
            raise MOLDISC009Error("terminal-methyl deletion reproduced the seed")
        entry = by_smiles.setdefault(
            smiles,
            {"inchikey": inchi.MolToInchiKey(product), "atom_indices": []},
        )
        entry["atom_indices"].append(atom_index)

    if len(by_smiles) != EXPECTED_UNIQUE_PRODUCTS:
        raise MOLDISC009Error(
            f"expected {EXPECTED_UNIQUE_PRODUCTS} unique JE2 demethyl products, found {len(by_smiles)}"
        )

    analogs = []
    for variant_id, smiles in zip(VARIANT_IDS, sorted(by_smiles), strict=True):
        info = by_smiles[smiles]
        suffix = sha256_json(
            {
                "generator_id": GENERATOR_ID,
                "seed_smiles": canonical_seed,
                "variant_id": variant_id,
                "product_smiles": smiles,
            }
        )[:10].upper()
        analogs.append(
            GeneratedJE2Analog(
                variant_id=variant_id,
                candidate_id=f"MOLDISC-009-JE2-{suffix}",
                smiles=smiles,
                inchikey=str(info["inchikey"]),
                removed_seed_atom_indices=tuple(sorted(info["atom_indices"])),
            )
        )
    return tuple(analogs)


def _build_profiles(
    assessments: Sequence[CandidateAssessment],
    coverage: Sequence[CandidateCoverage],
    analogs: Sequence[GeneratedJE2Analog],
) -> tuple[JE2AnalogProfile, ...]:
    assessment_by_id = {item.candidate_id: item for item in assessments}
    coverage_by_id = {item.candidate_id: item for item in coverage}
    variant_by_id = {item.candidate_id: item.variant_id for item in analogs}
    expected_ids = {SEED_CANDIDATE_ID, *variant_by_id}
    if set(assessment_by_id) != expected_ids or set(coverage_by_id) != expected_ids:
        raise MOLDISC009Error("workflow/coverage candidate sets do not match the frozen JE2 series")

    profiles = []
    for candidate_id in sorted(expected_ids):
        assessment = assessment_by_id[candidate_id]
        local = coverage_by_id[candidate_id]
        solubility = assessment.solubility or {}
        top = local.top_neighbors[0] if local.top_neighbors else None
        source_role = "SEED" if candidate_id == SEED_CANDIDATE_ID else "GENERATED"
        variant_id = "JE2-SEED" if source_role == "SEED" else variant_by_id[candidate_id]
        eligible = (
            source_role == "GENERATED"
            and assessment.chemistry_status == "PASS"
            and local.nearest_similarity >= COVERAGE_BOUNDARY
        )
        profiles.append(
            JE2AnalogProfile(
                candidate_id=candidate_id,
                variant_id=variant_id,
                source_role=source_role,
                smiles=assessment.smiles,
                chemistry_status=assessment.chemistry_status,
                esol_status=assessment.solubility_status,
                predicted_log_s_mol_l=(
                    float(solubility["predicted_log_s_mol_l"])
                    if solubility.get("predicted_log_s_mol_l") is not None else None
                ),
                esol_max_training_tanimoto=(
                    float(solubility["max_training_tanimoto"])
                    if solubility.get("max_training_tanimoto") is not None else None
                ),
                aqsoldb_nearest_similarity=local.nearest_similarity,
                aqsoldb_similarity_bin=local.similarity_bin,
                aqsoldb_neighbors_ge_0_4=local.neighbors_ge_0_4,
                aqsoldb_neighbors_ge_0_6=local.neighbors_ge_0_6,
                aqsoldb_neighbors_ge_0_8=local.neighbors_ge_0_8,
                exact_aqsoldb_match=bool(top is not None and abs(top.similarity - 1.0) <= 1e-12),
                aqsoldb_top_neighbor_smiles=(top.canonical_smiles if top else None),
                aqsoldb_top_neighbor_inchikey=(top.inchikey if top else None),
                aqsoldb_top_neighbor_measured_log_s_mol_l=(
                    top.median_measured_log_s_mol_l if top else None
                ),
                followup_eligible=eligible,
            )
        )
    return tuple(profiles)


def _select_generated(profiles: Sequence[JE2AnalogProfile]) -> JE2AnalogSelection:
    eligible = [
        item for item in profiles
        if item.source_role == "GENERATED" and item.followup_eligible
    ]
    eligible.sort(key=lambda item: (-item.aqsoldb_nearest_similarity, item.variant_id))
    if not eligible:
        return JE2AnalogSelection(None, None, None, ())
    selected = eligible[0]
    return JE2AnalogSelection(
        selected_candidate_id=selected.candidate_id,
        selected_variant_id=selected.variant_id,
        selected_nearest_similarity=selected.aqsoldb_nearest_similarity,
        eligible_generated_candidate_ids=tuple(item.candidate_id for item in eligible),
    )


def run_moldisc_009(
    *,
    config_path: str | Path,
    output_root: str | Path,
    predictor: FrozenESOLSolubilityPredictor | None = None,
    coverage_report: AqSolDBCoverageReport | None = None,
    timeout: float = 60.0,
) -> MOLDISC009Result:
    config = load_program_config_v9(config_path)
    config_hash = sha256_json(config)
    analogs = generate_je2_single_demethyl_series()
    generation_hash = sha256_json(
        {
            "generator_id": GENERATOR_ID,
            "seed_smiles": SEED_SMILES,
            "seed_inchikey": SEED_INCHIKEY,
            "analogs": [item.to_dict() for item in analogs],
        }
    )

    candidates = [
        {
            "id": SEED_CANDIDATE_ID,
            "name": "JE2 crystallographic seed",
            "smiles": SEED_SMILES,
            "origin": {
                "source_type": "RCSB_crystallographic_chemical_component",
                "evidence_level": "E4_CURATED_EXPERIMENTAL",
                "case_id": "ATX-007",
                "pdb_id": "1KZK",
                "chem_comp_id": "JE2",
                "selection_parent": "MOLDISC-008",
            },
        }
    ]
    candidates.extend(item.to_workflow_candidate() for item in analogs)

    model = predictor or FrozenESOLSolubilityPredictor.from_public_source(timeout=timeout)
    workflow_report = MolecularDiscoveryWorkflow(solubility_predictor=model).run(candidates)
    coverage = coverage_report or run_public_aqsoldb_coverage(candidates, timeout=timeout)
    profiles = _build_profiles(workflow_report.candidates, coverage.candidates, analogs)
    selection = _select_generated(profiles)

    scientific = {
        "program_id": PROGRAM_ID,
        "config_hash": config_hash,
        "generation_scientific_hash": generation_hash,
        "workflow_scientific_summary_hash": workflow_report.scientific_summary_hash,
        "coverage_scientific_hash": coverage.scientific_hash,
        "profiles": [item.to_dict() for item in profiles],
        "selection": selection.to_dict(),
    }
    result = MOLDISC009Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        generation_scientific_hash=generation_hash,
        workflow_scientific_summary_hash=workflow_report.scientific_summary_hash,
        coverage_scientific_hash=coverage.scientific_hash,
        profiles=profiles,
        selection=selection,
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
                "generation_scientific_hash": generation_hash,
                "workflow_scientific_summary_hash": workflow_report.scientific_summary_hash,
                "coverage_scientific_hash": coverage.scientific_hash,
                "selection": selection.to_dict(),
                "program_scientific_hash": result.program_scientific_hash,
            },
            indent=2, sort_keys=True, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "generation.json").write_text(
        json.dumps(
            {
                "generator_id": GENERATOR_ID,
                "seed_smiles": SEED_SMILES,
                "seed_inchikey": SEED_INCHIKEY,
                "generation_scientific_hash": generation_hash,
                "analogs": [item.to_dict() for item in analogs],
            },
            indent=2, sort_keys=True, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "evidence_profiles.json").write_text(
        json.dumps({"profiles": [item.to_dict() for item in profiles]}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (root / "program_report.md").write_text(_markdown(config, result), encoding="utf-8")
    return result


def _markdown(config: Mapping[str, Any], result: MOLDISC009Result) -> str:
    lines = [
        "# MOLDISC-009 — JE2 single-terminal-methyl deletion series",
        "",
        f"- generation hash: {result.generation_scientific_hash}",
        f"- workflow hash: {result.workflow_scientific_summary_hash}",
        f"- coverage hash: {result.coverage_scientific_hash}",
        f"- program hash: {result.program_scientific_hash}",
        "",
        "## Evidence profiles",
        "",
        "| Variant | Role | Chemistry | ESOL AD | AqSolDB nearest | >=0.4 | exact match | follow-up |",
        "|---|---|---|---|---:|---:|---|---|",
    ]
    for item in sorted(result.profiles, key=lambda row: (0 if row.source_role == "SEED" else 1, row.variant_id)):
        lines.append(
            f"| {item.variant_id} | {item.source_role} | {item.chemistry_status} | {item.esol_status} | "
            f"{item.aqsoldb_nearest_similarity:.6f} | {item.aqsoldb_neighbors_ge_0_4} | "
            f"{'YES' if item.exact_aqsoldb_match else 'NO'} | {'YES' if item.followup_eligible else 'NO'} |"
        )
    lines.extend(["", "## Frozen follow-up selection", ""])
    if result.selection.selected_candidate_id is None:
        lines.append("No generated analog met the frozen measured-source coverage rule.")
    else:
        lines.append(
            f"Selected: {result.selection.selected_variant_id} / {result.selection.selected_candidate_id} "
            f"at AqSolDB nearest similarity {result.selection.selected_nearest_similarity:.6f}."
        )
    lines.extend(["", "## Interpretation boundaries", ""])
    lines.extend(f"- {item}" for item in config["interpretation_boundaries"])
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "COVERAGE_BOUNDARY",
    "GENERATOR_ID",
    "GeneratedJE2Analog",
    "JE2AnalogProfile",
    "JE2AnalogSelection",
    "MOLDISC009Error",
    "MOLDISC009Result",
    "PROGRAM_ID",
    "SEED_CANDIDATE_ID",
    "generate_je2_single_demethyl_series",
    "load_program_config_v9",
    "run_moldisc_009",
]
