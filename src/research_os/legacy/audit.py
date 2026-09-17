"""Read-only audit of legacy scientific paths.

The report is intentionally generated from the repository and never edits the
legacy directories. It records conceptual gaps that v1.7 keeps out of the
real-engine interfaces.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def legacy_engine_audit(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root).resolve()
    entries = []
    for directory in ("Biolab", "formolecular"):
        path = root / directory
        files = sorted(str(item.relative_to(root)).replace("\\", "/") for item in path.rglob("*") if item.is_file() and item.suffix != ".pyc" and "__pycache__" not in item.parts) if path.is_dir() else []
        entries.append({"path": directory, "present": path.is_dir(), "files": files, "conceptual_gaps": [
            "legacy workflow is not treated as real-engine provenance",
            "engine availability/reference validation must be established by Research OS v1.7",
            "legacy files are preserved and are not modified by this audit",
        ]})
    return {"audit_id": "legacy-engine-audit.v1", "repo_root": str(root), "directories": entries, "migration_policy": "new Research OS interfaces only; preserve legacy directories"}
