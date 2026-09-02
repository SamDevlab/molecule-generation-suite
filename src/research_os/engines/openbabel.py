from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class OpenBabelResult:
    input_path: str
    output_path: str
    returncode: int
    stdout: str
    stderr: str
    command: tuple[str, ...]
    engine: str = "Open Babel"
    engine_version: str | None = None


class OpenBabelEngine:
    """Safe argv-based adapter for optional ligand/receptor conversion."""

    def __init__(self, executable: str | None = None):
        self.executable = shutil.which(executable) if executable else (shutil.which("obabel") or shutil.which("obabel.exe"))
        if executable and self.executable is None and Path(executable).is_file():
            self.executable = str(Path(executable))

    @property
    def available(self) -> bool:
        return bool(self.executable and Path(self.executable).is_file())

    @property
    def version(self) -> str | None:
        if not self.available:
            return None
        try:
            result = subprocess.run([self.executable, "-V"], capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        line = (result.stdout or result.stderr).strip().splitlines()
        return line[0] if line else None

    def convert(self, input_path: str | Path, output_path: str | Path, *, options: tuple[str, ...] = ()) -> OpenBabelResult:
        if not self.available:
            raise RuntimeError("Open Babel executable is unavailable")
        source = str(input_path)
        target = str(output_path)
        command = (str(self.executable), source, "-O", target, *options)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        return OpenBabelResult(source, target, result.returncode, result.stdout, result.stderr, command, version_or_none(self))


def version_or_none(engine: OpenBabelEngine) -> str | None:
    return engine.version
