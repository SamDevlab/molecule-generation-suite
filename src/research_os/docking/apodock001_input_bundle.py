"""Offline validation for the immutable APODOCK-001 v1.0.2 input bundle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from research_os.core.hashing import sha256_file, sha256_json


BUNDLE_SCHEMA_VERSION = "research-os.apodock001.input-bundle.v1"
BUNDLE_ID_PREFIX = "research-os.apodock001.input-bundle.v1+"


class FrozenInputBundleError(ValueError):
    """Raised when a frozen bundle is missing, mutated, or incomplete."""


def _safe_logical_name(value: Any) -> str:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise FrozenInputBundleError(f"invalid bundle logical name: {value!r}")
    return Path(value).as_posix()


def _payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key not in {"bundle_id", "bundle_hash"}}


def _expected_bundle_id(bundle_hash: str) -> str:
    return f"{BUNDLE_ID_PREFIX}{bundle_hash[:16]}"


def load_bundle_manifest(bundle_root: str | Path) -> dict[str, Any]:
    root = Path(bundle_root)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FrozenInputBundleError(f"frozen input bundle manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FrozenInputBundleError(f"cannot load frozen input bundle manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise FrozenInputBundleError("frozen input bundle manifest must be an object")
    if manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise FrozenInputBundleError("frozen input bundle schema changed")
    declared_hash = manifest.get("bundle_hash")
    if not isinstance(declared_hash, str) or sha256_json(_payload(manifest)) != declared_hash:
        raise FrozenInputBundleError("frozen input bundle hash mismatch")
    if manifest.get("bundle_id") != _expected_bundle_id(declared_hash):
        raise FrozenInputBundleError("frozen input bundle id does not derive from bundle hash")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise FrozenInputBundleError("frozen input bundle file list is empty")
    seen: set[str] = set()
    for record in files:
        if not isinstance(record, dict):
            raise FrozenInputBundleError("frozen input bundle file record is not an object")
        logical_name = _safe_logical_name(record.get("logical_name"))
        if logical_name in seen:
            raise FrozenInputBundleError(f"duplicate frozen input bundle file: {logical_name}")
        seen.add(logical_name)
        expected_hash = record.get("sha256")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64 or expected_hash.lower() != expected_hash:
            raise FrozenInputBundleError(f"invalid frozen input hash for {logical_name}")
        path = root / logical_name
        if not path.is_file() or path.stat().st_size == 0:
            raise FrozenInputBundleError(f"frozen input bundle file is missing: {path}")
        if sha256_file(path) != expected_hash:
            raise FrozenInputBundleError(f"frozen input bundle file hash mismatch: {logical_name}")
    return manifest


def verify_frozen_input_bundle(
    protocol: Mapping[str, Any],
    bundle_root: str | Path,
) -> dict[str, Any]:
    """Verify all v1.0.2 bytes and their relationship to the protocol offline."""

    declaration = protocol.get("input_bundle")
    if not isinstance(declaration, Mapping):
        raise FrozenInputBundleError("protocol does not declare an immutable input bundle")
    manifest = load_bundle_manifest(bundle_root)
    for key in ("schema_version", "bundle_id", "bundle_hash"):
        if declaration.get(key) != manifest.get("bundle_id" if key == "bundle_id" else key):
            raise FrozenInputBundleError(f"protocol input bundle {key} differs from local manifest")

    by_name = {record["logical_name"]: record for record in manifest["files"]}
    benchmark = protocol.get("benchmark")
    if not isinstance(benchmark, Mapping):
        raise FrozenInputBundleError("protocol benchmark is missing")
    case_ids = tuple(benchmark.get("case_order", ()))
    if case_ids != tuple(f"APD-{index:03d}" for index in range(1, 11)):
        raise FrozenInputBundleError("bundle validation requires the frozen ten-case order")
    expected_names = {
        "apd010/BEM_ideal.sdf",
        "apd010/BEM.cif",
        "apd010/MAV_ideal.sdf",
        "apd010/MAV.cif",
        "apd010/chemistry-gate.json",
    }
    for case in benchmark["cases"]:
        case_id = case["case_id"]
        for pdb_key in ("apo_pdb_id", "holo_pdb_id"):
            logical_name = f"pdb/{case[pdb_key]}.pdb"
            expected_names.add(logical_name)
            if logical_name not in by_name:
                raise FrozenInputBundleError(f"missing {case_id} PDB from frozen input bundle: {logical_name}")
            expected = case["apo_pdb_sha256" if pdb_key == "apo_pdb_id" else "holo_pdb_sha256"]
            if by_name[logical_name]["sha256"] != expected:
                raise FrozenInputBundleError(f"{case_id} {pdb_key} hash differs from protocol")
        if case_id != "APD-010":
            logical_name = f"reference-sdf/{case['reference_filename']}"
            expected_names.add(logical_name)
            if logical_name not in by_name:
                raise FrozenInputBundleError(f"missing {case_id} reference SDF from frozen input bundle")
            if by_name[logical_name]["sha256"] != case["reference_sdf_sha256"]:
                raise FrozenInputBundleError(f"{case_id} reference SDF hash differs from protocol")

    required_apd010 = {
        "apd010/BEM_ideal.sdf",
        "apd010/BEM.cif",
        "apd010/MAV_ideal.sdf",
        "apd010/MAV.cif",
        "apd010/chemistry-gate.json",
    }
    missing = sorted(required_apd010 - set(by_name))
    if missing:
        raise FrozenInputBundleError(f"APD-010 frozen source artifacts are missing: {missing}")
    unexpected = sorted(set(by_name) - expected_names)
    if unexpected:
        raise FrozenInputBundleError(f"unexpected files in frozen input bundle: {unexpected}")
    return manifest
