from __future__ import annotations
import re, shutil, subprocess
from pathlib import Path
from research_os.docking.schema import DockingRequest, DockingResult

class VinaUnavailableError(RuntimeError): pass

class VinaEngine:
    """External AutoDock Vina adapter using argv execution, never shell=True."""
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
    def run(self, request: DockingRequest) -> DockingResult:
        if not self.available: raise VinaUnavailableError("AutoDock Vina executable is unavailable")
        out = request.output_path or str(Path(request.ligand_path).with_name(Path(request.ligand_path).stem + "_docked.pdbqt")); g = request.grid
        cmd = [str(self.executable), "--receptor", request.receptor_path, "--ligand", request.ligand_path, "--center_x", str(g.center_x), "--center_y", str(g.center_y), "--center_z", str(g.center_z), "--size_x", str(g.size_x), "--size_y", str(g.size_y), "--size_z", str(g.size_z), "--exhaustiveness", str(request.exhaustiveness), "--cpu", str(request.cpu), "--seed", str(request.seed), "--out", out]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False); best = None
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                match = re.match(r"^\s*1\s+(-?\d+(?:\.\d+)?)\s+", line)
                if match: best = float(match.group(1)); break
        return DockingResult(best_affinity_kcal_mol=best, output_path=out if Path(out).exists() else None, stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode, engine="AutoDock Vina", engine_version=self.version, command=tuple(cmd))
