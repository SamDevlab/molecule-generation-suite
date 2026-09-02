from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping
import uuid

from research_os.core.hashing import sha256_file, sha256_json
from research_os.core.types import Evidence, GateResult, GateStatus, RunManifest


class ResearchBundleError(RuntimeError):
    pass


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return _jsonable(vars(value))
    return value


def _run_payload(run: Any) -> dict[str, Any]:
    if isinstance(run, RunManifest):
        payload = _jsonable(run._serializable())
        loss = run.first_loss
        payload["first_loss"] = _jsonable(asdict(loss)) if loss else None
        payload["run_status"] = run.status
        payload["run_digest"] = run.digest()
        return payload
    if hasattr(run, "to_dict"):
        payload = _jsonable(run.to_dict())
        first_loss = getattr(run, "first_loss", None)
        payload["first_loss"] = _jsonable(first_loss.to_dict() if hasattr(first_loss, "to_dict") else first_loss)
        return payload
    raise TypeError("bundle source must be a RunManifest or PlanRun")


def _run_id(run: Any) -> str:
    value = getattr(run, "run_id", None) or getattr(run, "plan_id", None)
    if not value:
        raise ValueError("bundle source has no run_id or plan_id")
    return str(value)


def _all_evidence(run: Any) -> list[Evidence]:
    if isinstance(run, RunManifest):
        return list(run.evidence)
    return [evidence for child in getattr(run, "runs", {}).values() for evidence in child.evidence]


def _all_provenance(run: Any) -> list[Any]:
    if isinstance(run, RunManifest):
        return list(run.provenance)
    return [item for child in getattr(run, "runs", {}).values() for item in child.provenance]


@dataclass(frozen=True)
class ResearchBundle:
    bundle_id: str
    run_id: str
    created_at: str
    root: str
    bundle_hash: str
    sealed: bool

    @classmethod
    def create(
        cls,
        run: Any,
        root: str | Path,
        *,
        environment: Any | None = None,
        dataset_manifests: Iterable[Any] = (),
        claims: Iterable[Any] = (),
        artifacts: Mapping[str, str | Path] | None = None,
    ) -> "ResearchBundle":
        bundle_id = f"BND-{uuid.uuid4().hex[:12].upper()}"
        run_id = _run_id(run)
        target = Path(root) / run_id
        if target.exists():
            raise ResearchBundleError(f"bundle target already exists: {target}")
        for directory in (target, target / "datasets", target / "provenance", target / "steps", target / "evidence", target / "claims", target / "artifacts"):
            directory.mkdir(parents=True, exist_ok=True)

        run_payload = _run_payload(run)
        _write_json(target / "manifest.json", run_payload)
        _write_json(target / "inputs.json", getattr(run, "inputs", run_payload.get("inputs", {})))
        _write_json(target / "config.json", getattr(run, "config", run_payload.get("config", {})))
        if environment is None and isinstance(run, RunManifest):
            environment = run.environment_manifest
        _write_json(target / "environment.json", environment.to_dict() if environment is not None and hasattr(environment, "to_dict") else environment or {})

        manifests = list(dataset_manifests) or list(getattr(run, "dataset_manifests", ()))
        claim_items = list(claims)
        if not claim_items:
            claim_items = list(getattr(run, "claims", ()))
        _write_json(target / "datasets" / "manifests.json", [_jsonable(item) for item in manifests])
        _write_json(target / "provenance" / "sources.json", [_jsonable(item) for item in _all_provenance(run)])
        steps = getattr(run, "steps", {})
        _write_json(target / "steps" / "steps.json", [_jsonable(item) for item in steps.values()] if isinstance(steps, dict) else [])
        evidence = _all_evidence(run)
        _write_json(target / "evidence" / "evidence.json", [_jsonable(item) for item in evidence])
        _write_json(target / "claims" / "claims.json", [_jsonable(item) for item in claim_items])
        artifact_index: dict[str, Any] = {}
        for name, path_value in (artifacts or {}).items():
            source = Path(path_value)
            if not source.is_file():
                raise FileNotFoundError(source)
            destination = target / "artifacts" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            artifact_index[name] = {"path": str(destination.relative_to(target)), "sha256": sha256_file(destination)}
        _write_json(target / "artifacts" / "index.json", artifact_index)
        first_loss = run_payload.get("first_loss")
        _write_json(target / "first_loss.json", first_loss)
        _write_json(target / "summary.json", {"run_id": run_id, "run_status": run_payload.get("run_status", run_payload.get("status")), "first_loss": first_loss, "evidence_count": len(evidence), "claim_count": len(claim_items)})

        payload_files = sorted(path for path in target.rglob("*") if path.is_file())
        file_hashes = {str(path.relative_to(target)).replace("\\", "/"): sha256_file(path) for path in payload_files}
        bundle_hash = sha256_json(file_hashes)
        created_at = datetime.now(timezone.utc).isoformat()
        _write_json(target / "integrity.json", {"files": file_hashes, "bundle_hash": bundle_hash})
        bundle_metadata = {"bundle_id": bundle_id, "run_id": run_id, "created_at": created_at, "bundle_hash": bundle_hash, "sealed": True}
        _write_json(target / "bundle.json", bundle_metadata)
        seal_hash = sha256_json({"bundle_hash": bundle_hash, "bundle_manifest_sha256": sha256_file(target / "bundle.json"), "integrity_sha256": sha256_file(target / "integrity.json")})
        _write_json(target / "seal.json", {"bundle_hash": bundle_hash, "bundle_manifest_sha256": sha256_file(target / "bundle.json"), "integrity_sha256": sha256_file(target / "integrity.json"), "seal_hash": seal_hash, "sealed": True})
        return cls(bundle_id, run_id, created_at, str(target), bundle_hash, True)

    def verify(self):
        from research_os.bundles.verify import verify_bundle
        return verify_bundle(self.root)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(_jsonable(value), indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")


def create_bundle(run: Any, root: str | Path, **kwargs: Any) -> ResearchBundle:
    return ResearchBundle.create(run, root, **kwargs)
