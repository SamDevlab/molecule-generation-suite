from __future__ import annotations

from pathlib import Path


KNOWLEDGE_DIRECTORIES = ("inbox", "sources", "documents", "zettels", "mocs", "equations", "claims", "entities", "review", "training", "rejected")


def ensure_knowledge_layout(root: str | Path) -> dict[str, Path]:
    """Create the future ingestion layout without copying any source corpus."""
    base = Path(root)
    paths = {name: base / name for name in KNOWLEDGE_DIRECTORIES}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
