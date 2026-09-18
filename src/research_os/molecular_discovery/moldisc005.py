"""MOLDISC-005: bounded NCT N-alkyl generation with dual solubility evidence."""

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
from research_os.molecular_discovery.workflow import (
    CandidateAssessment,
    MolecularDiscoveryWorkflow,
)


PROGRAM_ID = "MOLDISC-005"
GENERATOR_ID = "research-os.molecular-discovery.nct-n-alkyl-series.v1"
COVERAGE_BOUNDARY = 0.4
SEED_SMILES = "CN1CCCC1c1cccnc1"
SEED_INCHIKEY = "SNICXCGAKADSCV-UHFFFAOYSA-N"


class MOLDISC005Error(RuntimeError):
    """Fail-closed error for NCT generation or evidence-profile drift."""


@dataclass(frozen=True)
class GeneratedNCTAnalog:
    variant_id: str
    candidate_id: str
    smiles: str
    inchikey: str
    operation: str
    generator_id: str = GENERATOR_ID
    evidence_level: str = "E0_HEURISTIC"

    @property
    def generation_hash(self) -> str:
        return sha256_json(
            {
                "variant_id": self.variant_id,
                "candidate_id": self.candidate_id,
                "smiles": self.smiles,
                "inchikey": self.inchikey,
                "operation": self.operation,
                "generator_id": self.generator_id,
                "evidence_level": self.evidence_level,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "generation_hash": self.generation_hash,
        }

    def to_workflow_candidate(self) -> dict[str, Any]:
        return {
            "id": self.candidate_id,
            "name": f"NCT {self.variant_id}",
            "smiles": self.smiles,
            "origin": {
                "source_type": "heuristic_generation",
                "evidence_level": self.evidence_level,
                "generator_id": self.generator_id,
                "parent_id": "MOLDISC-005-SEED-NCT",
                "variant_id": self.variant_id,
                "operation": self.operation,
                "generation_hash": self.generation_hash,
            },
        }


@dataclass(frozen=True)
class AnalogEvidenceProfile:
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
    aqsoldb_top_neighbor_smiles: str | None
    aqsoldb_top_neighbor_measured_log_s_mol_l: float | None
    followup_eligible: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GeneratedAnalogSelection:
    selected_candidate_id: str | None
    selected_variant_id: str | None
    selected_nearest_similarity: float | None
    eligible_generated_candidate_ids: tuple[str, ...]
    coverage_boundary: float = COVERAGE_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "eligible_generated_candidate_ids": list(self.eligible_generated_candidate_ids),
        }


@dataclass(frozen=True)
class MOLDISC005Result:
    program_id: str
    config_hash: str
    generation_scientific_hash: str
    workflow_scientific_summary_hash: str
    coverage_scientific_hash: str
    profiles: tuple[AnalogEvidenceProfile, ...]
    selection: GeneratedAnalogSelection
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


def load_program_config_v5(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("program_id") != PROGRAM_ID:
        raise MOLDISC005Error(
            f"expected program_id {PROGRAM_ID}, got {config.get('program_id')!r}"
        )
    if config.get("program_version") != "1.0":
        raise MOLDISC005Error("MOLDISC-005 requires program_version 1.0")
    seed = config.get("seed") or {}
    if seed.get("canonical_smiles") != SEED_SMILES or seed.get("inchikey") != SEED_INCHIKEY:
        raise MOLDISC005Error("MOLDISC-005 NCT seed identity drifted")
    generation = config.get("generation") or {}
    if generation.get("generator_id") != GENERATOR_ID:
        raise MOLDISC005Error("MOLDISC-005 generator identity drifted")
    variants = generation.get("frozen_variants")
    expected_ids = ["N-H", "N-ETHYL", "N-PROPYL"]
    if not isinstance(variants, list) or [item.get("variant_id") for item in variants] != expected_ids:
        raise MOLDISC005Error("MOLDISC-005 frozen N-alkyl variant list drifted")
    if generation.get("use_downstream_metrics_during_generation") is not False:
        raise MOLDISC005Error("MOLDISC-005 generation must remain upstream of evidence outputs")
    evidence = config.get("solubility_evidence") or {}
    if float(evidence.get("aqsoldb_coverage_boundary", -1)) != COVERAGE_BOUNDARY:
        raise MOLDISC005Error("MOLDISC-005 AqSolDB coverage boundary drifted")
    if evidence.get("esol_absolute_ranking_allowed") is not False:
        raise MOLDISC005Error("MOLDISC-005 must not rank analogs by absolute ESOL prediction")
    docking = config.get("docking") or {}
    if docking.get("execute_in_v1") is not False:
        raise MOLDISC005Error("MOLDISC-005 v1 does not execute docking")
    return config


def _rdkit():
    try:
        from rdkit import Chem
        from rdkit.Chem import inchi
    except ImportError as exc:
        raise MOLDISC005Error(
            "MOLDISC-005 requires RDKit; install the 'discovery' extra"
        ) from exc
    return Chem, inchi


def _canonical_identity(molecule: Any) -> tuple[str, str]:
    Chem, inchi = _rdkit()
    Chem.SanitizeMol(molecule)
    smiles = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    return smiles, inchi.MolToInchiKey(molecule)


def _seed_methyl_indices(seed: Any) -> tuple[int, int]:
    Chem, _ = _rdkit()
    matches: list[tuple[int, int]] = []
    for atom in seed.GetAtoms():
        if atom.GetAtomicNum() != 7 or not atom.IsInRing() or atom.GetIsAromatic():
            continue
        for neighbor in atom.GetNeighbors():
            bond = seed.GetBondBetweenAtoms(atom.GetIdx(), neighbor.GetIdx())
            if (
                neighbor.GetAtomicNum() == 6
                and not neighbor.IsInRing()
                and neighbor.GetDegree() == 1
                and bond is not None
                and bond.GetBondType() == Chem.BondType.SINGLE
            ):
                matches.append((atom.GetIdx(), neighbor.GetIdx()))
    if len(matches) != 1:
        raise MOLDISC005Error(
            f"expected exactly one exocyclic N-methyl substituent in NCT, found {len(matches)}"
        )
    return matches[0]


def generate_nct_n_alkyl_series(seed_smiles: str = SEED_SMILES) -> tuple[GeneratedNCTAnalog, ...]:
    """Generate the frozen N-H, N-ethyl and N-propyl variants from NCT."""
    Chem, inchi = _rdkit()
    seed = Chem.MolFromSmiles(seed_smiles)
    if seed is None:
        raise MOLDISC005Error("MOLDISC-005 seed SMILES is invalid")
    seed_canonical = Chem.MolToSmiles(seed, canonical=True, isomericSmiles=True)
    seed_key = inchi.MolToInchiKey(seed)
    if seed_canonical != SEED_SMILES or seed_key != SEED_INCHIKEY:
        raise MOLDISC005Error("active RDKit NCT seed identity differs from the frozen seed")

    nitrogen_idx, methyl_idx = _seed_methyl_indices(seed)
    specs = (
        ("N-H", "remove_seed_N_methyl_substituent", 0),
        ("N-ETHYL", "extend_seed_N_methyl_substituent_by_one_carbon", 1),
        ("N-PROPYL", "extend_seed_N_methyl_substituent_by_two_carbons", 2),
    )
    generated: list[GeneratedNCTAnalog] = []
    seen: set[str] = set()

    for variant_id, operation, extension_count in specs:
        if extension_count == 0:
            editable = Chem.RWMol(seed)
            editable.RemoveAtom(methyl_idx)
            product = editable.GetMol()
        else:
            editable = Chem.RWMol(seed)
            terminal_idx = methyl_idx
            for _ in range(extension_count):
                new_idx = editable.AddAtom(Chem.Atom(6))
                editable.AddBond(terminal_idx, new_idx, Chem.BondType.SINGLE)
                terminal_idx = new_idx
            product = editable.GetMol()

        smiles, inchikey = _canonical_identity(product)
        if smiles == seed_canonical or smiles in seen:
            raise MOLDISC005Error(
                f"frozen variant {variant_id} did not produce a unique non-seed molecule"
            )
        seen.add(smiles)
        suffix = sha256_json(
            {
                "generator_id": GENERATOR_ID,
                "seed_smiles": seed_canonical,
                "variant_id": variant_id,
                "product_smiles": smiles,
            }
        )[:10].upper()
        generated.append(
            GeneratedNCTAnalog(
                variant_id=variant_id,
                candidate_id=f"MOLDISC-005-NCT-{suffix}",
                smiles=smiles,
                inchikey=inchikey,
                operation=operation,
            )
        )
    return tuple(generated)


def _build_profiles(
    assessments: Sequence[CandidateAssessment],
    coverage: Sequence[CandidateCoverage],
    analogs: Sequence[GeneratedNCTAnalog],
) -> tuple[AnalogEvidenceProfile, ...]:
    assessment_by_id = {item.candidate_id: item for item in assessments}
    coverage_by_id = {item.candidate_id: item for item in coverage}
    variant_by_id = {item.candidate_id: item.variant_id for item in analogs}
    expected_ids = {"MOLDISC-005-SEED-NCT", *variant_by_id}
    if set(assessment_by_id) != expected_ids or set(coverage_by_id) != expected_ids:
        raise MOLDISC005Error("workflow/coverage candidate identity sets do not match frozen series")

    profiles: list[AnalogEvidenceProfile] = []
    for candidate_id in sorted(expected_ids):
        assessment = assessment_by_id[candidate_id]
        local = coverage_by_id[candidate_id]
        solubility = assessment.solubility or {}
        top = local.top_neighbors[0] if local.top_neighbors else None
        source_role = "SEED" if candidate_id == "MOLDISC-005-SEED-NCT" else "GENERATED"
        variant_id = "N-METHYL-SEED" if source_role == "SEED" else variant_by_id[candidate_id]
        eligible = (
            source_role == "GENERATED"
            and assessment.chemistry_status == "PASS"
            and local.nearest_similarity >= COVERAGE_BOUNDARY
        )
        profiles.append(
            AnalogEvidenceProfile(
                candidate_id=candidate_id,
                variant_id=variant_id,
                source_role=source_role,
                smiles=assessment.smiles,
                chemistry_status=assessment.chemistry_status,
                esol_status=assessment.solubility_status,
                predicted_log_s_mol_l=(
                    float(solubility["predicted_log_s_mol_l"])
                    if solubility.get("predicted_log_s_mol_l") is not None
                    else None
                ),
                esol_max_training_tanimoto=(
                    float(solubility["max_training_tanimoto"])
                    if solubility.get("max_training_tanimoto") is not None
                    else None
                ),
                aqsoldb_nearest_similarity=local.nearest_similarity,
                aqsoldb_similarity_bin=local.similarity_bin,
                aqsoldb_neighbors_ge_0_4=local.neighbors_ge_0_4,
                aqsoldb_top_neighbor_smiles=(top.canonical_smiles if top else None),
                aqsoldb_top_neighbor_measured_log_s_mol_l=(
                    top.median_measured_log_s_mol_l if top else None
                ),
                followup_eligible=eligible,
            )
        )
    return tuple(profiles)


def _select_generated(profiles: Sequence[AnalogEvidenceProfile]) -> GeneratedAnalogSelection:
    eligible = [
        item
        for item in profiles
        if item.source_role == "GENERATED" and item.followup_eligible
    ]
    eligible.sort(key=lambda item: (-item.aqsoldb_nearest_similarity, item.variant_id))
    if not eligible:
        return GeneratedAnalogSelection(
            selected_candidate_id=None,
            selected_variant_id=None,
            selected_nearest_similarity=None,
            eligible_generated_candidate_ids=(),
        )
    selected = eligible[0]
    return GeneratedAnalogSelection(
        selected_candidate_id=selected.candidate_id,
        selected_variant_id=selected.variant_id,
        selected_nearest_similarity=selected.aqsoldb_nearest_similarity,
        eligible_generated_candidate_ids=tuple(item.candidate_id for item in eligible),
    )


def run_moldisc_005(
    *,
    config_path: str | Path,
    output_root: str | Path,
    predictor: FrozenESOLSolubilityPredictor | None = None,
    coverage_report: AqSolDBCoverageReport | None = None,
    timeout: float = 60.0,
) -> MOLDISC005Result:
    config = load_program_config_v5(config_path)
    config_hash = sha256_json(config)
    analogs = generate_nct_n_alkyl_series()
    generation_hash = sha256_json(
        {
            "generator_id": GENERATOR_ID,
            "seed_smiles": SEED_SMILES,
            "seed_inchikey": SEED_INCHIKEY,
            "analogs": [item.to_dict() for item in analogs],
        }
    )

    candidates: list[dict[str, Any]] = [
        {
            "id": "MOLDISC-005-SEED-NCT",
            "name": "NCT N-methyl measured seed",
            "smiles": SEED_SMILES,
            "origin": {
                "source_type": "RCSB_crystallographic_chemical_component",
                "evidence_level": "E4_CURATED_EXPERIMENTAL",
                "pdb_id": "1P2Y",
                "chem_comp_id": "NCT",
                "measured_anchor_source_id": "E-468",
            },
        }
    ]
    candidates.extend(item.to_workflow_candidate() for item in analogs)

    model = predictor or FrozenESOLSolubilityPredictor.from_public_source(timeout=timeout)
    workflow = MolecularDiscoveryWorkflow(solubility_predictor=model)
    workflow_report = workflow.run(candidates)

    coverage = coverage_report or run_public_aqsoldb_coverage(candidates, timeout=timeout)
    profiles = _build_profiles(workflow_report.candidates, coverage.candidates, analogs)
    selection = _select_generated(profiles)

    program_hash = sha256_json(
        {
            "program_id": PROGRAM_ID,
            "config_hash": config_hash,
            "generation_scientific_hash": generation_hash,
            "workflow_scientific_summary_hash": workflow_report.scientific_summary_hash,
            "coverage_scientific_hash": coverage.scientific_hash,
            "profiles": [item.to_dict() for item in profiles],
            "selection": selection.to_dict(),
        }
    )
    result = MOLDISC005Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        generation_scientific_hash=generation_hash,
        workflow_scientific_summary_hash=workflow_report.scientific_summary_hash,
        coverage_scientific_hash=coverage.scientific_hash,
        profiles=profiles,
        selection=selection,
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
                "generation_scientific_hash": generation_hash,
                "workflow_scientific_summary_hash": workflow_report.scientific_summary_hash,
                "coverage_scientific_hash": coverage.scientific_hash,
                "selection": selection.to_dict(),
                "program_scientific_hash": program_hash,
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
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
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "evidence_profiles.json").write_text(
        json.dumps(
            {"profiles": [item.to_dict() for item in profiles]},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "program_report.md").write_text(
        _markdown(config, result),
        encoding="utf-8",
    )
    return result


def _markdown(config: Mapping[str, Any], result: MOLDISC005Result) -> str:
    lines = [
        "# MOLDISC-005 — NCT N-alkyl series",
        "",
        f"- generation hash: {result.generation_scientific_hash}",
        f"- workflow hash: {result.workflow_scientific_summary_hash}",
        f"- coverage hash: {result.coverage_scientific_hash}",
        f"- program hash: {result.program_scientific_hash}",
        "",
        "## Dual evidence profiles",
        "",
        "| Variant | Role | Chemistry | ESOL AD | predicted logS | AqSolDB nearest | >=0.4 neighbors | follow-up eligible |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for item in sorted(
        result.profiles,
        key=lambda row: (0 if row.source_role == "SEED" else 1, row.variant_id),
    ):
        predicted = "—" if item.predicted_log_s_mol_l is None else f"{item.predicted_log_s_mol_l:.4f}"
        lines.append(
            f"| {item.variant_id} | {item.source_role} | {item.chemistry_status} | "
            f"{item.esol_status} | {predicted} | {item.aqsoldb_nearest_similarity:.4f} | "
            f"{item.aqsoldb_neighbors_ge_0_4} | {'YES' if item.followup_eligible else 'NO'} |"
        )
    lines.extend(["", "## Frozen follow-up selection", ""])
    if result.selection.selected_candidate_id is None:
        lines.append("No generated analog met the predeclared measured-source coverage rule.")
    else:
        lines.append(
            f"Selected generated analog: {result.selection.selected_variant_id} / "
            f"{result.selection.selected_candidate_id} at AqSolDB nearest similarity "
            f"{result.selection.selected_nearest_similarity:.4f}."
        )
    lines.extend(["", "## Interpretation boundaries", ""])
    lines.extend(f"- {item}" for item in config["interpretation_boundaries"])
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "COVERAGE_BOUNDARY",
    "GENERATOR_ID",
    "GeneratedAnalogSelection",
    "GeneratedNCTAnalog",
    "MOLDISC005Error",
    "MOLDISC005Result",
    "PROGRAM_ID",
    "generate_nct_n_alkyl_series",
    "load_program_config_v5",
    "run_moldisc_005",
]
