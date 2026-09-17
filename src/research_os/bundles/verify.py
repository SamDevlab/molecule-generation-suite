from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any

from research_os.core.hashing import sha256_file, sha256_json


class BundleVerificationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class BundleGate:
    rule_id: str
    status: BundleVerificationStatus
    reason: str
    diagnostics: dict[str, Any] | None = None


@dataclass(frozen=True)
class BundleVerificationResult:
    status: BundleVerificationStatus
    gates: tuple[BundleGate, ...]
    bundle_hash: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == BundleVerificationStatus.PASS

    @property
    def first_loss(self) -> BundleGate | None:
        return next((gate for gate in self.gates if gate.status != BundleVerificationStatus.PASS), None)


def verify_bundle(root: str | Path) -> BundleVerificationResult:
    target = Path(root)
    gates: list[BundleGate] = []
    required = ["manifest.json", "environment.json", "inputs.json", "config.json", "datasets/manifests.json", "provenance/sources.json", "steps/steps.json", "evidence/evidence.json", "claims/claims.json", "artifacts/index.json", "first_loss.json", "summary.json", "integrity.json", "bundle.json", "seal.json"]
    missing = [name for name in required if not (target / name).is_file()]
    if missing:
        return BundleVerificationResult(BundleVerificationStatus.FAIL, (BundleGate("BUNDLE-MANIFEST-001", BundleVerificationStatus.FAIL, "required bundle files are missing", {"missing": missing}),))
    gates.append(BundleGate("BUNDLE-MANIFEST-001", BundleVerificationStatus.PASS, "required bundle files are present"))
    try:
        manifest = _read(target / "manifest.json")
        integrity = _read(target / "integrity.json")
        bundle = _read(target / "bundle.json")
        seal = _read(target / "seal.json")
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        return BundleVerificationResult(BundleVerificationStatus.FAIL, tuple(gates + [BundleGate("BUNDLE-MANIFEST-001", BundleVerificationStatus.FAIL, "bundle JSON cannot be read", {"error_type": type(exc).__name__, "error": str(exc)})]))

    expected_files = integrity.get("files")
    if not isinstance(expected_files, dict):
        gates.append(BundleGate("BUNDLE-HASH-001", BundleVerificationStatus.FAIL, "integrity file has no file hash map"))
    else:
        mismatches = []
        ignored = {"integrity.json", "bundle.json", "seal.json"}
        actual_payload = {str(path.relative_to(target)).replace("\\", "/") for path in target.rglob("*") if path.is_file() and path.name not in ignored}
        unexpected = sorted(actual_payload - set(expected_files))
        for name, expected in expected_files.items():
            path = target / name
            if not path.is_file() or sha256_file(path) != expected:
                mismatches.append(name)
        recomputed = sha256_json(expected_files)
        if mismatches or unexpected or recomputed != bundle.get("bundle_hash") or recomputed != integrity.get("bundle_hash"):
            gates.append(BundleGate("BUNDLE-HASH-001", BundleVerificationStatus.FAIL, "one or more bundle hashes do not match", {"mismatches": mismatches, "unexpected_files": unexpected, "expected_bundle_hash": bundle.get("bundle_hash"), "actual_bundle_hash": recomputed}))
        else:
            gates.append(BundleGate("BUNDLE-HASH-001", BundleVerificationStatus.PASS, "payload hashes match the sealed integrity map"))

    env = _read(target / "environment.json")
    if env.get("environment_hash"):
        logical = dict(env)
        logical.pop("environment_hash", None)
        # EnvironmentManifest intentionally excludes volatile identity/timestamp.
        logical.pop("environment_id", None)
        logical.pop("created_at", None)
        dependencies = logical.get("dependencies", {})
        engines = logical.get("engines", {})
        logical["dependencies"] = {key: dependencies[key] for key in sorted(dependencies)}
        logical["engines"] = {key: engines[key] for key in sorted(engines)}
        # Capture uses the manifest's canonical payload, not this outer JSON shape.
        from research_os.environment.manifest import EnvironmentManifest
        try:
            without_hash = dict(env)
            without_hash.pop("environment_hash", None)
            parsed = EnvironmentManifest.from_mapping(without_hash)
            env_ok = parsed.valid
        except (TypeError, ValueError, KeyError):
            env_ok = False
        gates.append(BundleGate("BUNDLE-ENVIRONMENT-001", BundleVerificationStatus.PASS if env_ok else BundleVerificationStatus.FAIL, "environment hash verified" if env_ok else "environment hash mismatch"))
    else:
        gates.append(BundleGate("BUNDLE-ENVIRONMENT-001", BundleVerificationStatus.INDETERMINATE, "environment manifest has no environment_hash"))

    evidence = _read(target / "evidence/evidence.json")
    evidence_ids = {item.get("evidence_id") for item in evidence if isinstance(item, dict)}
    claims = _read(target / "claims/claims.json")
    missing_evidence = sorted({evidence_id for claim in claims if isinstance(claim, dict) for evidence_id in claim.get("evidence_ids", []) if evidence_id not in evidence_ids})
    gates.append(BundleGate("BUNDLE-EVIDENCE-001", BundleVerificationStatus.FAIL if missing_evidence else BundleVerificationStatus.PASS, "claim evidence references are valid" if not missing_evidence else "claims reference missing evidence", {"missing": missing_evidence} if missing_evidence else None))

    engine_manifest_path = target / "engines" / "manifests.json"
    if engine_manifest_path.is_file():
        try:
            raw_engines = _read(engine_manifest_path)
            from research_os.engines.manifest import EngineManifest
            invalid = [item.get("engine_id", "unknown") for item in raw_engines if isinstance(item, dict) and not EngineManifest.from_mapping(item).valid]
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            invalid = ["engines/manifests.json"]
        gates.append(BundleGate("BUNDLE-ENGINE-001", BundleVerificationStatus.FAIL if invalid else BundleVerificationStatus.PASS, "engine manifests are valid" if not invalid else "engine manifest hash validation failed", {"invalid": invalid} if invalid else None))

    steps = _read(target / "steps/steps.json")
    missing_step_evidence = sorted({evidence_id for step in steps if isinstance(step, dict) for evidence_id in [*step.get("consumed_evidence_ids", []), *step.get("produced_evidence_ids", [])] if evidence_id not in evidence_ids})
    gates.append(BundleGate("BUNDLE-STEP-001", BundleVerificationStatus.FAIL if missing_step_evidence else BundleVerificationStatus.PASS, "step evidence references are valid" if not missing_step_evidence else "steps reference missing evidence", {"missing": missing_step_evidence} if missing_step_evidence else None))

    artifact_index = _read(target / "artifacts/index.json")
    artifact_mismatches = []
    if not isinstance(artifact_index, dict):
        artifact_mismatches.append("artifacts/index.json")
    else:
        for name, item in artifact_index.items():
            if not isinstance(item, dict) or not item.get("path"):
                artifact_mismatches.append(name)
                continue
            artifact = target / str(item["path"])
            if not artifact.is_file() or sha256_file(artifact) != item.get("sha256"):
                artifact_mismatches.append(name)
    gates.append(BundleGate("BUNDLE-ARTIFACT-001", BundleVerificationStatus.FAIL if artifact_mismatches else BundleVerificationStatus.PASS, "artifact index is valid" if not artifact_mismatches else "artifact index references missing or changed artifacts", {"mismatches": artifact_mismatches} if artifact_mismatches else None))

    datasets = _read(target / "datasets/manifests.json")
    dataset_mismatches = []
    dataset_unknown = []
    for item in datasets:
        if not isinstance(item, dict) or not item.get("artifact_path"):
            continue
        path = Path(item["artifact_path"])
        if not path.is_file():
            dataset_unknown.append(str(path))
        elif sha256_file(path) != item.get("sha256"):
            dataset_mismatches.append(str(path))
    if dataset_mismatches:
        gates.append(BundleGate("BUNDLE-DATASET-001", BundleVerificationStatus.FAIL, "dataset artifact hash mismatch", {"mismatches": dataset_mismatches}))
    elif dataset_unknown:
        gates.append(BundleGate("BUNDLE-DATASET-001", BundleVerificationStatus.INDETERMINATE, "dataset artifact could not be located for verification", {"missing": dataset_unknown}))
    else:
        gates.append(BundleGate("BUNDLE-DATASET-001", BundleVerificationStatus.PASS, "dataset hashes verified or no external dataset artifacts were declared"))

    first_loss = _read(target / "first_loss.json")
    expected_loss = _manifest_first_loss(manifest)
    loss_ok = _loss_key(first_loss) == _loss_key(expected_loss)
    gates.append(BundleGate("BUNDLE-FIRST-LOSS-001", BundleVerificationStatus.PASS if loss_ok else BundleVerificationStatus.FAIL, "FIRST_LOSS is consistent with the manifest" if loss_ok else "FIRST_LOSS does not match the manifest"))

    seal_payload = {"bundle_hash": seal.get("bundle_hash"), "bundle_manifest_sha256": seal.get("bundle_manifest_sha256"), "integrity_sha256": seal.get("integrity_sha256")}
    seal_ok = bool(seal.get("sealed")) and seal.get("bundle_hash") == bundle.get("bundle_hash") and seal.get("bundle_manifest_sha256") == sha256_file(target / "bundle.json") and seal.get("integrity_sha256") == sha256_file(target / "integrity.json") and seal.get("seal_hash") == sha256_json(seal_payload)
    gates.append(BundleGate("BUNDLE-SEAL-001", BundleVerificationStatus.PASS if seal_ok else BundleVerificationStatus.FAIL, "bundle seal integrity verified" if seal_ok else "bundle seal integrity failed"))
    status = BundleVerificationStatus.FAIL if any(gate.status == BundleVerificationStatus.FAIL for gate in gates) else BundleVerificationStatus.INDETERMINATE if any(gate.status == BundleVerificationStatus.INDETERMINATE for gate in gates) else BundleVerificationStatus.PASS
    return BundleVerificationResult(status, tuple(gates), bundle.get("bundle_hash"))


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_first_loss(manifest: dict[str, Any]) -> Any:
    if manifest.get("first_loss") is not None:
        return manifest["first_loss"]
    for step in manifest.get("steps", {}).values() if isinstance(manifest.get("steps"), dict) else ():
        if isinstance(step, dict) and step.get("first_loss") is not None:
            return step["first_loss"]
    return None


def _loss_key(value: Any) -> tuple[Any, Any, Any]:
    if not isinstance(value, dict):
        return (None, None, None)
    return value.get("gate_id"), value.get("rule_id"), value.get("status")
