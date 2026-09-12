"""Pre-execution gate for the frozen APODOCK-001 protocol.

The gate is intentionally an execution-free boundary.  A future docking
adapter must call :meth:`APODOCK001Runner.verify_execution_manifest` before it
can construct a Vina process.  This module itself never imports or invokes
Vina/Open Babel.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from research_os.docking.apodock001_protocol import (
    DEFAULT_PROTOCOL_PATH,
    ProtocolValidationError,
    build_dry_run_report,
    is_canonical_sha256,
    load_and_validate,
    load_and_validate_v102,
    load_protocol,
    validate_protocol,
    validate_protocol_v102,
)


class APODOCK001ExecutionError(ProtocolValidationError):
    """Raised before execution when a run manifest differs from the freeze."""


class APODOCK001Runner:
    """Load one immutable spec and expose only verified execution inputs."""

    def __init__(self, spec_path: str | Path = DEFAULT_PROTOCOL_PATH) -> None:
        self.spec_path = Path(spec_path)
        raw_protocol = load_protocol(self.spec_path)
        if raw_protocol.get("protocol_version") == "1.0.2":
            self.protocol = load_and_validate_v102(self.spec_path)
        else:
            self.protocol = load_and_validate(self.spec_path)

    def dry_run(self) -> dict[str, Any]:
        return build_dry_run_report(self.protocol)

    def expected_execution_manifest(self) -> dict[str, Any]:
        """Build the exact pre-execution manifest expected by this protocol."""

        if self.protocol.get("protocol_version") == "1.0.2":
            validate_protocol_v102(self.protocol)
        else:
            validate_protocol(self.protocol)
        benchmark = self.protocol["benchmark"]
        chemistry = self.protocol["chemistry"]
        vina = self.protocol["vina"]
        manifest = {
            "schema_version": "research-os.apodock001.execution.v1",
            "protocol_id": self.protocol["protocol_id"],
            "protocol_hash": self.protocol["protocol_hash"],
            "benchmark": {
                "id": benchmark["id"],
                "source_list_sha256": benchmark["source_list_sha256"],
                "case_metadata_sha256": benchmark["case_metadata_sha256"],
                "selection_manifest_hash": benchmark["selection_manifest_hash"],
                "case_order": list(benchmark["case_order"]),
                "input_hashes": {
                    case["case_id"]: {
                        "apo_pdb_sha256": case["apo_pdb_sha256"],
                        "holo_pdb_sha256": case["holo_pdb_sha256"],
                        "holo_reference_coordinate_hash": case["holo_reference_coordinate_hash"],
                        "transformed_holo_reference_coordinate_hash": case["transformed_holo_reference_coordinate_hash"],
                        **({"reference_sdf_sha256": case["reference_sdf_sha256"]} if "reference_sdf_sha256" in case else {}),
                    }
                    for case in benchmark["cases"]
                },
            },
            "chemistry": {
                "gate_id": chemistry["gate_id"],
                "gate_version": chemistry["gate_version"],
                "ready_count": chemistry["required_ready_count"],
                "apd010": {
                    key: chemistry["apd010"][key]
                    for key in (
                        "adapter_id",
                        "adapter_version",
                        "input_identity",
                        "output_identity",
                        "structural_identity",
                    )
                },
            },
            "receptor_preparation": deepcopy(self.protocol["receptor_preparation"]),
            "ligand_preparation": deepcopy(self.protocol["ligand_preparation"]),
            "vina": deepcopy(vina),
            "box": deepcopy(self.protocol["box"]),
            "analysis": deepcopy(self.protocol["analysis"]),
        }
        if "input_bundle" in self.protocol:
            manifest["input_bundle"] = deepcopy(self.protocol["input_bundle"])
        return manifest

    def verify_execution_manifest(self, observed: Mapping[str, Any]) -> None:
        """Fail closed unless the complete observed manifest matches exactly."""

        expected = self.expected_execution_manifest()
        if dict(observed) != expected:
            raise APODOCK001ExecutionError(
                "execution manifest differs from frozen APODOCK-001 protocol; "
                "no docking process may be started"
            )

    def verify_tool_identity(self, *, vina_version: str, vina_sha256: str) -> None:
        """Verify the already-observed binary identity without invoking it."""

        expected = self.protocol["vina"]
        if vina_version != expected["version"]:
            raise APODOCK001ExecutionError(
                f"Vina version mismatch: {vina_version!r} != {expected['version']!r}"
            )
        if (
            not is_canonical_sha256(vina_sha256)
            or vina_sha256 != expected["binary_sha256"]
        ):
            raise APODOCK001ExecutionError("Vina binary SHA-256 mismatch")
