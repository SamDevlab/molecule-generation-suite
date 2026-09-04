"""Safe adapter for the NASA PCoE random-walk MATLAB battery artifact."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any
import zipfile

from research_os.core.hashing import sha256_file
from research_os.core.types import EvidenceLevel
from research_os.resolution.models import BatteryDatasetAssessment, ElectrochemicalObservation, PublicDatasetArtifact, UNKNOWN


@dataclass(frozen=True)
class BatteryAnalysisResult:
    artifact: PublicDatasetArtifact
    observations: tuple[ElectrochemicalObservation, ...]
    summary: dict[str, Any]
    assessment: BatteryDatasetAssessment


def analyze_nasa_pcoe_rw3(archive_path: str | Path, *, source_id: str = "SRC-NASA-PCOE-RW3", dataset_id: str = "battery-nasa-pcoe-rw3", source_url: str = "https://data.nasa.gov/docs/legacy/ames/3.Battery_Uniform_Distribution_Variable_Charge_Room_Temp_DataSet_2Post.zip", license_name: str = "https://www.usa.gov/government-works", max_observations_per_cell: int = 3) -> BatteryAnalysisResult:
    """Read the real MATLAB members and produce measured step summaries.

    Archive entries are read as bytes and passed to scipy's MATLAB reader;
    scripts and R code shipped beside the data are never executed.
    """
    path = Path(archive_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = sha256_file(path)
    retrieved_at = "UNKNOWN"
    manifest_path = path.with_name(path.stem + ".manifest.json")
    if manifest_path.is_file():
        try:
            retrieved_at = str(json.loads(manifest_path.read_text(encoding="utf-8")).get("retrieved_at") or "UNKNOWN")
        except (OSError, ValueError, TypeError):
            retrieved_at = "UNKNOWN"
    observations: list[ElectrochemicalObservation] = []
    cell_summary: dict[str, Any] = {}
    schema = {"matlab_top_level": ["procedure", "description", "step"], "step_fields": ["comment", "type", "time", "relativeTime", "voltage", "current", "temperature", "date"]}
    units = {"relativeTime": "s", "time": "s", "voltage": "V", "current": "A", "temperature": "degC"}
    try:
        from scipy.io import loadmat
    except ImportError:
        artifact = PublicDatasetArtifact(dataset_id, "NASA PCoE RW3", source_id, source_url, license_name, retrieved_at, "ARTIFACT_RETRIEVED_PARSER_NOT_CONFIGURED", str(path.resolve()), digest, path.stat().st_size, schema, units, {"temperature": "room temperature procedure", "discharge_cutoff": "3.2 V", "random_walk_current": "0.5-4 A"}, (source_id, source_url), ("scipy is required for MATLAB member parsing",))
        assessment = BatteryDatasetAssessment(dataset_id, artifact, (), EvidenceLevel.E0_HEURISTIC, "INSUFFICIENT_EVIDENCE", {"parser": "scipy unavailable"}, ("Artifact hash is verified, but no observations were parsed.",))
        return BatteryAnalysisResult(artifact, (), {}, assessment)
    with zipfile.ZipFile(path) as archive:
        mat_names = sorted(name for name in archive.namelist() if name.lower().endswith(".mat"))
        for member in mat_names:
            cell_id = Path(member).stem
            raw = loadmat(BytesIO(archive.read(member)), squeeze_me=True, struct_as_record=False)
            data = raw.get("data")
            if data is None:
                continue
            steps = getattr(data, "step", ())
            if not hasattr(steps, "__len__") or isinstance(steps, (str, bytes)):
                steps = (steps,)
            step_count = len(steps)
            types: dict[str, int] = {}
            temperatures: list[float] = []
            invalid_temperature_count = 0
            currents: list[float] = []
            voltages: list[float] = []
            durations: list[float] = []
            for index, step in enumerate(steps):
                operation = str(getattr(step, "type", UNKNOWN))
                comment = str(getattr(step, "comment", UNKNOWN))
                types[operation] = types.get(operation, 0) + 1
                raw_temperatures = _finite_values(getattr(step, "temperature", None))
                valid_temperatures = [item for item in raw_temperatures if -100.0 <= item <= 100.0]
                invalid_temperature_count += len(raw_temperatures) - len(valid_temperatures)
                temperature = _safe_mean(valid_temperatures)
                current = _finite_mean(getattr(step, "current", None))
                voltage = _finite_mean(getattr(step, "voltage", None))
                relative_time = _finite_last(getattr(step, "relativeTime", None))
                for bucket, value in ((temperatures, temperature), (currents, current), (voltages, voltage), (durations, relative_time)):
                    if value is not None:
                        bucket.append(value)
                if len(observations) < max_observations_per_cell * max(1, len(mat_names)):
                    observations.append(ElectrochemicalObservation(
                        observation_id=f"{dataset_id.upper()}-{cell_id}-STEP-{index:05d}",
                        dataset_id=dataset_id,
                        source_id=source_id,
                        cell_id=cell_id,
                        cycle_index=index,
                        operation={"C": "charge", "D": "discharge", "R": "rest"}.get(operation, operation),
                        temperature_c=temperature,
                        current_a=current,
                        voltage_v=voltage,
                        capacity_ah=None,
                        resistance_ohm=None,
                        time_s=relative_time,
                        units={"temperature_c": "degC", "current_a": "A", "voltage_v": "V", "time_s": "s", "capacity_ah": "Ah", "resistance_ohm": "ohm"},
                        conditions={"procedure": str(getattr(data, "procedure", UNKNOWN)), "step_comment": comment, "cell_id": cell_id},
                        method="NASA PCoE MATLAB step summary; arithmetic mean and final relativeTime",
                        locator=f"{member}:data.step[{index}]",
                        evidence_level=EvidenceLevel.E4_CURATED_EXPERIMENTAL,
                    ))
            cell_summary[cell_id] = {"step_count": step_count, "operation_counts": types, "temperature_mean_c": _safe_mean(temperatures), "current_mean_a": _safe_mean(currents), "voltage_mean_v": _safe_mean(voltages), "duration_mean_s": _safe_mean(durations), "invalid_temperature_samples_excluded": invalid_temperature_count, "procedure": str(getattr(data, "procedure", UNKNOWN))}
    artifact = PublicDatasetArtifact(dataset_id, "NASA PCoE RW3 room-temperature random-walk battery artifact", source_id, source_url, license_name, retrieved_at, "ARTIFACT_RETRIEVED_AND_PARSED", str(path.resolve()), digest, path.stat().st_size, schema, units, {"procedure": "room temperature random walk", "discharge_cutoff": "3.2 V", "random_walk_current": "0.5-4 A", "reference_interval": "after every 50 RW cycles"}, (source_id, source_url), ("Capacity and uncertainty are not fields in the parsed step schema and remain UNKNOWN.", "The derived summaries are descriptive and do not establish a predictive degradation model."))
    summary = {"cell_count": len(cell_summary), "cells": cell_summary, "observation_sample_count": len(observations), "total_step_count": sum(item["step_count"] for item in cell_summary.values()), "missing_fields": ["capacity_ah", "resistance_ohm", "uncertainty"], "analysis_protocol": "per-step measured-array summary; nonphysical temperature sentinel values outside [-100,100] degC excluded; no imputation"}
    assessment = BatteryDatasetAssessment(dataset_id, artifact, tuple(item.observation_id for item in observations), EvidenceLevel.E4_CURATED_EXPERIMENTAL, "PARTIALLY_RESOLVED", summary, ("Artifact and measured voltage/current/temperature/time step fields were parsed.", "A condition-complete degradation trajectory still requires capacity and uncertainty treatment; they were not invented.",))
    return BatteryAnalysisResult(artifact, tuple(observations), summary, assessment)


def _finite_values(value: Any) -> list[float]:
    try:
        flat = getattr(value, "flat", None)
        values = [float(item) for item in (flat if flat is not None else [value])]
    except (TypeError, ValueError):
        try:
            values = [float(value)]
        except (TypeError, ValueError):
            return []
    return [item for item in values if math.isfinite(item)]


def _finite_mean(value: Any) -> float | None:
    values = _finite_values(value)
    return mean(values) if values else None


def _finite_last(value: Any) -> float | None:
    values = _finite_values(value)
    return values[-1] if values else None


def _safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None
