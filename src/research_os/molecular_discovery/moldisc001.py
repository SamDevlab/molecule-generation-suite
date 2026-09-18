"""MOLDISC-001: real, bounded Molecular Discovery program around PDB 1T40 / ID5."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from research_os.core.hashing import sha256_json
from research_os.molecular_discovery.generation import GenerationReport, generate_halogen_analogs
from research_os.molecular_discovery.solubility import FrozenESOLSolubilityPredictor
from research_os.molecular_discovery.workflow import MolecularDiscoveryReport, MolecularDiscoveryWorkflow


PROGRAM_ID = "MOLDISC-001"


class MolecularDiscoveryProgramError(RuntimeError):
    """Fail-closed error for program identity drift or invalid program inputs."""


@dataclass(frozen=True)
class MOLDISC001Result:
    program_id: str
    config_hash: str
    generation: GenerationReport
    discovery_report: MolecularDiscoveryReport
    candidate_count: int
    seed_candidate_id: str
    program_scientific_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "config_hash": self.config_hash,
            "generation": self.generation.to_dict(),
            "discovery_report": self.discovery_report.to_dict(),
            "candidate_count": self.candidate_count,
            "seed_candidate_id": self.seed_candidate_id,
            "program_scientific_hash": self.program_scientific_hash,
        }


def load_program_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("program_id") != PROGRAM_ID:
        raise MolecularDiscoveryProgramError(
            f"expected program_id {PROGRAM_ID}, got {config.get('program_id')!r}"
        )
    if config.get("program_version") != "1.0":
        raise MolecularDiscoveryProgramError("MOLDISC-001 v1 requires program_version 1.0")
    target = config.get("target") or {}
    seed = config.get("seed") or {}
    generation = config.get("generation") or {}
    if target.get("pdb_id") != "1T40":
        raise MolecularDiscoveryProgramError("MOLDISC-001 target identity drifted from PDB 1T40")
    if seed.get("pdb_chem_comp_id") != "ID5":
        raise MolecularDiscoveryProgramError("MOLDISC-001 seed identity drifted from PDB chemical component ID5")
    if generation.get("generator_id") != "research-os.molecular-discovery.halogen-single-substitution.v1":
        raise MolecularDiscoveryProgramError("MOLDISC-001 generator identity drifted")
    return config


def _verify_seed(config: Mapping[str, Any]) -> tuple[str, str]:
    try:
        from rdkit import Chem
        from rdkit.Chem import inchi
    except ImportError as exc:
        raise MolecularDiscoveryProgramError(
            "MOLDISC-001 requires RDKit; install the 'discovery' extra"
        ) from exc

    seed = config["seed"]
    molecule = Chem.MolFromSmiles(str(seed["smiles"]))
    if molecule is None:
        raise MolecularDiscoveryProgramError("MOLDISC-001 frozen seed SMILES is invalid")
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    observed_inchikey = inchi.MolToInchiKey(molecule)
    if observed_inchikey != seed["inchi_key"]:
        raise MolecularDiscoveryProgramError(
            f"MOLDISC-001 seed InChIKey drifted: expected {seed['inchi_key']}, got {observed_inchikey}"
        )
    return canonical, observed_inchikey


def _seed_candidate(config: Mapping[str, Any], canonical_smiles: str) -> dict[str, Any]:
    seed = config["seed"]
    return {
        "id": f"{PROGRAM_ID}-SEED-{seed['seed_id']}",
        "name": seed["name"],
        "smiles": canonical_smiles,
        "origin": {
            "source_type": seed["source_type"],
            "evidence_level": seed["source_evidence_level"],
            "source_url": seed["source_url"],
            "pdb_chem_comp_id": seed["pdb_chem_comp_id"],
            "inchi_key": seed["inchi_key"],
            "parent_program_id": PROGRAM_ID,
        },
    }


def _program_hash_payload(
    *,
    config_hash: str,
    generation: GenerationReport,
    discovery_report: MolecularDiscoveryReport,
    target: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "program_id": PROGRAM_ID,
        "config_hash": config_hash,
        "target": {
            "pdb_id": target["pdb_id"],
            "validated_parent_case": target["validated_parent_case"],
            "future_analog_docking_context": target["future_analog_docking_context"],
            "docking_execution_in_program_v1": target["docking_execution_in_program_v1"],
        },
        "generation_scientific_hash": generation.scientific_hash,
        "discovery_scientific_summary_hash": discovery_report.scientific_summary_hash,
    }


def run_moldisc_001(
    *,
    config_path: str | Path,
    output_root: str | Path,
    predictor: FrozenESOLSolubilityPredictor,
) -> MOLDISC001Result:
    """Execute the frozen MOLDISC-001 protocol.

    The protocol does not use solubility or docking outputs to decide which
    analogs are generated. Candidate generation is therefore frozen upstream of
    downstream model observations.
    """
    config = load_program_config(config_path)
    config_hash = sha256_json(config)
    canonical_seed, _ = _verify_seed(config)
    seed = config["seed"]
    generation_config = config["generation"]

    generation = generate_halogen_analogs(
        canonical_seed,
        seed_id=f"{PROGRAM_ID}-{seed['seed_id']}",
        max_candidates=int(generation_config["max_candidates"]),
    )
    candidates = []
    if bool(config["triage"].get("include_seed", True)):
        candidates.append(_seed_candidate(config, canonical_seed))
    candidates.extend(candidate.to_workflow_candidate() for candidate in generation.candidates)

    workflow = MolecularDiscoveryWorkflow(solubility_predictor=predictor)
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=False)
    discovery_report = workflow.run_to_directory(candidates, root / "workflow")

    program_hash = sha256_json(
        _program_hash_payload(
            config_hash=config_hash,
            generation=generation,
            discovery_report=discovery_report,
            target=config["target"],
        )
    )
    result = MOLDISC001Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        generation=generation,
        discovery_report=discovery_report,
        candidate_count=len(candidates),
        seed_candidate_id=f"{PROGRAM_ID}-SEED-{seed['seed_id']}",
        program_scientific_hash=program_hash,
    )

    (root / "program_manifest.json").write_text(
        json.dumps(
            {
                "program_id": PROGRAM_ID,
                "program_version": config["program_version"],
                "config_hash": config_hash,
                "program_scientific_hash": program_hash,
                "candidate_count": len(candidates),
                "target": config["target"],
                "seed": config["seed"],
                "generation_scientific_hash": generation.scientific_hash,
                "workflow_scientific_summary_hash": discovery_report.scientific_summary_hash,
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "generation.json").write_text(
        json.dumps(generation.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "program_report.md").write_text(
        _markdown(config, result),
        encoding="utf-8",
    )
    return result


def _markdown(config: Mapping[str, Any], result: MOLDISC001Result) -> str:
    discovery = result.discovery_report
    groups: dict[str, int] = {}
    for candidate in discovery.candidates:
        groups[candidate.priority_group] = groups.get(candidate.priority_group, 0) + 1
    lines = [
        "# MOLDISC-001 — ID5 halogen-neighborhood solubility triage",
        "",
        f"- Target: {config['target']['name']} / PDB {config['target']['pdb_id']}",
        f"- Seed: {config['seed']['seed_id']} ({config['seed']['name']})",
        f"- Total candidates: {result.candidate_count}",
        f"- Generated analogs: {result.generation.candidate_count}",
        f"- Program scientific hash: {result.program_scientific_hash}",
        "",
        "## Triage counts",
        "",
    ]
    for group in sorted(groups):
        lines.append(f"- {group}: {groups[group]}")
    lines.extend(
        [
            "",
            "## Docking boundary",
            "",
            "MOLDISC-001 v1 does not automatically dock generated analogs. If docking is later executed against the 1T40 holo receptor, generated analogs are non-cognate ligands and the run must declare NON_COGNATE_HOLO_CROSSDOCKING with the partially validated capability boundary.",
            "",
            "## Interpretation boundaries",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in config["interpretation_boundaries"])
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "MOLDISC001Result",
    "MolecularDiscoveryProgramError",
    "PROGRAM_ID",
    "load_program_config",
    "run_moldisc_001",
]
