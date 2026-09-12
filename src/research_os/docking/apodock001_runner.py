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
    load_and_validate,
    validate_protocol,
)


class APODOCK001ExecutionError(ProtocolValidationError):
    """Raised before execution when a run manifest differs from the freeze."""


class APODOCK001Runner:
    """Load one immutable spec and expose only verified execution inputs."""

    def __init__(self, spec_path: str | Path = DEFAULT_PROTOCOL_PATH) -> None:
        self.spec_path = Path(spec_path)
        self.protocol = load_and_validate(self.spec_path)

    def dry_run(self) -> dict[str, Any]:
        return build_dry_run_report(self.protocol)

    def expected_execution_manifest(self) -> dict[str, Any]:
        """Build the exact pre-execution manifest expected by this protocol."""

        validate_protocol(self.protocol)
        benchmark = self.protocol["benchmark"]
        chemistry = self.protocol["chemistry"]
        vina = self.protocol["vina"]
        return {
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
        if vina_sha256.lower() != expected["binary_sha256"].lower():
            raise APODOCK001ExecutionError("Vina binary SHA-256 mismatch")
