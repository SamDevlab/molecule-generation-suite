"""Non-destructive export/backup for ledger, bundles and manifest indexes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any, Iterable

from research_os.core.hashing import sha256_file, sha256_json


@dataclass(frozen=True)
class BackupManifest:
    backup_id: str
    source_root: str
    target_root: str
    files: dict[str, str]
    created_at: str

    @property
    def digest(self) -> str:
        return sha256_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {"backup_id": self.backup_id, "source_root": self.source_root, "target_root": self.target_root, "files": dict(self.files), "created_at": self.created_at, "digest": sha256_json({"backup_id": self.backup_id, "source_root": self.source_root, "target_root": self.target_root, "files": self.files, "created_at": self.created_at})}


def create_backup(source_root: str | Path, target_root: str | Path, *, include: Iterable[str] = ("research-ledger", "bundles", "manifests", "artifacts")) -> BackupManifest:
    source = Path(source_root).resolve()
    target = Path(target_root).resolve()
    if not source.is_dir():
        raise FileNotFoundError(source)
    if target == source or source in target.parents:
        raise ValueError("backup target must not be the source or a child of the source")
    if target.exists():
        raise FileExistsError(target)
    target.mkdir(parents=True)
    copied: dict[str, str] = {}
    for name in include:
        current = source / name
        if not current.exists():
            continue
        destination = target / name
        if current.is_dir():
            shutil.copytree(current, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(current, destination)
        for path in destination.rglob("*") if destination.is_dir() else (destination,):
            if path.is_file():
                copied[str(path.relative_to(target)).replace("\\", "/")] = sha256_file(path)
    created = datetime.now(timezone.utc).isoformat()
    import uuid
    manifest = BackupManifest(f"BKP-{uuid.uuid4().hex[:12].upper()}", str(source), str(target), copied, created)
    (target / "backup.manifest.json").write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest

