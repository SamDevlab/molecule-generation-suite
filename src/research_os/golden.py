"""Safe, deterministic end-to-end fixture for the Research OS v1.4 milestone."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import uuid

from research_os.bundles import BundleVerificationResult, ResearchBundle, verify_bundle
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.datasets import DatasetManifest, DatasetRegistry, DatasetRegistryError, DatasetSourceType
from research_os.environment import EnvironmentManifest, capture_environment
from research_os.knowledge.claims import ClaimStatus, ScientificClaim
from research_os.combustion import CombustionLab
from research_os.fuel import FuelLab
from research_os.labs.base import Lab
from research_os.orchestration import LabRegistry, PlanStep, PlanRun, ResearchOrchestrator, build_fuel_combustion_thermal_propulsion_plan, default_registry
from research_os.proof.engine import ProofEngine
from research_os.proof.rules import Rule
from research_os.propulsion import PropulsionLab
from research_os.thermal import ThermalLab


class GoldenFixtureLab(Lab):
    """A clearly-labelled deterministic test fixture, never an E3 physics engine."""

    evidence_kind = "synthetic_test_evidence"

    def __init__(self, name: str, output: dict[str, Any]):
        self.name = name
        self.output = dict(output)

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return dict(raw)

    def rules(self) -> list[Rule]:
        return [Rule("GOLDEN-FIXTURE-001", "Golden fixture inputs are present", lambda context, evidence: GateResult("GATE-GOLDEN-FIXTURE", "GOLDEN-FIXTURE-001", GateStatus.PASS, "deterministic test fixture accepted"))]

    def run(self, raw: dict[str, Any], experiment: str = "golden_fixture") -> RunManifest:
        manifest = RunManifest(
            lab=self.name,
            experiment=experiment,
            inputs=self.normalize(raw),
            config={"engine": "GoldenFixtureLab", "engine_mode": "test_fixture", "seed": 42},
        )
        ProofEngine().evaluate(manifest, self.rules())
        evidence = Evidence(
            evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}",
            kind=self.evidence_kind,
            level=EvidenceLevel.TEST_SYNTHETIC,
            source="golden_workflow test_fixture",
            payload={"seed": 42, "output": self.output, "limitations": ["synthetic fixture; not a physical or experimental result"]},
        )
        manifest.evidence.append(evidence)
        manifest.gates.append(GateResult("GATE-GOLDEN-FIXTURE", "GOLDEN-FIXTURE-002", GateStatus.PASS, "synthetic test evidence recorded", evidence_ids=(evidence.evidence_id,)))
        return manifest


class GoldenCombustionLab(GoldenFixtureLab):
    def __init__(self):
        super().__init__("CombustionLab", {"adiabatic_temperature_k": 1800.0, "model": "fixture_only"})


class GoldenPropulsionLab(GoldenFixtureLab):
    def __init__(self):
        super().__init__("PropulsionLab", {"ideal_kinetic_specific_impulse_s": 220.0, "model": "fixture_only"})


@dataclass(frozen=True)
class GoldenWorkflowResult:
    mode: str
    plan_run: PlanRun
    bundle: ResearchBundle
    dataset_manifest: DatasetManifest
    environment: EnvironmentManifest
    claim: ScientificClaim
    verification: BundleVerificationResult

    @property
    def passed(self) -> bool:
        return self.plan_run.passed and self.verification.passed


def run_golden_workflow(
    output_root: str | Path,
    *,
    mode: str = "stub",
    repo_root: str | Path | None = None,
    force_missing_engine: bool = False,
) -> GoldenWorkflowResult:
    """Run the safe Fuel -> Combustion -> Thermal -> Propulsion proof fixture."""
    if mode not in {"stub", "real"}:
        raise ValueError("golden workflow mode must be 'stub' or 'real'")
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    data_root = output / "datasets"
    csv_path = Path(__file__).resolve().parents[2] / "examples" / "golden_workflow" / "data" / "golden_fuels.csv"
    registry = DatasetRegistry(root=data_root)
    if "1" in registry.list_versions("golden-fuels"):
        dataset = registry.get("golden-fuels", "1")
        if not registry.verify_dataset("golden-fuels", "1"):
            raise DatasetRegistryError("existing golden dataset artifact does not match its manifest")
    else:
        dataset = registry.register_dataset(
            dataset_id="golden-fuels",
            version="1",
            schema_id="golden-fuels-v1",
            path=csv_path,
            curated_path=data_root / "curated" / "golden_fuels.parquet",
            transformation_run_id="RUN-GOLDEN-DATASET-42",
            sources=("golden_workflow_fixture",),
            source_types=(DatasetSourceType.TEST_SYNTHETIC,),
            evidence_levels=(EvidenceLevel.TEST_SYNTHETIC,),
            synthetic_fraction=1.0,
            notes="Safe infrastructure fixture; not experimental ground truth.",
        )
    environment = capture_environment(repo_root=repo_root or Path(__file__).resolve().parents[2])

    fuel = {"components": [{"name": "ethanol fixture", "smiles": "CCO", "fraction": 1.0}], "fraction_basis": "mole"}
    combustion = {"fuel": "CH4:1", "oxidizer": "O2:1", "equivalence_ratio": 1.0, "temperature_k": 298.15, "pressure_pa": 101325.0}
    thermal = {"hot_temperature_k": 1200.0, "cold_temperature_k": 400.0, "conductivity_w_mk": 16.0, "thickness_m": 0.01, "area_m2": 1.0}
    propulsion = {"combustion": combustion, "exit_pressure_pa": 10000.0, "nozzle_efficiency": 0.9}
    plan = build_fuel_combustion_thermal_propulsion_plan(fuel=fuel, combustion=combustion, thermal=thermal, propulsion=propulsion)
    if mode == "stub":
        lab_registry = LabRegistry()
        lab_registry.register(GoldenFixtureLab("FuelLab", {"composition_validated": True}))
        lab_registry.register(GoldenCombustionLab())
        lab_registry.register(GoldenFixtureLab("ThermalLab", {"heat_rate_w": 1280000.0}))
        lab_registry.register(GoldenPropulsionLab())
    elif force_missing_engine:
        class MissingEngine:
            available = False
            version = None

        missing_combustion = CombustionLab(engine=MissingEngine())
        lab_registry = LabRegistry()
        lab_registry.register(FuelLab())
        lab_registry.register(missing_combustion)
        lab_registry.register(ThermalLab())
        lab_registry.register(PropulsionLab(combustion_lab=missing_combustion))
    else:
        lab_registry = default_registry()
    plan_run = ResearchOrchestrator(lab_registry).run(plan)
    for child in plan_run.runs.values():
        child.attach_dataset(dataset)
        child.attach_environment(environment)
        if child.lifecycle.value in {"COMPLETED", "FAILED", "INDETERMINATE"}:
            child.seal()

    evidence_ids = tuple(evidence.evidence_id for child in plan_run.runs.values() for evidence in child.evidence)
    claim = ScientificClaim(
        statement="The recorded computational protocol completed successfully for the supplied test inputs." if plan_run.passed else "The recorded computational protocol did not complete because a required gate was not satisfied.",
        run_id=plan_run.plan_id,
        evidence_ids=evidence_ids,
        minimum_evidence_level=EvidenceLevel.TEST_SYNTHETIC if mode == "stub" else EvidenceLevel.E3_PHYSICS,
        status=ClaimStatus.SUPPORTED if plan_run.passed else ClaimStatus.INSUFFICIENT_EVIDENCE,
        limitations=("Stub mode contains synthetic test evidence and is not a physical or experimental result.", "Real mode remains limited by the availability and validity domain of external engines."),
        conditions={"mode": mode, "seed": 42, "dataset_id": dataset.dataset_id, "dataset_version": dataset.version},
    )
    bundle = ResearchBundle.create(plan_run, output / "runs", environment=environment, dataset_manifests=(dataset,), claims=(claim,))
    verification = verify_bundle(bundle.root)
    return GoldenWorkflowResult(mode, plan_run, bundle, dataset, environment, claim, verification)


def run_deliberate_failure(output_root: str | Path, *, repo_root: str | Path | None = None) -> GoldenWorkflowResult:
    """Run real mode; absent Cantera must remain INDETERMINATE and skip descendants."""
    return run_golden_workflow(output_root, mode="real", repo_root=repo_root, force_missing_engine=True)
