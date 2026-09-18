"""MOLDISC-003: select a source-backed REDOCK-003 seed by measured solubility coverage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.request import Request, urlopen

from research_os.core.hashing import sha256_json
from research_os.molecular_discovery.aqsoldb_coverage import (
    AqSolDBCoverageReport,
    CandidateCoverage,
    run_public_aqsoldb_coverage,
)


PROGRAM_ID = "MOLDISC-003"
RCSB_ENDPOINT = "https://data.rcsb.org/rest/v1/core/chemcomp/{chem_comp_id}"
ELIGIBILITY_BOUNDARY = 0.4


class MOLDISC003Error(RuntimeError):
    """Fail-closed error for seed-cohort identity or source retrieval problems."""


@dataclass(frozen=True)
class RCSBChemicalIdentity:
    case_id: str
    pdb_id: str
    chem_comp_id: str
    target: str
    selected_smiles: str
    canonical_smiles: str
    rdkit_inchikey: str
    reported_inchikey: str | None
    reported_name: str | None
    formula: str | None
    formula_weight: float | None
    source_url: str

    @property
    def inchikey_matches_reported(self) -> bool | None:
        if self.reported_inchikey is None:
            return None
        return self.rdkit_inchikey == self.reported_inchikey

    def scientific_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "pdb_id": self.pdb_id,
            "chem_comp_id": self.chem_comp_id,
            "target": self.target,
            "selected_smiles": self.selected_smiles,
            "canonical_smiles": self.canonical_smiles,
            "rdkit_inchikey": self.rdkit_inchikey,
            "reported_inchikey": self.reported_inchikey,
            "reported_name": self.reported_name,
            "formula": self.formula,
            "formula_weight": self.formula_weight,
            "source_url": self.source_url,
            "inchikey_matches_reported": self.inchikey_matches_reported,
        }


@dataclass(frozen=True)
class SeedSelection:
    selected_case_id: str | None
    selected_chem_comp_id: str | None
    selected_pdb_id: str | None
    selected_nearest_similarity: float | None
    eligible_case_ids: tuple[str, ...]
    eligibility_boundary: float = ELIGIBILITY_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "eligible_case_ids": list(self.eligible_case_ids),
        }


@dataclass(frozen=True)
class MOLDISC003Result:
    program_id: str
    config_hash: str
    rcsb_identity_hash: str
    coverage: AqSolDBCoverageReport
    selection: SeedSelection
    program_scientific_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "config_hash": self.config_hash,
            "rcsb_identity_hash": self.rcsb_identity_hash,
            "coverage": self.coverage.to_dict(),
            "selection": self.selection.to_dict(),
            "program_scientific_hash": self.program_scientific_hash,
        }


def load_program_config_v3(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("program_id") != PROGRAM_ID:
        raise MOLDISC003Error(
            f"expected program_id {PROGRAM_ID}, got {config.get('program_id')!r}"
        )
    if config.get("program_version") != "1.0":
        raise MOLDISC003Error("MOLDISC-003 requires program_version 1.0")
    cases = config.get("cases")
    if not isinstance(cases, list) or len(cases) != 15:
        raise MOLDISC003Error("MOLDISC-003 requires exactly 15 frozen REDOCK-003 cases")
    case_ids = [str(item.get("case_id") or "") for item in cases]
    if len(set(case_ids)) != 15:
        raise MOLDISC003Error("MOLDISC-003 case IDs must be unique")
    rule = config.get("selection_rule") or {}
    if float(rule.get("eligibility_boundary", -1)) != ELIGIBILITY_BOUNDARY:
        raise MOLDISC003Error("MOLDISC-003 eligibility boundary drifted from 0.4")
    if rule.get("post_result_threshold_tuning") is not False:
        raise MOLDISC003Error("MOLDISC-003 forbids post-result threshold tuning")
    return config


def _rdkit_identity(smiles: str) -> tuple[str, str]:
    try:
        from rdkit import Chem
        from rdkit.Chem import inchi
    except ImportError as exc:
        raise MOLDISC003Error(
            "MOLDISC-003 requires RDKit; install the 'discovery' extra"
        ) from exc
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise MOLDISC003Error(f"RCSB supplied invalid or unsanitizable SMILES: {smiles!r}")
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    return canonical, inchi.MolToInchiKey(molecule)


def _descriptor_candidates(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    direct = payload.get("rcsb_chem_comp_descriptor")
    if isinstance(direct, Mapping):
        smiles = (
            direct.get("SMILES_stereo")
            or direct.get("smiles_stereo")
            or direct.get("SMILES")
            or direct.get("smiles")
        )
        inchikey = direct.get("InChIKey") or direct.get("inchikey")
        if smiles:
            return str(smiles), str(inchikey) if inchikey else None

    descriptors = payload.get("pdbx_chem_comp_descriptor")
    if not isinstance(descriptors, list):
        descriptors = []

    canonical_smiles: list[tuple[str, str, str]] = []
    plain_smiles: list[tuple[str, str, str]] = []
    inchikeys: list[str] = []
    for item in descriptors:
        if not isinstance(item, Mapping):
            continue
        kind = str(item.get("type") or "").strip()
        descriptor = str(item.get("descriptor") or "").strip()
        program = str(item.get("program") or "").strip()
        version = str(item.get("program_version") or "").strip()
        if not descriptor:
            continue
        normalized = kind.upper().replace(" ", "_")
        if normalized == "INCHIKEY":
            inchikeys.append(descriptor)
        elif "SMILES" in normalized and "CANONICAL" in normalized:
            canonical_smiles.append((program, version, descriptor))
        elif "SMILES" in normalized:
            plain_smiles.append((program, version, descriptor))

    def choose(items: Sequence[tuple[str, str, str]]) -> str | None:
        if not items:
            return None
        # Stable preference only; the active RDKit identity is recorded separately.
        priority = {"OPENEYE OETOOLKITS": 0, "CACTVS": 1, "ACDLABS": 2}
        ranked = sorted(
            items,
            key=lambda row: (
                priority.get(row[0].upper(), 99),
                row[0].upper(),
                row[1],
                row[2],
            ),
        )
        return ranked[0][2]

    return choose(canonical_smiles) or choose(plain_smiles), sorted(inchikeys)[0] if inchikeys else None


def parse_rcsb_chemcomp(
    payload: Mapping[str, Any],
    *,
    case: Mapping[str, Any],
    source_url: str,
) -> RCSBChemicalIdentity:
    chem_comp_id = str(case["chem_comp_id"])
    rcsb_id = str(payload.get("rcsb_id") or chem_comp_id)
    if rcsb_id.upper() != chem_comp_id.upper():
        raise MOLDISC003Error(
            f"RCSB chem-comp identity mismatch: requested {chem_comp_id}, got {rcsb_id}"
        )
    smiles, reported_inchikey = _descriptor_candidates(payload)
    if not smiles:
        raise MOLDISC003Error(f"RCSB chem comp {chem_comp_id} contains no usable SMILES descriptor")
    canonical, rdkit_inchikey = _rdkit_identity(smiles)

    chem_comp = payload.get("chem_comp")
    if not isinstance(chem_comp, Mapping):
        chem_comp = {}
    raw_weight = chem_comp.get("formula_weight")
    try:
        formula_weight = float(raw_weight) if raw_weight is not None else None
    except (TypeError, ValueError):
        formula_weight = None

    return RCSBChemicalIdentity(
        case_id=str(case["case_id"]),
        pdb_id=str(case["pdb_id"]),
        chem_comp_id=chem_comp_id,
        target=str(case["target"]),
        selected_smiles=smiles,
        canonical_smiles=canonical,
        rdkit_inchikey=rdkit_inchikey,
        reported_inchikey=reported_inchikey,
        reported_name=(str(chem_comp.get("name")).strip() if chem_comp.get("name") else None),
        formula=(str(chem_comp.get("formula")).strip() if chem_comp.get("formula") else None),
        formula_weight=formula_weight,
        source_url=source_url,
    )


def fetch_rcsb_identity(case: Mapping[str, Any], *, timeout: float = 30.0) -> RCSBChemicalIdentity:
    chem_comp_id = str(case["chem_comp_id"])
    url = RCSB_ENDPOINT.format(chem_comp_id=chem_comp_id)
    request = Request(url, headers={"User-Agent": "Research-OS/5.1 MOLDISC-003"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed RCSB HTTPS API
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise MOLDISC003Error(f"failed to retrieve RCSB chem comp {chem_comp_id} from {url}") from exc
    if not isinstance(payload, Mapping):
        raise MOLDISC003Error(f"RCSB chem comp {chem_comp_id} returned a non-object payload")
    return parse_rcsb_chemcomp(payload, case=case, source_url=url)


def _select_seed(
    coverage: Sequence[CandidateCoverage],
    identities: Sequence[RCSBChemicalIdentity],
) -> SeedSelection:
    identity_by_case = {item.case_id: item for item in identities}
    eligible = [item for item in coverage if item.nearest_similarity >= ELIGIBILITY_BOUNDARY]
    eligible.sort(key=lambda item: (-item.nearest_similarity, item.candidate_id))
    if not eligible:
        return SeedSelection(
            selected_case_id=None,
            selected_chem_comp_id=None,
            selected_pdb_id=None,
            selected_nearest_similarity=None,
            eligible_case_ids=(),
        )
    selected = eligible[0]
    identity = identity_by_case[selected.candidate_id]
    return SeedSelection(
        selected_case_id=selected.candidate_id,
        selected_chem_comp_id=identity.chem_comp_id,
        selected_pdb_id=identity.pdb_id,
        selected_nearest_similarity=selected.nearest_similarity,
        eligible_case_ids=tuple(item.candidate_id for item in eligible),
    )


def run_moldisc_003(
    *,
    config_path: str | Path,
    output_root: str | Path,
    timeout: float = 60.0,
) -> MOLDISC003Result:
    config = load_program_config_v3(config_path)
    config_hash = sha256_json(config)

    identities = tuple(
        fetch_rcsb_identity(case, timeout=min(timeout, 30.0))
        for case in config["cases"]
    )
    rcsb_identity_hash = sha256_json(
        [item.scientific_dict() for item in identities]
    )

    candidates = [
        {
            "id": item.case_id,
            "name": f"{item.chem_comp_id} / {item.target}",
            "smiles": item.canonical_smiles,
            "origin": {
                "source_type": "RCSB_crystallographic_chemical_component",
                "pdb_id": item.pdb_id,
                "chem_comp_id": item.chem_comp_id,
                "rdkit_inchikey": item.rdkit_inchikey,
            },
        }
        for item in identities
    ]
    coverage = run_public_aqsoldb_coverage(candidates, timeout=timeout)
    if coverage.candidate_count != 15:
        raise MOLDISC003Error("MOLDISC-003 did not evaluate all 15 frozen seeds")
    selection = _select_seed(coverage.candidates, identities)

    program_hash = sha256_json(
        {
            "program_id": PROGRAM_ID,
            "config_hash": config_hash,
            "rcsb_identity_hash": rcsb_identity_hash,
            "coverage_scientific_hash": coverage.scientific_hash,
            "selection": selection.to_dict(),
        }
    )
    result = MOLDISC003Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        rcsb_identity_hash=rcsb_identity_hash,
        coverage=coverage,
        selection=selection,
        program_scientific_hash=program_hash,
    )

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=False)
    (root / "program_manifest.json").write_text(
        json.dumps(
            {
                "program_id": PROGRAM_ID,
                "program_version": config["program_version"],
                "config_hash": config_hash,
                "rcsb_identity_hash": rcsb_identity_hash,
                "coverage_scientific_hash": coverage.scientific_hash,
                "program_scientific_hash": program_hash,
                "selection": selection.to_dict(),
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "rcsb_identities.json").write_text(
        json.dumps(
            {
                "source": "RCSB PDB Data API",
                "identity_hash": rcsb_identity_hash,
                "identities": [item.scientific_dict() for item in identities],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "coverage.json").write_text(
        json.dumps(coverage.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "program_report.md").write_text(
        _markdown(config, result, identities),
        encoding="utf-8",
    )
    return result


def _markdown(
    config: Mapping[str, Any],
    result: MOLDISC003Result,
    identities: Sequence[RCSBChemicalIdentity],
) -> str:
    identity_by_case = {item.case_id: item for item in identities}
    lines = [
        "# MOLDISC-003 — REDOCK-003 seed solubility-coverage scan",
        "",
        f"- RCSB identity hash: {result.rcsb_identity_hash}",
        f"- AqSolDB coverage hash: {result.coverage.scientific_hash}",
        f"- Program hash: {result.program_scientific_hash}",
        f"- Eligibility boundary: {ELIGIBILITY_BOUNDARY}",
        "",
        "## Frozen seed coverage",
        "",
        "| Case | PDB | Ligand | Target | nearest AqSolDB Tanimoto | eligible |",
        "|---|---|---|---|---:|---|",
    ]
    for item in sorted(
        result.coverage.candidates,
        key=lambda row: (-row.nearest_similarity, row.candidate_id),
    ):
        identity = identity_by_case[item.candidate_id]
        lines.append(
            f"| {item.candidate_id} | {identity.pdb_id} | {identity.chem_comp_id} | "
            f"{identity.target} | {item.nearest_similarity:.4f} | "
            f"{'YES' if item.nearest_similarity >= ELIGIBILITY_BOUNDARY else 'NO'} |"
        )
    lines.extend(["", "## Selection", ""])
    if result.selection.selected_case_id is None:
        lines.append("No frozen REDOCK-003 seed met the predeclared AqSolDB coverage boundary.")
    else:
        lines.append(
            f"Selected for a separately frozen follow-up: {result.selection.selected_case_id} / "
            f"{result.selection.selected_pdb_id} / {result.selection.selected_chem_comp_id} at "
            f"nearest similarity {result.selection.selected_nearest_similarity:.4f}."
        )
    lines.extend(["", "## Interpretation boundaries", ""])
    lines.extend(f"- {item}" for item in config["interpretation_boundaries"])
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "ELIGIBILITY_BOUNDARY",
    "MOLDISC003Error",
    "MOLDISC003Result",
    "PROGRAM_ID",
    "RCSBChemicalIdentity",
    "SeedSelection",
    "fetch_rcsb_identity",
    "load_program_config_v3",
    "parse_rcsb_chemcomp",
    "run_moldisc_003",
]
