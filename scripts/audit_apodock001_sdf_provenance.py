"""Audit provenance and scientific equivalence of the APD-001..009 SDF inputs.

This is an audit-only utility.  It downloads RCSB instance SDFs, compares them
with the frozen byte hashes and with the corresponding CCD ideal structures,
and checks same-frame coordinates against the frozen holo PDB instances.  It
never imports or invokes Vina and it never performs a rigid fit.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
from typing import Any
from urllib.request import Request, urlopen

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from research_os.core.hashing import sha256_json
from research_os.docking import apodock001
from research_os.docking import redocking


PROTOCOL_PATH = Path("configs/apodock001-protocol-freeze-v1.0.1.json")
EXPECTED_PROTOCOL_ID = "research-os.apodock001.protocol.v1.0.1+9e293289c9729603"
DEFAULT_USER_AGENT = "Research-OS/5.1 APODOCK-001-SDF-PROVENANCE-AUDIT"
HISTORICAL_ARTIFACT = {
    "workflow_run": "34642755042",
    "head_sha": "fa0a737eaa1989856474068f330c3c2c52d74344",
    "artifact_name": "apodock001-preflight-v1.0",
    "artifact_id": "10280154166",
    "artifact_zip_sha256": "2026a042818c4ec021fea672d4ceba72a31734c61da4ce8c97413dcb3bfcace8",
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _download(url: str, destination: Path, user_agent: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Cache-Control": "no-cache",
            "Connection": "close",
        },
    )
    with urlopen(request, timeout=60.0) as response:
        payload = response.read()
        headers = {key.lower(): value for key, value in response.headers.items()}
        status = int(response.status)
    if not payload:
        raise RuntimeError(f"empty response from {url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return {
        "url": url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "http_status": status,
        "content_type": headers.get("content-type"),
        "content_length_header": headers.get("content-length"),
        "etag": headers.get("etag"),
        "last_modified": headers.get("last-modified"),
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "path": str(destination),
    }


def _load_single_sdf(path: Path) -> Chem.Mol:
    supplier = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=True)
    molecules = [mol for mol in supplier if mol is not None]
    if len(molecules) != 1:
        raise ValueError(f"expected one molecule in {path}, found {len(molecules)}")
    molecule = molecules[0]
    if molecule.GetNumConformers() != 1:
        raise ValueError(f"expected one conformer in {path}")
    return molecule


def _heavy_atom_indices(molecule: Chem.Mol) -> list[int]:
    return [atom.GetIdx() for atom in molecule.GetAtoms() if atom.GetAtomicNum() > 1]


def _molecule_identity(molecule: Chem.Mol) -> dict[str, Any]:
    heavy_indices = _heavy_atom_indices(molecule)
    elements = Counter(molecule.GetAtomWithIdx(index).GetSymbol() for index in heavy_indices)
    normalized = Chem.RemoveHs(Chem.Mol(molecule))
    return {
        "formula": rdMolDescriptors.CalcMolFormula(molecule),
        "heavy_atom_count": len(heavy_indices),
        "formal_charge": sum(atom.GetFormalCharge() for atom in molecule.GetAtoms()),
        "element_counts": dict(sorted(elements.items())),
        "canonical_smiles": Chem.MolToSmiles(normalized, canonical=True, isomericSmiles=False),
        "canonical_isomeric_smiles": Chem.MolToSmiles(normalized, canonical=True, isomericSmiles=True),
    }


def _heavy_graph(molecule: Chem.Mol) -> tuple[list[str], list[set[int]], list[int]]:
    original = _heavy_atom_indices(molecule)
    index_map = {original_index: heavy_index for heavy_index, original_index in enumerate(original)}
    elements = [molecule.GetAtomWithIdx(index).GetSymbol() for index in original]
    adjacency = [set() for _ in original]
    for bond in molecule.GetBonds():
        begin = bond.GetBeginAtomIdx()
        end = bond.GetEndAtomIdx()
        if begin in index_map and end in index_map:
            left = index_map[begin]
            right = index_map[end]
            adjacency[left].add(right)
            adjacency[right].add(left)
    return elements, adjacency, original


def _pdb_serial(line: str) -> int:
    return int(line[6:11].strip())


def _pdb_conect_serials(line: str) -> list[int]:
    serials: list[int] = []
    for start in range(6, len(line), 5):
        field = line[start : start + 5].strip()
        if field:
            serials.append(int(field))
    return serials


def _cif_loop_rows(text: str, field: str) -> tuple[list[str], list[list[str]]]:
    lines = text.splitlines()
    field_index = next(index for index, line in enumerate(lines) if line.strip() == field)
    header_start = field_index
    while header_start > 0 and lines[header_start - 1].strip().startswith("_"):
        header_start -= 1
    headers: list[str] = []
    cursor = header_start
    while cursor < len(lines) and lines[cursor].strip().startswith("_"):
        headers.append(lines[cursor].strip())
        cursor += 1
    rows: list[list[str]] = []
    while cursor < len(lines):
        stripped = lines[cursor].strip()
        if not stripped or stripped.startswith("#") or stripped == "loop_" or stripped.startswith("_"):
            break
        rows.append(shlex.split(stripped, comments=False, posix=True))
        cursor += 1
    return headers, rows


def _ccd_graph(cif_text: str) -> tuple[list[dict[str, str]], list[set[int]]]:
    atom_headers, atom_rows = _cif_loop_rows(cif_text, "_chem_comp_atom.comp_id")
    atom_index = {name: index for index, name in enumerate(atom_headers)}
    atoms = [
        {
            "atom_id": row[atom_index["_chem_comp_atom.atom_id"]],
            "alt_atom_id": row[atom_index["_chem_comp_atom.alt_atom_id"]],
            "element": row[atom_index["_chem_comp_atom.type_symbol"]],
        }
        for row in atom_rows
        if row[atom_index["_chem_comp_atom.type_symbol"]] not in {"H", "D"}
    ]
    atom_ids = {atom["atom_id"]: index for index, atom in enumerate(atoms)}
    alternate_ids = {atom["alt_atom_id"]: index for index, atom in enumerate(atoms) if atom["alt_atom_id"] not in {"?", "."}}
    bond_headers, bond_rows = _cif_loop_rows(cif_text, "_chem_comp_bond.comp_id")
    bond_index = {name: index for index, name in enumerate(bond_headers)}
    adjacency = [set() for _ in atoms]
    for row in bond_rows:
        first_name = row[bond_index["_chem_comp_bond.atom_id_1"]]
        second_name = row[bond_index["_chem_comp_bond.atom_id_2"]]
        first = atom_ids.get(first_name, alternate_ids.get(first_name))
        second = atom_ids.get(second_name, alternate_ids.get(second_name))
        if first is None or second is None or first == second:
            continue
        adjacency[first].add(second)
        adjacency[second].add(first)
    for atom in atoms:
        atom["cif_index"] = str(atom_ids[atom["atom_id"]])
    return atoms, adjacency


def _selected_pdb_ligand(
    pdb_text: str,
    *,
    component_ids: tuple[str, ...],
    author_chain: str,
) -> tuple[list[dict[str, Any]], dict[int, set[int]]]:
    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    for line in pdb_text.splitlines():
        if len(line) < 54 or not redocking._primary_altloc(line):
            continue
        if line[:6].strip() != "HETATM" or line[21].strip() != author_chain:
            continue
        component = line[17:20].strip()
        if component not in component_ids:
            continue
        element = redocking._element_from_pdb_line(line)
        if element in {"H", "D"}:
            continue
        try:
            sequence = int(line[22:26].strip())
        except ValueError:
            continue
        insertion = line[26].strip()
        point = (
            float(line[30:38]),
            float(line[38:46]),
            float(line[46:54]),
        )
        grouped.setdefault((component, sequence, insertion), []).append(
            {
                "serial": _pdb_serial(line),
                "atom_name": line[12:16].strip(),
                "element": element,
                "point": point,
                "component": component,
                "sequence": sequence,
                "insertion": insertion,
            }
        )

    selected: list[dict[str, Any]] = []
    for component in component_ids:
        candidates = [key for key in grouped if key[0] == component]
        if len(candidates) != 1:
            raise ValueError(f"expected one {component} instance on chain {author_chain}, found {len(candidates)}")
        selected.extend(grouped[candidates[0]])

    selected_serials = {item["serial"] for item in selected}
    adjacency = {serial: set() for serial in selected_serials}
    for line in pdb_text.splitlines():
        if not line.startswith("CONECT"):
            continue
        serials = _pdb_conect_serials(line)
        if not serials:
            continue
        source = serials[0]
        for target in serials[1:]:
            if source in selected_serials and target in selected_serials and source != target:
                adjacency[source].add(target)
                adjacency[target].add(source)
    return selected, adjacency


def _graph_isomorphisms(
    source_elements: list[str],
    source_adjacency: list[set[int]],
    target_elements: list[str],
    target_adjacency: list[set[int]],
    *,
    source_labels: list[tuple[Any, ...]],
    limit: int = 4096,
) -> list[tuple[int, ...]]:
    if len(source_elements) != len(target_elements):
        return []
    candidates = [
        [
            target_index
            for target_index, element in enumerate(target_elements)
            if element == source_element
            and len(target_adjacency[target_index]) == len(source_adjacency[source_index])
        ]
        for source_index, source_element in enumerate(source_elements)
    ]
    if any(not options for options in candidates):
        return []

    order = sorted(
        range(len(source_elements)),
        key=lambda index: (
            len(candidates[index]),
            -len(source_adjacency[index]),
            source_elements[index],
            source_labels[index],
        ),
    )
    mapping: dict[int, int] = {}
    used: set[int] = set()
    results: list[tuple[int, ...]] = []

    def visit(position: int) -> None:
        if len(results) >= limit:
            return
        if position == len(order):
            results.append(tuple(mapping[index] for index in range(len(source_elements))))
            return
        source_index = order[position]
        for target_index in candidates[source_index]:
            if target_index in used:
                continue
            compatible = True
            for assigned_source, assigned_target in mapping.items():
                if (assigned_source in source_adjacency[source_index]) != (
                    assigned_target in target_adjacency[target_index]
                ):
                    compatible = False
                    break
            if not compatible:
                continue
            mapping[source_index] = target_index
            used.add(target_index)
            visit(position + 1)
            used.remove(target_index)
            del mapping[source_index]

    visit(0)
    return results


def _coordinate_comparison(
    selected_pdb_atoms: list[dict[str, Any]],
    ccd_atoms: list[dict[str, str]],
    ccd_adjacency: list[set[int]],
    molecule: Chem.Mol,
    frozen_holo_coordinate_hash: str,
) -> dict[str, Any]:
    ccd_name_to_index: dict[str, int] = {}
    for index, atom in enumerate(ccd_atoms):
        ccd_name_to_index[atom["atom_id"]] = index
        if atom["alt_atom_id"] not in {"?", "."}:
            ccd_name_to_index.setdefault(atom["alt_atom_id"], index)
    try:
        pdb_ccd_indices = [ccd_name_to_index[item["atom_name"]] for item in selected_pdb_atoms]
    except KeyError as exc:
        return {
            "graph_isomorphism_count": 0,
            "graph_match": False,
            "same_frame_rigid_fit_performed": False,
            "reason": f"holo PDB atom name is absent from CCD graph: {exc}",
        }
    pdb_elements = [ccd_atoms[index]["element"] for index in pdb_ccd_indices]
    pdb_adjacency = [
        {pdb_ccd_indices.index(neighbor) for neighbor in ccd_adjacency[ccd_index] if neighbor in pdb_ccd_indices}
        for ccd_index in pdb_ccd_indices
    ]
    sdf_elements, sdf_adjacency, sdf_indices = _heavy_graph(molecule)
    mappings = _graph_isomorphisms(
        pdb_elements,
        pdb_adjacency,
        sdf_elements,
        sdf_adjacency,
        source_labels=[(item["atom_name"], item["serial"]) for item in selected_pdb_atoms],
    )
    if not mappings:
        return {
            "graph_isomorphism_count": 0,
            "graph_match": False,
            "same_frame_rigid_fit_performed": False,
            "reason": "no element-labeled heavy-atom graph isomorphism",
        }

    conformer = molecule.GetConformer()
    sdf_points = [conformer.GetAtomPosition(index) for index in sdf_indices]
    pdb_points = [item["point"] for item in selected_pdb_atoms]
    comparisons: list[dict[str, Any]] = []
    for mapping in mappings:
        deltas = []
        for pdb_index, sdf_index in enumerate(mapping):
            point = sdf_points[sdf_index]
            delta = (
                point.x - pdb_points[pdb_index][0],
                point.y - pdb_points[pdb_index][1],
                point.z - pdb_points[pdb_index][2],
            )
            deltas.append((delta[0] ** 2 + delta[1] ** 2 + delta[2] ** 2) ** 0.5)
        comparisons.append(
            {
                "mapping": list(mapping),
                "max_delta_angstrom": max(deltas),
                "rmsd_angstrom": (sum(value * value for value in deltas) / len(deltas)) ** 0.5,
                "mapped_coordinate_hash": sha256_json(
                    [[round(sdf_points[index].x, 6), round(sdf_points[index].y, 6), round(sdf_points[index].z, 6)] for index in mapping]
                ),
            }
        )
    best = min(comparisons, key=lambda item: (item["max_delta_angstrom"], item["rmsd_angstrom"], item["mapping"]))
    return {
        "graph_isomorphism_count": len(mappings),
        "graph_match": True,
        "same_frame_rigid_fit_performed": False,
        "frozen_holo_coordinate_hash": frozen_holo_coordinate_hash,
        "mapped_coordinate_hash": best["mapped_coordinate_hash"],
        "frozen_holo_coordinate_hash_matches": best["mapped_coordinate_hash"] == frozen_holo_coordinate_hash,
        "best_mapping": best["mapping"],
        "max_delta_angstrom": best["max_delta_angstrom"],
        "rmsd_angstrom": best["rmsd_angstrom"],
        "coordinate_equivalent_threshold_angstrom": 0.0011,
        "coordinate_equivalent": best["max_delta_angstrom"] <= 0.0011,
    }


def _case_url(case: apodock001.ApoHoloCase, auth_seq_id: int) -> str:
    return (
        f"https://models.rcsb.org/v1/{case.holo_pdb_id.lower()}/ligand?"
        f"auth_asym_id={case.holo_ligand_author_chain}&auth_seq_id={auth_seq_id}&encoding=sdf"
    )


def _ideal_ccd_url(component_id: str) -> str:
    return f"https://files.rcsb.org/ligands/view/{component_id}_ideal.sdf"


def _protocol_cases(protocol: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = {case["case_id"]: case for case in protocol["benchmark"]["cases"] if case["case_id"] != "APD-010"}
    if tuple(sorted(cases)) != tuple(f"APD-{index:03d}" for index in range(1, 10)):
        raise ValueError("protocol does not contain exactly APD-001..APD-009")
    return cases


def audit(args: argparse.Namespace) -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if protocol["protocol_id"] != EXPECTED_PROTOCOL_ID:
        raise ValueError(f"unexpected protocol id: {protocol['protocol_id']}")
    protocol_cases = _protocol_cases(protocol)
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    pdb_dir = Path(args.pdb_dir)
    historical_dir = Path(args.historical_artifact_dir) if args.historical_artifact_dir else None
    historical_files = []
    if historical_dir and historical_dir.is_dir():
        historical_files = sorted(str(path.relative_to(historical_dir)) for path in historical_dir.rglob("*" ) if path.is_file())

    records: list[dict[str, Any]] = []
    for case in apodock001.FROZEN_PUBLISHED_CASES[:9]:
        config_case = protocol_cases[case.case_id]
        pdb_path = pdb_dir / f"{case.holo_pdb_id}.pdb"
        if not pdb_path.is_file():
            raise FileNotFoundError(pdb_path)
        pdb_sha256 = _sha256(pdb_path.read_bytes())
        if pdb_sha256 != config_case["holo_pdb_sha256"]:
            raise ValueError(f"frozen holo PDB hash mismatch for {case.case_id}")
        selected_atoms, _pdb_adjacency = _selected_pdb_ligand(
            pdb_path.read_text(encoding="utf-8", errors="replace"),
            component_ids=case.holo_ligand_components,
            author_chain=case.holo_ligand_author_chain,
        )
        auth_seq_id = selected_atoms[0]["sequence"]
        if len({item["sequence"] for item in selected_atoms}) != 1:
            raise ValueError(f"unexpected multiple sequence ids for {case.case_id}")
        url = _case_url(case, auth_seq_id)
        attempt_records = []
        case_dir = workdir / "downloads" / case.case_id
        for attempt in range(1, args.attempts + 1):
            destination = case_dir / f"attempt-{attempt}.sdf"
            attempt_records.append(_download(url, destination, args.user_agent))

        first_sdf = case_dir / "attempt-1.sdf"
        molecule = _load_single_sdf(first_sdf)
        current_identity = _molecule_identity(molecule)
        selected_pdb_identity = {
            "heavy_atom_count": len(selected_atoms),
            "element_counts": dict(sorted(Counter(item["element"] for item in selected_atoms).items())),
            "component_ids": list(case.holo_ligand_components),
            "author_chain": case.holo_ligand_author_chain,
            "auth_seq_id": auth_seq_id,
        }

        ideal_url = _ideal_ccd_url(case.holo_ligand_components[0])
        ideal_path = workdir / "ccd" / f"{case.holo_ligand_components[0]}_ideal.sdf"
        ideal_download = _download(ideal_url, ideal_path, args.user_agent)
        ideal_molecule = _load_single_sdf(ideal_path)
        ideal_identity = _molecule_identity(ideal_molecule)
        cif_url = f"https://files.rcsb.org/ligands/view/{case.holo_ligand_components[0]}.cif"
        cif_path = workdir / "ccd" / f"{case.holo_ligand_components[0]}.cif"
        cif_download = _download(cif_url, cif_path, args.user_agent)
        ccd_atoms, ccd_adjacency = _ccd_graph(cif_path.read_text(encoding="utf-8"))
        coordinate = _coordinate_comparison(
            selected_atoms,
            ccd_atoms,
            ccd_adjacency,
            molecule,
            config_case["holo_reference_coordinate_hash"],
        )
        chemical_equivalent = (
            current_identity["formula"] == ideal_identity["formula"]
            and current_identity["heavy_atom_count"] == ideal_identity["heavy_atom_count"]
            and current_identity["formal_charge"] == ideal_identity["formal_charge"]
            and current_identity["element_counts"] == ideal_identity["element_counts"]
            and current_identity["canonical_isomeric_smiles"] == ideal_identity["canonical_isomeric_smiles"]
            and selected_pdb_identity["heavy_atom_count"] == current_identity["heavy_atom_count"]
            and selected_pdb_identity["element_counts"] == current_identity["element_counts"]
            and coordinate.get("graph_match") is True
        )
        coordinate_equivalent = coordinate.get("coordinate_equivalent") is True
        frozen_hash = config_case["reference_sdf_sha256"]
        observed_hashes = [item["sha256"] for item in attempt_records]
        byte_match = frozen_hash in observed_hashes
        if byte_match:
            classification = "BYTE_MATCH"
        elif not chemical_equivalent:
            classification = "CHEMISTRY_DRIFT"
        elif not coordinate_equivalent:
            classification = "COORDINATE_DRIFT"
        else:
            classification = "REPRESENTATION_DRIFT"
        records.append(
            {
                "case_id": case.case_id,
                "filename": config_case["reference_filename"],
                "pdb_id": case.holo_pdb_id,
                "ccd_id": case.holo_ligand_components[0],
                "auth_chain": case.holo_ligand_author_chain,
                "auth_seq_id": auth_seq_id,
                "url": url,
                "frozen_reference_sdf_sha256": frozen_hash,
                "download_attempts": attempt_records,
                "download_hashes_identical": len(set(observed_hashes)) == 1,
                "observed_reference_sdf_sha256": observed_hashes[0],
                "byte_match": byte_match,
                "current_identity": current_identity,
                "ccd_ideal_download": ideal_download,
                "ccd_cif_download": cif_download,
                "ccd_ideal_identity": ideal_identity,
                "holo_pdb_identity": selected_pdb_identity,
                "coordinate_comparison": coordinate,
                "chemical_equivalent_to_ccd_and_holo_instance": chemical_equivalent,
                "classification": classification,
            }
        )

    equivalent = all(record["classification"] in {"BYTE_MATCH", "REPRESENTATION_DRIFT"} for record in records)
    byte_exact = all(record["byte_match"] for record in records)
    report = {
        "audit_kind": "APODOCK-001 SDF provenance audit; no docking",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_id": protocol["protocol_id"],
        "protocol_hash": protocol["protocol_hash"],
        "protocol_manifest_unchanged": True,
        "historical_artifact": {
            **HISTORICAL_ARTIFACT,
            "files": historical_files,
            "contains_reference_sdfs": any(path.lower().endswith((".sdf", ".sd", ".mol")) for path in historical_files),
            "frozen_sdf_bytes_recovered": False,
        },
        "source_contract": {
            "historical_download_user_agent": "Research-OS/5.1 REDOCK-001",
            "audit_url_template": "https://models.rcsb.org/v1/{pdb_id}/ligand?auth_asym_id={chain}&auth_seq_id={auth_seq_id}&encoding=sdf",
            "current_downloads_per_case": args.attempts,
            "ccd_ideal_endpoint": "https://files.rcsb.org/ligands/view/{ccd}_ideal.sdf",
        },
        "records": records,
        "summary": {
            "case_count": len(records),
            "byte_exact_cases": sum(record["byte_match"] for record in records),
            "stable_current_download_cases": sum(record["download_hashes_identical"] for record in records),
            "scientifically_equivalent_cases": sum(record["classification"] in {"BYTE_MATCH", "REPRESENTATION_DRIFT"} for record in records),
            "classifications": dict(sorted(Counter(record["classification"] for record in records).items())),
            "all_nine_scientifically_equivalent": equivalent,
            "all_nine_byte_exact": byte_exact,
            "v1_0_1_byte_exactly_executable": byte_exact,
            "v1_0_2_scientifically_justified_if_reviewed": equivalent and not byte_exact,
            "vina_docking_executed": False,
            "vina_received_receptor_or_ligand": False,
            "prospective_scores_or_poses_observed": False,
        },
        "scientific_identity_note": (
            "The frozen v1.0.1 byte hashes remain authoritative. A stable current SDF that is chemically and "
            "coordinate equivalent is representation drift, not permission to mutate v1.0.1; it can support a "
            "separately reviewed v1.0.2 input bundle only."
        ),
    }
    report["audit_report_hash"] = sha256_json(report)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", default=".audit/apodock001-sdf-provenance")
    parser.add_argument("--pdb-dir", default=".run-input-preflight/pdb")
    parser.add_argument("--historical-artifact-dir", default=".audit/apodock001-sdf-provenance/historical-artifact")
    parser.add_argument("--output", default="docs/apodock001-sdf-provenance-audit-v1.0.1.json")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    args = parser.parse_args()
    if args.attempts != 3:
        raise SystemExit("this audit requires exactly three independent downloads per case")
    report = audit(args)
    summary = report["summary"]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
