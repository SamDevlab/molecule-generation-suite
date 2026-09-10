from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import shutil
from typing import Iterable


@dataclass(frozen=True)
class ExecutableResolution:
    name: str
    available: bool
    path: str | None
    source: str
    diagnostic: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _usable_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if os.name == "nt":
        return True
    return os.access(path, os.X_OK)


def resolve_executable(
    name: str,
    *,
    env_var: str,
    bundled_candidates: Iterable[str | Path] = (),
    path_candidates: Iterable[str] = (),
    environment: dict[str, str] | None = None,
) -> ExecutableResolution:
    """Resolve an external executable without machine-specific hard-coded paths.

    Precedence is explicit environment override -> declared bundled candidates -> PATH.
    An explicitly configured but invalid environment override is fail-closed and does
    not silently fall back to another executable.
    """

    env = os.environ if environment is None else environment
    explicit = env.get(env_var)
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if _usable_file(candidate):
            return ExecutableResolution(name, True, str(candidate), f"env:{env_var}")
        return ExecutableResolution(
            name,
            False,
            str(candidate),
            f"env:{env_var}",
            "explicit executable override is missing or not executable",
        )

    for raw in bundled_candidates:
        candidate = Path(raw).expanduser().resolve()
        if _usable_file(candidate):
            return ExecutableResolution(name, True, str(candidate), "bundled")

    names = tuple(path_candidates) or (name,)
    for candidate_name in names:
        resolved = shutil.which(candidate_name)
        if resolved:
            return ExecutableResolution(name, True, str(Path(resolved).resolve()), "PATH")

    return ExecutableResolution(
        name,
        False,
        None,
        "unresolved",
        f"set {env_var} or install one of {', '.join(names)} on PATH",
    )


def require_executable(resolution: ExecutableResolution) -> str:
    if not resolution.available or resolution.path is None:
        raise FileNotFoundError(
            f"{resolution.name} unavailable: {resolution.diagnostic or 'no executable resolved'}"
        )
    return resolution.path


def biolab_preflight(
    base_dir: str | Path,
    *,
    environment: dict[str, str] | None = None,
) -> dict[str, object]:
    base = Path(base_dir).expanduser().resolve()
    vina = resolve_executable(
        "vina",
        env_var="RESEARCH_OS_VINA",
        bundled_candidates=(base / "vina", base / "vina.exe"),
        path_candidates=("vina", "vina.exe"),
        environment=environment,
    )
    obabel = resolve_executable(
        "obabel",
        env_var="RESEARCH_OS_OBABEL",
        path_candidates=("obabel", "obabel.exe"),
        environment=environment,
    )

    resolutions = (vina, obabel)
    missing = [item.name for item in resolutions if not item.available]
    return {
        "status": "PASS" if not missing else "INDETERMINATE",
        "base_dir": str(base),
        "executables": {item.name: item.to_dict() for item in resolutions},
        "first_loss": None if not missing else "MISSING_EXTERNAL_EXECUTABLE",
        "missing": missing,
        "limitations": [
            "preflight proves executable resolution only; it does not validate a docking protocol",
            "legacy Biolab outputs remain exploratory until migrated behind Research OS evidence gates",
        ],
    }
