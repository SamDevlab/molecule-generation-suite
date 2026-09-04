"""Retrieve one explicitly supplied public battery artifact and write a manifest.

The tool is intentionally narrow: it does not crawl, execute archive members,
or infer license terms.  It records the URL, bytes and archive member list so a
later adapter can decide whether the schema is condition-complete.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
import zipfile


def retrieve(url: str, output: Path, manifest_path: Path, *, title: str, source_id: str, license_name: str, timeout: int = 60) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    request = Request(url, headers={"User-Agent": "Research-OS/3.4 public-artifact-retrieval"})
    with urlopen(request, timeout=timeout) as response, output.open("wb") as target:
        expected = response.headers.get("Content-Length")
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            target.write(chunk)
            digest.update(chunk)
            total += len(chunk)
    members: list[dict[str, object]] = []
    if zipfile.is_zipfile(output):
        with zipfile.ZipFile(output) as archive:
            for info in archive.infolist():
                members.append({"name": info.filename, "size": info.file_size, "compressed_size": info.compress_size})
    payload = {
        "dataset_id": "battery-nasa-pcoe-rw3",
        "title": title,
        "source_id": source_id,
        "source_url": url,
        "license": license_name,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "retrieval_status": "ARTIFACT_RETRIEVED",
        "artifact_path": str(output.resolve()),
        "artifact_sha256": digest.hexdigest(),
        "artifact_size_bytes": total,
        "content_length_header": int(expected) if expected and expected.isdigit() else expected,
        "archive_members": members,
        "schema_status": "ARCHIVE_MEMBERS_INSPECTED; RECORD_SCHEMA_REQUIRES_ADAPTER",
        "provenance": [source_id, url],
        "notes": ["Archive members were listed but not executed.", "Source license was recorded from the NASA Open Data metadata and remains subject to project review."],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--license", required=True, dest="license_name")
    args = parser.parse_args()
    print(json.dumps(retrieve(args.url, args.output, args.manifest, title=args.title, source_id=args.source_id, license_name=args.license_name), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
