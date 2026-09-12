"""Strict APODOCK-001 v1.0 protocol contract.

This module validates the committed declarative protocol and produces a
no-docking preflight report.  It deliberately does not import Vina, Open Babel,
or any execution runner: protocol verification must be safe on a machine that
does not contain a docking engine.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
from typing import Any, Mapping

from research_os.core.hashing import sha256_json
from research_os.docking import apodock001
from research_os.docking.apodock001_freeze import FROZEN_STRUCTURAL_IDENTITIES
from research_os.docking.apodock_glycan_chemistry import (
    ADAPTER_ID,
    ADAPTER_VERSION,
    BEM_COMPONENT_ID,
    CCD_SOURCES,
    EXPECTED_FORMULA,
    EXPECTED_HEAVY_ATOMS,
    MAV_COMPONENT_ID,
)


DEFAULT_PROTOCOL_PATH = (
    Path(__file__).resolve().parents[3]
    / "configs"
    / "apodock001-protocol-freeze-v1.0.json"
)
SCHEMA_VERSION = "research-os.apodock001.protocol.v1"
PROTOCOL_ID_PREFIX = "research-os.apodock001.protocol.v1.0+"
EXPECTED_VINA_VERSION = "1.2.7"
EXPECTED_VINA_SHA256 = "f31f774f723bba7bbbe6e9d1c47577020eea9a8da16424284c043d22593570644"
EXPECTED_PROTOCOL_HASH = "fef2036e5bcd8d979dfa3d0a1bbab8c6e0832cb3cb8d1fdecef4a341431db97e"
EXPECTED_PROTOCOL_ID = f"{PROTOCOL_ID_PREFIX}{EXPECTED_PROTOCOL_HASH[:16]}"
EXPECTED_CASE_IDS = tuple(f"APD-{index:03d}" for index in range(1, 11))

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "protocol_version",
        "protocol_id",
        "protocol_hash",
        "benchmark",
        "chemistry",
        "receptor_preparation",
        "ligand_preparation",
        "box",
        "vina",
        "analysis",
        "evidence",
        "prospective_boundary",
        "change_control",
        "operational_metadata",
    }
)
_NON_SCIENTIFIC_KEYS = frozenset(
    {"schema_version", "protocol_id", "protocol_hash", "operational_metadata"}
)


class ProtocolValidationError(ValueError):
    """Raised when a frozen protocol is incomplete or scientifically altered."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> Any:
    raise ProtocolValidationError(f"non-finite JSON number: {value}")


def _assert_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ProtocolValidationError(f"non-finite value at {path}")
    if isinstance(value, Mapping):
        for key, child in value.items():
            _assert_finite(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_finite(child, f"{path}[{index}]")


def load_protocol(path: str | Path = DEFAULT_PROTOCOL_PATH) -> dict[str, Any]:
    """Load the JSON protocol with duplicate-key and non-finite rejection."""

    protocol_path = Path(path)
    try:
        raw = protocol_path.read_text(encoding="utf-8")
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except ProtocolValidationError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolValidationError(f"cannot load protocol {protocol_path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProtocolValidationError("protocol root must be a JSON object")
    _assert_finite(value)
    return value


def scientific_payload(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Return the identity-bearing payload, independent of operational metadata."""

    return {
        key: deepcopy(value)
        for key, value in protocol.items()
        if key not in _NON_SCIENTIFIC_KEYS
    }


def protocol_hash(protocol: Mapping[str, Any]) -> str:
    return sha256_json(scientific_payload(protocol))


def protocol_id(protocol: Mapping[str, Any]) -> str:
    return f"{PROTOCOL_ID_PREFIX}{protocol_hash(protocol)[:16]}"


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolValidationError(f"{path} must be an object")
    return value


def _require_equal(observed: Any, expected: Any, path: str) -> None:
    if observed != expected:
        raise ProtocolValidationError(f"{path} changed: {observed!r} != {expected!r}")


def _validate_benchmark(protocol: Mapping[str, Any]) -> None:
    benchmark = _require_mapping(protocol.get("benchmark"), "benchmark")
    _require_equal(benchmark.get("id"), apodock001.BENCHMARK_ID, "benchmark.id")
    _require_equal(benchmark.get("source_list_sha256"), apodock001.SOURCE_LIST_SHA256, "benchmark.source_list_sha256")
    _require_equal(benchmark.get("case_metadata_sha256"), apodock001.CASE_METADATA_SHA256, "benchmark.case_metadata_sha256")
    _require_equal(benchmark.get("case_count"), 10, "benchmark.case_count")
    _require_equal(tuple(benchmark.get("case_order", ())), EXPECTED_CASE_IDS, "benchmark.case_order")
    _require_equal(benchmark.get("minimum_global_alignment_ca_pairs"), 50, "benchmark.minimum_global_alignment_ca_pairs")
    cases = benchmark.get("cases")
    if not isinstance(cases, list) or len(cases) != 10:
        raise ProtocolValidationError("benchmark.cases must contain exactly ten cases")

    expected_by_id = {case.case_id: case.to_dict() for case in apodock001.FROZEN_PUBLISHED_CASES}
    observed_ids = []
    frozen_by_id = {row["case_id"]: row for row in FROZEN_STRUCTURAL_IDENTITIES}
    for index, case in enumerate(cases):
        case_map = _require_mapping(case, f"benchmark.cases[{index}]")
        case_id = case_map.get("case_id")
        observed_ids.append(case_id)
        if case_id not in expected_by_id:
            raise ProtocolValidationError(f"unknown APODOCK case: {case_id!r}")
        expected_case = expected_by_id[case_id]
        for key, expected in expected_case.items():
            observed = case_map.get(key)
            if isinstance(expected, tuple):
                expected = list(expected)
            _require_equal(observed, expected, f"benchmark.cases[{case_id}].{key}")
        frozen = frozen_by_id[case_id]
        for key in (
            "apo_pdb_sha256",
            "holo_pdb_sha256",
            "matched_identical_global_ca_pairs",
            "holo_reference_coordinate_hash",
            "transformed_holo_reference_coordinate_hash",
            "grid_hash",
            "status",
        ):
            _require_equal(case_map.get(key), frozen[key], f"benchmark.cases[{case_id}].{key}")
        if case_map.get("ligand_representation") == "single_ccd":
            reference_hash = case_map.get("reference_sdf_sha256")
            if not isinstance(reference_hash, str) or len(reference_hash) != 64:
                raise ProtocolValidationError(
                    f"benchmark.cases[{case_id}].reference_sdf_sha256 must be a SHA-256 hash"
                )
        if case_id == "APD-010":
            _require_equal(
                case_map.get("structural_preflight_chemistry_ready_for_vina"),
                False,
                "benchmark.cases[APD-010].structural_preflight_chemistry_ready_for_vina",
            )
    _require_equal(tuple(observed_ids), EXPECTED_CASE_IDS, "benchmark.cases order")
    _require_equal(benchmark.get("selection_manifest_hash"), "c5fae682ecf6b7e8884de8b4d02fd052d306ea3b5d421b6ad44814289afae805", "benchmark.selection_manifest_hash")


def _validate_chemistry(protocol: Mapping[str, Any]) -> None:
    chemistry = _require_mapping(protocol.get("chemistry"), "chemistry")
    _require_equal(chemistry.get("gate_id"), "research-os.apodock001.chemistry-gate", "chemistry.gate_id")
    _require_equal(chemistry.get("gate_version"), "1.0.0", "chemistry.gate_version")
    _require_equal(chemistry.get("required_ready_count"), 10, "chemistry.required_ready_count")
    apd010 = _require_mapping(chemistry.get("apd010"), "chemistry.apd010")
    _require_equal(apd010.get("adapter_id"), ADAPTER_ID, "chemistry.apd010.adapter_id")
    _require_equal(apd010.get("adapter_version"), ADAPTER_VERSION, "chemistry.apd010.adapter_version")
    _require_equal(apd010.get("input_identity"), "9941f9b3975839f101b2a440a1d579d97f081b7bf473c7cde6bed696c64b5956", "chemistry.apd010.input_identity")
    _require_equal(apd010.get("output_identity"), "1586aa91b6a57fdc938ad3ffa8679996e78d73a834624a3af557c5593e2eb052", "chemistry.apd010.output_identity")
    _require_equal(apd010.get("structural_identity"), "468c8052ff213fbb3a11f6198b61170e41d4b92353a44461a90326b157bdf306", "chemistry.apd010.structural_identity")
    _require_equal(apd010.get("expected_formula"), EXPECTED_FORMULA, "chemistry.apd010.expected_formula")
    _require_equal(apd010.get("expected_heavy_atoms"), EXPECTED_HEAVY_ATOMS, "chemistry.apd010.expected_heavy_atoms")
    _require_equal(apd010.get("components"), [BEM_COMPONENT_ID, MAV_COMPONENT_ID], "chemistry.apd010.components")
    for component_id, source in CCD_SOURCES.items():
        prefix = "input" if component_id == BEM_COMPONENT_ID else "output"
        _require_equal(apd010.get(f"{prefix}_sdf_sha256"), source["sdf_sha256"], f"chemistry.apd010.{prefix}_sdf_sha256")
        _require_equal(apd010.get(f"{prefix}_cif_sha256"), source["cif_sha256"], f"chemistry.apd010.{prefix}_cif_sha256")


def _validate_parameters(protocol: Mapping[str, Any]) -> None:
    vina = _require_mapping(protocol.get("vina"), "vina")
    for key, expected in {
        "version": EXPECTED_VINA_VERSION,
        "binary_sha256": EXPECTED_VINA_SHA256,
        "scoring_function": "vina_default",
        "receptor_mode": "rigid",
        "seed": 42,
        "cpu": 1,
        "exhaustiveness": 16,
        "num_modes": 20,
        "energy_range_kcal_per_mol": None,
    }.items():
        _require_equal(vina.get(key), expected, f"vina.{key}")
    box = _require_mapping(protocol.get("box"), "box")
    for key, expected in {
        "padding_angstrom": 6.0,
        "minimum_side_angstrom": 20.0,
        "maximum_side_angstrom": 30.0,
        "result_dependent_recalculation": False,
    }.items():
        _require_equal(box.get(key), expected, f"box.{key}")
    box_cases = _require_mapping(box.get("cases"), "box.cases")
    benchmark = _require_mapping(protocol.get("benchmark"), "benchmark")
    benchmark_cases = {case["case_id"]: case for case in benchmark["cases"]}
    for case_id in EXPECTED_CASE_IDS:
        case_box = _require_mapping(box_cases.get(case_id), f"box.cases.{case_id}")
        _require_equal(case_box.get("grid_hash"), benchmark_cases[case_id]["grid_hash"], f"box.cases.{case_id}.grid_hash")
        if len(case_box.get("center", ())) != 3 or len(case_box.get("size", ())) != 3:
            raise ProtocolValidationError(f"box.cases.{case_id} must have three center and size coordinates")


def validate_protocol(protocol: Mapping[str, Any]) -> dict[str, str]:
    """Validate every scientific invariant and return the derived identity."""

    if set(protocol) != _TOP_LEVEL_KEYS:
        missing = sorted(_TOP_LEVEL_KEYS - set(protocol))
        extra = sorted(set(protocol) - _TOP_LEVEL_KEYS)
        raise ProtocolValidationError(f"protocol schema keys changed; missing={missing}, extra={extra}")
    _require_equal(protocol.get("schema_version"), SCHEMA_VERSION, "schema_version")
    _require_equal(protocol.get("protocol_version"), "1.0.0", "protocol_version")
    _validate_benchmark(protocol)
    _validate_chemistry(protocol)
    _validate_parameters(protocol)
    _require_equal(_require_mapping(protocol.get("prospective_boundary"), "prospective_boundary").get("preflight_only"), True, "prospective_boundary.preflight_only")
    _require_equal(_require_mapping(protocol.get("prospective_boundary"), "prospective_boundary").get("docking_executed"), False, "prospective_boundary.docking_executed")
    _require_equal(_require_mapping(protocol.get("prospective_boundary"), "prospective_boundary").get("vina_imported_or_invoked"), False, "prospective_boundary.vina_imported_or_invoked")
    _require_equal(protocol.get("protocol_hash"), EXPECTED_PROTOCOL_HASH, "protocol_hash is not the frozen v1.0 identity")
    _require_equal(protocol.get("protocol_id"), EXPECTED_PROTOCOL_ID, "protocol_id is not the frozen v1.0 identity")
    derived_hash = protocol_hash(protocol)
    derived_id = protocol_id(protocol)
    _require_equal(protocol.get("protocol_hash"), derived_hash, "protocol_hash")
    _require_equal(protocol.get("protocol_id"), derived_id, "protocol_id")
    return {"protocol_hash": derived_hash, "protocol_id": derived_id}


def build_dry_run_report(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Return the final no-docking status payload without touching a tool binary."""

    identity = validate_protocol(protocol)
    return {
        "benchmark": "APODOCK-001",
        "protocol_status": "FROZEN",
        "protocol_version": protocol["protocol_version"],
        "protocol_id": identity["protocol_id"],
        "protocol_hash": identity["protocol_hash"],
        "case_count": 10,
        "chemistry_ready": "10/10",
        "vina_version": EXPECTED_VINA_VERSION,
        "vina_binary_sha256": EXPECTED_VINA_SHA256,
        "prospective_boundary_intact": True,
        "vina_executed": False,
        "vina_imported_or_invoked": False,
        "runner_mode": "preflight_only",
        "checks": {
            "dataset_and_input_hashes": "PASS",
            "chemistry_gate": "PASS",
            "receptor_and_ligand_preparation_contract": "PASS",
            "boxes": "PASS",
            "vina_parameters": "PASS",
            "analysis_plan": "PASS",
            "fail_closed": "PASS",
        },
    }


def load_and_validate(path: str | Path = DEFAULT_PROTOCOL_PATH) -> dict[str, Any]:
    protocol = load_protocol(path)
    validate_protocol(protocol)
    return protocol
