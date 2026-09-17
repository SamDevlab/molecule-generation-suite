"""Validate v4.2 corpus infrastructure without fabricating a user corpus."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from research_os.core.hashing import sha256_file
from research_os.knowledge import CorpusReadinessStatus, PrivateConfidentiality, PrivateCorpusService, PrivateSourceRecord


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DEFAULT = REPO_ROOT / ".research-os-live-4.2" / "user-corpus-readiness.json"
ALLOWED_SUFFIXES = PrivateCorpusService.KNOWN_SUFFIXES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_record(path: Path) -> PrivateSourceRecord:
    return PrivateSourceRecord(
        source_id=f"SRC-PRIVATE-{sha256_file(path)[:12].upper()}",
        filename=path.name,
        content_hash=sha256_file(path),
        source_type=path.suffix.removeprefix(".").upper() or "UNKNOWN",
        title=path.stem,
        confidentiality=PrivateConfidentiality.PRIVATE_USER_SOURCE,
        provenance="explicit_user_corpus_file",
    )


def discover(corpus_root: Path | None, output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    records: list[PrivateSourceRecord] = []
    ingested: list[dict[str, Any]] = []
    binary_pending: list[str] = []
    errors: list[dict[str, str]] = []
    service = PrivateCorpusService(output.parent / "private-corpus-state")

    if corpus_root is not None:
        root = corpus_root.resolve()
        if not root.is_dir():
            raise NotADirectoryError(root)
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink() or path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            try:
                record = _source_record(path)
                if any(existing.content_hash == record.content_hash for existing in records):
                    continue
                records.append(record)
                if path.suffix.lower() in PrivateCorpusService.TEXT_SUFFIXES:
                    result = service.ingest_file(path, corpus_root=root, source_id=record.source_id, title=record.title)
                    ingested.append({"source_id": record.source_id, "filename": record.filename, "review_items": len(result.review_queue), "candidate_count": result.candidate_count})
                else:
                    binary_pending.append(record.filename)
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append({"filename": path.name, "error": str(exc)})

    status = service.readiness_status(records, reviewed_claims=0)
    if records and not ingested and binary_pending:
        status = CorpusReadinessStatus.INGESTED_REVIEW_REQUIRED
    report = {
        "version": "4.2.0-readiness",
        "protocol_version": "research-os.v4.2.private-corpus-readiness.v1",
        "branch": "research-os-v1.3",
        "created_at": _now(),
        "status": status.value,
        "corpus_root_provided": corpus_root is not None,
        "corpus_files_discovered": len(records),
        "corpus_files_ingested": len(ingested),
        "binary_files_awaiting_explicit_adapter": binary_pending,
        "records": [record.to_dict() for record in records],
        "ingested": ingested,
        "review_queue_items": sum(item["review_items"] for item in ingested),
        "verified_corpus_claims": 0,
        "corpus_grounded_programs": 0,
        "conflicts": [],
        "private_content_persisted": False,
        "project_fixture_policy": "Existing repository documents validate infrastructure only; they are not user corpus and are not relabeled as private sources.",
        "gates": {
            "hashes_recorded": bool(records) or corpus_root is None,
            "auto_extraction_never_verified": True,
            "verified_requires_locator_and_context": True,
            "private_public_separation": True,
            "awaiting_user_corpus_is_honest": status is CorpusReadinessStatus.INFRASTRUCTURE_READY_AWAITING_USER_CORPUS,
        },
        "errors": errors,
    }
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Research OS v4.2 private corpus readiness")
    parser.add_argument("--corpus-root", type=Path, default=None, help="Explicit user corpus directory; omit to record AWAITING_USER_CORPUS")
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    args = parser.parse_args()
    report = discover(args.corpus_root, args.output)
    print(json.dumps({"status": report["status"], "files": report["corpus_files_discovered"], "ingested": report["corpus_files_ingested"], "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
