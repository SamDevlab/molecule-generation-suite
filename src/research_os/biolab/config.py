from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import shutil
from typing import Any, Mapping

from research_os.docking.schema import GridBox


class BiolabConfigError(ValueError):
    """Raised when a Biolab configuration is incomplete or malformed."""


@dataclass(frozen=True)
class VinaConfig:
    executable: str | None = None
    exhaustiveness: int = 8
    cpu: int = 1

    def __post_init__(self) -> None:
        if self.exhaustiveness <= 0 or self.cpu <= 0:
            raise BiolabConfigError("vina exhaustiveness and cpu must be positive")


@dataclass(frozen=True)
class OpenBabelConfig:
    executable: str | None = None


@dataclass(frozen=True)
class ComputeConfig:
    max_workers: int = 1

    def __post_init__(self) -> None:
        if self.max_workers <= 0:
            raise BiolabConfigError("compute.max_workers must be positive")


@dataclass(frozen=True)
class DockingConfig:
    replicas: int = 1

    def __post_init__(self) -> None:
        if self.replicas <= 0:
            raise BiolabConfigError("docking.replicas must be positive")


@dataclass(frozen=True)
class TargetConfig:
    target_id: str
    role: str
    receptor: str
    grid: GridBox
    species: str | None = None
    structure_id: str | None = None
    structure_source: str | None = None

    def receptor_path(self, *, base_dir: str | Path | None = None) -> Path:
        path = Path(self.receptor)
        return (Path(base_dir) / path).resolve() if base_dir is not None and not path.is_absolute() else path


@dataclass(frozen=True)
class BiolabConfig:
    vina: VinaConfig
    openbabel: OpenBabelConfig
    compute: ComputeConfig
    docking: DockingConfig
    targets: dict[str, TargetConfig] = field(default_factory=dict)
    source_path: str | None = None

    def target(self, target_id: str) -> TargetConfig:
        try:
            return self.targets[target_id.lower()]
        except KeyError as exc:
            raise BiolabConfigError(f"unknown Biolab target: {target_id}") from exc

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, source_path: str | Path | None = None) -> "BiolabConfig":
        def section(name: str) -> Mapping[str, Any]:
            value = raw.get(name, {})
            if not isinstance(value, Mapping):
                raise BiolabConfigError(f"{name} must be a mapping")
            return value

        vina = section("vina")
        openbabel = section("openbabel")
        compute = section("compute")
        docking = section("docking")
        raw_targets = raw.get("targets", {})
        if not isinstance(raw_targets, Mapping):
            raise BiolabConfigError("targets must be a mapping")

        targets: dict[str, TargetConfig] = {}
        for target_id, target_raw in raw_targets.items():
            if not isinstance(target_raw, Mapping):
                raise BiolabConfigError(f"target {target_id} must be a mapping")
            grid = _grid_from_mapping(target_raw.get("grid", {}), target_id=str(target_id))
            receptor = target_raw.get("receptor")
            role = target_raw.get("role")
            if not receptor or not role:
                raise BiolabConfigError(f"target {target_id} requires role and receptor")
            key = str(target_id).strip().lower()
            if not key:
                raise BiolabConfigError("target id cannot be empty")
            targets[key] = TargetConfig(key, str(role), str(receptor), grid, _optional_str(target_raw.get("species")), _optional_str(target_raw.get("structure_id")), _optional_str(target_raw.get("structure_source")))

        return cls(
            vina=VinaConfig(
                executable=_optional_str(vina.get("executable")),
                exhaustiveness=int(vina.get("exhaustiveness", 8)),
                cpu=int(vina.get("cpu", 1)),
            ),
            openbabel=OpenBabelConfig(executable=_optional_str(openbabel.get("executable"))),
            compute=ComputeConfig(max_workers=int(compute.get("max_workers", 1))),
            docking=DockingConfig(replicas=int(docking.get("replicas", 1))),
            targets=targets,
            source_path=str(source_path) if source_path is not None else None,
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _grid_from_mapping(raw: Any, *, target_id: str) -> GridBox:
    if not isinstance(raw, Mapping):
        raise BiolabConfigError(f"target {target_id}.grid must be a mapping")
    center = raw.get("center")
    size = raw.get("size")
    if center is not None or size is not None:
        if not isinstance(center, (list, tuple)) or len(center) != 3:
            raise BiolabConfigError(f"target {target_id}.grid.center must contain three values")
        if not isinstance(size, (list, tuple)) or len(size) != 3:
            raise BiolabConfigError(f"target {target_id}.grid.size must contain three values")
        values = [*center, *size]
    else:
        values = [raw.get(key) for key in ("center_x", "center_y", "center_z", "size_x", "size_y", "size_z")]
    if any(value is None for value in values):
        raise BiolabConfigError(f"target {target_id}.grid requires center and size")
    try:
        return GridBox(*(float(value) for value in values))
    except (TypeError, ValueError) as exc:
        raise BiolabConfigError(f"target {target_id}.grid contains non-numeric values") from exc


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return {}
    if value.startswith(("'", '"')) and value.endswith(value[0]):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        return [_parse_scalar(item) for item in value[1:-1].split(",") if item.strip()]
    lowered = value.lower()
    if lowered in {"null", "none", "~"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return float(value) if any(char in value for char in ".eE") else int(value)
    except ValueError:
        return value


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Small dependency-free fallback for the mapping-shaped project config.

    PyYAML is used when installed.  The fallback intentionally supports only
    mappings and inline lists, which keeps configuration loading available in
    the minimal Core installation without pretending to be a full YAML parser.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if ":" not in line:
            raise BiolabConfigError("fallback YAML parser accepts mapping entries only")
        key, raw_value = line.strip().split(":", 1)
        key = key.strip()
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if raw_value.strip():
            parent[key] = _parse_scalar(raw_value)
        else:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
    return root


def load_biolab_config(path: str | Path) -> BiolabConfig:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        raw = _parse_simple_yaml(text)
    else:
        raw = yaml.safe_load(text) or {}
    if not isinstance(raw, Mapping):
        raise BiolabConfigError("Biolab configuration root must be a mapping")
    return BiolabConfig.from_mapping(raw, source_path=source)


# Short alias for callers that already use generic config terminology.
load_config = load_biolab_config


def resolve_executable(executable: str | None) -> str | None:
    """Resolve a configured executable without inventing a fallback result."""
    if not executable:
        return None
    return shutil.which(executable) or executable if Path(executable).is_file() else shutil.which(executable)
