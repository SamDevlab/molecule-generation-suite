from __future__ import annotations
import re, shutil, subprocess
import time
import hashlib
from pathlib import Path
from research_os.core.hashing import sha256_file
from research_os.docking.schema import DockingRequest, DockingResult

class VinaUnavailableError(RuntimeError): pass

class VinaEngine:
    """External AutoDock Vina adapter using argv execution without a shell."""
    def __init__(self, executable: str | None = None):
        self.executable = executable or shutil.which("vina") or shutil.which("vina.exe")
    @property
    def available(self) -> bool:
        return bool(self.executable and Path(self.executable).exists())
    @property
    def version(self) -> str | None:
        if not self.available: return None
        try:
            proc = subprocess.run([self.executable, "--version"], capture_output=True, text=True, timeout=10, check=False)
            text = (proc.stdout or proc.stderr).strip(); return text.splitlines()[0] if text else None
        except Exception: return None
    def run(self, request: DockingRequest, *, timeout: float | None = None) -> DockingResult:
        if not self.available: raise VinaUnavailableError("AutoDock Vina executable is unavailable")
        request.grid.validate()
        if not Path(request.receptor_path).is_file(): raise FileNotFoundError(request.receptor_path)
        if not Path(request.ligand_path).is_file(): raise FileNotFoundError(request.ligand_path)
        out = request.output_path or str(Path(request.ligand_path).with_name(Path(request.ligand_path).stem + "_docked.pdbqt")); g = request.grid
        cmd = [str(self.executable), "--receptor", request.receptor_path, "--ligand", request.ligand_path, "--center_x", str(g.center_x), "--center_y", str(g.center_y), "--center_z", str(g.center_z), "--size_x", str(g.size_x), "--size_y", str(g.size_y), "--size_z", str(g.size_z), "--exhaustiveness", str(request.exhaustiveness), "--cpu", str(request.cpu), "--seed", str(request.seed), "--out", out]
        started = time.monotonic()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout if timeout is not None else request.timeout, shell=False)
        except subprocess.TimeoutExpired as exc:
            return DockingResult(None, None, str(exc.stdout or ""), str(exc.stderr or ""), -1, "AutoDock Vina", self.version, tuple(cmd), "EXECUTION_FAILED", sha256_file(request.receptor_path), sha256_file(request.ligand_path), None, hashlib.sha256(str(exc.stdout or "").encode()).hexdigest(), g.grid_hash, request.target_id, request.species, request.protocol_id, True)
        best = None
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                match = re.match(r"^\s*1\s+(-?\d+(?:\.\d+)?)\s+", line)
                if match: best = float(match.group(1)); break
        output_hash = sha256_file(out) if Path(out).is_file() else None
        return DockingResult(best_affinity_kcal_mol=best, output_path=out if Path(out).exists() else None, stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode, engine="AutoDock Vina", engine_version=self.version, command=tuple(cmd), status="SUPPORTED_AND_EXECUTED" if proc.returncode == 0 else "EXECUTION_FAILED", receptor_sha256=sha256_file(request.receptor_path), ligand_sha256=sha256_file(request.ligand_path), output_sha256=output_hash, log_sha256=hashlib.sha256((proc.stdout + proc.stderr).encode()).hexdigest(), grid_hash=g.grid_hash, target_id=request.target_id, species=request.species, protocol_id=request.protocol_id)
