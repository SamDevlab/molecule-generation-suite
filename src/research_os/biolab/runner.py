from __future__ import annotations

from pathlib import Path
from typing import Any
import subprocess

from research_os.biolab.config import BiolabConfig, resolve_executable
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.docking.lab import DockingLab
from research_os.engines.openbabel import OpenBabelEngine
from research_os.engines.vina import VinaEngine


class BiolabRunner:
    """Run configured target-specific docking while preserving fail-closed semantics."""

    def __init__(self, config: BiolabConfig, *, vina_engine=None, openbabel_engine=None):
        self.config = config
        self.vina_engine = vina_engine or VinaEngine(resolve_executable(config.vina.executable))
        self.openbabel_engine = openbabel_engine or OpenBabelEngine(config.openbabel.executable)

    def target_request(self, target_id: str, *, ligand_path: str | Path, output_path: str | Path | None = None, seed: int = 42) -> dict[str, Any]:
        target = self.config.target(target_id)
        base_dir = Path(self.config.source_path).parent.parent if self.config.source_path else None
        return {
            "target_id": target.target_id,
            "receptor_path": target.receptor_path(base_dir=base_dir),
            "ligand_path": ligand_path,
            "grid": target.grid.to_dict(),
            "exhaustiveness": self.config.vina.exhaustiveness,
            "cpu": self.config.vina.cpu,
            "seed": seed,
            "output_path": output_path,
            "species": target.species,
            "require_species": target.species is not None,
            "role": target.role,
            "receptor_metadata": {"species": target.species, "structure_id": target.structure_id, "source": target.structure_source},
        }

    def run_target(self, target_id: str, *, ligand_path: str | Path, output_path: str | Path | None = None, experiment: str = "configured_docking") -> RunManifest:
        target = self.config.target(target_id)
        if self.config.docking.replicas == 1:
            return DockingLab(engine=self.vina_engine).run(self.target_request(target_id, ligand_path=ligand_path, output_path=output_path), experiment=experiment)

        manifest = RunManifest(
            lab="Biolab",
            experiment=experiment,
            inputs={"target_id": target.target_id, "ligand_path": str(ligand_path), "replicas": self.config.docking.replicas},
            config={"target_role": target.role, "grid": target.grid.to_dict(), "vina": self.config.vina.__dict__},
        )
        for replica in range(self.config.docking.replicas):
            replica_output = output_path
            if output_path is not None:
                output = Path(output_path)
                replica_output = output.with_name(f"{output.stem}_rep{replica}{output.suffix}")
            run = DockingLab(engine=self.vina_engine).run(self.target_request(target_id, ligand_path=ligand_path, output_path=replica_output, seed=42 + replica), experiment=f"{experiment}_replica_{replica}")
            manifest.evidence.extend(run.evidence)
            manifest.gates.extend(run.gates)
            if not run.passed:
                return manifest
        manifest.gates.append(GateResult("GATE-BIOLAB-REPLICAS", "BIOLAB-REPLICA-001", GateStatus.PASS, "all configured docking replicas completed", evidence_ids=tuple(e.evidence_id for e in manifest.evidence)))
        return manifest

    def convert_with_openbabel(self, input_path: str | Path, output_path: str | Path, *, options: tuple[str, ...] = ()) -> RunManifest:
        manifest = RunManifest(lab="Biolab", experiment="openbabel_conversion", inputs={"input_path": str(input_path), "output_path": str(output_path), "options": list(options)}, config={"engine": "Open Babel", "engine_version": self.openbabel_engine.version})
        if not self.openbabel_engine.available:
            manifest.gates.append(GateResult("GATE-BIOLAB-ENGINE", "BIOLAB-OPENBABEL-001", GateStatus.INDETERMINATE, "Open Babel unavailable; conversion was not executed"))
            return manifest
        try:
            result = self.openbabel_engine.convert(input_path, output_path, options=options)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            manifest.gates.append(GateResult("GATE-BIOLAB-ENGINE", "BIOLAB-OPENBABEL-002", GateStatus.FAIL, "Open Babel conversion failed", diagnostics={"error_type": type(exc).__name__, "error": str(exc)}))
            return manifest
        if result.returncode != 0:
            manifest.gates.append(GateResult("GATE-BIOLAB-ENGINE", "BIOLAB-OPENBABEL-002", GateStatus.FAIL, "Open Babel returned a non-zero status", diagnostics={"returncode": result.returncode, "stderr": result.stderr[-2000:]}))
            return manifest
        evidence = Evidence(evidence_id=f"EVD-{manifest.run_id}", kind="openbabel_conversion", level=EvidenceLevel.E2_COMPUTATIONAL, source=f"{result.engine} {result.engine_version or 'unknown'}", payload=result.__dict__)
        manifest.evidence.append(evidence)
        manifest.gates.append(GateResult("GATE-BIOLAB-ENGINE", "BIOLAB-OPENBABEL-002", GateStatus.PASS, "Open Babel conversion completed", evidence_ids=(evidence.evidence_id,)))
        return manifest
