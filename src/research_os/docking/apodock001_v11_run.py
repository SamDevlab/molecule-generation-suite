"""Run-specific APODOCK-001 v1.1 prospective execution infrastructure.

The merged v1.1 freeze adapter is intentionally unable to spawn Vina.  This
module is the separate, run-branch-only implementation that consumes the
frozen manifest, verifies the prepared artifacts and tool identities, and
crosses the prospective boundary only after an exact authorization label.

No analysis is performed by :class:`APODOCK001V11ProspectiveRunner` until the
complete raw-results seal has been written.  The module reuses the reviewed
preparation, command, staging, seal, representation, and evaluator helpers;
it changes only the v1.1 operational identity and timeout policy.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Mapping, Sequence

from rdkit import Chem

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking.apodock001_analysis import (
    ANALYSIS_ENGINE_ID,
    EXPECTED_CASE_IDS,
    _analyze_case,
    aggregate_case_analyses,
    build_transformed_reference,
    write_analysis_manifest,
    verify_raw_results_seal,
)
from research_os.docking.apodock001_execution import (
    APODOCK001CasePlan,
    APODOCK001InfrastructureError,
    ExecutionAuthorization,
    PreparedArtifact,
    ToolIdentity,
    _case_plan,
    build_environment_manifest,
    build_vina_command,
    prepare_ligand_conformer,
    prepare_pdbqt,
    prepare_receptor_input,
    verify_openbabel_tool,
    verify_prepared_artifact,
    verify_pristine_run_directory,
    verify_vina_tool,
    write_json,
)
from research_os.docking.apodock001_future import (
    POSE_ADAPTER_ID,
    POSE_ADAPTER_VERSION,
    build_complete_raw_results_seal,
    classify_timeout_record,
    normalize_openbabel_pose_for_reference,
    scientific_pose_identity,
)
from research_os.docking.apodock001_input_bundle import verify_frozen_input_bundle
from research_os.docking.apodock001_protocol import load_and_validate_v102
from research_os.docking.apodock001_v11 import (
    APODOCK001V11Plan,
    V11ProtocolValidationError,
    build_v11_plan,
    load_and_validate_v11,
    validate_v11_protocol,
)
from research_os.docking.apodock_glycan_chemistry import (
    load_named_ccd_sdf,
)
from research_os.docking.redocking import load_single_sdf
from research_os.engines.openbabel import OpenBabelEngine


V11_AUTHORIZATION_LABEL = "APODOCK-001-v1.1"
V11_TIMEOUT_SECONDS = 1800.0
V11_RETRY_COUNT = 0
V11_RUN_ID_PREFIX = "research-os.apodock001.run.v2+"
_POSE_NUMBER_RE = re.compile(r"pose_(\d+)\.pdbqt$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_pristine(path: Path) -> bool:
    if not path.exists():
        return True
    return not any(path.rglob("*"))


def _expected_execution_manifest(protocol: Mapping[str, Any]) -> dict[str, Any]:
    benchmark = protocol["benchmark"]
    chemistry = protocol["chemistry"]
    return {
        "schema_version": "research-os.apodock001.execution.v1.1",
        "protocol_id": protocol["protocol_id"],
        "protocol_hash": protocol["protocol_hash"],
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
                    "transformed_holo_reference_coordinate_hash": case[
                        "transformed_holo_reference_coordinate_hash"
                    ],
                    **(
                        {"reference_sdf_sha256": case["reference_sdf_sha256"]}
                        if "reference_sdf_sha256" in case
                        else {}
                    ),
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
        "receptor_preparation": deepcopy(protocol["receptor_preparation"]),
        "ligand_preparation": deepcopy(protocol["ligand_preparation"]),
        "vina": deepcopy(protocol["vina"]),
        "box": deepcopy(protocol["box"]),
        "analysis": deepcopy(protocol["analysis"]),
        "runtime_policy": deepcopy(protocol["runtime_policy"]),
        "failure_policy": deepcopy(protocol["failure_policy"]),
    }


def _relative_to(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _write_molecule(path: Path, molecule: Chem.Mol) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(path))
    try:
        writer.write(molecule)
    finally:
        writer.close()
    if not path.is_file() or path.stat().st_size == 0:
        raise APODOCK001InfrastructureError(f"molecule artifact was not produced: {path}")


class V11PoseRepresentationAdapter:
    """Open Babel representation adapter with the approved future repair."""

    adapter_id = POSE_ADAPTER_ID
    adapter_version = POSE_ADAPTER_VERSION

    def __init__(
        self,
        *,
        engine: OpenBabelEngine,
        protocol: Mapping[str, Any],
        bundle_root: Path,
        raw_hashes: Mapping[str, str | None],
    ) -> None:
        self.engine = engine
        self.protocol = protocol
        self.bundle_root = bundle_root
        self.raw_hashes = raw_hashes
        self._references: dict[str, Any] = {}
        self.scientific_identities: dict[str, dict[str, str]] = {}

    def _case(self, case_id: str) -> Mapping[str, Any]:
        return next(case for case in self.protocol["benchmark"]["cases"] if case["case_id"] == case_id)

    def _reference(self, case_id: str) -> Any:
        if case_id not in self._references:
            self._references[case_id] = build_transformed_reference(
                self.protocol, self.bundle_root, self._case(case_id)
            )
        return self._references[case_id]

    def convert(self, input_path: Path, output_path: Path) -> Mapping[str, Any]:
        case_id = next((part for part in input_path.parts if part in EXPECTED_CASE_IDS), None)
        if case_id is None:
            raise APODOCK001InfrastructureError(f"cannot identify case for pose: {input_path}")
        match = _POSE_NUMBER_RE.search(input_path.name)
        if match is None:
            raise APODOCK001InfrastructureError(f"cannot identify pose number: {input_path.name}")
        pose_index = int(match.group(1))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = self.engine.convert(
            input_path,
            output_path,
            options=(),
            timeout=60.0,
            protocol_id=self.adapter_id,
        )
        if result.returncode != 0 or not output_path.is_file():
            raise APODOCK001InfrastructureError(
                f"Open Babel pose conversion failed for {case_id} pose {pose_index}"
            )

        reference = self._reference(case_id)
        if reference.molecule is None:
            return {
                "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "input_sha256": result.input_sha256,
                "output_sha256": result.output_sha256,
                "reference_status": reference.failure_stage,
            }

        repaired, mapping = normalize_openbabel_pose_for_reference(
            output_path, reference.molecule
        )
        _write_molecule(output_path, repaired)
        source_raw_hash = self.raw_hashes.get(case_id)
        if source_raw_hash:
            self.scientific_identities.setdefault(case_id, {})[str(pose_index)] = scientific_pose_identity(
                repaired,
                source_raw_sha256=source_raw_hash,
                atom_mapping=mapping,
            )
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "input_sha256": result.input_sha256,
            "output_sha256": sha256_file(output_path),
            "scientific_pose_identity": self.scientific_identities.get(case_id, {}).get(str(pose_index)),
        }


class APODOCK001V11ProspectiveRunner:
    """One-pass v1.1 runner; the only run-specific Vina execution boundary."""

    def __init__(
        self,
        *,
        spec_path: str | Path,
        v102_path: str | Path,
        source_root: str | Path,
        run_root: str | Path,
        prepared_root: str | Path,
        staging_root: str | Path,
        git_sha: str,
    ) -> None:
        self.spec_path = Path(spec_path)
        self.v102_path = Path(v102_path)
        self.source_root = Path(source_root)
        self.run_root = Path(run_root)
        self.prepared_root = Path(prepared_root)
        self.staging_root = Path(staging_root)
        self.git_sha = git_sha
        self.parent_protocol = load_and_validate_v102(self.v102_path)
        self.protocol = load_and_validate_v11(self.spec_path, v102_path=self.v102_path)
        validate_v11_protocol(self.protocol, v102=self.parent_protocol)
        change_control = self.protocol["change_control"]
        if change_control["parent_protocol_id"] != self.parent_protocol["protocol_id"]:
            raise V11ProtocolValidationError("v1.1 parent protocol identity differs")
        if change_control["parent_protocol_hash"] != self.parent_protocol["protocol_hash"]:
            raise V11ProtocolValidationError("v1.1 parent protocol hash differs")
        self.plan: APODOCK001V11Plan = build_v11_plan(self.protocol)
        self.cases: tuple[APODOCK001CasePlan, ...] = tuple(
            _case_plan(self.protocol, case) for case in self.protocol["benchmark"]["cases"]
        )
        if tuple(case.case_id for case in self.cases) != EXPECTED_CASE_IDS:
            raise APODOCK001InfrastructureError("v1.1 case order is not APD-001 through APD-010")
        if self.plan.planned_run_id != self.protocol["operational_metadata"]["planned_run_id"]:
            raise APODOCK001InfrastructureError("v1.1 planned run identity is inconsistent")
        if self.run_root.resolve() == self.staging_root.resolve():
            raise APODOCK001InfrastructureError("staging_root must differ from run_root")
        if self.run_root.resolve() == self.prepared_root.resolve():
            raise APODOCK001InfrastructureError("prepared_root must differ from run_root")
        self.execution_manifest = _expected_execution_manifest(self.protocol)

    def verify_execution_manifest(self, observed: Mapping[str, Any] | None = None) -> None:
        if dict(self.execution_manifest if observed is None else observed) != self.execution_manifest:
            raise APODOCK001InfrastructureError("v1.1 execution manifest differs from frozen protocol")

    def verify_tools(
        self,
        *,
        vina_executable: str | Path,
        openbabel_executable: str | Path,
    ) -> tuple[ToolIdentity, ToolIdentity]:
        vina = verify_vina_tool(
            vina_executable,
            required_version=str(self.protocol["vina"]["version"]),
            required_sha256=str(self.protocol["vina"]["binary_sha256"]),
        )
        options = tuple(self.protocol["receptor_preparation"]["options"])
        openbabel = verify_openbabel_tool(
            openbabel_executable,
            required_version=str(self.protocol["receptor_preparation"]["binary_version"]),
            required_options=options,
        )
        if openbabel.version != "3.1.1":
            raise APODOCK001InfrastructureError("Open Babel version is not 3.1.1")
        return vina, openbabel

    def _verify_tool_identities(self, vina: ToolIdentity, openbabel: ToolIdentity) -> None:
        if vina.version != self.protocol["vina"]["version"]:
            raise APODOCK001InfrastructureError("Vina version identity changed")
        if vina.sha256 != self.protocol["vina"]["binary_sha256"]:
            raise APODOCK001InfrastructureError("Vina binary identity changed")
        if openbabel.version != "3.1.1":
            raise APODOCK001InfrastructureError("Open Babel version identity changed")
        required_options = tuple(self.protocol["receptor_preparation"]["options"])
        if tuple(openbabel.option_probe) != required_options:
            raise APODOCK001InfrastructureError("Open Babel option identity changed")

    def preflight(self) -> dict[str, Any]:
        verify_frozen_input_bundle(self.protocol, self.source_root)
        self.verify_execution_manifest()
        verify_pristine_run_directory(self.run_root)
        verify_pristine_run_directory(self.staging_root)
        return {
            "status": "READY_FOR_EXPLICIT_AUTHORIZATION",
            "protocol_id": self.plan.protocol_id,
            "protocol_hash": self.plan.protocol_hash,
            "planned_run_id": self.plan.planned_run_id,
            "execution_authorized": False,
            "prospective_execution_started": False,
            "run_id": None,
            "results": [],
            "scores": [],
            "poses": [],
            "run_root_pristine": _is_pristine(self.run_root),
            "staging_root_pristine": _is_pristine(self.staging_root),
            "vina_docking_executed": False,
        }

    def _artifact_manifest(
        self,
        case: APODOCK001CasePlan,
        artifact_kind: str,
        output_path: Path,
    ) -> dict[str, Any]:
        return {
            "case_id": case.case_id,
            "artifact_kind": artifact_kind,
            "source_hashes": deepcopy(case.input_hashes),
            "chemistry": deepcopy(case.chemistry),
            "preparation": deepcopy(case.preparation[artifact_kind]),
            "output_path": str(output_path),
            "output_sha256": sha256_file(output_path),
            "expected_destination": getattr(case, f"{artifact_kind}_prepared_output"),
            "protocol_id": self.plan.protocol_id,
            "planned_run_id": self.plan.planned_run_id,
        }

    def verify_prepared_artifacts(
        self,
        prepared_artifacts: Mapping[str, Mapping[str, Mapping[str, Any]]],
    ) -> None:
        if set(prepared_artifacts) != set(EXPECTED_CASE_IDS):
            raise APODOCK001InfrastructureError("prepared artifacts must cover exactly ten cases")
        for case in self.cases:
            case_artifacts = prepared_artifacts[case.case_id]
            if set(case_artifacts) != {"receptor", "ligand"}:
                raise APODOCK001InfrastructureError(f"{case.case_id} must have receptor and ligand artifacts")
            for kind in ("receptor", "ligand"):
                artifact = case_artifacts[kind]
                verify_prepared_artifact(
                    artifact,
                    expected_case=case,
                    artifact_kind=kind,
                    protocol_id=self.plan.protocol_id,
                    planned_run_id=self.plan.planned_run_id,
                    expected_destination=getattr(case, f"{kind}_prepared_output"),
                )
                path = Path(str(artifact["output_path"])).resolve()
                if path == self.run_root.resolve() or self.run_root.resolve() in path.parents:
                    raise APODOCK001InfrastructureError("prepared artifact must remain outside run_root")

    def prepare_inputs(
        self,
        *,
        openbabel: OpenBabelEngine,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        if self.prepared_root.exists() and any(self.prepared_root.rglob("*")):
            raise APODOCK001InfrastructureError("prepared_root is not pristine")
        receptor_options = tuple(self.protocol["receptor_preparation"]["options"])
        ligand_options = tuple(self.protocol["ligand_preparation"]["options"])
        prepared: dict[str, dict[str, dict[str, Any]]] = {}
        for case in self.cases:
            case_dir = self.prepared_root / case.case_id
            receptor_source = self.source_root / case.receptor_input
            selected_receptor = case_dir / "receptor_selected.pdb"
            receptor_pdbqt = case_dir / "receptor.pdbqt"
            prepare_receptor_input(
                source_path=receptor_source,
                output_pdb_path=selected_receptor,
                author_chain=str(self._case_record(case.case_id)["apo_receptor_author_chain"]),
                expected_sha256=case.input_hashes["apo_pdb_sha256"],
            )
            prepare_pdbqt(
                input_path=selected_receptor,
                output_path=receptor_pdbqt,
                options=receptor_options,
                openbabel=openbabel,
                protocol_id=self.plan.protocol_id,
            )
            if not receptor_pdbqt.is_file() or receptor_pdbqt.stat().st_size == 0:
                raise APODOCK001InfrastructureError(f"empty receptor PDBQT for {case.case_id}")

            ligand_sdf = case_dir / "ligand_conformer.sdf"
            adapter_report: dict[str, Any] | None = None
            if case.case_id != "APD-010":
                source_sdf = self.source_root / case.ligand_input
                if sha256_file(source_sdf) != case.input_hashes["reference_sdf_sha256"]:
                    raise APODOCK001InfrastructureError(f"ligand source hash mismatch for {case.case_id}")
                molecule = load_single_sdf(source_sdf)
            else:
                chemistry = self.protocol["chemistry"]["apd010"]
                bem = load_named_ccd_sdf(
                    self.source_root / "apd010/BEM_ideal.sdf",
                    self.source_root / "apd010/BEM.cif",
                    "BEM",
                    expected_sdf_sha256=chemistry["input_sdf_sha256"],
                    expected_cif_sha256=chemistry["input_cif_sha256"],
                )
                mav = load_named_ccd_sdf(
                    self.source_root / "apd010/MAV_ideal.sdf",
                    self.source_root / "apd010/MAV.cif",
                    "MAV",
                    expected_sdf_sha256=chemistry["output_sdf_sha256"],
                    expected_cif_sha256=chemistry["output_cif_sha256"],
                )
                from research_os.docking.apodock001_execution import adapt_apd010_for_execution

                molecule = adapt_apd010_for_execution(
                    bem,
                    mav,
                    chemistry_contract=chemistry,
                )
                adapter_report = {
                    "adapter_id": chemistry["adapter_id"],
                    "adapter_version": chemistry["adapter_version"],
                    "input_identity": chemistry["input_identity"],
                    "output_identity": chemistry["output_identity"],
                    "structural_identity": chemistry["structural_identity"],
                    "formula": chemistry["expected_formula"],
                    "heavy_atoms": chemistry["expected_heavy_atoms"],
                }
                _write_molecule(case_dir / "apd010-adapted-graph.sdf", molecule)
            conformer_metadata = prepare_ligand_conformer(
                molecule,
                ligand_sdf,
                seed=int(self.protocol["ligand_preparation"]["seed"]),
                uff_max_iters=int(self.protocol["ligand_preparation"]["uff_max_iters"]),
            )
            ligand_pdbqt = case_dir / "ligand.pdbqt"
            prepare_pdbqt(
                input_path=ligand_sdf,
                output_path=ligand_pdbqt,
                options=ligand_options,
                openbabel=openbabel,
                protocol_id=self.plan.protocol_id,
            )
            if not ligand_pdbqt.is_file() or ligand_pdbqt.stat().st_size == 0:
                raise APODOCK001InfrastructureError(f"empty ligand PDBQT for {case.case_id}")
            if adapter_report is not None:
                adapter_report["conformer"] = conformer_metadata
                write_json(case_dir / "apd010-adapter-report.json", adapter_report)
            prepared[case.case_id] = {
                "receptor": self._artifact_manifest(case, "receptor", receptor_pdbqt),
                "ligand": self._artifact_manifest(case, "ligand", ligand_pdbqt),
            }
        self.verify_prepared_artifacts(prepared)
        return prepared

    def _case_record(self, case_id: str) -> Mapping[str, Any]:
        return next(case for case in self.protocol["benchmark"]["cases"] if case["case_id"] == case_id)

    def command_audit(self, vina_executable: str | Path) -> list[dict[str, Any]]:
        audit: list[dict[str, Any]] = []
        expected_flags = (
            "--receptor", "--ligand", "--center_x", "--center_y", "--center_z",
            "--size_x", "--size_y", "--size_z", "--exhaustiveness", "--cpu",
            "--seed", "--num_modes", "--out",
        )
        for case in self.cases:
            command = build_vina_command(case, vina_executable, run_root=self.run_root)
            flags = tuple(item for item in command if item.startswith("--"))
            if flags != expected_flags or "--energy_range" in command:
                raise APODOCK001InfrastructureError("v1.1 command audit failed")
            if command[command.index("--exhaustiveness") + 1] != "32":
                raise APODOCK001InfrastructureError("v1.1 exhaustiveness command is not 32")
            if command[command.index("--cpu") + 1] != "1":
                raise APODOCK001InfrastructureError("v1.1 CPU command is not 1")
            if command[command.index("--seed") + 1] != "42":
                raise APODOCK001InfrastructureError("v1.1 seed command is not 42")
            if command[command.index("--num_modes") + 1] != "20":
                raise APODOCK001InfrastructureError("v1.1 num_modes command is not 20")
            audit.append({"case_id": case.case_id, "command": list(command), "flags": list(flags)})
        return audit

    def write_pre_execution_checkpoint(
        self,
        path: str | Path,
        *,
        vina: ToolIdentity,
        openbabel: ToolIdentity,
        prepared_artifacts: Mapping[str, Mapping[str, Mapping[str, Any]]],
        commands: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        self.verify_prepared_artifacts(prepared_artifacts)
        if len(commands) != 10:
            raise APODOCK001InfrastructureError("command audit must contain ten commands")
        checkpoint: dict[str, Any] = {
            "schema_version": "research-os.apodock001.pre-execution-checkpoint.v2",
            "base_sha": self.git_sha,
            "execution_implementation_sha": self.git_sha,
            "protocol_id": self.plan.protocol_id,
            "protocol_hash": self.plan.protocol_hash,
            "planned_run_id": self.plan.planned_run_id,
            "input_bundle_id": self.protocol["input_bundle"]["bundle_id"],
            "analysis_engine_id": ANALYSIS_ENGINE_ID,
            "vina": vina.to_dict(),
            "openbabel": openbabel.to_dict(),
            "chemistry_ready_count": 10,
            "prepared_receptors": 10,
            "prepared_ligands": 10,
            "prepared_artifacts": 20,
            "prepared_artifact_hashes": {
                case_id: {
                    kind: prepared_artifacts[case_id][kind]["output_sha256"]
                    for kind in ("receptor", "ligand")
                }
                for case_id in EXPECTED_CASE_IDS
            },
            "command_audit_count": len(commands),
            "commands": list(commands),
            "timeout_seconds": V11_TIMEOUT_SECONDS,
            "retry_count": V11_RETRY_COUNT,
            "run_root_pristine": _is_pristine(self.run_root),
            "staging_root_pristine": _is_pristine(self.staging_root),
            "results": [],
            "run_id": None,
            "execution_authorized": False,
            "prospective_execution_started": False,
            "vina_docking_executed": False,
        }
        if not checkpoint["run_root_pristine"] or not checkpoint["staging_root_pristine"]:
            raise APODOCK001InfrastructureError("run or staging root is not pristine")
        checkpoint["checkpoint_sha256"] = sha256_json(checkpoint)
        write_json(path, checkpoint)
        return checkpoint

    def _stage_prepared_artifacts(
        self,
        prepared_artifacts: Mapping[str, Mapping[str, Mapping[str, Any]]],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        self.verify_prepared_artifacts(prepared_artifacts)
        verify_pristine_run_directory(self.staging_root)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        staged: dict[str, dict[str, dict[str, Any]]] = {}
        for case in self.cases:
            staged[case.case_id] = {}
            for kind in ("receptor", "ligand"):
                source = Path(str(prepared_artifacts[case.case_id][kind]["output_path"]))
                destination = self.staging_root / case.case_id / f"{kind}.pdbqt"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                if sha256_file(source) != sha256_file(destination):
                    raise APODOCK001InfrastructureError(f"staging hash mismatch: {case.case_id} {kind}")
                staged[case.case_id][kind] = PreparedArtifact(
                    case_id=case.case_id,
                    artifact_kind=kind,
                    source_hashes=deepcopy(prepared_artifacts[case.case_id][kind]["source_hashes"]),
                    chemistry=deepcopy(case.chemistry),
                    preparation=deepcopy(case.preparation[kind]),
                    source_path=str(source),
                    staged_path=str(destination),
                    staged_sha256=sha256_file(destination),
                    expected_destination=getattr(case, f"{kind}_prepared_output"),
                    protocol_id=self.plan.protocol_id,
                    planned_run_id=self.plan.planned_run_id,
                ).to_manifest()
        for case in self.cases:
            for kind in ("receptor", "ligand"):
                verify_prepared_artifact(
                    staged[case.case_id][kind],
                    expected_case=case,
                    artifact_kind=kind,
                    protocol_id=self.plan.protocol_id,
                    planned_run_id=self.plan.planned_run_id,
                    expected_destination=getattr(case, f"{kind}_prepared_output"),
                )
        return staged

    def _copy_staged_to_run_root(self, staged: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> None:
        for case in self.cases:
            for kind in ("receptor", "ligand"):
                source = Path(str(staged[case.case_id][kind]["output_path"]))
                destination = self.run_root / getattr(case, f"{kind}_prepared_output")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                if sha256_file(destination) != staged[case.case_id][kind]["output_sha256"]:
                    raise APODOCK001InfrastructureError(f"run-root artifact hash mismatch: {case.case_id} {kind}")

    @staticmethod
    def _command_input_paths(command: Sequence[str]) -> tuple[Path, Path]:
        receptor = Path(command[command.index("--receptor") + 1])
        ligand = Path(command[command.index("--ligand") + 1])
        if not receptor.is_file() or receptor.stat().st_size == 0:
            raise APODOCK001InfrastructureError(f"missing receptor input: {receptor}")
        if not ligand.is_file() or ligand.stat().st_size == 0:
            raise APODOCK001InfrastructureError(f"missing ligand input: {ligand}")
        return receptor, ligand

    def _derive_run_id(
        self,
        *,
        vina: ToolIdentity,
        openbabel: ToolIdentity,
        prepared_artifacts: Mapping[str, Mapping[str, Mapping[str, Any]]],
        records: Sequence[Mapping[str, Any]],
    ) -> str:
        payload = {
            "schema_version": "research-os.apodock001.run-identity.v2",
            "protocol_id": self.plan.protocol_id,
            "protocol_hash": self.plan.protocol_hash,
            "planned_run_id": self.plan.planned_run_id,
            "execution_implementation_sha": self.git_sha,
            "tools": {
                "vina_version": vina.version,
                "vina_sha256": vina.sha256,
                "openbabel_version": openbabel.version,
            },
            "prepared_artifact_hashes": {
                case_id: {
                    kind: prepared_artifacts[case_id][kind]["output_sha256"]
                    for kind in ("receptor", "ligand")
                }
                for case_id in EXPECTED_CASE_IDS
            },
            "case_attempts": [
                {
                    key: record.get(key)
                    for key in ("case_id", "status", "returncode", "raw_output_sha256", "failure_stage")
                }
                for record in records
            ],
        }
        return f"{V11_RUN_ID_PREFIX}{sha256_json(payload)[:16]}"

    def execute_prospective(
        self,
        *,
        vina: ToolIdentity,
        openbabel: ToolIdentity,
        prepared_artifacts: Mapping[str, Mapping[str, Mapping[str, Any]]],
        authorization: ExecutionAuthorization,
        checkpoint_path: str | Path,
        environment_manifest: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        authorization.require(V11_AUTHORIZATION_LABEL)
        self.preflight()
        self._verify_tool_identities(vina, openbabel)
        self.verify_prepared_artifacts(prepared_artifacts)
        staged = self._stage_prepared_artifacts(prepared_artifacts)
        self.verify_prepared_artifacts(
            {
                case_id: {
                    kind: {
                        **staged[case_id][kind],
                        "output_path": staged[case_id][kind]["output_path"],
                    }
                    for kind in ("receptor", "ligand")
                }
                for case_id in EXPECTED_CASE_IDS
            }
        )
        verify_pristine_run_directory(self.run_root)
        self.run_root.mkdir(parents=True, exist_ok=False)
        self._copy_staged_to_run_root(staged)
        checkpoint = Path(checkpoint_path)
        if not checkpoint.is_file():
            raise APODOCK001InfrastructureError("pre-execution checkpoint is missing")
        shutil.copyfile(checkpoint, self.run_root / "pre-execution-checkpoint.json")
        write_json(self.run_root / "execution-manifest.json", self.execution_manifest)
        if environment_manifest is None:
            environment_manifest = build_environment_manifest(
                protocol_id=self.plan.protocol_id,
                git_sha=self.git_sha,
                vina=vina,
                openbabel=openbabel,
            )
        write_json(self.run_root / "environment-manifest.json", environment_manifest)
        write_json(self.run_root / "tool-identities.json", {"vina": vina.to_dict(), "openbabel": openbabel.to_dict()})
        write_json(
            self.run_root / "prepared-artifact-manifests.json",
            {case_id: dict(artifacts) for case_id, artifacts in staged.items()},
        )
        write_json(
            self.run_root / "parameter-manifest.json",
            {
                "protocol_id": self.plan.protocol_id,
                "seed": self.protocol["vina"]["seed"],
                "cpu": self.protocol["vina"]["cpu"],
                "exhaustiveness": self.protocol["vina"]["exhaustiveness"],
                "num_modes": self.protocol["vina"]["num_modes"],
                "energy_range": None,
                "timeout_seconds": V11_TIMEOUT_SECONDS,
                "retry_count": V11_RETRY_COUNT,
            },
        )
        commands = self.command_audit(vina.executable)
        write_json(self.run_root / "commands.json", {"commands": commands})

        lock = {
            "schema_version": "research-os.apodock001.execution-lock.v2",
            "protocol_id": self.plan.protocol_id,
            "protocol_hash": self.plan.protocol_hash,
            "planned_run_id": self.plan.planned_run_id,
            "execution_implementation_sha": self.git_sha,
            "authorization_label": V11_AUTHORIZATION_LABEL,
            "started_at": _utc_now(),
            "prospective_execution_started": True,
        }
        write_json(self.run_root / "prospective-run.lock", lock)

        records: list[dict[str, Any]] = []
        for case in self.cases:
            command = build_vina_command(case, vina.executable, run_root=self.run_root)
            self._command_input_paths(command)
            stdout_path = self.run_root / case.stdout_output
            stderr_path = self.run_root / case.stderr_output
            raw_path = self.run_root / case.raw_vina_output
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            started_at = _utc_now()
            failure_stage: str | None = None
            returncode: int | None = None
            try:
                with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
                    completed = subprocess.run(
                        command,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        check=False,
                        shell=False,
                        timeout=V11_TIMEOUT_SECONDS,
                    )
                returncode = int(completed.returncode)
            except subprocess.TimeoutExpired:
                returncode = -1
                failure_stage = "ADAPTER_SUBPROCESS_TIMEOUT"
            raw_hash = sha256_file(raw_path) if raw_path.is_file() and raw_path.stat().st_size > 0 else None
            if failure_stage is None:
                if returncode != 0:
                    failure_stage = "EXECUTION_FAILED"
                elif raw_hash is None:
                    failure_stage = "RAW_OUTPUT_MISSING"
            status = "COMPLETED" if failure_stage is None else "FAILED"
            record: dict[str, Any] = {
                "case_id": case.case_id,
                "command": list(command),
                "started_at": started_at,
                "ended_at": _utc_now(),
                "returncode": returncode,
                "status": status,
                "failure_stage": failure_stage,
                "timeout_seconds": V11_TIMEOUT_SECONDS,
                "retry_count": V11_RETRY_COUNT,
                "stdout_path": _relative_to(self.run_root, stdout_path),
                "stdout_sha256": sha256_file(stdout_path),
                "stderr_path": _relative_to(self.run_root, stderr_path),
                "stderr_sha256": sha256_file(stderr_path),
                "raw_output_path": _relative_to(self.run_root, raw_path),
                "raw_output_sha256": raw_hash,
            }
            if failure_stage == "ADAPTER_SUBPROCESS_TIMEOUT":
                record["timeout_classification"] = classify_timeout_record(
                    record, timeout_seconds=V11_TIMEOUT_SECONDS
                )
            records.append(record)

        run_id = self._derive_run_id(
            vina=vina,
            openbabel=openbabel,
            prepared_artifacts=prepared_artifacts,
            records=records,
        )
        raw_hashes = {record["case_id"]: record["raw_output_sha256"] for record in records}
        seal = build_complete_raw_results_seal(
            protocol_id=self.plan.protocol_id,
            protocol_hash=self.plan.protocol_hash,
            planned_run_id=self.plan.planned_run_id,
            run_id=run_id,
            raw_output_hashes=raw_hashes,
        )
        write_json(self.run_root / "raw-results-seal.json", seal)
        manifest = {
            "schema_version": "research-os.apodock001.run-manifest.v2",
            "status": "RAW_RESULTS_SEALED",
            "raw_results_sealed": True,
            "protocol_id": self.plan.protocol_id,
            "protocol_hash": self.plan.protocol_hash,
            "planned_run_id": self.plan.planned_run_id,
            "run_id": run_id,
            "execution_implementation_sha": self.git_sha,
            "authorization_label": V11_AUTHORIZATION_LABEL,
            "timeout_seconds": V11_TIMEOUT_SECONDS,
            "retry_count": V11_RETRY_COUNT,
            "tool_identities": {"vina": vina.to_dict(), "openbabel": openbabel.to_dict()},
            "cases": records,
            "raw_results_seal_sha256": seal["raw_results_seal_sha256"],
            "analysis_manifest": None,
        }
        write_json(self.run_root / "run-manifest.json", manifest)
        return manifest


def analyze_v11_sealed_run(
    *,
    protocol_path: str | Path,
    v102_path: str | Path,
    bundle_root: str | Path,
    run_root: str | Path,
    openbabel: OpenBabelEngine,
    analysis_commit_sha: str,
) -> dict[str, Any]:
    """Run the frozen evaluator after verifying the v1.1 raw-results seal."""

    protocol = load_and_validate_v11(protocol_path, v102_path=v102_path)
    verify_frozen_input_bundle(protocol, bundle_root)
    planned_run_id = str(protocol["operational_metadata"]["planned_run_id"])
    seal = verify_raw_results_seal(
        run_root,
        protocol_id=str(protocol["protocol_id"]),
        protocol_hash=str(protocol["protocol_hash"]),
        planned_run_id=planned_run_id,
    )
    raw_hashes = {case_id: record.get("raw_output_sha256") for case_id, record in seal.records.items()}
    adapter = V11PoseRepresentationAdapter(
        engine=openbabel,
        protocol=protocol,
        bundle_root=Path(bundle_root),
        raw_hashes=raw_hashes,
    )
    cases = tuple(
        _analyze_case(
            protocol,
            Path(bundle_root),
            Path(run_root),
            seal.records[case_id],
            adapter,
        )
        for case_id in EXPECTED_CASE_IDS
    )
    manifest: dict[str, Any] = {
        "schema_version": "research-os.apodock001.analysis.v1",
        "status": "ANALYSIS_COMPLETE",
        "protocol_id": protocol["protocol_id"],
        "protocol_hash": protocol["protocol_hash"],
        "planned_run_id": planned_run_id,
        "run_id": seal.run_id,
        "raw_results_seal_sha256": seal.raw_results_seal_sha256,
        "analysis_engine_id": ANALYSIS_ENGINE_ID,
        "analysis_commit_sha": analysis_commit_sha,
        "pose_representation_adapter": adapter.adapter_id,
        "pose_representation_adapter_version": adapter.adapter_version,
        "same_frame_no_fit": True,
        "symmetry_max_matches": 10000,
        "primary_pose_rule": "first pose in raw Vina output order",
        "secondary_pose_rule": "minimum RMSD among first 20 raw poses",
        "success_threshold_angstrom": 2.0,
        "scientific_pose_identities": adapter.scientific_identities,
        "aggregation": aggregate_case_analyses(cases),
        "indeterminates": [
            {"case_id": case.case_id, "first_loss": case.first_loss, "reason": case.first_loss_reason}
            for case in cases
            if case.status != "DETERMINATE"
        ],
    }
    manifest["analysis_manifest_sha256"] = sha256_json(manifest)
    return manifest


def build_v102_v11_comparison(
    historical_analysis_path: str | Path,
    v11_analysis: Mapping[str, Any],
) -> dict[str, Any]:
    historical = json.loads(Path(historical_analysis_path).read_text(encoding="utf-8"))
    old_cases = {case["case_id"]: case for case in historical["aggregation"]["cases"]}
    new_cases = {case["case_id"]: case for case in v11_analysis["aggregation"]["cases"]}
    per_case = []
    for case_id in EXPECTED_CASE_IDS:
        old = old_cases[case_id]
        new = new_cases[case_id]
        def delta(key: str) -> float | None:
            first = old.get(key)
            second = new.get(key)
            if first is None or second is None:
                return None
            return float(second) - float(first)
        per_case.append(
            {
                "case_id": case_id,
                "v1.0.2_execution": old.get("status"),
                "v1.1_execution": new.get("status"),
                "delta_pose_1_rmsd_angstrom": delta("pose_1_rmsd_angstrom"),
                "delta_minimum_rmsd_angstrom": delta("minimum_rmsd_angstrom"),
                "v1.0.2_first_loss": old.get("first_loss"),
                "v1.1_first_loss": new.get("first_loss"),
            }
        )
    return {
        "schema_version": "research-os.apodock001.v102-v11-comparison.v1",
        "historical_protocol_id": historical["protocol_id"],
        "v11_protocol_id": v11_analysis["protocol_id"],
        "descriptive_only": True,
        "causal_language": "consistent with / supports / does not support; no strong causal claim",
        "hypothesis": "Does increasing exhaustiveness from 16 to 32 improve pose sampling under otherwise frozen controls?",
        "v1.0.2": historical["aggregation"],
        "v1.1": v11_analysis["aggregation"],
        "per_case": per_case,
    }


def write_comparison_markdown(path: str | Path, comparison: Mapping[str, Any]) -> None:
    old = comparison["v1.0.2"]
    new = comparison["v1.1"]
    lines = [
        "# APODOCK-001 v1.0.2 → v1.1 descriptive comparison",
        "",
        "This comparison is descriptive only; the exhaustiveness change does not establish strong causality.",
        "",
        "| Metric | v1.0.2 | v1.1 |",
        "| --- | ---: | ---: |",
        f"| Attempted | 10/10 | 10/10 |",
        f"| Completed | {10 - old['failed_execution_count']}/10 | {10 - new['failed_execution_count']}/10 |",
        f"| Execution failures | {old['failed_execution_count']} | {new['failed_execution_count']} |",
        f"| Determinate | {old['determinate_count']} | {new['determinate_count']} |",
        f"| Primary success | {old['primary']['success_count']}/{old['primary']['denominator']} | {new['primary']['success_count']}/{new['primary']['denominator']} |",
        f"| Secondary success | {old['secondary']['success_count']}/{old['secondary']['denominator']} | {new['secondary']['success_count']}/{new['secondary']['denominator']} |",
        f"| Primary mean RMSD | {old['primary']['mean_over_determinate']} | {new['primary']['mean_over_determinate']} |",
        f"| Primary median RMSD | {old['primary']['median_over_determinate']} | {new['primary']['median_over_determinate']} |",
        f"| Secondary mean RMSD | {old['secondary']['mean_over_determinate']} | {new['secondary']['mean_over_determinate']} |",
        f"| Secondary median RMSD | {old['secondary']['median_over_determinate']} | {new['secondary']['median_over_determinate']} |",
        "",
        "Per-case deltas are recorded in `comparison-manifest.json`.  Interpret any direction as descriptive and use `supports` or `does not support`, never `proves`.",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_evidence_bundle_manifest(
    *,
    run_root: str | Path,
    protocol_id: str,
    protocol_hash: str,
    run_id: str,
    raw_seal_sha256: str,
) -> dict[str, Any]:
    root = Path(run_root)
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "evidence-bundle-manifest.json":
            continue
        records.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
    payload = {
        "schema_version": "research-os.apodock001.evidence-bundle.v2",
        "protocol_id": protocol_id,
        "protocol_hash": protocol_hash,
        "run_id": run_id,
        "raw_results_seal_sha256": raw_seal_sha256,
        "files": records,
    }
    manifest = {**payload, "evidence_bundle_sha256": sha256_json(payload)}
    write_json(root / "evidence-bundle-manifest.json", manifest)
    return manifest


__all__ = [
    "APODOCK001V11ProspectiveRunner",
    "V11PoseRepresentationAdapter",
    "V11_AUTHORIZATION_LABEL",
    "V11_RETRY_COUNT",
    "V11_RUN_ID_PREFIX",
    "V11_TIMEOUT_SECONDS",
    "analyze_v11_sealed_run",
    "build_v102_v11_comparison",
    "write_comparison_markdown",
    "write_evidence_bundle_manifest",
]
