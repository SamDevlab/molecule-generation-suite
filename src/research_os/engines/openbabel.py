from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import time
from research_os.core.hashing import sha256_file


class OpenBabelUnavailableError(RuntimeError):
    pass


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
    status: str = "SUPPORTED_AND_EXECUTED"
    input_sha256: str | None = None
    output_sha256: str | None = None
    timed_out: bool = False
    protocol_id: str | None = None
    elapsed_seconds: float | None = None


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

    def convert(self, input_path: str | Path, output_path: str | Path, *, options: tuple[str, ...] = (), timeout: float = 30.0, protocol_id: str = "openbabel.convert.v1") -> OpenBabelResult:
        if not self.available:
            raise OpenBabelUnavailableError("Open Babel executable is unavailable")
        source = str(input_path)
        target = str(output_path)
        if not Path(source).is_file():
            raise FileNotFoundError(source)
        command = (str(self.executable), source, "-O", target, *options)
        started = time.monotonic()
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout, shell=False)
        except subprocess.TimeoutExpired as exc:
            return OpenBabelResult(source, target, -1, str(exc.stdout or ""), str(exc.stderr or ""), command, version_or_none(self), "EXECUTION_FAILED", sha256_file(source), None, True, protocol_id, time.monotonic() - started)
        output_hash = sha256_file(target) if Path(target).is_file() else None
        return OpenBabelResult(source, target, result.returncode, result.stdout, result.stderr, command, version_or_none(self), "SUPPORTED_AND_EXECUTED" if result.returncode == 0 else "EXECUTION_FAILED", sha256_file(source), output_hash, False, protocol_id, time.monotonic() - started)


def version_or_none(engine: OpenBabelEngine) -> str | None:
    return engine.version
