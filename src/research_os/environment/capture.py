from __future__ import annotations

from importlib import metadata
import platform
from pathlib import Path
import shutil
import subprocess
from typing import Any

from research_os.environment.manifest import DependencyInfo, EnvironmentManifest
from research_os.engines.registry import EngineRegistry


def _command(*args: str, cwd: str | Path | None = None) -> str | None:
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    value = (result.stdout or result.stderr).strip().splitlines()
    return value[0].strip() if value else None


def _package_version(name: str) -> DependencyInfo:
    try:
        return DependencyInfo(True, metadata.version(name))
    except metadata.PackageNotFoundError:
        return DependencyInfo(False, None)


def _module_version(name: str, import_name: str | None = None) -> DependencyInfo:
    try:
        module = __import__(import_name or name)
    except ImportError:
        return DependencyInfo(False, None)
    version = getattr(module, "__version__", None) or getattr(module, "version", None)
    if version is None and name == "rdkit":
        version = getattr(getattr(module, "rdBase", None), "rdkitVersion", None)
    return DependencyInfo(True, version)


def _engine_version(command: str | None, *version_args: str) -> DependencyInfo:
    executable = shutil.which(command) if command else None
    if executable is None:
        return DependencyInfo(False, None)
    version = _command(executable, *version_args)
    return DependencyInfo(True, version)


def capture_environment(*, repo_root: str | Path | None = None) -> EnvironmentManifest:
    root = Path(repo_root).resolve() if repo_root is not None else None
    dependencies = {
        "numpy": _package_version("numpy"),
        "rdkit": _package_version("rdkit"),
        "cantera": _package_version("cantera"),
        "pyarrow": _package_version("pyarrow"),
        "duckdb": _package_version("duckdb"),
        "pycalphad": _package_version("pycalphad"),
        "pymatgen": _package_version("pymatgen"),
        "matminer": _package_version("matminer"),
    }
    engines = {
        "rdkit": _module_version("rdkit"),
        "cantera": _module_version("cantera"),
        "vina": _engine_version("vina", "--version"),
        "openbabel": _engine_version("obabel", "-V"),
        "pycalphad": dependencies["pycalphad"],
        "pymatgen": dependencies["pymatgen"],
        "matminer": dependencies["matminer"],
    }
    git = {
        "commit": _command("git", "rev-parse", "HEAD", cwd=root),
        "branch": _command("git", "branch", "--show-current", cwd=root),
        "dirty": bool(_command("git", "status", "--porcelain", cwd=root)),
    }
    engine_manifests = tuple(item.to_dict() for item in EngineRegistry().probe_all())
    return EnvironmentManifest(
        python={"version": platform.python_version(), "implementation": platform.python_implementation()},
        platform={"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "architecture": platform.architecture()[0]},
        git=git,
        dependencies=dependencies,
        engines=engines,
        engine_manifests=engine_manifests,
    )
