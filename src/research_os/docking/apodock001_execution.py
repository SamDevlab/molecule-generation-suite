"""Normative, fail-closed execution infrastructure for APODOCK-001 v1.0.1.

This module prepares the future prospective run without performing one by
default.  The frozen protocol remains the only source of scientific inputs;
this adapter adds operational planning, tool verification, preparation
boundaries, command construction, authorization, rerun protection, and an
evidence-bundle scaffold.

Importing this module never starts a subprocess.  The only method that may
start Vina is :meth:`APODOCK001ExecutionAdapter.execute_case`, and it requires
an explicit :class:`ExecutionAuthorization` whose default is disabled.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
from typing import Any, Mapping, Sequence

from rdkit import Chem

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking.apodock001_protocol import (
    DEFAULT_PROTOCOL_PATH,
    is_canonical_sha256,
)
from research_os.docking.apodock001_runner import APODOCK001Runner
from research_os.docking.apodock001_input_bundle import verify_frozen_input_bundle
from research_os.docking.apodock_glycan_chemistry import (
    adapt_apd010,
    chemistry_identity,
)
from research_os.docking.redocking import generate_independent_conformer
from research_os.engines.openbabel import OpenBabelEngine, OpenBabelResult


EXPECTED_OPENBABEL_VERSION = "3.1.1"
EXECUTION_PLAN_SCHEMA = "research-os.apodock001.execution-plan.v1"
EVIDENCE_SCAFFOLD_SCHEMA = "research-os.apodock001.evidence-scaffold.v1"
PLANNED_RUN_PREFIX = "research-os.apodock001.planned-run.v1+"

FROZEN_VINA_FLAGS: tuple[str, ...] = (
    "--receptor",
    "--ligand",
    "--center_x",
    "--center_y",
    "--center_z",
    "--size_x",
    "--size_y",
    "--size_z",
    "--exhaustiveness",
    "--cpu",
    "--seed",
    "--num_modes",
    "--out",
)


class APODOCK001InfrastructureError(RuntimeError):
    """Raised when the frozen execution infrastructure cannot proceed."""


class ExecutionAuthorizationError(APODOCK001InfrastructureError):
    """Raised when a Vina subprocess is requested without explicit consent."""


class ExistingProspectiveRunError(APODOCK001InfrastructureError):
    """Raised when a prospective run directory is not pristine."""


PREPARED_ARTIFACT_KINDS: tuple[str, ...] = ("receptor", "ligand")


@dataclass(frozen=True)
class ToolIdentity:
    name: str
    executable: str
    version: str
    version_output: str
    sha256: str | None
    required_sha256: str | None
    required_version: str
    option_probe: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class APODOCK001CasePlan:
    case_id: str
    receptor_input: str
    ligand_input: str
    input_hashes: dict[str, str]
    chemistry: dict[str, Any]
    receptor_prepared_output: str
    ligand_prepared_output: str
    raw_vina_output: str
    stdout_output: str
    stderr_output: str
    box: dict[str, Any]
    vina: dict[str, Any]
    preparation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class APODOCK001ExecutionPlan:
    schema_version: str
    protocol_id: str
    protocol_hash: str
    planned_run_id: str
    cases: tuple[APODOCK001CasePlan, ...]
    execution_manifest: dict[str, Any]

    def scientific_payload(self) -> dict[str, Any]:
        """Return the deterministic plan payload without local paths."""

        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "protocol_hash": self.protocol_hash,
            "cases": [case.to_dict() for case in self.cases],
            "execution_manifest": self.execution_manifest,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.scientific_payload(),
            "planned_run_id": self.planned_run_id,
        }


@dataclass(frozen=True)
class PreparedArtifact:
    """One immutable, pre-execution artifact staged for a future run."""

    case_id: str
    artifact_kind: str
    source_hashes: dict[str, str]
    chemistry: dict[str, Any]
    preparation: dict[str, Any]
    source_path: str
    staged_path: str
    staged_sha256: str
    expected_destination: str
    protocol_id: str
    planned_run_id: str

    def to_manifest(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "artifact_kind": self.artifact_kind,
            "source_hashes": deepcopy(self.source_hashes),
            "chemistry": deepcopy(self.chemistry),
            "preparation": deepcopy(self.preparation),
            "output_path": self.staged_path,
            "output_sha256": self.staged_sha256,
            "expected_destination": self.expected_destination,
            "protocol_id": self.protocol_id,
            "planned_run_id": self.planned_run_id,
        }


@dataclass(frozen=True)
class ExecutionAuthorization:
    """Explicit opt-in required by any method that could invoke Vina."""

    execution_authorized: bool = False
    authorization_label: str | None = None

    def require(self, expected_label: str | None = None) -> None:
        if not self.execution_authorized:
            raise ExecutionAuthorizationError(
                "prospective execution is disabled; explicit authorization is required"
            )
        required = expected_label or "APODOCK-001-v1.0.1"
        if self.authorization_label != required:
            raise ExecutionAuthorizationError(
                f"authorization label must be {required}"
            )


def _normalized_version(text: str | None, expected: str) -> str:
    raw = (text or "").strip()
    if not re.search(rf"(?<!\d){re.escape(expected)}(?!\d)", raw):
        raise APODOCK001InfrastructureError(
            f"tool version mismatch: expected {expected!r}, observed {raw!r}"
        )
    return expected


def _executable_file(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_file():
        raise APODOCK001InfrastructureError(f"executable not found: {candidate}")
    if os.name != "nt" and not os.access(candidate, os.X_OK):
        raise APODOCK001InfrastructureError(f"executable is not executable: {candidate}")
    return candidate


def _probe(executable: Path, args: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            [str(executable), *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise APODOCK001InfrastructureError(
            f"could not probe {executable} {' '.join(args)}: {exc}"
        ) from exc
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0 or not output:
        raise APODOCK001InfrastructureError(
            f"tool probe failed for {executable} {' '.join(args)}"
        )
    return output


def verify_vina_tool(
    executable: str | Path,
    *,
    required_version: str,
    required_sha256: str,
    version_output: str | None = None,
) -> ToolIdentity:
    """Verify the exact Vina bytes and version before any docking command."""

    path = _executable_file(executable)
    digest = sha256_file(path)
    if (
        not is_canonical_sha256(required_sha256)
        or not is_canonical_sha256(digest)
        or digest != required_sha256
    ):
        raise APODOCK001InfrastructureError(
            f"Vina SHA-256 mismatch: {digest} != {required_sha256}"
        )
    raw_version = version_output or _probe(path, ("--version",))
    version = _normalized_version(raw_version, required_version)
    return ToolIdentity(
        name="AutoDock Vina",
        executable=str(path),
        version=version,
        version_output=raw_version,
        sha256=digest,
        required_sha256=required_sha256,
        required_version=required_version,
    )


def verify_openbabel_tool(
    executable: str | Path,
    *,
    required_version: str = EXPECTED_OPENBABEL_VERSION,
    version_output: str | None = None,
    help_output: str | None = None,
    required_options: Sequence[str] = (),
) -> ToolIdentity:
    """Verify Open Babel version and the declared command-line surface."""

    path = _executable_file(executable)
    raw_version = version_output or _probe(path, ("-V",))
    version = _normalized_version(raw_version, required_version)
    option_probe: list[str] = []
    if required_options:
        help_text = help_output or _probe(path, ("--help",))
        option_evidence = help_text
        if "--partialcharge" in required_options and "--partialcharge" not in option_evidence:
            # Open Babel 3.1.1 exposes charge models through the plugin list,
            # not consistently through the generic CLI help text.
            charge_help = _probe(path, ("-L", "charges"))
            if "gasteiger" not in charge_help.lower():
                raise APODOCK001InfrastructureError(
                    "Open Babel Gasteiger charge model is unavailable"
                )
            option_evidence = f"{option_evidence}\n--partialcharge\ngasteiger"
        if "-xr" in required_options and "-xr" not in help_text:
            # ``-xr`` is a PDBQT format option and is exposed by the
            # format-specific help rather than the generic usage text.
            format_help = _probe(path, ("-H", "pdbqt"))
            option_evidence = f"{option_evidence}\n{format_help}"
        for option in required_options:
            if option not in option_evidence:
                raise APODOCK001InfrastructureError(
                    f"Open Babel required option is unavailable: {option}"
                )
            option_probe.append(option)
    return ToolIdentity(
        name="Open Babel",
        executable=str(path),
        version=version,
        version_output=raw_version,
        sha256=sha256_file(path),
        required_sha256=None,
        required_version=required_version,
        option_probe=tuple(option_probe),
    )


def _logical_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"execution plan path must be relative: {value!r}")
    return path.as_posix()


def _path_is_within(candidate: Path, parent: Path) -> bool:
    candidate_resolved = candidate.resolve()
    parent_resolved = parent.resolve()
    return candidate_resolved == parent_resolved or parent_resolved in candidate_resolved.parents


def _case_plan(protocol: Mapping[str, Any], case: Mapping[str, Any]) -> APODOCK001CasePlan:
    case_id = str(case["case_id"])
    bundle_mode = "input_bundle" in protocol
    ligand_filename = case.get("reference_filename")
    if ligand_filename:
        ligand_input = f"reference-sdf/{ligand_filename}" if bundle_mode else f"sources/{ligand_filename}"
        ligand_identity = str(case["reference_sdf_sha256"])
        ligand_kind = "frozen_reference_sdf"
    else:
        ligand_input = (
            "apd010/BEM_ideal.sdf+MAV_ideal.sdf"
            if bundle_mode
            else "derived/APD-010-BEM-MAV-1.0.0.sdf"
        )
        ligand_identity = str(protocol["chemistry"]["apd010"]["output_sdf_sha256"])
        ligand_kind = "frozen_apd010_adapter_output"
    input_hashes = {
        "apo_pdb_sha256": str(case["apo_pdb_sha256"]),
        "holo_pdb_sha256": str(case["holo_pdb_sha256"]),
        "holo_reference_coordinate_hash": str(case["holo_reference_coordinate_hash"]),
        "transformed_holo_reference_coordinate_hash": str(
            case["transformed_holo_reference_coordinate_hash"]
        ),
        "ligand_input_sha256": ligand_identity,
    }
    if "reference_sdf_sha256" in case:
        input_hashes["reference_sdf_sha256"] = str(case["reference_sdf_sha256"])
    chemistry = {
        "kind": ligand_kind,
        "ligand_input_sha256": ligand_identity,
        "chemistry_ready_for_vina": bool(case["chemistry_ready_for_vina"]),
    }
    if case_id == "APD-010":
        chemistry.update(
            {
                "adapter_id": protocol["chemistry"]["apd010"]["adapter_id"],
                "adapter_version": protocol["chemistry"]["apd010"]["adapter_version"],
                "input_identity": protocol["chemistry"]["apd010"]["input_identity"],
                "output_identity": protocol["chemistry"]["apd010"]["output_identity"],
                "structural_identity": protocol["chemistry"]["apd010"]["structural_identity"],
            }
        )
    box = deepcopy(protocol["box"]["cases"][case_id])
    vina = {
        key: deepcopy(protocol["vina"][key])
        for key in (
            "version",
            "binary_sha256",
            "scoring_function",
            "receptor_mode",
            "seed",
            "cpu",
            "exhaustiveness",
            "num_modes",
            "energy_range_kcal_per_mol",
            "flags",
        )
    }
    preparation = {
        "receptor": deepcopy(protocol["receptor_preparation"]),
        "ligand": deepcopy(protocol["ligand_preparation"]),
    }
    return APODOCK001CasePlan(
        case_id=case_id,
        receptor_input=_logical_path(
            f"pdb/{case['apo_pdb_id']}.pdb" if bundle_mode else f"sources/{case['apo_pdb_id']}.pdb"
        ),
        ligand_input=_logical_path(ligand_input),
        input_hashes=input_hashes,
        chemistry=chemistry,
        receptor_prepared_output=_logical_path(f"prepared/{case_id}/receptor.pdbqt"),
        ligand_prepared_output=_logical_path(f"prepared/{case_id}/ligand.pdbqt"),
        raw_vina_output=_logical_path(f"raw/{case_id}/vina_poses.pdbqt"),
        stdout_output=_logical_path(f"logs/{case_id}/vina.stdout"),
        stderr_output=_logical_path(f"logs/{case_id}/vina.stderr"),
        box=box,
        vina=vina,
        preparation=preparation,
    )


def build_execution_plan(
    protocol: Mapping[str, Any],
    runner: APODOCK001Runner,
) -> APODOCK001ExecutionPlan:
    """Build a deterministic plan from the frozen protocol only."""

    manifest = runner.expected_execution_manifest()
    cases = tuple(_case_plan(protocol, case) for case in protocol["benchmark"]["cases"])
    payload = {
        "schema_version": EXECUTION_PLAN_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "protocol_hash": protocol["protocol_hash"],
        "cases": [case.to_dict() for case in cases],
        "execution_manifest": manifest,
    }
    plan_hash = sha256_json(payload)
    return APODOCK001ExecutionPlan(
        schema_version=EXECUTION_PLAN_SCHEMA,
        protocol_id=str(protocol["protocol_id"]),
        protocol_hash=str(protocol["protocol_hash"]),
        planned_run_id=f"{PLANNED_RUN_PREFIX}{plan_hash[:16]}",
        cases=cases,
        execution_manifest=manifest,
    )


def build_vina_command(
    case: APODOCK001CasePlan,
    vina_executable: str | Path,
    *,
    run_root: str | Path,
) -> tuple[str, ...]:
    """Construct the frozen Vina argv without invoking a subprocess."""

    if tuple(case.vina["flags"]) != FROZEN_VINA_FLAGS:
        raise APODOCK001InfrastructureError("Vina flags differ from the frozen contract")
    if case.vina["energy_range_kcal_per_mol"] is not None:
        raise APODOCK001InfrastructureError("energy_range is not allowed by the frozen protocol")
    root = Path(run_root)
    values: tuple[tuple[str, str], ...] = (
        ("--receptor", str(root / case.receptor_prepared_output)),
        ("--ligand", str(root / case.ligand_prepared_output)),
        ("--center_x", str(case.box["center"][0])),
        ("--center_y", str(case.box["center"][1])),
        ("--center_z", str(case.box["center"][2])),
        ("--size_x", str(case.box["size"][0])),
        ("--size_y", str(case.box["size"][1])),
        ("--size_z", str(case.box["size"][2])),
        ("--exhaustiveness", str(case.vina["exhaustiveness"])),
        ("--cpu", str(case.vina["cpu"])),
        ("--seed", str(case.vina["seed"])),
        ("--num_modes", str(case.vina["num_modes"])),
        ("--out", str(root / case.raw_vina_output)),
    )
    command: tuple[str, ...] = (str(vina_executable),) + tuple(
        item for pair in values for item in pair
    )
    if tuple(item for item in command[1:] if item.startswith("--")) != FROZEN_VINA_FLAGS:
        raise APODOCK001InfrastructureError("constructed Vina command contains unexpected flags")
    return command


def verify_prepared_artifact(
    artifact: Mapping[str, Any],
    *,
    expected_case: APODOCK001CasePlan,
    artifact_kind: str | None = None,
    protocol_id: str | None = None,
    planned_run_id: str | None = None,
    expected_destination: str | None = None,
) -> None:
    """Verify a prepared artifact manifest before future execution."""

    if artifact.get("case_id") != expected_case.case_id:
        raise APODOCK001InfrastructureError("prepared artifact case identity mismatch")
    if artifact_kind is not None:
        if artifact_kind not in PREPARED_ARTIFACT_KINDS:
            raise APODOCK001InfrastructureError(
                f"unknown prepared artifact kind: {artifact_kind}"
            )
        expected_source_hashes = _expected_artifact_source_hashes(
            expected_case, artifact_kind
        )
        if artifact.get("artifact_kind") != artifact_kind:
            raise APODOCK001InfrastructureError(
                "prepared artifact kind differs from the plan"
            )
        if artifact.get("source_hashes") != expected_source_hashes:
            raise APODOCK001InfrastructureError(
                "prepared input hashes differ from the plan"
            )
        if artifact.get("chemistry") != expected_case.chemistry:
            raise APODOCK001InfrastructureError(
                "prepared chemistry identity differs from the plan"
            )
        if artifact.get("preparation") != expected_case.preparation[artifact_kind]:
            raise APODOCK001InfrastructureError(
                "preparation contract differs from the plan"
            )
        for key, expected in (
            ("protocol_id", protocol_id),
            ("planned_run_id", planned_run_id),
            ("expected_destination", expected_destination),
        ):
            if expected is not None and artifact.get(key) != expected:
                raise APODOCK001InfrastructureError(
                    f"prepared artifact {key} differs from the plan"
                )
    else:
        # Retain the generic verifier for callers that validate a single
        # legacy prepared artifact.  Prospective execution uses the strict
        # receptor/ligand form above and never takes this compatibility path.
        if artifact.get("source_hashes") != expected_case.input_hashes:
            raise APODOCK001InfrastructureError(
                "prepared input hashes differ from the plan"
            )
        if artifact.get("preparation") != expected_case.preparation:
            raise APODOCK001InfrastructureError(
                "preparation contract differs from the plan"
            )
    output_path = Path(str(artifact.get("output_path", "")))
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise APODOCK001InfrastructureError("prepared artifact is absent or empty")
    observed_hash = sha256_file(output_path)
    if artifact.get("output_sha256") != observed_hash:
        raise APODOCK001InfrastructureError("prepared artifact hash mismatch")


def _expected_artifact_source_hashes(
    case: APODOCK001CasePlan,
    artifact_kind: str,
) -> dict[str, str]:
    if artifact_kind not in PREPARED_ARTIFACT_KINDS:
        raise APODOCK001InfrastructureError(
            f"unknown prepared artifact kind: {artifact_kind}"
        )
    # Each prepared output carries the complete frozen case identity, not
    # only the source file directly consumed by that preparation step. This
    # prevents a valid receptor and ligand from different input identities
    # being combined accidentally.
    return deepcopy(case.input_hashes)


def verify_pristine_run_directory(run_root: str | Path) -> None:
    """Reject a directory that could cause an accidental prospective rerun."""

    root = Path(run_root)
    if not root.exists():
        return
    if not root.is_dir():
        raise ExistingProspectiveRunError(f"run path is not a directory: {root}")
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        raise ExistingProspectiveRunError(f"prospective output directory is not empty: {path}")


def build_environment_manifest(
    *,
    protocol_id: str,
    git_sha: str,
    vina: ToolIdentity | None,
    openbabel: ToolIdentity | None,
) -> dict[str, Any]:
    """Create an operational environment record without changing protocol identity."""

    try:
        import rdkit

        rdkit_version = getattr(rdkit, "__version__", None) or getattr(
            rdkit.rdBase, "rdkitVersion", None
        )
    except ImportError:
        rdkit_version = None
    return {
        "schema_version": "research-os.apodock001.environment.v1",
        "protocol_id": protocol_id,
        "git_sha": git_sha,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "architecture": platform.architecture()[0],
        },
        "rdkit_version": rdkit_version,
        "vina": vina.to_dict() if vina else None,
        "openbabel": openbabel.to_dict() if openbabel else None,
    }


def build_evidence_scaffold(
    plan: APODOCK001ExecutionPlan,
    *,
    git_sha: str,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a no-results evidence scaffold for the future run."""

    required_files = (
        "protocol.json",
        "execution-manifest.json",
        "environment-manifest.json",
        "tool-identities.json",
        "input-identities.json",
        "preparation-manifests.json",
        "chemistry-gate.json",
        "box-manifest.json",
        "parameter-manifest.json",
        "commands.json",
        "stdout/",
        "stderr/",
        "raw-vina/",
        "output-hashes.json",
        "run-manifest.json",
        "raw-results-seal.json",
        "analysis-manifest.json",
    )
    scaffold = {
        "schema_version": EVIDENCE_SCAFFOLD_SCHEMA,
        "status": "NOT_EXECUTED",
        "protocol_id": plan.protocol_id,
        "protocol_hash": plan.protocol_hash,
        "git_sha": git_sha,
        "planned_run_id": plan.planned_run_id,
        "run_id": None,
        "required_files": list(required_files),
        "environment_manifest": deepcopy(dict(environment)),
        "raw_results_sealed": False,
        "results": [],
        "scores": [],
        "poses": [],
        "analysis": None,
    }
    scaffold["scaffold_sha256"] = sha256_json(
        {key: value for key, value in scaffold.items() if key != "scaffold_sha256"}
    )
    return scaffold


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def select_receptor_chain(pdb_text: str, author_chain: str) -> str:
    """Keep only the frozen receptor ATOM chain; no small molecules are added."""

    records: list[str] = []
    for line in pdb_text.splitlines():
        if len(line) < 22 or line[:6].strip() != "ATOM":
            continue
        if line[21].strip() != author_chain:
            continue
        if line[16].strip() not in {"", "A", "1"}:
            continue
        records.append(line)
    if not records:
        raise APODOCK001InfrastructureError(
            f"frozen receptor author chain {author_chain!r} has no ATOM records"
        )
    return "\n".join(records + ["TER", "END"]) + "\n"


def prepare_receptor_input(
    *,
    source_path: str | Path,
    output_pdb_path: str | Path,
    author_chain: str,
    expected_sha256: str,
) -> str:
    """Materialize the frozen chain-cleaned receptor input, without Open Babel."""

    source = Path(source_path)
    if not source.is_file() or sha256_file(source) != expected_sha256:
        raise APODOCK001InfrastructureError("receptor source hash mismatch")
    target = Path(output_pdb_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        select_receptor_chain(source.read_text(encoding="utf-8", errors="replace"), author_chain),
        encoding="utf-8",
    )
    return sha256_file(target)


def prepare_ligand_conformer(
    source_molecule: Chem.Mol,
    output_sdf_path: str | Path,
    *,
    seed: int,
    uff_max_iters: int,
) -> dict[str, Any]:
    """Generate the frozen independent ligand conformer deterministically."""

    if seed != 42 or uff_max_iters != 1000:
        raise APODOCK001InfrastructureError("ligand conformer contract differs from freeze")
    # The existing implementation is the reviewed ETKDGv3/UFF implementation.
    result = generate_independent_conformer(source_molecule, output_sdf_path)
    if result.get("random_seed") != seed:
        raise APODOCK001InfrastructureError("conformer seed mismatch")
    return result


def adapt_apd010_for_execution(
    bem: Any,
    mav: Any,
    *,
    chemistry_contract: Mapping[str, Any],
) -> Any:
    """Return only the frozen BEM+MAV adapter output for APD-010."""

    result = adapt_apd010(bem, mav)
    expected = chemistry_contract
    if result.adapter_id != expected["adapter_id"]:
        raise APODOCK001InfrastructureError("APD-010 adapter identity differs from freeze")
    if result.adapter_version != expected["adapter_version"]:
        raise APODOCK001InfrastructureError("APD-010 adapter version differs from freeze")
    if result.input_identity != expected["input_identity"]:
        raise APODOCK001InfrastructureError("APD-010 adapter input identity differs from freeze")
    if result.output_identity != expected["output_identity"]:
        raise APODOCK001InfrastructureError("APD-010 adapter output identity differs from freeze")
    if chemistry_identity(result.molecule) != expected["output_identity"]:
        raise APODOCK001InfrastructureError("APD-010 chemical graph identity differs from freeze")
    return result.molecule


def prepare_pdbqt(
    *,
    input_path: str | Path,
    output_path: str | Path,
    options: Sequence[str],
    openbabel: OpenBabelEngine,
    protocol_id: str,
) -> OpenBabelResult:
    """Run only the frozen Open Babel preparation contract."""

    allowed = {
        ("-h", "--partialcharge", "gasteiger"),
        ("-h", "--partialcharge", "gasteiger", "-xr"),
    }
    if tuple(options) not in allowed:
        raise APODOCK001InfrastructureError("Open Babel preparation options diverge")
    return openbabel.convert(
        input_path,
        output_path,
        options=tuple(options),
        timeout=120.0,
        protocol_id=protocol_id,
    )


class APODOCK001ExecutionAdapter:
    """Plan and guard one future APODOCK-001 prospective run."""

    def __init__(
        self,
        spec_path: str | Path = DEFAULT_PROTOCOL_PATH,
        *,
        source_root: str | Path = "inputs/apodock001",
        run_root: str | Path = "runs/apodock001-v1.0.1",
        staging_root: str | Path | None = None,
        git_sha: str = "unknown",
    ) -> None:
        self.spec_path = Path(spec_path)
        self.runner = APODOCK001Runner(self.spec_path)
        self.protocol = self.runner.protocol
        self.source_root = Path(source_root)
        if "input_bundle" in self.protocol and self.source_root == Path("inputs/apodock001"):
            self.source_root = Path("inputs/apodock001/v1.0.2")
        if "input_bundle" in self.protocol:
            verify_frozen_input_bundle(self.protocol, self.source_root)
        self.run_root = Path(run_root)
        self.staging_root = (
            Path(staging_root)
            if staging_root is not None
            else self.run_root.parent / f"{self.run_root.name}.staging"
        )
        run_root_resolved = self.run_root.resolve()
        staging_root_resolved = self.staging_root.resolve()
        if run_root_resolved == staging_root_resolved or run_root_resolved in staging_root_resolved.parents:
            raise APODOCK001InfrastructureError(
                "staging_root must be separate from run_root"
            )
        self.git_sha = git_sha
        self.plan = build_execution_plan(self.protocol, self.runner)

    def verify_execution_manifest(self, observed: Mapping[str, Any] | None = None) -> None:
        self.runner.verify_execution_manifest(
            self.plan.execution_manifest if observed is None else observed
        )

    def verify_tools(
        self,
        *,
        vina_executable: str | Path,
        openbabel_executable: str | Path,
        openbabel_help: str | None = None,
    ) -> tuple[ToolIdentity, ToolIdentity]:
        vina = verify_vina_tool(
            vina_executable,
            required_version=str(self.protocol["vina"]["version"]),
            required_sha256=str(self.protocol["vina"]["binary_sha256"]),
        )
        self.runner.verify_tool_identity(
            vina_version=vina.version,
            vina_sha256=vina.sha256 or "",
        )
        required_options = tuple(self.protocol["receptor_preparation"]["options"])
        obabel = verify_openbabel_tool(
            openbabel_executable,
            required_version=str(self.protocol["receptor_preparation"]["binary_version"]),
            help_output=openbabel_help,
            required_options=required_options,
        )
        if obabel.version != EXPECTED_OPENBABEL_VERSION:
            raise APODOCK001InfrastructureError("Open Babel version is not 3.1.1")
        return vina, obabel

    def preflight(
        self,
        *,
        vina: ToolIdentity | None = None,
        openbabel: ToolIdentity | None = None,
        observed_manifest: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if "input_bundle" in self.protocol:
            verify_frozen_input_bundle(self.protocol, self.source_root)
        self.verify_execution_manifest(observed_manifest)
        verify_pristine_run_directory(self.run_root)
        environment = build_environment_manifest(
            protocol_id=self.plan.protocol_id,
            git_sha=self.git_sha,
            vina=vina,
            openbabel=openbabel,
        )
        scaffold = build_evidence_scaffold(
            self.plan,
            git_sha=self.git_sha,
            environment=environment,
        )
        return {
            "status": "READY_FOR_EXPLICIT_AUTHORIZATION",
            "execution_authorized": False,
            "protocol_id": self.plan.protocol_id,
            "protocol_hash": self.plan.protocol_hash,
            "planned_run_id": self.plan.planned_run_id,
            "case_count": len(self.plan.cases),
            "cases": [case.case_id for case in self.plan.cases],
            "run_root": str(self.run_root),
            "staging_root": str(self.staging_root),
            "environment": environment,
            "evidence_scaffold": scaffold,
            "vina_docking_executed": False,
        }

    def build_command(self, case_id: str, vina_executable: str | Path) -> tuple[str, ...]:
        case = next((item for item in self.plan.cases if item.case_id == case_id), None)
        if case is None:
            raise APODOCK001InfrastructureError(f"unknown frozen case: {case_id}")
        return build_vina_command(case, vina_executable, run_root=self.run_root)

    def _verify_prepared_artifact_collection(
        self,
        prepared_artifacts: Mapping[str, Mapping[str, Mapping[str, Any]]],
        *,
        staged: bool,
    ) -> None:
        expected_case_ids = {case.case_id for case in self.plan.cases}
        if set(prepared_artifacts) != expected_case_ids:
            raise APODOCK001InfrastructureError(
                "prepared artifacts must cover exactly APD-001 through APD-010"
            )
        for case in self.plan.cases:
            artifacts = prepared_artifacts[case.case_id]
            if set(artifacts) != set(PREPARED_ARTIFACT_KINDS):
                raise APODOCK001InfrastructureError(
                    f"{case.case_id} must contain exactly one receptor and one ligand artifact"
                )
            for artifact_kind in PREPARED_ARTIFACT_KINDS:
                expected_destination = getattr(
                    case, f"{artifact_kind}_prepared_output"
                )
                verify_prepared_artifact(
                    artifacts[artifact_kind],
                    expected_case=case,
                    artifact_kind=artifact_kind,
                    protocol_id=self.plan.protocol_id,
                    planned_run_id=self.plan.planned_run_id,
                    expected_destination=expected_destination,
                )
                output_path = Path(str(artifacts[artifact_kind]["output_path"])).resolve()
                if staged:
                    expected_staged_path = (
                        self.staging_root / case.case_id / f"{artifact_kind}.pdbqt"
                    ).resolve()
                    if output_path != expected_staged_path:
                        raise APODOCK001InfrastructureError(
                            f"{case.case_id} {artifact_kind} is not at the normative staging path"
                        )
                elif _path_is_within(output_path, self.run_root):
                    raise APODOCK001InfrastructureError(
                        "prepared source artifact must remain outside run_root"
                    )

    def stage_prepared_artifacts(
        self,
        prepared_artifacts: Mapping[str, Mapping[str, Mapping[str, Any]]],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Copy verified prepared inputs into an external immutable staging root."""

        self._verify_prepared_artifact_collection(prepared_artifacts, staged=False)
        verify_pristine_run_directory(self.staging_root)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        staged: dict[str, dict[str, dict[str, Any]]] = {}
        for case in self.plan.cases:
            staged[case.case_id] = {}
            for artifact_kind in PREPARED_ARTIFACT_KINDS:
                source = Path(str(prepared_artifacts[case.case_id][artifact_kind]["output_path"]))
                destination = (
                    self.staging_root / case.case_id / f"{artifact_kind}.pdbqt"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                source_hash = sha256_file(source)
                staged_hash = sha256_file(destination)
                if staged_hash != source_hash:
                    raise APODOCK001InfrastructureError(
                        f"staged {case.case_id} {artifact_kind} hash differs from source"
                    )
                manifest = PreparedArtifact(
                    case_id=case.case_id,
                    artifact_kind=artifact_kind,
                    source_hashes=deepcopy(
                        prepared_artifacts[case.case_id][artifact_kind]["source_hashes"]
                    ),
                    chemistry=deepcopy(case.chemistry),
                    preparation=deepcopy(
                        prepared_artifacts[case.case_id][artifact_kind]["preparation"]
                    ),
                    source_path=str(source),
                    staged_path=str(destination),
                    staged_sha256=staged_hash,
                    expected_destination=getattr(
                        case, f"{artifact_kind}_prepared_output"
                    ),
                    protocol_id=self.plan.protocol_id,
                    planned_run_id=self.plan.planned_run_id,
                )
                staged[case.case_id][artifact_kind] = manifest.to_manifest()
        self._verify_prepared_artifact_collection(staged, staged=True)
        return staged

    def verify_staged_artifacts(
        self,
        staged_artifacts: Mapping[str, Mapping[str, Mapping[str, Any]]],
    ) -> None:
        """Re-verify every staged byte and manifest immediately before the boundary."""

        self._verify_prepared_artifact_collection(staged_artifacts, staged=True)

    def _copy_staged_artifacts_to_run_root(
        self,
        staged_artifacts: Mapping[str, Mapping[str, Mapping[str, Any]]],
    ) -> None:
        for case in self.plan.cases:
            for artifact_kind in PREPARED_ARTIFACT_KINDS:
                artifact = staged_artifacts[case.case_id][artifact_kind]
                source = Path(str(artifact["output_path"]))
                destination = self.run_root / getattr(
                    case, f"{artifact_kind}_prepared_output"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                if sha256_file(destination) != artifact["output_sha256"]:
                    raise APODOCK001InfrastructureError(
                        f"run_root copy changed {case.case_id} {artifact_kind} bytes"
                    )

    @staticmethod
    def _verify_command_inputs(command: Sequence[str]) -> None:
        for flag in ("--receptor", "--ligand"):
            try:
                path = Path(command[command.index(flag) + 1])
            except (ValueError, IndexError) as exc:
                raise APODOCK001InfrastructureError(
                    f"Vina command is missing {flag}"
                ) from exc
            if not path.is_file() or path.stat().st_size == 0:
                raise APODOCK001InfrastructureError(
                    f"Vina command input is absent or empty: {path}"
                )

    def execute_prospective(
        self,
        *,
        vina: ToolIdentity,
        openbabel: ToolIdentity,
        prepared_artifacts: Mapping[str, Mapping[str, Any]],
        authorization: ExecutionAuthorization = ExecutionAuthorization(),
    ) -> dict[str, Any]:
        """Run each frozen case once after a future explicit authorization.

        This method is intentionally not called by the CLI or CI in this
        change. It is the single future entry point that can cross the
        prospective boundary. All receptor/ligand artifacts are first copied
        into and re-verified in the external staging root; only then is the
        run lock created and the prepared set copied into ``run_root``. A
        failed case is recorded once and is never retried here.
        """

        authorization.require(f"APODOCK-001-v{self.protocol['protocol_version']}")
        if "input_bundle" in self.protocol:
            verify_frozen_input_bundle(self.protocol, self.source_root)
        self.verify_execution_manifest()
        if vina.version != str(self.protocol["vina"]["version"]):
            raise APODOCK001InfrastructureError("Vina identity is not frozen")
        self.runner.verify_tool_identity(
            vina_version=vina.version,
            vina_sha256=vina.sha256 or "",
        )
        if openbabel.version != EXPECTED_OPENBABEL_VERSION:
            raise APODOCK001InfrastructureError("Open Babel identity is not frozen")
        staged_artifacts = self.stage_prepared_artifacts(prepared_artifacts)
        self.verify_staged_artifacts(staged_artifacts)
        verify_pristine_run_directory(self.run_root)

        self.run_root.mkdir(parents=True, exist_ok=False)
        lock = {
            "schema_version": "research-os.apodock001.execution-lock.v1",
            "protocol_id": self.plan.protocol_id,
            "planned_run_id": self.plan.planned_run_id,
            "git_sha": self.git_sha,
            "prospective_execution_started": True,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json(self.run_root / "prospective-run.lock", lock)
        self._copy_staged_artifacts_to_run_root(staged_artifacts)

        records: list[dict[str, Any]] = []
        for case in self.plan.cases:
            command = build_vina_command(case, vina.executable, run_root=self.run_root)
            self._verify_command_inputs(command)
            stdout_path = self.run_root / case.stdout_output
            stderr_path = self.run_root / case.stderr_output
            raw_path = self.run_root / case.raw_vina_output
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            started_at = datetime.now(timezone.utc).isoformat()
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    shell=False,
                    timeout=900.0,
                )
                stdout = completed.stdout or ""
                stderr = completed.stderr or ""
                returncode = completed.returncode
            except subprocess.TimeoutExpired as exc:
                stdout = str(exc.stdout or "")
                stderr = str(exc.stderr or "")
                returncode = -1
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            records.append(
                {
                    "case_id": case.case_id,
                    "command": list(command),
                    "started_at": started_at,
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "returncode": returncode,
                    "status": "COMPLETED" if returncode == 0 and raw_path.is_file() else "FAILED",
                    "stdout_path": str(stdout_path),
                    "stdout_sha256": sha256_file(stdout_path),
                    "stderr_path": str(stderr_path),
                    "stderr_sha256": sha256_file(stderr_path),
                    "raw_output_path": str(raw_path),
                    "raw_output_sha256": sha256_file(raw_path) if raw_path.is_file() else None,
                }
            )

        raw_hashes = {record["case_id"]: record["raw_output_sha256"] for record in records}
        raw_seal = sha256_json(raw_hashes)
        manifest = {
            "schema_version": "research-os.apodock001.run-manifest.v1",
            "status": "RAW_RESULTS_SEALED",
            "protocol_id": self.plan.protocol_id,
            "protocol_hash": self.plan.protocol_hash,
            "planned_run_id": self.plan.planned_run_id,
            "run_id": None,
            "git_sha": self.git_sha,
            "tool_identities": {
                "vina": vina.to_dict(),
                "openbabel": openbabel.to_dict(),
            },
            "cases": records,
            "raw_results_sealed": True,
            "raw_results_seal_sha256": raw_seal,
            "analysis_manifest": None,
        }
        run_digest = sha256_json(manifest)
        manifest["run_id"] = f"research-os.apodock001.run.v1+{run_digest[:16]}"
        write_json(self.run_root / "run-manifest.json", manifest)
        write_json(
            self.run_root / "raw-results-seal.json",
            {
                "schema_version": "research-os.apodock001.raw-results-seal.v1",
                "status": "SEALED",
                "protocol_id": self.plan.protocol_id,
                "run_id": manifest["run_id"],
                "raw_results_seal_sha256": raw_seal,
                "raw_output_hashes": raw_hashes,
            },
        )
        return manifest

    def execute_case(
        self,
        case_id: str,
        vina_executable: str | Path,
        *,
        authorization: ExecutionAuthorization = ExecutionAuthorization(),
    ) -> subprocess.CompletedProcess[str]:
        """Execute exactly one case only after a future explicit authorization.

        This method is intentionally never called by the infrastructure CLI or
        workflow.  The authorization check precedes command construction and
        subprocess creation, so a normal/default path cannot start Vina.
        """

        authorization.require()
        self.preflight()
        command = self.build_command(case_id, vina_executable)
        self._verify_command_inputs(command)
        return subprocess.run(command, capture_output=True, text=True, check=False, shell=False)


__all__ = [
    "APODOCK001CasePlan",
    "APODOCK001ExecutionAdapter",
    "APODOCK001ExecutionPlan",
    "APODOCK001InfrastructureError",
    "ExecutionAuthorization",
    "ExecutionAuthorizationError",
    "ExistingProspectiveRunError",
    "PreparedArtifact",
    "ToolIdentity",
    "build_environment_manifest",
    "build_evidence_scaffold",
    "build_execution_plan",
    "build_vina_command",
    "adapt_apd010_for_execution",
    "prepare_ligand_conformer",
    "prepare_pdbqt",
    "prepare_receptor_input",
    "select_receptor_chain",
    "verify_openbabel_tool",
    "verify_prepared_artifact",
    "verify_pristine_run_directory",
    "verify_vina_tool",
    "write_json",
]
