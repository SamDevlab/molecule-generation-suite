"""MOLDISC-011: bounded second terminal-methyl deletion of DEMETHYL-03."""

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


PROGRAM_ID = "MOLDISC-011"
GENERATOR_ID = "research-os.molecular-discovery.demethyl03-single-terminal-methyl-deletion.v1"
SEED_CANDIDATE_ID = "MOLDISC-009-JE2-5461A4A267"
SEED_SMILES = "Cc1ccccc1CNC(=O)[C@H]1N(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)CSC1(C)C"
SEED_INCHIKEY = "XBNKKAGGYBXOJG-GMQQYTKMSA-N"
PARENT_MOLDISC009_HASH = "75ffaf31d6df6983e7692fca4f0a3fa2277c743dcac2b99cee179c9b39116615"
PARENT_MOLDISC010_HASH = "360ef9eb66981287781a971a7e09aebbe2749be765af5b4c6dcb33e3839eb48b"
COVERAGE_BOUNDARY = 0.4
EXPECTED_TERMINAL_METHYL_SITES = 3
EXPECTED_UNIQUE_PRODUCTS = 2
VARIANT_IDS = ("STEP2-DEMETHYL-01", "STEP2-DEMETHYL-02")
EXPECTED_PRODUCTS = (
    {
        "smiles": "CC1(C)SCN(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)[C@@H]1C(=O)NCc1ccccc1",
        "inchikey": "DRIAWXDDGSORDT-KKUQBAQOSA-N",
    },
    {
        "smiles": "Cc1ccccc1CNC(=O)[C@@H]1C(C)SCN1C(=O)[C@@H](O)[C@H](Cc1ccccc1)NC(=O)c1cccc(O)c1",
        "inchikey": "WKWQZNZXWQKASU-XVJGRJRPSA-N",
    },
)


class MOLDISC011Error(RuntimeError):
    """Fail-closed error for MOLDISC-011 protocol or identity drift."""


@dataclass(frozen=True)
class GeneratedSecondDemethylAnalog:
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
            "name": f"DEMETHYL-03 {self.variant_id}",
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
class SecondDemethylProfile:
    candidate_id: str
    variant_id: str
    source_role: str
    canonical_smiles: str
    inchikey: str
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
    aqsoldb_top_neighbor_observation_count: int | None
    aqsoldb_top_neighbor_measured_log_s_mol_l_median: float | None
    aqsoldb_top_neighbor_measured_log_s_mol_l_min: float | None
    aqsoldb_top_neighbor_measured_log_s_mol_l_max: float | None
    followup_eligible: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SecondDemethylSelection:
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
            "selection_used_esol": False,
            "moldisc010_score_used_for_selection": False,
            "docking_executed": False,
        }


@dataclass(frozen=True)
class MOLDISC011Result:
    program_id: str
    config_hash: str
    generation_scientific_hash: str
    workflow_scientific_summary_hash: str
    coverage_scientific_hash: str
    raw_terminal_methyl_sites: int
    profiles: tuple[SecondDemethylProfile, ...]
    selection: SecondDemethylSelection
    program_scientific_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "config_hash": self.config_hash,
            "generation_scientific_hash": self.generation_scientific_hash,
            "workflow_scientific_summary_hash": self.workflow_scientific_summary_hash,
            "coverage_scientific_hash": self.coverage_scientific_hash,
            "raw_terminal_methyl_sites": self.raw_terminal_methyl_sites,
            "profiles": [item.to_dict() for item in self.profiles],
            "selection": self.selection.to_dict(),
            "program_scientific_hash": self.program_scientific_hash,
        }


def _rdkit():
    try:
        from rdkit import Chem
        from rdkit.Chem import inchi
    except ImportError as exc:
        raise MOLDISC011Error("MOLDISC-011 requires RDKit; install the 'discovery' extra") from exc
    return Chem, inchi


def load_program_config_v11(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != "1.0":
        raise MOLDISC011Error("MOLDISC-011 requires frozen program_id/version 1.0")

    parent = config.get("parent_program") or {}
    if (
        parent.get("program_id") != "MOLDISC-009"
        or parent.get("program_scientific_hash") != PARENT_MOLDISC009_HASH
        or parent.get("selected_variant_id") != "DEMETHYL-03"
        or parent.get("selected_candidate_id") != SEED_CANDIDATE_ID
        or parent.get("selection_used_esol") is not False
    ):
        raise MOLDISC011Error("MOLDISC-011 MOLDISC-009 parent identity drifted")

    moldisc010 = config.get("moldisc010_evidence") or {}
    if (
        moldisc010.get("program_scientific_hash") != PARENT_MOLDISC010_HASH
        or moldisc010.get("technical_status") != "PASS"
        or moldisc010.get("docking_context") != "NON_COGNATE_HOLO_CROSSDOCKING"
        or moldisc010.get("capability") != "PARTIALLY_VALIDATED"
        or moldisc010.get("evidence_level") != "E2_COMPUTATIONAL"
    ):
        raise MOLDISC011Error("MOLDISC-010 parent evidence identity drifted")

    seed = config.get("seed") or {}
    if (
        seed.get("candidate_id") != SEED_CANDIDATE_ID
        or seed.get("canonical_smiles") != SEED_SMILES
        or seed.get("inchikey") != SEED_INCHIKEY
    ):
        raise MOLDISC011Error("MOLDISC-011 DEMETHYL-03 seed identity drifted")

    generation = config.get("generation") or {}
    if (
        generation.get("generator_id") != GENERATOR_ID
        or int(generation.get("expected_seed_terminal_methyl_sites", -1)) != EXPECTED_TERMINAL_METHYL_SITES
        or int(generation.get("expected_unique_generated_candidates", -1)) != EXPECTED_UNIQUE_PRODUCTS
        or tuple(generation.get("variant_ids_in_sorted_product_order") or ()) != VARIANT_IDS
        or generation.get("use_downstream_metrics_during_generation") is not False
    ):
        raise MOLDISC011Error("MOLDISC-011 generation protocol drifted")
    if tuple(item.get("smiles") for item in generation.get("expected_products") or ()) != tuple(
        item["smiles"] for item in EXPECTED_PRODUCTS
    ):
        raise MOLDISC011Error("MOLDISC-011 expected product SMILES drifted")
    if tuple(item.get("inchikey") for item in generation.get("expected_products") or ()) != tuple(
        item["inchikey"] for item in EXPECTED_PRODUCTS
    ):
        raise MOLDISC011Error("MOLDISC-011 expected product InChIKeys drifted")

    evidence = config.get("evidence") or {}
    if abs(float(evidence.get("aqsoldb_coverage_boundary", -1)) - COVERAGE_BOUNDARY) > 1e-12:
        raise MOLDISC011Error("MOLDISC-011 AqSolDB boundary drifted")
    if (
        evidence.get("esol_used_for_selection") is not False
        or evidence.get("moldisc010_score_used_for_generation") is not False
        or evidence.get("moldisc010_score_used_for_selection") is not False
        or evidence.get("docking_executed") is not False
    ):
        raise MOLDISC011Error("MOLDISC-011 evidence boundary drifted")
    return config


def _seed_identity() -> tuple[Any, str, str]:
    Chem, inchi = _rdkit()
    seed = Chem.MolFromSmiles(SEED_SMILES)
    if seed is None:
        raise MOLDISC011Error("frozen DEMETHYL-03 seed SMILES is not parseable")
    canonical = Chem.MolToSmiles(seed, canonical=True, isomericSmiles=True)
    key = inchi.MolToInchiKey(seed)
    if canonical != SEED_SMILES or key != SEED_INCHIKEY:
        raise MOLDISC011Error("active RDKit DEMETHYL-03 identity differs from frozen seed")
    return seed, canonical, key


def _terminal_methyl_indices(seed: Any) -> tuple[int, ...]:
    indices = tuple(
        atom.GetIdx()
        for atom in seed.GetAtoms()
        if atom.GetAtomicNum() == 6 and atom.GetDegree() == 1 and atom.GetTotalNumHs() == 3
    )
    if len(indices) != EXPECTED_TERMINAL_METHYL_SITES:
        raise MOLDISC011Error(
            f"expected {EXPECTED_TERMINAL_METHYL_SITES} terminal methyl sites, found {len(indices)}"
        )
    return indices


def generate_second_demethyl_series() -> tuple[GeneratedSecondDemethylAnalog, ...]:
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
            raise MOLDISC011Error(
                f"terminal-methyl deletion at seed atom {atom_index} did not sanitize"
            ) from exc
        smiles = Chem.MolToSmiles(product, canonical=True, isomericSmiles=True)
        if smiles == canonical_seed:
            raise MOLDISC011Error("terminal-methyl deletion reproduced the DEMETHYL-03 seed")
        entry = by_smiles.setdefault(
            smiles,
            {"inchikey": inchi.MolToInchiKey(product), "atom_indices": []},
        )
        entry["atom_indices"].append(atom_index)

    if len(by_smiles) != EXPECTED_UNIQUE_PRODUCTS:
        raise MOLDISC011Error(
            f"expected {EXPECTED_UNIQUE_PRODUCTS} unique products, found {len(by_smiles)}"
        )
    expected_by_smiles = {item["smiles"]: item["inchikey"] for item in EXPECTED_PRODUCTS}
    if set(by_smiles) != set(expected_by_smiles):
        raise MOLDISC011Error("generated products differ from the frozen expected SMILES")

    analogs = []
    for variant_id, smiles in zip(VARIANT_IDS, sorted(by_smiles), strict=True):
        info = by_smiles[smiles]
        if str(info["inchikey"]) != expected_by_smiles[smiles]:
            raise MOLDISC011Error(f"generated InChIKey drifted for {variant_id}")
        suffix = sha256_json(
            {
                "generator_id": GENERATOR_ID,
                "seed_smiles": canonical_seed,
                "variant_id": variant_id,
                "product_smiles": smiles,
            }
        )[:10].upper()
        analogs.append(
            GeneratedSecondDemethylAnalog(
                variant_id=variant_id,
                candidate_id=f"MOLDISC-011-JE2-{suffix}",
                smiles=smiles,
                inchikey=str(info["inchikey"]),
                removed_seed_atom_indices=tuple(sorted(info["atom_indices"])),
            )
        )
    if sorted(len(item.removed_seed_atom_indices) for item in analogs) != [1, 2]:
        raise MOLDISC011Error("symmetry-equivalent deletion sites did not collapse as expected")
    return tuple(analogs)


def _build_profiles(
    assessments: Sequence[CandidateAssessment],
    coverage: Sequence[CandidateCoverage],
    analogs: Sequence[GeneratedSecondDemethylAnalog],
) -> tuple[SecondDemethylProfile, ...]:
    assessment_by_id = {item.candidate_id: item for item in assessments}
    coverage_by_id = {item.candidate_id: item for item in coverage}
    variant_by_id = {item.candidate_id: item.variant_id for item in analogs}
    expected_ids = {SEED_CANDIDATE_ID, *variant_by_id}
    if set(assessment_by_id) != expected_ids or set(coverage_by_id) != expected_ids:
        raise MOLDISC011Error("workflow/coverage candidate sets do not match the frozen neighborhood")

    profiles: list[SecondDemethylProfile] = []
    for candidate_id in sorted(expected_ids):
        assessment = assessment_by_id[candidate_id]
        local = coverage_by_id[candidate_id]
        if assessment.smiles != local.canonical_smiles:
            raise MOLDISC011Error(f"canonical identity mismatch for {candidate_id}")
        solubility = assessment.solubility or {}
        top = local.top_neighbors[0] if local.top_neighbors else None
        source_role = "SEED" if candidate_id == SEED_CANDIDATE_ID else "GENERATED"
        variant_id = "DEMETHYL-03-SEED" if source_role == "SEED" else variant_by_id[candidate_id]
        exact = bool(
            top is not None
            and top.canonical_smiles == local.canonical_smiles
            and top.inchikey == local.inchikey
        )
        eligible = (
            source_role == "GENERATED"
            and assessment.chemistry_status == "PASS"
            and local.nearest_similarity >= COVERAGE_BOUNDARY
        )
        profiles.append(
            SecondDemethylProfile(
                candidate_id=candidate_id,
                variant_id=variant_id,
                source_role=source_role,
                canonical_smiles=local.canonical_smiles,
                inchikey=local.inchikey,
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
                exact_aqsoldb_match=exact,
                aqsoldb_top_neighbor_smiles=top.canonical_smiles if top else None,
                aqsoldb_top_neighbor_inchikey=top.inchikey if top else None,
                aqsoldb_top_neighbor_observation_count=top.observation_count if top else None,
                aqsoldb_top_neighbor_measured_log_s_mol_l_median=(
                    top.median_measured_log_s_mol_l if top else None
                ),
                aqsoldb_top_neighbor_measured_log_s_mol_l_min=(
                    top.minimum_measured_log_s_mol_l if top else None
                ),
                aqsoldb_top_neighbor_measured_log_s_mol_l_max=(
                    top.maximum_measured_log_s_mol_l if top else None
                ),
                followup_eligible=eligible,
            )
        )
    return tuple(profiles)


def _select_generated(profiles: Sequence[SecondDemethylProfile]) -> SecondDemethylSelection:
    eligible = [
        item for item in profiles
        if item.source_role == "GENERATED" and item.followup_eligible
    ]
    eligible.sort(key=lambda item: (-item.aqsoldb_nearest_similarity, item.variant_id))
    if not eligible:
        return SecondDemethylSelection(None, None, None, ())
    selected = eligible[0]
    return SecondDemethylSelection(
        selected_candidate_id=selected.candidate_id,
        selected_variant_id=selected.variant_id,
        selected_nearest_similarity=selected.aqsoldb_nearest_similarity,
        eligible_generated_candidate_ids=tuple(item.candidate_id for item in eligible),
    )


def run_moldisc_011(
    *,
    config_path: str | Path,
    output_root: str | Path,
    predictor: FrozenESOLSolubilityPredictor | None = None,
    coverage_report: AqSolDBCoverageReport | None = None,
    timeout: float = 60.0,
) -> MOLDISC011Result:
    config = load_program_config_v11(config_path)
    config_hash = sha256_json(config)
    analogs = generate_second_demethyl_series()
    raw_site_count = sum(len(item.removed_seed_atom_indices) for item in analogs)
    if raw_site_count != EXPECTED_TERMINAL_METHYL_SITES:
        raise MOLDISC011Error("raw terminal-methyl site count drifted")
    generation_hash = sha256_json(
        {
            "generator_id": GENERATOR_ID,
            "seed_candidate_id": SEED_CANDIDATE_ID,
            "seed_smiles": SEED_SMILES,
            "seed_inchikey": SEED_INCHIKEY,
            "raw_terminal_methyl_sites": raw_site_count,
            "analogs": [item.to_dict() for item in analogs],
        }
    )

    candidates = [
        {
            "id": SEED_CANDIDATE_ID,
            "name": "MOLDISC-009 selected DEMETHYL-03",
            "smiles": SEED_SMILES,
            "origin": {
                "source_type": "moldisc-009-selected-generated-candidate",
                "evidence_level": "E0_HEURISTIC",
                "parent_id": "MOLDISC-009",
                "variant_id": "DEMETHYL-03",
                "selection_used_esol": False,
            },
        }
    ]
    candidates.extend(item.to_workflow_candidate() for item in analogs)

    model = predictor or FrozenESOLSolubilityPredictor.from_public_source(timeout=timeout)
    workflow_report = MolecularDiscoveryWorkflow(solubility_predictor=model).run(candidates)
    if any(item.docking_status != "NOT_REQUESTED" for item in workflow_report.candidates):
        raise MOLDISC011Error("MOLDISC-011 unexpectedly executed docking")
    coverage = coverage_report or run_public_aqsoldb_coverage(candidates, timeout=timeout)
    profiles = _build_profiles(workflow_report.candidates, coverage.candidates, analogs)
    selection = _select_generated(profiles)

    scientific = {
        "program_id": PROGRAM_ID,
        "config_hash": config_hash,
        "generation_scientific_hash": generation_hash,
        "workflow_scientific_summary_hash": workflow_report.scientific_summary_hash,
        "coverage_scientific_hash": coverage.scientific_hash,
        "raw_terminal_methyl_sites": raw_site_count,
        "profiles": [item.to_dict() for item in profiles],
        "selection": selection.to_dict(),
        "moldisc010_score_used_for_generation": False,
        "moldisc010_score_used_for_selection": False,
        "docking_executed": False,
    }
    result = MOLDISC011Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        generation_scientific_hash=generation_hash,
        workflow_scientific_summary_hash=workflow_report.scientific_summary_hash,
        coverage_scientific_hash=coverage.scientific_hash,
        raw_terminal_methyl_sites=raw_site_count,
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
                "raw_terminal_methyl_sites": raw_site_count,
                "unique_products": len(analogs),
                "selection": selection.to_dict(),
                "moldisc010_score_used_for_generation": False,
                "moldisc010_score_used_for_selection": False,
                "docking_executed": False,
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
                "seed_candidate_id": SEED_CANDIDATE_ID,
                "seed_smiles": SEED_SMILES,
                "seed_inchikey": SEED_INCHIKEY,
                "raw_terminal_methyl_sites": raw_site_count,
                "unique_products": len(analogs),
                "generation_scientific_hash": generation_hash,
                "analogs": [item.to_dict() for item in analogs],
            },
            indent=2, sort_keys=True, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "evidence_profiles.json").write_text(
        json.dumps(
            {
                "profiles": [item.to_dict() for item in profiles],
                "coverage_source": {
                    "source_commit": coverage.source_commit,
                    "source_blob_sha": coverage.source_blob_sha,
                    "parsed_source_hash": coverage.parsed_source_hash,
                },
            },
            indent=2, sort_keys=True, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "program_report.md").write_text(_markdown(config, result), encoding="utf-8")
    return result


def _markdown(config: Mapping[str, Any], result: MOLDISC011Result) -> str:
    lines = [
        "# MOLDISC-011 — DEMETHYL-03 second terminal-methyl deletion series",
        "",
        f"- generation hash: {result.generation_scientific_hash}",
        f"- workflow hash: {result.workflow_scientific_summary_hash}",
        f"- coverage hash: {result.coverage_scientific_hash}",
        f"- program hash: {result.program_scientific_hash}",
        f"- raw terminal-methyl sites: {result.raw_terminal_methyl_sites}",
        "- unique products: 2",
        "- MOLDISC-010 score used for generation/selection: NO/NO",
        "- docking executed: NO",
        "",
        "## Evidence profiles",
        "",
        "| Variant | Role | Chemistry | ESOL AD | AqSolDB nearest | >=0.4 | Exact canonical match | Follow-up |",
        "|---|---|---|---|---:|---:|---|---|",
    ]
    for item in sorted(result.profiles, key=lambda row: (0 if row.source_role == "SEED" else 1, row.variant_id)):
        lines.append(
            f"| {item.variant_id} | {item.source_role} | {item.chemistry_status} | {item.esol_status} | "
            f"{item.aqsoldb_nearest_similarity:.6f} | {item.aqsoldb_neighbors_ge_0_4} | "
            f"{'YES' if item.exact_aqsoldb_match else 'NO'} | {'YES' if item.followup_eligible else 'NO'} |"
        )
    lines.extend(["", "## Frozen selection", ""])
    if result.selection.selected_candidate_id is None:
        lines.append("No generated product met the frozen chemistry + AqSolDB >= 0.4 rule.")
    else:
        lines.append(
            f"Selected: {result.selection.selected_variant_id} / {result.selection.selected_candidate_id} "
            f"at AqSolDB nearest Tanimoto {result.selection.selected_nearest_similarity:.6f}."
        )
    lines.extend(
        [
            "",
            "AqSolDB neighbor measurements are structural context only and are not transferred to candidates unless the top neighbor is an exact canonical structure match.",
            "Frozen ESOL numeric outputs remain model outputs; OUT_OF_DOMAIN values are unsupported extrapolative outputs and are not treated as reliable solubility measurements.",
            "MOLDISC-011 makes no docking, affinity, potency, efficacy, safety, ADMET, or biological conclusion.",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "COVERAGE_BOUNDARY",
    "EXPECTED_PRODUCTS",
    "EXPECTED_TERMINAL_METHYL_SITES",
    "EXPECTED_UNIQUE_PRODUCTS",
    "GENERATOR_ID",
    "MOLDISC011Error",
    "MOLDISC011Result",
    "PARENT_MOLDISC009_HASH",
    "PARENT_MOLDISC010_HASH",
    "SEED_CANDIDATE_ID",
    "SEED_INCHIKEY",
    "SEED_SMILES",
    "SecondDemethylProfile",
    "SecondDemethylSelection",
    "VARIANT_IDS",
    "generate_second_demethyl_series",
    "load_program_config_v11",
    "run_moldisc_011",
]
