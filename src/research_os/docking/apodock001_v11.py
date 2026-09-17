"""APODOCK-001 v1.1 preregistration and offline execution boundary.

The v1.1 freeze tests one scientific hypothesis: a single higher
exhaustiveness search may improve sampling while every other scientific
control remains equal to v1.0.2.  This module intentionally exposes only
validation, deterministic identity, command construction, and preflight.  It
does not expose a Vina execution path in the freeze PR.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from research_os.core.hashing import sha256_json
from research_os.docking.apodock001_execution import (
    APODOCK001InfrastructureError,
    ExecutionAuthorizationError,
    FROZEN_VINA_FLAGS,
    verify_frozen_input_bundle,
    verify_pristine_run_directory,
)
from research_os.docking.apodock001_protocol import load_protocol, load_and_validate_v102


V11_PROTOCOL_VERSION = "1.1"
V11_PROTOCOL_ID_PREFIX = "research-os.apodock001.protocol.v1.1+"
V11_PLANNED_RUN_ID_PREFIX = "research-os.apodock001.planned-run.v2+"
V11_EXHAUSTIVENESS = 32
V11_TIMEOUT_SECONDS = 1800
V11_RETRY_COUNT = 0
V11_ANALYSIS_ENGINE_ID = "research-os.apodock001.analysis.v1+25ebfa66ecace1dd"
_NON_SCIENTIFIC_KEYS = frozenset({"schema_version", "protocol_id", "protocol_hash", "operational_metadata"})


class V11ProtocolValidationError(ValueError):
    """Raised when the v1.1 preregistration is incomplete or mutated."""


@dataclass(frozen=True)
class APODOCK001V11Plan:
    protocol_id: str
    protocol_hash: str
    planned_run_id: str
    case_order: tuple[str, ...]
    execution_manifest: Mapping[str, Any]


def v11_scientific_payload(protocol: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in protocol.items()
        if key not in _NON_SCIENTIFIC_KEYS
    }


def v11_protocol_hash(protocol: Mapping[str, Any]) -> str:
    return sha256_json(v11_scientific_payload(protocol))


def v11_protocol_id(protocol: Mapping[str, Any]) -> str:
    return f"{V11_PROTOCOL_ID_PREFIX}{v11_protocol_hash(protocol)[:16]}"


def v11_planned_run_id(protocol: Mapping[str, Any]) -> str:
    payload = {
        "schema_version": "research-os.apodock001.execution-plan.v2",
        "protocol_id": protocol["protocol_id"],
        "protocol_hash": protocol["protocol_hash"],
        "case_order": list(protocol["benchmark"]["case_order"]),
        "input_bundle": protocol["input_bundle"],
        "vina": {
            key: protocol["vina"][key]
            for key in (
                "version",
                "binary_sha256",
                "scoring_function",
                "receptor_mode",
                "seed",
                "cpu",
                "exhaustiveness",
                "num_modes",
            )
        },
        "runtime_policy": protocol["runtime_policy"],
        "failure_policy": protocol["failure_policy"],
        "analysis_engine_id": V11_ANALYSIS_ENGINE_ID,
    }
    return f"{V11_PLANNED_RUN_ID_PREFIX}{sha256_json(payload)[:16]}"


def build_v11_protocol(v102: Mapping[str, Any]) -> dict[str, Any]:
    """Derive the v1.1 manifest from v1.0.2 without changing frozen inputs."""

    base = deepcopy(dict(v102))
    if base.get("protocol_version") != "1.0.2":
        raise V11ProtocolValidationError("v1.1 must derive from the frozen v1.0.2 manifest")
    base["protocol_version"] = V11_PROTOCOL_VERSION
    base["vina"]["exhaustiveness"] = V11_EXHAUSTIVENESS
    base["runtime_policy"] = {
        "case_timeout_seconds": V11_TIMEOUT_SECONDS,
        "timeout_stage": "ADAPTER_SUBPROCESS_TIMEOUT",
        "timeout_behavior": "record_failed_case_and_continue_in_frozen_order",
        "retry_count": V11_RETRY_COUNT,
    }
    base["failure_policy"] = {
        "one_attempt_per_case": True,
        "retry_count": V11_RETRY_COUNT,
        "parameter_changes_after_start": False,
        "post_result_tuning": False,
        "seal_after_all_case_attempts": True,
    }
    base["change_control"] = {
        **base["change_control"],
        "v1.1_hypothesis": "a single higher-exhaustiveness search may improve sampling; no other scientific control changes",
        "parent_protocol_id": v102["protocol_id"],
        "parent_protocol_hash": v102["protocol_hash"],
    }
    base["operational_metadata"] = {
        **base.get("operational_metadata", {}),
        "freeze_status": "PREREGISTERED_BEFORE_V1.1_RESULTS",
        "planned_run_id": None,
        "analysis_engine_id": V11_ANALYSIS_ENGINE_ID,
    }
    base["protocol_hash"] = v11_protocol_hash(base)
    base["protocol_id"] = v11_protocol_id(base)
    base["operational_metadata"]["planned_run_id"] = v11_planned_run_id(base)
    return base


def validate_v11_protocol(protocol: Mapping[str, Any], *, v102: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Validate the v1.1 mutation boundary and return identities."""

    if v102 is None:
        v102 = load_and_validate_v102()
    expected_top_level = set(v102) | {"runtime_policy", "failure_policy"}
    if set(protocol) != expected_top_level:
        raise V11ProtocolValidationError("v1.1 top-level schema changed unexpectedly")
    if protocol.get("protocol_version") != V11_PROTOCOL_VERSION:
        raise V11ProtocolValidationError("protocol_version is not 1.1")
    for key in ("schema_version", "evidence", "prospective_boundary"):
        if protocol.get(key) != v102.get(key):
            raise V11ProtocolValidationError(f"control changed unexpectedly: {key}")
    if protocol.get("input_bundle") != v102.get("input_bundle"):
        raise V11ProtocolValidationError("v1.1 input bundle differs from v1.0.2")
    for key in (
        "benchmark",
        "chemistry",
        "receptor_preparation",
        "ligand_preparation",
        "box",
        "analysis",
    ):
        if protocol.get(key) != v102.get(key):
            raise V11ProtocolValidationError(f"control changed unexpectedly: {key}")
    for key in ("version", "binary_sha256", "scoring_function", "receptor_mode", "seed", "cpu", "exhaustiveness", "num_modes", "flags", "energy_range_kcal_per_mol"):
        if key == "exhaustiveness":
            continue
        if protocol["vina"].get(key) != v102["vina"].get(key):
            raise V11ProtocolValidationError(f"Vina control changed unexpectedly: {key}")
    if protocol["vina"].get("exhaustiveness") != V11_EXHAUSTIVENESS:
        raise V11ProtocolValidationError("v1.1 exhaustiveness must be exactly 32")
    if protocol.get("runtime_policy") != {
        "case_timeout_seconds": V11_TIMEOUT_SECONDS,
        "timeout_stage": "ADAPTER_SUBPROCESS_TIMEOUT",
        "timeout_behavior": "record_failed_case_and_continue_in_frozen_order",
        "retry_count": V11_RETRY_COUNT,
    }:
        raise V11ProtocolValidationError("runtime policy changed")
    if protocol.get("failure_policy") != {
        "one_attempt_per_case": True,
        "retry_count": V11_RETRY_COUNT,
        "parameter_changes_after_start": False,
        "post_result_tuning": False,
        "seal_after_all_case_attempts": True,
    }:
        raise V11ProtocolValidationError("failure policy changed")
    expected_change_control = deepcopy(v102["change_control"])
    expected_change_control.update(
        {
            "v1.1_hypothesis": "a single higher-exhaustiveness search may improve sampling; no other scientific control changes",
            "parent_protocol_id": v102["protocol_id"],
            "parent_protocol_hash": v102["protocol_hash"],
        }
    )
    if protocol.get("change_control") != expected_change_control:
        raise V11ProtocolValidationError("change-control declaration changed")
    if protocol.get("operational_metadata", {}).get("analysis_engine_id") != V11_ANALYSIS_ENGINE_ID:
        raise V11ProtocolValidationError("analysis engine identity changed")
    derived_hash = v11_protocol_hash(protocol)
    derived_id = v11_protocol_id(protocol)
    if protocol.get("protocol_hash") != derived_hash:
        raise V11ProtocolValidationError("protocol_hash does not match canonical v1.1 payload")
    if protocol.get("protocol_id") != derived_id:
        raise V11ProtocolValidationError("protocol_id does not match canonical v1.1 payload")
    expected_plan = v11_planned_run_id(protocol)
    if protocol.get("operational_metadata", {}).get("planned_run_id") != expected_plan:
        raise V11ProtocolValidationError("planned_run_id does not match canonical v1.1 plan")
    return {
        "protocol_hash": derived_hash,
        "protocol_id": derived_id,
        "planned_run_id": expected_plan,
    }


def load_and_validate_v11(path: str | Path, *, v102_path: str | Path | None = None) -> dict[str, Any]:
    protocol = load_protocol(path)
    base = load_and_validate_v102(v102_path) if v102_path else load_and_validate_v102()
    validate_v11_protocol(protocol, v102=base)
    return protocol


def build_v11_plan(protocol: Mapping[str, Any]) -> APODOCK001V11Plan:
    identity = validate_v11_protocol(protocol)
    execution_manifest = {
        "schema_version": "research-os.apodock001.execution.v1.1",
        "protocol_id": protocol["protocol_id"],
        "protocol_hash": protocol["protocol_hash"],
        "planned_run_id": identity["planned_run_id"],
        "case_order": list(protocol["benchmark"]["case_order"]),
        "execution_authorized": False,
        "prospective_execution_started": False,
    }
    return APODOCK001V11Plan(
        protocol_id=identity["protocol_id"],
        protocol_hash=identity["protocol_hash"],
        planned_run_id=identity["planned_run_id"],
        case_order=tuple(protocol["benchmark"]["case_order"]),
        execution_manifest=execution_manifest,
    )


class APODOCK001V11ExecutionAdapter:
    """Offline-only v1.1 freeze adapter.

    The freeze branch has no method capable of spawning Vina.  The future run
    branch may add the explicitly authorized execution implementation after
    this protocol has been reviewed and merged.
    """

    def __init__(
        self,
        spec_path: str | Path,
        *,
        v102_path: str | Path,
        source_root: str | Path,
        run_root: str | Path,
        staging_root: str | Path,
        git_sha: str,
    ) -> None:
        self.spec_path = Path(spec_path)
        self.protocol = load_and_validate_v11(self.spec_path, v102_path=v102_path)
        self.plan = build_v11_plan(self.protocol)
        self.source_root = Path(source_root)
        self.run_root = Path(run_root)
        self.staging_root = Path(staging_root)
        if self.run_root.resolve() == self.staging_root.resolve():
            raise APODOCK001InfrastructureError("v1.1 staging_root must differ from run_root")
        self.git_sha = git_sha

    def build_command(self, case_id: str, vina_executable: str | Path) -> tuple[str, ...]:
        if case_id not in self.plan.case_order:
            raise APODOCK001InfrastructureError(f"unknown frozen case: {case_id}")
        box = self.protocol["box"]["cases"][case_id]
        values = (
            ("--center_x", str(box["center"][0])),
            ("--center_y", str(box["center"][1])),
            ("--center_z", str(box["center"][2])),
            ("--size_x", str(box["size"][0])),
            ("--size_y", str(box["size"][1])),
            ("--size_z", str(box["size"][2])),
            ("--exhaustiveness", str(self.protocol["vina"]["exhaustiveness"])),
            ("--cpu", str(self.protocol["vina"]["cpu"])),
            ("--seed", str(self.protocol["vina"]["seed"])),
            ("--num_modes", str(self.protocol["vina"]["num_modes"])),
        )
        command = [str(vina_executable), "--receptor", str(self.run_root / f"prepared/{case_id}/receptor.pdbqt"), "--ligand", str(self.run_root / f"prepared/{case_id}/ligand.pdbqt")]
        for flag, value in values:
            command.extend((flag, value))
        command.extend(("--out", str(self.run_root / f"raw/{case_id}/vina_poses.pdbqt")))
        if tuple(flag for flag in command if flag.startswith("--")) != FROZEN_VINA_FLAGS:
            raise APODOCK001InfrastructureError("v1.1 command flags diverge from the frozen surface")
        return tuple(command)

    def preflight(self) -> dict[str, Any]:
        verify_frozen_input_bundle(self.protocol, self.source_root)
        verify_pristine_run_directory(self.run_root)
        return {
            "status": "READY_FOR_EXPLICIT_AUTHORIZATION",
            "execution_authorized": False,
            "prospective_execution_started": False,
            "protocol_id": self.plan.protocol_id,
            "protocol_hash": self.plan.protocol_hash,
            "planned_run_id": self.plan.planned_run_id,
            "run_id": None,
            "evidence_scaffold_status": "NOT_EXECUTED",
            "results": [],
            "scores": [],
            "poses": [],
            "git_sha": self.git_sha,
            "vina_docking_executed": False,
        }

    def execute_prospective(self, *args: Any, **kwargs: Any) -> None:
        raise ExecutionAuthorizationError(
            "v1.1 freeze adapter has no execution path; authorize only from a separate future run branch"
        )


def write_v11_protocol(path: str | Path, v102_path: str | Path) -> dict[str, Any]:
    base = load_and_validate_v102(v102_path)
    protocol = build_v11_protocol(base)
    validate_v11_protocol(protocol, v102=base)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(protocol, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return protocol


__all__ = [
    "APODOCK001V11ExecutionAdapter",
    "APODOCK001V11Plan",
    "V11_EXHAUSTIVENESS",
    "V11_PLANNED_RUN_ID_PREFIX",
    "V11_PROTOCOL_ID_PREFIX",
    "V11_PROTOCOL_VERSION",
    "V11ProtocolValidationError",
    "build_v11_plan",
    "build_v11_protocol",
    "load_and_validate_v11",
    "v11_planned_run_id",
    "v11_protocol_hash",
    "v11_protocol_id",
    "write_v11_protocol",
]
