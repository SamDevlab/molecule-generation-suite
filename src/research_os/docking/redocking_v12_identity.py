from __future__ import annotations

from typing import Any

from research_os.core.hashing import sha256_json


_FLOAT_DIGITS = 12


def _normalize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, _FLOAT_DIGITS)
    if isinstance(value, dict):
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def _selected(mapping: dict[str, Any] | None, *keys: str) -> dict[str, Any]:
    source = mapping or {}
    return {key: source.get(key) for key in keys}


def scientific_payload(report: dict[str, Any]) -> dict[str, Any]:
    """Build the REDOCK-001 v1.2 scientific identity payload.

    Runtime duration, local paths, stdout/stderr and host metadata are deliberately
    excluded. Content hashes, frozen scientific choices, engine versions, observed
    scores/RMSDs and case statuses remain included.
    """

    records: list[dict[str, Any]] = []
    for record in report.get("records", []):
        provenance = record.get("provenance") or {}
        preparation = provenance.get("preparation") or {}
        docking = provenance.get("docking") or {}
        raw_pdb = provenance.get("raw_pdb") or {}
        extraction = provenance.get("extraction") or {}
        reference = provenance.get("reference") or {}
        grid = provenance.get("grid") or {}
        starting = provenance.get("starting_conformer") or {}
        engines = provenance.get("engines") or {}

        prep_identity: dict[str, Any] = {}
        for name in ("receptor", "ligand"):
            item = preparation.get(name) or {}
            prep_identity[name] = _selected(
                item,
                "returncode",
                "engine",
                "engine_version",
                "status",
                "input_sha256",
                "output_sha256",
                "timed_out",
                "protocol_id",
            )

        docking_identity = _selected(
            docking,
            "best_affinity_kcal_mol",
            "returncode",
            "engine",
            "engine_version",
            "status",
            "receptor_sha256",
            "ligand_sha256",
            "output_sha256",
            "log_sha256",
            "grid_hash",
            "target_id",
            "protocol_id",
            "timed_out",
        )

        records.append(
            {
                "case": record.get("case"),
                "result": record.get("result"),
                "provenance": {
                    "protocol_id": provenance.get("protocol_id"),
                    "raw_pdb_sha256": raw_pdb.get("sha256"),
                    "extraction": _selected(
                        extraction,
                        "ligand_auth_seq_id",
                        "ligand_insertion_code",
                        "ligand_heavy_atoms_from_pdb",
                        "receptor_atom_count",
                        "receptor_sha256",
                        "native_ligand_pdb_sha256",
                    ),
                    "reference": _selected(reference, "sha256", "heavy_atoms", "pdb_heavy_atoms"),
                    "grid": grid,
                    "starting_conformer": _selected(
                        starting,
                        "sha256",
                        "uff_optimized",
                        "random_seed",
                        "heavy_atoms",
                    ),
                    "engine_versions": {
                        "openbabel": (engines.get("openbabel") or {}).get("version"),
                        "vina": (engines.get("vina") or {}).get("version"),
                    },
                    "preparation": prep_identity,
                    "docking": docking_identity,
                    "error": provenance.get("error"),
                },
                "poses": record.get("poses") or [],
            }
        )

    payload = {
        "protocol_id": report.get("protocol_id"),
        "symmetry_mapping_max_matches": report.get("symmetry_mapping_max_matches"),
        "frozen_cases": report.get("frozen_cases") or [],
        "records": records,
        "summary": {
            key: value
            for key, value in (report.get("summary") or {}).items()
            if key != "summary_hash"
        },
    }
    return _normalize(payload)


def scientific_result_hash(report: dict[str, Any]) -> str:
    return sha256_json(scientific_payload(report))


def execution_hash(report: dict[str, Any], scientific_hash: str) -> str:
    return sha256_json(
        {
            "scientific_result_hash": scientific_hash,
            "environment": _normalize(report.get("environment") or {}),
        }
    )
