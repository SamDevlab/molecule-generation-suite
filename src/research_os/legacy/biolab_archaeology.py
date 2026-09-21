"""Deterministic, read-only archaeology of the historical Biolab corpus.

The importer intentionally treats the external corpus as historical
computational context.  It normalizes molecular identity and provenance, but
never creates current evidence, selects a lead, or opens a generation gate.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from research_os.core.hashing import sha256_file, sha256_json


VERSION = "biolab-legacy-archaeology.v0.1"
DEFAULT_SCOPE = "priority"
STRUCTURAL_SIMILARITY_THRESHOLD = 0.4
MORGAN_RADIUS = 2
MORGAN_BITS = 2048

PRIORITY_SOURCES = (
    ("Biolab/TOP_10_HITS_REFINADOS.csv", "BIOLAB_TOP_HIT"),
    ("Biolab/matriz_compostos_filtrados.csv", "BIOLAB_FILTERED"),
    ("formolecular/csv_elite_farma/RANKING_FARMACOS_ELITE_ADMET.csv", "FARMA_ELITE"),
    ("formolecular/novo_horizonte/top10_validado_4EY7.csv", "NH_VALIDATED_4EY7"),
    ("formolecular/novo_horizonte/top10_isolado.csv", "NH_ISOLATED"),
    ("formolecular/novo_horizonte/banco_mestre_unificado.csv", "MASTER_UNIFIED"),
)

_IDENTITY_TOKENS = (
    "smiles",
    "canonical smiles",
    "canonical_smiles",
    "isomeric smiles",
    "isomeric_smiles",
    "inchi",
    "inchikey",
)
_IDENTIFIER_TOKENS = (
    "compound_id",
    "molecule_id",
    "id_mestre",
    "id",
    "nome",
    "name",
    "par_molecular",
)
_LABEL_TOKENS = ("veredito", "verdict", "historical_label", "label")
_EXCLUDED_METRIC_TOKENS = set(_IDENTITY_TOKENS + _IDENTIFIER_TOKENS)

CURRENT_PANEL_KEYS = ("A0B0", "A1B0", "A0B1", "A1B1")
CURRENT_PANEL_INCHIKEYS = {
    "A0B0": "DRIAWXDDGSORDT-KKUQBAQOSA-N",
    "A1B0": "NAZMDUVPQSKJEQ-KKUQBAQOSA-N",
    "A0B1": "DMSDTDPQGPRTNA-FDFHNCONSA-N",
    "A1B1": "URHJIBSBOJFXDI-FDFHNCONSA-N",
}
OVERLAP_COLUMNS = (
    ("filtered", "BIOLAB_FILTERED"),
    ("farma_elite", "FARMA_ELITE"),
    ("top_hit", "BIOLAB_TOP_HIT"),
    ("nh_4ey7", "NH_VALIDATED_4EY7"),
    ("nh_isolated", "NH_ISOLATED"),
    ("master", "MASTER_UNIFIED"),
)


class LegacyArchaeologyError(RuntimeError):
    """Raised when the external corpus cannot be imported safely."""


@dataclass(frozen=True)
class SourceSpec:
    source_path: str
    role: str


@dataclass(frozen=True)
class SourceInfo:
    source_path: str
    source_sha256: str
    file_size: int
    row_count: int
    columns: tuple[str, ...]
    encoding: str
    delimiter: str
    malformed_row_count: int
    classification: str = "LEGACY_COMPUTATIONAL_RESULT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "file_size": self.file_size,
            "row_count": self.row_count,
            "columns": list(self.columns),
            "encoding": self.encoding,
            "delimiter": self.delimiter,
            "malformed_row_count": self.malformed_row_count,
            "classification": self.classification,
        }


def _require_rdkit():
    try:
        from rdkit import Chem, DataStructs
        from rdkit.Chem import rdFingerprintGenerator, rdMolDescriptors
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise LegacyArchaeologyError("RDKit is required for identity reconstruction") from exc
    return Chem, DataStructs, rdFingerprintGenerator, rdMolDescriptors


def _canonical_key(value: str) -> str:
    return "".join(character.lower() for character in value.strip() if character.isalnum())


def _detect_encoding(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return "cp1252"
    return "utf-8"


def _detect_delimiter(header_line: str) -> str:
    counts = {delimiter: header_line.count(delimiter) for delimiter in (",", ";", "\t", "|")}
    return max(counts, key=counts.get) if max(counts.values()) else ","


def _read_source(path: Path, source_path: str) -> tuple[SourceInfo, list[dict[str, str]]]:
    with path.open("rb") as binary_handle:
        sample = binary_handle.read(4096)
    encoding = _detect_encoding(sample)
    with path.open("r", encoding=encoding, newline="") as handle:
        header_line = handle.readline()
    delimiter = _detect_delimiter(header_line)
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        headers = [value.strip() for value in next(reader, [])]
        rows: list[dict[str, str]] = []
        malformed = 0
        for values in reader:
            if not values or all(not value.strip() for value in values):
                continue
            if len(values) != len(headers):
                malformed += 1
            row = {header: values[index].strip() if index < len(values) else "" for index, header in enumerate(headers)}
            if len(values) > len(headers):
                row["__extra__"] = json.dumps(values[len(headers):], ensure_ascii=False, separators=(",", ":"))
            rows.append(row)
    info = SourceInfo(
        source_path=source_path,
        source_sha256=sha256_file(path),
        file_size=path.stat().st_size,
        row_count=len(rows),
        columns=tuple(headers),
        encoding=encoding,
        delimiter=delimiter,
        malformed_row_count=malformed,
    )
    return info, rows


def _find_column(columns: Iterable[str], tokens: Iterable[str]) -> str | None:
    columns = tuple(columns)
    normalized = {_canonical_key(column): column for column in columns}
    for token in tokens:
        candidate = normalized.get(_canonical_key(token))
        if candidate is not None:
            return candidate
    for column in columns:
        normalized_column = _canonical_key(column)
        if any(_canonical_key(token) in normalized_column for token in tokens):
            return column
    return None


def _parse_float(value: str) -> float | int | str:
    if not value:
        return value
    try:
        parsed = float(value)
    except ValueError:
        return value
    return int(parsed) if parsed.is_integer() else parsed


def _metric_value(value: str) -> Any:
    return _parse_float(value) if value else ""


def _source_record(
    source: SourceSpec,
    info: SourceInfo,
    row: dict[str, str],
    source_row: int,
) -> dict[str, Any]:
    columns = tuple(column for column in info.columns if column != "__extra__")
    smiles_column = _find_column(columns, ("SMILES", "isomeric SMILES", "canonical SMILES"))
    inchi_column = _find_column(columns, ("InChI",))
    inchikey_column = _find_column(columns, ("InChIKey",))
    identifier_column = _find_column(columns, _IDENTIFIER_TOKENS)
    label_column = _find_column(columns, _LABEL_TOKENS)
    original_smiles = row.get(smiles_column, "").strip() if smiles_column else ""
    original_inchi = row.get(inchi_column, "").strip() if inchi_column else ""
    original_inchikey = row.get(inchikey_column, "").strip() if inchikey_column else ""
    original_identifier = row.get(identifier_column, "").strip() if identifier_column else ""
    if not original_identifier:
        original_identifier = f"{source.source_path}:row-{source_row}"
    label = row.get(label_column, "").strip() if label_column else ""
    metric_columns = {
        column: _metric_value(row.get(column, ""))
        for column in columns
        if _canonical_key(column) not in {_canonical_key(item) for item in _EXCLUDED_METRIC_TOKENS}
        and column != label_column
    }
    return {
        "source_file": source.source_path,
        "source_row": source_row,
        "source_sha256": info.source_sha256,
        "source_role": source.role,
        "original_identifier": original_identifier,
        "original_smiles": original_smiles,
        "original_inchi": original_inchi,
        "original_inchikey": original_inchikey,
        "historical_label": label,
        "historical_label_source": source.source_path if label else "",
        "legacy_metrics": metric_columns,
        "has_structure_field": bool(original_smiles or original_inchi or original_inchikey),
    }


def _normalize_identity(record: dict[str, Any]) -> dict[str, Any]:
    Chem, _, _, rdMolDescriptors = _require_rdkit()
    smiles = record["original_smiles"]
    if not smiles:
        if record["original_inchi"] or record["original_inchikey"]:
            return {
                "identity_status": "IDENTITY_PARTIAL",
                "normalized_isomeric_smiles": "",
                "inchi": record["original_inchi"],
                "inchikey": record["original_inchikey"],
                "formula": "",
                "heavy_atom_count": "",
            }
        return {
            "identity_status": "IDENTITY_MISSING",
            "normalized_isomeric_smiles": "",
            "inchi": "",
            "inchikey": "",
            "formula": "",
            "heavy_atom_count": "",
        }
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return {
            "identity_status": "IDENTITY_INVALID",
            "normalized_isomeric_smiles": "",
            "inchi": "",
            "inchikey": "",
            "formula": "",
            "heavy_atom_count": "",
        }
    normalized_smiles = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    inchi = Chem.MolToInchi(molecule)
    inchikey = Chem.InchiToInchiKey(inchi) if inchi else ""
    if not inchikey:
        status = "IDENTITY_PARTIAL"
    else:
        status = "IDENTITY_VALID"
    return {
        "identity_status": status,
        "normalized_isomeric_smiles": normalized_smiles,
        "inchi": inchi,
        "inchikey": inchikey,
        "formula": rdMolDescriptors.CalcMolFormula(molecule),
        "heavy_atom_count": int(molecule.GetNumHeavyAtoms()),
    }


def _group_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for record in records:
        if record["identity_status"] == "IDENTITY_VALID":
            key = f"INCHIKEY:{record['inchikey']}"
        else:
            stable = f"{record['source_file']}:{record['source_row']}"
            key = f"RECORD:{hashlib.sha256(stable.encode('utf-8')).hexdigest()[:16]}"
        groups.setdefault(key, []).append(record)
    result: list[dict[str, Any]] = []
    source_order = {source_path: index for index, (source_path, _) in enumerate(PRIORITY_SOURCES)}
    for key, members in groups.items():
        members.sort(key=lambda item: (source_order.get(item["source_file"], 999), item["source_row"]))
        representative = members[0]
        valid = representative["identity_status"] == "IDENTITY_VALID"
        roles = []
        source_files = []
        for member in members:
            if member["source_role"] not in roles:
                roles.append(member["source_role"])
            if member["source_file"] not in source_files:
                source_files.append(member["source_file"])
        source_records = [
            {
                "source_file": member["source_file"],
                "source_row": member["source_row"],
                "source_sha256": member["source_sha256"],
                "source_role": member["source_role"],
                "original_identifier": member["original_identifier"],
                "original_smiles": member["original_smiles"],
                "original_inchi": member["original_inchi"],
                "original_inchikey": member["original_inchikey"],
                "historical_label": member["historical_label"],
                "historical_label_source": member["historical_label_source"],
                "legacy_metrics": member["legacy_metrics"],
            }
            for member in members
        ]
        result.append(
            {
                "legacy_record_id": f"LEGACY-{key.replace(':', '-')}",
                "source_file": representative["source_file"],
                "source_row": representative["source_row"],
                "original_identifier": representative["original_identifier"],
                "original_smiles": representative["original_smiles"],
                "original_inchi": representative["original_inchi"],
                "original_inchikey": representative["original_inchikey"],
                "original_identity": json.dumps(
                    {
                        "identifier": representative["original_identifier"],
                        "smiles": representative["original_smiles"],
                        "inchi": representative["original_inchi"],
                        "inchikey": representative["original_inchikey"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "normalized_isomeric_smiles": representative["normalized_isomeric_smiles"],
                "inchi": representative["inchi"],
                "inchikey": representative["inchikey"],
                "formula": representative["formula"],
                "heavy_atom_count": representative["heavy_atom_count"],
                "normalized_identity": json.dumps(
                    {
                        "isomeric_smiles": representative["normalized_isomeric_smiles"],
                        "inchi": representative["inchi"],
                        "inchikey": representative["inchikey"],
                        "formula": representative["formula"],
                        "heavy_atom_count": representative["heavy_atom_count"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "identity_status": representative["identity_status"],
                "legacy_roles": ";".join(roles),
                "legacy_source_count": len(source_files),
                "historical_label": "; ".join(
                    f"{member['historical_label']} ({member['historical_label_source']})"
                    for member in members
                    if member["historical_label"]
                ),
                "legacy_metrics": json.dumps(
                    [member["legacy_metrics"] for member in source_records],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "source_provenance": json.dumps(source_records, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                "evidence_origin": "LEGACY",
                "evidence_level": "COMPUTATIONAL",
                "experimental_validation": "NONE",
                "promotion_to_current_evidence": "FORBIDDEN",
                "_source_files": source_files,
                "_source_records": source_records,
                "_valid": valid,
            }
        )
    result.sort(key=lambda item: item["legacy_record_id"])
    for item in result:
        for private_key in ("_source_files", "_source_records", "_valid"):
            item.pop(private_key, None)
    return result


def _load_current_panel(repo_root: Path) -> OrderedDict[str, dict[str, Any]]:
    config = repo_root / "programs" / "moldisc-019-experimental-bridge" / "program.json"
    try:
        payload = json.loads(config.read_text(encoding="utf-8"))
        members = payload["panel"]["members"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise LegacyArchaeologyError(f"cannot load current panel from {config}") from exc
    panel = OrderedDict()
    for key in CURRENT_PANEL_KEYS:
        member = dict(members[key])
        if member["inchikey"] != CURRENT_PANEL_INCHIKEYS[key]:
            raise LegacyArchaeologyError(f"current panel identity drift for {key}")
        panel[key] = member
    return panel


def _compare_current_panel(records: list[dict[str, Any]], panel: OrderedDict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    Chem, DataStructs, rdFingerprintGenerator, _ = _require_rdkit()
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=MORGAN_RADIUS, fpSize=MORGAN_BITS)
    panel_molecules = OrderedDict()
    panel_fingerprints = OrderedDict()
    for key, member in panel.items():
        molecule = Chem.MolFromSmiles(member["canonical_isomeric_smiles"])
        if molecule is None:
            raise LegacyArchaeologyError(f"invalid current panel SMILES for {key}")
        panel_molecules[key] = molecule
        panel_fingerprints[key] = generator.GetFingerprint(molecule)
    rows: list[dict[str, Any]] = []
    valid_records = [record for record in records if record["identity_status"] == "IDENTITY_VALID"]
    for panel_key, member in panel.items():
        current_block = member["inchikey"].split("-", 1)[0]
        for record in valid_records:
            legacy_block = record["inchikey"].split("-", 1)[0]
            similarity = float(DataStructs.TanimotoSimilarity(panel_fingerprints[panel_key], generator.GetFingerprint(Chem.MolFromSmiles(record["normalized_isomeric_smiles"]))))
            if record["inchikey"] == member["inchikey"]:
                match_type = "EXACT_IDENTITY_MATCH"
            elif legacy_block == current_block:
                match_type = "CONNECTIVITY_MATCH"
            elif similarity >= STRUCTURAL_SIMILARITY_THRESHOLD:
                match_type = "STRUCTURAL_SIMILARITY"
            else:
                match_type = "NO_MATCH"
            rows.append(
                {
                    "current_panel_key": panel_key,
                    "current_inchikey": member["inchikey"],
                    "legacy_inchikey": record["inchikey"],
                    "match_type": match_type,
                    "similarity": f"{similarity:.6f}",
                    "legacy_source": record["source_file"],
                    "legacy_record_id": record["legacy_record_id"],
                    "historical_label": record["historical_label"],
                }
            )
    counts = defaultdict(int)
    for row in rows:
        counts[row["match_type"]] += 1
    return rows, {
        "parameters": {
            "fingerprint": "Morgan",
            "radius": MORGAN_RADIUS,
            "nBits": MORGAN_BITS,
            "metric": "Tanimoto",
            "structural_similarity_threshold": STRUCTURAL_SIMILARITY_THRESHOLD,
        },
        "pair_count": len(rows),
        "match_counts": dict(sorted(counts.items())),
        "no_ranking_created": True,
    }


def _kni_findings(records: list[dict[str, Any]], panel_json: dict[str, Any]) -> dict[str, Any]:
    terms = ("c-2545", "c2545", "phenyl-kni-727", "kni-727", "kni727")
    hits = []
    for record in records:
        haystack = json.dumps(record, ensure_ascii=False).casefold()
        if any(term in haystack for term in terms):
            hits.append(record["legacy_record_id"])
    boundary = panel_json.get("c2545_boundary", {})
    return {
        "explicit_legacy_hits": sorted(hits),
        "status": "EXPLICIT_LEGACY_IDENTITY_FOUND" if hits else "NO_EXPLICIT_LEGACY_IDENTITY_FOUND",
        "current_boundary": {
            "name": boundary.get("name", "PHENYL-KNI-727"),
            "source_stereochemistry": boundary.get("source_stereochemistry", "UNRESOLVED"),
            "full_identity_match": boundary.get("full_identity_match", False),
            "measurement_transfer_allowed": boundary.get("measurement_transfer_allowed", False),
        },
        "interpretation": "same connectivity does not imply same stereochemical identity; no measurement transfer",
    }


def _model_inventory(legacy_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries = []
    groups = (
        ("formolecular/modelos_ia", "formolecular/modelos_ia/metadados_treino.json", "formolecular/modelos_ia/metadados_aero.json"),
        ("formolecular/modelos_ia_farma", "formolecular/modelos_ia_farma/metadados_farma_admet.json"),
    )
    metrics_by_name = {
        "oraculo_qed.pkl": ("QED", "r2_qed", "formolecular/modelos_ia/metadados_treino.json"),
        "oraculo_aero.pkl": ("AERO/OB_Pct", "r2_aero", "formolecular/modelos_ia/metadados_treino.json"),
        "oraculo_food.pkl": ("FOOD/Peso_Molar", "r2_food", "formolecular/modelos_ia/metadados_treino.json"),
        "oraculo_agro.pkl": ("AGRO/Eficiencia_Nutricional", "r2_agro", "formolecular/modelos_ia/metadados_treino.json"),
        "oraculo_mat.pkl": ("MATERIAIS/TPSA_Superficie", "r2_mat", "formolecular/modelos_ia/metadados_treino.json"),
        "oraculo_aero_isp.pkl": ("ISP", "r2_isp", "formolecular/modelos_ia/metadados_aero.json"),
        "oraculo_farma_admet_qed.pkl": ("FARMA QED", "r2_qed", "formolecular/modelos_ia_farma/metadados_farma_admet.json"),
    }
    metadata_cache: dict[str, dict[str, Any]] = {}
    for directory, *metadata_paths in groups:
        for metadata_path in metadata_paths:
            path = legacy_root / metadata_path
            if path.is_file():
                metadata_cache[metadata_path] = json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((legacy_root / directory).glob("*.pkl")):
            metric_name, metric_key, metadata_path = metrics_by_name.get(path.name, ("UNKNOWN", "", metadata_paths[0] if metadata_paths else ""))
            metadata = metadata_cache.get(metadata_path, {})
            entries.append(
                {
                    "filename": path.name,
                    "source_path": str(path.relative_to(legacy_root)).replace("\\", "/"),
                    "file_size": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "metadata_source": metadata_path,
                    "metadata_sha256": sha256_file(legacy_root / metadata_path) if (legacy_root / metadata_path).is_file() else "",
                    "declared_algorithm": "RandomForestRegressor (source-script declaration)",
                    "training_rows": metadata.get("tamanho_ultimo_treino"),
                    "declared_metric": metric_name,
                    "declared_metric_key": metric_key,
                    "declared_metric_value": metadata.get(metric_key) if metric_key else None,
                    "classification": "SELF_REPORTED_PROJECT_METRIC",
                    "pickle_executed": False,
                }
            )
    entries.sort(key=lambda item: item["source_path"])
    return entries, {"pickle_files_inventoried": len(entries), "pickle_files_executed": 0}


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _read_panel_json(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "programs" / "moldisc-019-experimental-bridge" / "panel.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyArchaeologyError(f"cannot load panel boundary from {path}") from exc


def _readme(stats: dict[str, Any], legacy_root: Path) -> str:
    return f"""# Biolab Legacy Archaeology v0.1

This directory contains a deterministic, read-only reconstruction of the six
priority historical Biolab/formolecular CSV sources.  The source corpus stays
outside Git; only normalized indexes, summaries, manifests, tests, and
provenance are committed.

## Evidence boundary

Every imported record is classified as `evidence_origin=LEGACY`,
`evidence_level=COMPUTATIONAL`, `experimental_validation=NONE`, and
`promotion_to_current_evidence=FORBIDDEN`.  Historical labels and scores are
preserved as provenance, not current scientific conclusions.  This corpus
cannot create E4 evidence and cannot open the next-generation gate.

## Scope

- source root used for this generation: `{legacy_root}`
- priority sources found: `{stats['priority_sources_found']}`
- rows scanned: `{stats['rows_scanned']}`
- identity-valid rows: `{stats['identity_valid']}`
- exact identities after deduplication: `{stats['unique_exact_identities']}`
- duplicate exact-identity rows: `{stats['duplicate_identities']}`
- multi-source exact identities: `{stats['multi_source_identities']}`

The comparison output is a historical comparison with the frozen BIOEXP-001
panel (`A0B0`, `A1B0`, `A0B1`, `A1B1`).  It is not a ranking and contains no
new molecule generation, docking, lead selection, model training, or E4
promotion.

## Legacy pipeline vs Research OS

Legacy: generation/filtering → scoring/docking → ranking.

Current Research OS: hypothesis → bounded computation → provenance/evidence
gate → experiment.

## Reproduction

```text
python tools/legacy_biolab_import.py --legacy-root <external-corpus> --scope priority
```

Use `--dry-run` to inspect source schemas and identity statistics without
writing artifacts.
"""


def _comparison_report(stats: dict[str, Any], comparison: dict[str, Any], panel_status: dict[str, Any], kni: dict[str, Any]) -> str:
    exact = panel_status.get("exact_matches", {})
    connectivity = panel_status.get("connectivity_matches", {})
    structural = panel_status.get("structural_similarity_pairs", {})
    lines = [
        "# Current Panel Comparison",
        "",
        "This report compares historical computational records with the frozen BIOEXP-001 panel.",
        "It does not select candidates, rank legacy molecules, create E4, or open generation.",
        "",
        "## Evidence boundary",
        "",
        "All records are `LEGACY` / `COMPUTATIONAL` with no experimental validation.",
        "Exact, connectivity, and structural-similarity matches are provenance findings only.",
        "",
        "## Questions",
        "",
        f"1. Exact identity in the legacy corpus: **{sum(exact.values())} panel members**.",
        f"2. Same connectivity without exact identity: **{sum(connectivity.values())} panel members**.",
        f"3. Legacy source coverage is preserved in `legacy_molecular_index.csv` and `source_overlap.csv`.",
        f"4. Structural similarity pairs at the declared Morgan/Tanimoto threshold: **{sum(structural.values())}**.",
        f"5. Multi-source exact identities: **{stats['multi_source_identities']}**.",
        "6. Any convergence is historical provenance, not current efficacy or potency evidence.",
        "",
        "## Per-panel status",
        "",
        "| Panel key | InChIKey | Exact matches | Connectivity matches | Structural-similarity pairs |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for key in CURRENT_PANEL_KEYS:
        lines.append(f"| {key} | {CURRENT_PANEL_INCHIKEYS[key]} | {exact.get(key, 0)} | {connectivity.get(key, 0)} | {structural.get(key, 0)} |")
    lines.extend(
        [
            "",
            "## Similarity protocol",
            "",
            f"`fingerprint=Morgan`, `radius={comparison['parameters']['radius']}`, `nBits={comparison['parameters']['nBits']}`, `metric=Tanimoto`, `structural_similarity_threshold={comparison['parameters']['structural_similarity_threshold']}`.",
            "All current-panel × legacy-identity pairs, including `NO_MATCH`, are retained in `current_panel_matches.csv`.",
            "",
            "## C-2545 / KNI boundary",
            "",
            f"Status: `{kni['status']}`. The current panel boundary remains `{kni['current_boundary']['name']}` with source stereochemistry `{kni['current_boundary']['source_stereochemistry']}` and measurement transfer `{kni['current_boundary']['measurement_transfer_allowed']}`.",
            "Same connectivity does not imply the same stereochemical identity; no solubility measurement is transferred.",
            "",
            "## Invariants",
            "",
            "`REAL_EXPERIMENT_EXECUTED=NO`, `E4_CREATED=NO`, `NEXT_GENERATION_ALLOWED=NO`.",
        ]
    )
    return "\n".join(lines) + "\n"


def _model_inventory_markdown(entries: list[dict[str, Any]]) -> str:
    lines = [
        "# Legacy Model Inventory",
        "",
        "Pickle files were inventoried by filename, size, hash, and adjacent metadata only. No pickle was loaded or executed.",
        "All declared metrics are classified as `SELF_REPORTED_PROJECT_METRIC` pending split, leakage, and independent-validation audit.",
        "",
        "| File | SHA-256 | Algorithm | Training rows | Declared metric | Value |",
        "| --- | --- | --- | ---: | --- | ---: |",
    ]
    for entry in entries:
        value = "" if entry["declared_metric_value"] is None else f"{entry['declared_metric_value']:.4f}"
        lines.append(f"| `{entry['source_path']}` | `{entry['sha256']}` | {entry['declared_algorithm']} | {entry['training_rows'] or ''} | {entry['declared_metric']} | {value} |")
    lines.extend(
        [
            "",
            "The aero metric with R² 0.2297 is explicitly `LEGACY_MODEL_PERFORMANCE_WEAK` and is not used for new conclusions.",
            "QED can be calculated directly with RDKit; an ML QED surrogate is not automatically superior or necessary.",
        ]
    )
    return "\n".join(lines) + "\n"


def _audit_backlog() -> str:
    return """# Legacy Model Audit Backlog

This v0.1 increment inventories model artifacts but does not deserialize or
execute them and does not perform a full audit of millions of historical rows.

Future review questions:

- What train/test split was used?
- Was the split random, scaffold-based, or otherwise grouped?
- Are duplicate structures or near-duplicates present across splits?
- Is there target leakage or a derived label leak?
- Are labels synthetic, heuristic, or externally measured?
- Is there an independent external validation set?
- Are units, conditions, and target definitions compatible with current claims?

Until answered, all metrics remain `SELF_REPORTED_PROJECT_METRIC`. QED should
prefer deterministic RDKit calculation when the exact property is available,
unless a surrogate has a justified operational purpose.
"""


def _evidence_contract() -> dict[str, Any]:
    return {
        "origin": "LEGACY",
        "evidence_level": "COMPUTATIONAL",
        "experimental_validation": "NONE",
        "promotion_to_current_evidence": False,
        "may_inform_historical_context": True,
        "may_create_e4": False,
        "may_open_generation_gate": False,
    }


def _collect_source_records(legacy_root: Path, scope: str) -> tuple[list[SourceInfo], list[dict[str, Any]]]:
    if scope != DEFAULT_SCOPE:
        raise LegacyArchaeologyError(f"unsupported scope: {scope}")
    source_infos: list[SourceInfo] = []
    records: list[dict[str, Any]] = []
    for source_path, role in PRIORITY_SOURCES:
        path = legacy_root / source_path
        if not path.is_file():
            continue
        spec = SourceSpec(source_path, role)
        info, rows = _read_source(path, source_path)
        source_infos.append(info)
        for row_number, row in enumerate(rows, start=2):
            record = _source_record(spec, info, row, row_number)
            record.update(_normalize_identity(record))
            records.append(record)
    return source_infos, records


def _summary(source_infos: list[SourceInfo], raw_records: list[dict[str, Any]], index: list[dict[str, Any]]) -> dict[str, Any]:
    counts = defaultdict(int)
    for record in raw_records:
        counts[record["identity_status"].lower().replace("identity_", "identity_")] += 1
    exact = [record for record in index if record["identity_status"] == "IDENTITY_VALID"]
    duplicate = sum(len(json.loads(record["source_provenance"])) - 1 for record in exact)
    multi_source = sum(len({item["source_file"] for item in json.loads(record["source_provenance"])}) > 1 for record in exact)
    return {
        "priority_sources_found": len(source_infos),
        "priority_sources_expected": len(PRIORITY_SOURCES),
        "rows_scanned": len(raw_records),
        "molecular_rows": sum(record["has_structure_field"] for record in raw_records),
        "identity_valid": counts["identity_valid"],
        "identity_partial": counts["identity_partial"],
        "identity_invalid": counts["identity_invalid"],
        "identity_missing": counts["identity_missing"],
        "unique_exact_identities": len(exact),
        "duplicate_identities": duplicate,
        "multi_source_identities": multi_source,
        "index_rows": len(index),
    }


def dry_run(legacy_root: str | Path, *, scope: str = DEFAULT_SCOPE, repo_root: str | Path = ".") -> dict[str, Any]:
    """Inspect priority sources and normalize in memory without writing files."""
    root = Path(legacy_root).expanduser().resolve()
    source_infos, raw_records = _collect_source_records(root, scope)
    index = _group_records(raw_records)
    return {
        "dry_run": True,
        "version": VERSION,
        "legacy_root": str(root),
        "scope": scope,
        "sources": [info.to_dict() for info in source_infos],
        "statistics": _summary(source_infos, raw_records, index),
        "repo_root": str(Path(repo_root).resolve()),
    }


def build_artifacts(
    legacy_root: str | Path,
    *,
    output_dir: str | Path = "legacy/biolab-v0",
    repo_root: str | Path = ".",
    scope: str = DEFAULT_SCOPE,
) -> dict[str, Any]:
    """Import priority sources and write only normalized/provenance artifacts."""
    root = Path(legacy_root).expanduser().resolve()
    repository = Path(repo_root).resolve()
    output = Path(output_dir)
    if not output.is_absolute():
        output = repository / output
    output.mkdir(parents=True, exist_ok=True)
    source_infos, raw_records = _collect_source_records(root, scope)
    if len(source_infos) != len(PRIORITY_SOURCES):
        missing = [path for path, _ in PRIORITY_SOURCES if not (root / path).is_file()]
        raise LegacyArchaeologyError(f"priority source set incomplete; missing: {missing}")
    index = _group_records(raw_records)
    stats = _summary(source_infos, raw_records, index)
    panel = _load_current_panel(repository)
    panel_json = _read_panel_json(repository)
    comparison_rows, comparison_parameters = _compare_current_panel(index, panel)
    exact_counts = defaultdict(int)
    connectivity_counts = defaultdict(int)
    structural_counts = defaultdict(int)
    for row in comparison_rows:
        if row["match_type"] == "EXACT_IDENTITY_MATCH":
            exact_counts[row["current_panel_key"]] += 1
        elif row["match_type"] == "CONNECTIVITY_MATCH":
            connectivity_counts[row["current_panel_key"]] += 1
        elif row["match_type"] == "STRUCTURAL_SIMILARITY":
            structural_counts[row["current_panel_key"]] += 1
    panel_status = {
        "exact_matches": dict(exact_counts),
        "connectivity_matches": dict(connectivity_counts),
        "structural_similarity_pairs": dict(structural_counts),
    }
    kni = _kni_findings(index, panel_json)
    model_entries, model_stats = _model_inventory(root)
    stats.update(model_stats)

    datasets = [info.to_dict() for info in source_infos]
    _write_json(output / "datasets.json", datasets)
    index_fields = [
        "legacy_record_id", "source_file", "source_row", "original_identifier", "original_smiles", "original_inchi", "original_inchikey", "original_identity",
        "normalized_isomeric_smiles", "inchi", "inchikey", "formula", "heavy_atom_count", "normalized_identity",
        "identity_status", "legacy_roles", "legacy_source_count", "historical_label",
        "legacy_metrics", "source_provenance", "evidence_origin", "evidence_level",
        "experimental_validation", "promotion_to_current_evidence",
    ]
    _write_csv(output / "legacy_molecular_index.csv", index_fields, index)
    overlap_fields = ["legacy_record_id", "inchikey", "source_file", "source_role", "compound"]
    overlap_rows = []
    for record in index:
        if record["identity_status"] != "IDENTITY_VALID":
            continue
        source_roles = {item["source_role"] for item in json.loads(record["source_provenance"])}
        overlap_rows.append(
            {
                "legacy_record_id": record["legacy_record_id"],
                "inchikey": record["inchikey"],
                "source_file": record["source_file"],
                "source_role": record["legacy_roles"],
                "compound": record["inchikey"],
                **{column: int(role in source_roles) for column, role in OVERLAP_COLUMNS},
            }
        )
    overlap_fields.extend(column for column, _ in OVERLAP_COLUMNS)
    _write_csv(output / "source_overlap.csv", overlap_fields, overlap_rows)
    match_fields = ["current_panel_key", "current_inchikey", "legacy_inchikey", "match_type", "similarity", "legacy_source", "legacy_record_id", "historical_label"]
    _write_csv(output / "current_panel_matches.csv", match_fields, comparison_rows)
    _write_json(
        output / "evidence_contract.json",
        _evidence_contract(),
    )
    _write_json(
        output / "model_inventory.json",
        {"version": VERSION, "models": model_entries, "statistics": model_stats},
    )
    _write_text(output / "MODEL_INVENTORY.md", _model_inventory_markdown(model_entries))
    _write_text(output / "MODEL_AUDIT_BACKLOG.md", _audit_backlog())
    _write_text(output / "CURRENT_PANEL_COMPARISON.md", _comparison_report(stats, comparison_parameters, panel_status, kni))
    _write_text(output / "README.md", _readme(stats, root))

    canonical_corpus_hash = sha256_json(
        {
            "version": VERSION,
            "sources": [info.to_dict() for info in source_infos],
            "index": index,
            "comparison_parameters": comparison_parameters,
        }
    )
    output_paths = sorted(path for path in output.iterdir() if path.is_file() and path.name != "manifest.json")
    manifest = {
        "version": VERSION,
        "legacy_root": str(root),
        "scope": scope,
        "classification": {
            "evidence_origin": "LEGACY",
            "evidence_level": "COMPUTATIONAL",
            "experimental_validation": "NONE",
            "promotion_to_current_evidence": "FORBIDDEN",
        },
        "sources": datasets,
        "outputs": {path.name: sha256_file(path) for path in output_paths},
        "canonical_corpus_hash": canonical_corpus_hash,
        "statistics": stats,
        "current_panel": {
            "panel_keys": list(CURRENT_PANEL_KEYS),
            "inchikeys": dict(CURRENT_PANEL_INCHIKEYS),
            "status": panel_status,
            "comparison": comparison_parameters,
            "kni_c2545": kni,
        },
        "invariants": {
            "legacy_can_create_e4": False,
            "real_experiment_executed": False,
            "e4_created": False,
            "next_generation_allowed": False,
            "raw_data_committed": False,
        },
        "model_inventory": model_stats,
        "manifest_hash_scope": "generated outputs excluding manifest.json to avoid self-reference",
    }
    _write_json(output / "manifest.json", manifest)
    return manifest


__all__ = [
    "CURRENT_PANEL_INCHIKEYS",
    "CURRENT_PANEL_KEYS",
    "LegacyArchaeologyError",
    "PRIORITY_SOURCES",
    "VERSION",
    "build_artifacts",
    "dry_run",
]
