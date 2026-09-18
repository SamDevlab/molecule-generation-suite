"""MOLDISC-002: AqSolDB structural coverage of the frozen MOLDISC-001 neighborhood."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from research_os.core.hashing import sha256_json
from research_os.molecular_discovery.aqsoldb_coverage import (
    AqSolDBCoverageReport,
    run_public_aqsoldb_coverage,
)
from research_os.molecular_discovery.generation import generate_halogen_analogs
from research_os.molecular_discovery.moldisc001 import _verify_seed, load_program_config


PROGRAM_ID = "MOLDISC-002"


class MOLDISC002Error(RuntimeError):
    """Fail-closed error for MOLDISC-002 protocol or parent identity drift."""


@dataclass(frozen=True)
class MOLDISC002Result:
    program_id: str
    config_hash: str
    parent_generation_scientific_hash: str
    coverage: AqSolDBCoverageReport
    program_scientific_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "config_hash": self.config_hash,
            "parent_generation_scientific_hash": self.parent_generation_scientific_hash,
            "coverage": self.coverage.to_dict(),
            "program_scientific_hash": self.program_scientific_hash,
        }


def load_program_config_v2(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("program_id") != PROGRAM_ID:
        raise MOLDISC002Error(
            f"expected program_id {PROGRAM_ID}, got {config.get('program_id')!r}"
        )
    if config.get("program_version") != "1.0":
        raise MOLDISC002Error("MOLDISC-002 requires program_version 1.0")
    parent = config.get("parent_program") or {}
    if parent.get("program_id") != "MOLDISC-001":
        raise MOLDISC002Error("MOLDISC-002 parent program identity drifted")
    source = config.get("source") or {}
    if source.get("source_commit") != "98cdd10a372058743e4f3fb950a1c9974ec9603a":
        raise MOLDISC002Error("MOLDISC-002 AqSolDB source commit drifted")
    protocol = config.get("coverage_protocol") or {}
    if protocol.get("training_or_fitting") is not False:
        raise MOLDISC002Error("MOLDISC-002 must remain a no-training coverage study")
    return config


def _parent_candidates(config: Mapping[str, Any], config_path: str | Path) -> tuple[list[dict[str, Any]], str]:
    program_root = Path(config_path).resolve().parents[2]
    parent_rel = Path(str(config["parent_program"]["config_path"]))
    parent_path = program_root / parent_rel
    parent_config = load_program_config(parent_path)

    seed = parent_config["seed"]
    canonical_seed, _ = _verify_seed(parent_config)
    generation = generate_halogen_analogs(
        canonical_seed,
        seed_id=f"MOLDISC-001-{seed['seed_id']}",
        max_candidates=int(parent_config["generation"]["max_candidates"]),
    )
    expected_hash = str(config["parent_program"]["parent_generation_scientific_hash"])
    if generation.scientific_hash != expected_hash:
        raise MOLDISC002Error(
            "MOLDISC-001 generation identity drifted; refusing to change candidates in MOLDISC-002"
        )

    candidates: list[dict[str, Any]] = [
        {
            "id": f"MOLDISC-001-SEED-{seed['seed_id']}",
            "name": seed["name"],
            "smiles": canonical_seed,
            "origin": {
                "source_type": seed["source_type"],
                "evidence_level": seed["source_evidence_level"],
                "pdb_chem_comp_id": seed["pdb_chem_comp_id"],
            },
        }
    ]
    candidates.extend(item.to_workflow_candidate() for item in generation.candidates)
    expected_count = int(config["parent_program"]["candidate_count"])
    if len(candidates) != expected_count:
        raise MOLDISC002Error(
            f"MOLDISC-002 expected {expected_count} frozen candidates, got {len(candidates)}"
        )
    return candidates, generation.scientific_hash


def run_moldisc_002(
    *,
    config_path: str | Path,
    output_root: str | Path,
    timeout: float = 60.0,
) -> MOLDISC002Result:
    config = load_program_config_v2(config_path)
    config_hash = sha256_json(config)
    candidates, parent_generation_hash = _parent_candidates(config, config_path)

    coverage = run_public_aqsoldb_coverage(candidates, timeout=timeout)
    if coverage.candidate_count != int(config["parent_program"]["candidate_count"]):
        raise MOLDISC002Error("AqSolDB coverage did not evaluate the full frozen candidate set")

    program_hash = sha256_json(
        {
            "program_id": PROGRAM_ID,
            "config_hash": config_hash,
            "parent_generation_scientific_hash": parent_generation_hash,
            "coverage_scientific_hash": coverage.scientific_hash,
        }
    )
    result = MOLDISC002Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        parent_generation_scientific_hash=parent_generation_hash,
        coverage=coverage,
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
                "parent_generation_scientific_hash": parent_generation_hash,
                "coverage_scientific_hash": coverage.scientific_hash,
                "program_scientific_hash": program_hash,
                "candidate_count": coverage.candidate_count,
                "source": config["source"],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "coverage.json").write_text(
        json.dumps(coverage.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "program_report.md").write_text(
        _markdown(config, result),
        encoding="utf-8",
    )
    return result


def _markdown(config: Mapping[str, Any], result: MOLDISC002Result) -> str:
    bin_counts: dict[str, int] = {}
    for item in result.coverage.candidates:
        bin_counts[item.similarity_bin] = bin_counts.get(item.similarity_bin, 0) + 1

    lines = [
        "# MOLDISC-002 — AqSolDB structural coverage",
        "",
        f"- Parent generation hash: {result.parent_generation_scientific_hash}",
        f"- AqSolDB unique valid structures: {result.coverage.unique_structure_count}",
        f"- Candidate count: {result.coverage.candidate_count}",
        f"- Coverage scientific hash: {result.coverage.scientific_hash}",
        f"- Program scientific hash: {result.program_scientific_hash}",
        "",
        "## Nearest-neighbor bins",
        "",
    ]
    for label in ("[0.0,0.4)", "[0.4,0.6)", "[0.6,0.8)", "[0.8,1.0]"):
        lines.append(f"- {label}: {bin_counts.get(label, 0)}")
    lines.extend(
        [
            "",
            "## Candidate coverage",
            "",
            "| Candidate | nearest Tanimoto | bin | neighbors >=0.4 | >=0.6 | >=0.8 |",
            "|---|---:|---|---:|---:|---:|",
        ]
    )
    for item in sorted(
        result.coverage.candidates,
        key=lambda row: (-row.nearest_similarity, row.candidate_id),
    ):
        lines.append(
            f"| {item.candidate_id} | {item.nearest_similarity:.4f} | {item.similarity_bin} | "
            f"{item.neighbors_ge_0_4} | {item.neighbors_ge_0_6} | {item.neighbors_ge_0_8} |"
        )
    lines.extend(["", "## Interpretation boundaries", ""])
    lines.extend(f"- {item}" for item in config["interpretation_boundaries"])
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "MOLDISC002Error",
    "MOLDISC002Result",
    "PROGRAM_ID",
    "load_program_config_v2",
    "run_moldisc_002",
]
