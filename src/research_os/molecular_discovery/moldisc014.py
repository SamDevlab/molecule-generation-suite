"""MOLDISC-014: source-directed AqSolDB interpolation panel.

This program generates exactly three bounded structures from the selected
MOLDISC-011 seed, then characterizes all four panel members.  The edits are
defined from connectivity only; AqSolDB measurements and ESOL outputs are
never used to define, filter, rank, or select the panel.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from research_os.core.hashing import sha256_json
from research_os.molecular_discovery.aqsoldb_coverage import (
    AQSOLDB_DOI,
    AQSOLDB_ID,
    AQSOLDB_SOURCE_BLOB_SHA,
    AQSOLDB_SOURCE_COMMIT,
    EXPECTED_PARSED_SOURCE_HASH,
    EXPECTED_SOURCE_ROW_COUNT,
    AqSolDBCoverageReport,
    AqSolDBSourceRecord,
    assess_aqsoldb_coverage,
    download_aqsoldb,
)
from research_os.molecular_discovery.solubility import FrozenESOLSolubilityPredictor
from research_os.molecule.lab import MoleculeLab


PROGRAM_ID = "MOLDISC-014"
PROGRAM_VERSION = "1.0"
GENERATOR_ID = "research-os.molecular-discovery.aqsoldb-source-interpolation.v1"
PARENT_MOLDISC011_HASH = "8cb29619a82ca4680424c1b37c9bdce37b83e6cc8d570788435e1e9a62b159ff"
CONTEXT_MOLDISC013_HASH = "325edfa890dabc1f8640f9977c6b2e308b582293493631a040752739fd6d89a4"
SEED_VARIANT_ID = "STEP2-DEMETHYL-01"
SEED_CANDIDATE_ID = "MOLDISC-011-JE2-286E6F2BE8"
SEED_SMILES = "CC1(C)SCN(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)[C@@H]1C(=O)NCc1ccccc1"
SEED_INCHIKEY = "DRIAWXDDGSORDT-KKUQBAQOSA-N"
SEED_HEAVY_ATOMS = 39

SOURCE_RAW_SMILES = "CC(C)(C)NC(=O)C1N(CSC1(C)C)C(=O)C(O)C(CC2=CC=CC=C2)NC(=O)C3=CC=CC=C3"
SOURCE_CANONICAL_SMILES = "CC(C)(C)NC(=O)C1N(C(=O)C(O)C(Cc2ccccc2)NC(=O)c2ccccc2)CSC1(C)C"
SOURCE_INCHIKEY = "URHJIBSBOJFXDI-UHFFFAOYSA-N"
SOURCE_CONNECTIVITY_BLOCK = "URHJIBSBOJFXDI"
SOURCE_ID = "C-2545"
SOURCE_OBSERVATION_COUNT = 1
SOURCE_MEASURED_LOG_S = -3.62

DELTA_OH_VARIANT_ID = "SOURCE-DELTA-OH"
DELTA_OH_CANDIDATE_ID = "MOLDISC-014-SOURCE-DELTA-OH"
DELTA_OH_SMILES = "CC1(C)SCN(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2ccccc2)[C@@H]1C(=O)NCc1ccccc1"
DELTA_OH_INCHIKEY = "NAZMDUVPQSKJEQ-KKUQBAQOSA-N"
DELTA_OH_HEAVY_ATOMS = 38

DELTA_NSUB_VARIANT_ID = "SOURCE-DELTA-NSUB"
DELTA_NSUB_CANDIDATE_ID = "MOLDISC-014-SOURCE-DELTA-NSUB"
DELTA_NSUB_SMILES = "CC(C)(C)NC(=O)[C@H]1N(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)CSC1(C)C"
DELTA_NSUB_INCHIKEY = "DMSDTDPQGPRTNA-FDFHNCONSA-N"
DELTA_NSUB_HEAVY_ATOMS = 36

DELTA_BOTH_VARIANT_ID = "SOURCE-DELTA-BOTH"
DELTA_BOTH_CANDIDATE_ID = "MOLDISC-014-SOURCE-DELTA-BOTH"
DELTA_BOTH_SMILES = "CC(C)(C)NC(=O)[C@H]1N(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2ccccc2)CSC1(C)C"
DELTA_BOTH_INCHIKEY = "URHJIBSBOJFXDI-FDFHNCONSA-N"
DELTA_BOTH_HEAVY_ATOMS = 35

PANEL_VARIANT_IDS = (
    SEED_VARIANT_ID,
    DELTA_OH_VARIANT_ID,
    DELTA_NSUB_VARIANT_ID,
    DELTA_BOTH_VARIANT_ID,
)
PANEL_CANDIDATE_IDS = (
    SEED_CANDIDATE_ID,
    DELTA_OH_CANDIDATE_ID,
    DELTA_NSUB_CANDIDATE_ID,
    DELTA_BOTH_CANDIDATE_ID,
)


class MOLDISC014Error(RuntimeError):
    """Fail-closed error for MOLDISC-014 protocol or identity drift."""


def _rdkit():
    try:
        from rdkit import Chem
        from rdkit.Chem import inchi
    except ImportError as exc:
        raise MOLDISC014Error("MOLDISC-014 requires RDKit; install the 'discovery' extra") from exc
    return Chem, inchi


def _identity(smiles: str) -> dict[str, Any]:
    Chem, inchi = _rdkit()
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise MOLDISC014Error(f"invalid or unsanitizable SMILES: {smiles!r}")
    return {
        "canonical_isomeric_smiles": Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True),
        "canonical_nonisomeric_smiles": Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=False),
        "inchikey": inchi.MolToInchiKey(molecule),
        "connectivity_inchikey_block": inchi.MolToInchiKey(molecule).split("-", 1)[0],
        "heavy_atom_count": molecule.GetNumHeavyAtoms(),
        "molecule": molecule,
    }


def _sanitize(molecule: Any, label: str) -> Any:
    Chem, _ = _rdkit()
    try:
        Chem.SanitizeMol(molecule)
    except Exception as exc:
        raise MOLDISC014Error(f"{label} failed RDKit sanitization") from exc
    return molecule


def _remove_phenolic_hydroxyl(seed: Any) -> Any:
    Chem, _ = _rdkit()
    matches = []
    for atom in seed.GetAtoms():
        if atom.GetAtomicNum() != 8 or atom.GetDegree() != 1 or atom.GetTotalNumHs() < 1:
            continue
        neighbor = atom.GetNeighbors()[0]
        if neighbor.GetIsAromatic() and neighbor.GetAtomicNum() == 6:
            matches.append(atom.GetIdx())
    if len(matches) != 1:
        raise MOLDISC014Error(f"expected exactly one phenolic hydroxyl, found {len(matches)}")
    editable = Chem.RWMol(seed)
    editable.RemoveAtom(matches[0])
    return _sanitize(editable.GetMol(), "SOURCE-DELTA-OH")


def _find_n_benzyl(seed: Any) -> tuple[int, int]:
    candidates: list[tuple[int, int]] = []
    for nitrogen in seed.GetAtoms():
        if nitrogen.GetAtomicNum() != 7:
            continue
        has_carbonyl_neighbor = any(
            neighbor.GetAtomicNum() == 6
            and any(
                bond.GetBondType() == ChemBondType.DOUBLE
                and bond.GetOtherAtom(neighbor).GetAtomicNum() == 8
                for bond in neighbor.GetBonds()
            )
            for neighbor in nitrogen.GetNeighbors()
        )
        if not has_carbonyl_neighbor:
            continue
        for neighbor in nitrogen.GetNeighbors():
            if neighbor.GetAtomicNum() != 6 or neighbor.GetIsAromatic():
                continue
            if neighbor.GetTotalNumHs() != 2 or neighbor.GetDegree() != 2:
                continue
            aromatic_neighbors = [item for item in neighbor.GetNeighbors() if item.GetIsAromatic()]
            if len(aromatic_neighbors) == 1:
                candidates.append((nitrogen.GetIdx(), neighbor.GetIdx()))
    if len(candidates) != 1:
        raise MOLDISC014Error(f"expected exactly one terminal N-benzyl substituent, found {len(candidates)}")
    return candidates[0]


def _replace_n_benzyl_with_tert_butyl(seed: Any) -> Any:
    Chem, _ = _rdkit()
    nitrogen_idx, benzyl_root_idx = _find_n_benzyl(seed)
    component: set[int] = set()
    stack = [benzyl_root_idx]
    while stack:
        current = stack.pop()
        if current in component or current == nitrogen_idx:
            continue
        component.add(current)
        atom = seed.GetAtomWithIdx(current)
        stack.extend(neighbor.GetIdx() for neighbor in atom.GetNeighbors() if neighbor.GetIdx() != nitrogen_idx)
    if len(component) != 7:
        raise MOLDISC014Error(f"N-benzyl component has unexpected size: {len(component)}")

    editable = Chem.RWMol(seed)
    for index in sorted(component, reverse=True):
        editable.RemoveAtom(index)
    new_nitrogen_idx = nitrogen_idx - sum(index < nitrogen_idx for index in component)
    central = editable.AddAtom(Chem.Atom("C"))
    editable.AddBond(new_nitrogen_idx, central, ChemBondType.SINGLE)
    for _ in range(3):
        methyl = editable.AddAtom(Chem.Atom("C"))
        editable.AddBond(central, methyl, ChemBondType.SINGLE)
    return _sanitize(editable.GetMol(), "SOURCE-DELTA-NSUB")


# The small aliases keep the graph-edit predicates readable while importing
# RDKit lazily for environments that only inspect the package metadata.
def _bond_type(name: str) -> Any:
    Chem, _ = _rdkit()
    return getattr(Chem.BondType, name)


ChemBondType = type("_ChemBondType", (), {"DOUBLE": _bond_type("DOUBLE"), "SINGLE": _bond_type("SINGLE")})


@dataclass(frozen=True)
class PanelEntry:
    variant_id: str
    candidate_id: str
    source_role: str
    canonical_smiles: str
    canonical_nonisomeric_smiles: str
    inchikey: str
    connectivity_inchikey_block: str
    heavy_atom_count: int
    edits: tuple[str, ...]
    generator_id: str
    evidence_level: str = "E0_HEURISTIC"

    @property
    def generation_hash(self) -> str:
        return sha256_json({
            "variant_id": self.variant_id,
            "candidate_id": self.candidate_id,
            "source_role": self.source_role,
            "canonical_smiles": self.canonical_smiles,
            "canonical_nonisomeric_smiles": self.canonical_nonisomeric_smiles,
            "inchikey": self.inchikey,
            "connectivity_inchikey_block": self.connectivity_inchikey_block,
            "heavy_atom_count": self.heavy_atom_count,
            "edits": list(self.edits),
            "generator_id": self.generator_id,
            "evidence_level": self.evidence_level,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "edits": list(self.edits),
            "generation_hash": self.generation_hash,
        }


def _panel_entry(variant_id: str, candidate_id: str, source_role: str, molecule: Any, edits: tuple[str, ...]) -> PanelEntry:
    Chem, inchi = _rdkit()
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    nonisomeric = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=False)
    key = inchi.MolToInchiKey(molecule)
    return PanelEntry(
        variant_id=variant_id,
        candidate_id=candidate_id,
        source_role=source_role,
        canonical_smiles=canonical,
        canonical_nonisomeric_smiles=nonisomeric,
        inchikey=key,
        connectivity_inchikey_block=key.split("-", 1)[0],
        heavy_atom_count=molecule.GetNumHeavyAtoms(),
        edits=edits,
        generator_id=GENERATOR_ID,
    )


def load_program_config_v14(path: str | Path) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MOLDISC014Error(f"could not load MOLDISC-014 config: {path}") from exc
    if not isinstance(config, dict) or config.get("program_id") != PROGRAM_ID or config.get("program_version") != PROGRAM_VERSION:
        raise MOLDISC014Error("MOLDISC-014 requires frozen program_id/version 1.0")

    upstream = config.get("upstream") or {}
    if (
        upstream.get("moldisc011_program_scientific_hash") != PARENT_MOLDISC011_HASH
        or upstream.get("selected_variant_id") != SEED_VARIANT_ID
        or upstream.get("selected_candidate_id") != SEED_CANDIDATE_ID
        or upstream.get("moldisc013_geometry_used_for_generation") is not False
        or upstream.get("moldisc013_geometry_used_for_selection") is not False
        or upstream.get("moldisc013_program_scientific_hash") != CONTEXT_MOLDISC013_HASH
    ):
        raise MOLDISC014Error("MOLDISC-014 upstream identity or geometry boundary drifted")

    seed = config.get("seed") or {}
    if (
        seed.get("variant_id") != SEED_VARIANT_ID
        or seed.get("candidate_id") != SEED_CANDIDATE_ID
        or seed.get("canonical_smiles") != SEED_SMILES
        or seed.get("inchikey") != SEED_INCHIKEY
        or seed.get("heavy_atoms") != SEED_HEAVY_ATOMS
    ):
        raise MOLDISC014Error("MOLDISC-011 selected seed identity drifted")

    source = config.get("source") or {}
    if (
        source.get("source_id") != AQSOLDB_ID
        or source.get("doi") != AQSOLDB_DOI
        or source.get("source_commit") != AQSOLDB_SOURCE_COMMIT
        or source.get("source_blob_sha") != AQSOLDB_SOURCE_BLOB_SHA
        or source.get("parsed_source_hash") != EXPECTED_PARSED_SOURCE_HASH
        or source.get("expected_raw_smiles") != SOURCE_RAW_SMILES
        or source.get("expected_canonical_nonisomeric_smiles") != SOURCE_CANONICAL_SMILES
        or source.get("expected_inchikey") != SOURCE_INCHIKEY
        or source.get("expected_connectivity_block") != SOURCE_CONNECTIVITY_BLOCK
        or source.get("expected_source_ids") != [SOURCE_ID]
        or source.get("expected_observation_count") != SOURCE_OBSERVATION_COUNT
        or float(source.get("expected_measured_log_s_mol_l", float("nan"))) != SOURCE_MEASURED_LOG_S
    ):
        raise MOLDISC014Error("immutable AqSolDB source identity drifted in config")

    deltas = config.get("deltas") or {}
    expected_deltas = {
        DELTA_OH_VARIANT_ID: (DELTA_OH_CANDIDATE_ID, DELTA_OH_SMILES, DELTA_OH_INCHIKEY, DELTA_OH_HEAVY_ATOMS),
        DELTA_NSUB_VARIANT_ID: (DELTA_NSUB_CANDIDATE_ID, DELTA_NSUB_SMILES, DELTA_NSUB_INCHIKEY, DELTA_NSUB_HEAVY_ATOMS),
        DELTA_BOTH_VARIANT_ID: (DELTA_BOTH_CANDIDATE_ID, DELTA_BOTH_SMILES, DELTA_BOTH_INCHIKEY, DELTA_BOTH_HEAVY_ATOMS),
    }
    if tuple(deltas) != (DELTA_OH_VARIANT_ID, DELTA_NSUB_VARIANT_ID, DELTA_BOTH_VARIANT_ID):
        raise MOLDISC014Error("MOLDISC-014 must contain exactly the two orthogonal deltas")
    for variant_id, expected in expected_deltas.items():
        item = deltas.get(variant_id) or {}
        if (
            item.get("candidate_id"), item.get("canonical_smiles"), item.get("inchikey"), item.get("expected_heavy_atoms")
        ) != expected:
            raise MOLDISC014Error(f"{variant_id} identity drifted")
    if config.get("panel_variant_ids") != list(PANEL_VARIANT_IDS):
        raise MOLDISC014Error("MOLDISC-014 panel is not exactly seed plus three products")

    boundaries = config.get("boundaries") or {}
    required_false = (
        "source_measurement_used_for_edit_definition",
        "source_measurement_used_for_generation",
        "source_measurement_used_for_filtering",
        "source_measurement_used_for_ranking",
        "candidate_selection_executed",
        "docking_executed",
        "moldisc010_score_used",
        "moldisc012_score_used",
        "moldisc013_geometry_used",
    )
    if any(boundaries.get(key) is not False for key in required_false) or boundaries.get("source_structure_used_for_edit_definition") is not True:
        raise MOLDISC014Error("MOLDISC-014 measurement, selection, or docking boundary drifted")
    if boundaries.get("selected_candidate_id") is not None or boundaries.get("measurement_transfer_rule") != "exact_canonical_isomeric_structure_match_only":
        raise MOLDISC014Error("MOLDISC-014 selection or measurement-transfer rule drifted")
    if config.get("generator_id") != GENERATOR_ID or config.get("evidence_level") != "E0_HEURISTIC":
        raise MOLDISC014Error("MOLDISC-014 generator or evidence identity drifted")
    return config


def generate_panel() -> tuple[PanelEntry, ...]:
    Chem, _ = _rdkit()
    seed_identity = _identity(SEED_SMILES)
    if (
        seed_identity["canonical_isomeric_smiles"] != SEED_SMILES
        or seed_identity["inchikey"] != SEED_INCHIKEY
        or seed_identity["heavy_atom_count"] != SEED_HEAVY_ATOMS
    ):
        raise MOLDISC014Error("active MOLDISC-011 seed identity differs from frozen identity")
    seed = seed_identity["molecule"]
    delta_oh = _remove_phenolic_hydroxyl(seed)
    delta_nsub = _replace_n_benzyl_with_tert_butyl(seed)
    delta_both = _replace_n_benzyl_with_tert_butyl(delta_oh)
    entries = (
        _panel_entry(SEED_VARIANT_ID, SEED_CANDIDATE_ID, "UPSTREAM_SELECTED_SEED", seed, ()),
        _panel_entry(DELTA_OH_VARIANT_ID, DELTA_OH_CANDIDATE_ID, "SOURCE_DIRECTED_GENERATED", delta_oh, ("phenolic_hydroxyl_deletion",)),
        _panel_entry(DELTA_NSUB_VARIANT_ID, DELTA_NSUB_CANDIDATE_ID, "SOURCE_DIRECTED_GENERATED", delta_nsub, ("N_benzyl_to_N_tert_butyl",)),
        _panel_entry(DELTA_BOTH_VARIANT_ID, DELTA_BOTH_CANDIDATE_ID, "SOURCE_DIRECTED_GENERATED", delta_both, ("phenolic_hydroxyl_deletion", "N_benzyl_to_N_tert_butyl")),
    )
    expected = {
        SEED_VARIANT_ID: (SEED_CANDIDATE_ID, SEED_SMILES, SEED_INCHIKEY, SEED_HEAVY_ATOMS),
        DELTA_OH_VARIANT_ID: (DELTA_OH_CANDIDATE_ID, DELTA_OH_SMILES, DELTA_OH_INCHIKEY, DELTA_OH_HEAVY_ATOMS),
        DELTA_NSUB_VARIANT_ID: (DELTA_NSUB_CANDIDATE_ID, DELTA_NSUB_SMILES, DELTA_NSUB_INCHIKEY, DELTA_NSUB_HEAVY_ATOMS),
        DELTA_BOTH_VARIANT_ID: (DELTA_BOTH_CANDIDATE_ID, DELTA_BOTH_SMILES, DELTA_BOTH_INCHIKEY, DELTA_BOTH_HEAVY_ATOMS),
    }
    for entry in entries:
        identity = expected[entry.variant_id]
        if (entry.candidate_id, entry.canonical_smiles, entry.inchikey, entry.heavy_atom_count) != identity:
            raise MOLDISC014Error(f"generated identity drifted for {entry.variant_id}")
    if len({entry.canonical_smiles for entry in entries}) != 4 or any(entry.canonical_smiles == SEED_SMILES for entry in entries[1:]):
        raise MOLDISC014Error("MOLDISC-014 products are not unique from the seed")
    return entries


@dataclass(frozen=True)
class SourceNeighborAudit:
    source_id: str
    doi: str
    source_commit: str
    source_blob_sha: str
    parsed_source_hash: str
    source_row_count: int
    source_ids: tuple[str, ...]
    raw_source_smiles: str
    canonical_isomeric_smiles: str
    canonical_nonisomeric_smiles: str
    active_runtime_inchikey: str
    connectivity_inchikey_block: str
    observation_count: int
    measured_log_s_values: tuple[float, ...]
    stereo_specified: bool

    @property
    def scientific_hash(self) -> str:
        return sha256_json(self._scientific_payload())

    def _scientific_payload(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "doi": self.doi,
            "source_commit": self.source_commit,
            "source_blob_sha": self.source_blob_sha,
            "parsed_source_hash": self.parsed_source_hash,
            "source_row_count": self.source_row_count,
            "source_ids": list(self.source_ids),
            "raw_source_smiles": self.raw_source_smiles,
            "canonical_isomeric_smiles": self.canonical_isomeric_smiles,
            "canonical_nonisomeric_smiles": self.canonical_nonisomeric_smiles,
            "active_runtime_inchikey": self.active_runtime_inchikey,
            "connectivity_inchikey_block": self.connectivity_inchikey_block,
            "observation_count": self.observation_count,
            "measured_log_s_values": list(self.measured_log_s_values),
            "stereochemistry_specified": self.stereo_specified,
            "measurement_transfer_rule": "exact_canonical_isomeric_structure_match_only",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._scientific_payload(),
            "stereochemistry_specified_label": "YES" if self.stereo_specified else "NO",
            "scientific_hash": self.scientific_hash,
        }


def audit_frozen_source(
    records: Sequence[AqSolDBSourceRecord],
    *,
    source_row_count: int,
    parsed_source_hash: str,
) -> SourceNeighborAudit:
    if source_row_count != EXPECTED_SOURCE_ROW_COUNT or parsed_source_hash != EXPECTED_PARSED_SOURCE_HASH:
        raise MOLDISC014Error("AqSolDB parsed source identity drifted")
    Chem, inchi = _rdkit()
    matches = []
    for record in records:
        molecule = Chem.MolFromSmiles(record.smiles)
        if molecule is None:
            continue
        canonical_isomeric = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
        canonical_nonisomeric = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=False)
        runtime_key = inchi.MolToInchiKey(molecule)
        if canonical_nonisomeric == SOURCE_CANONICAL_SMILES and runtime_key == SOURCE_INCHIKEY:
            matches.append((record, canonical_isomeric, canonical_nonisomeric, runtime_key))
    if len(matches) != SOURCE_OBSERVATION_COUNT:
        raise MOLDISC014Error(f"expected one immutable recurring source observation, found {len(matches)}")
    record, canonical_isomeric, canonical_nonisomeric, runtime_key = matches[0]
    if (
        record.source_id != SOURCE_ID
        or record.source_inchikey != SOURCE_INCHIKEY
        or record.measured_log_s_mol_l != SOURCE_MEASURED_LOG_S
        or canonical_nonisomeric != SOURCE_CANONICAL_SMILES
        or runtime_key != SOURCE_INCHIKEY
    ):
        raise MOLDISC014Error("recurring AqSolDB source record contradicted frozen identity")
    stereo_specified = canonical_isomeric != canonical_nonisomeric or runtime_key.split("-")[1] != "UHFFFAOYSA"
    return SourceNeighborAudit(
        source_id=AQSOLDB_ID,
        doi=AQSOLDB_DOI,
        source_commit=AQSOLDB_SOURCE_COMMIT,
        source_blob_sha=AQSOLDB_SOURCE_BLOB_SHA,
        parsed_source_hash=parsed_source_hash,
        source_row_count=source_row_count,
        source_ids=(record.source_id,),
        raw_source_smiles=record.smiles,
        canonical_isomeric_smiles=canonical_isomeric,
        canonical_nonisomeric_smiles=canonical_nonisomeric,
        active_runtime_inchikey=runtime_key,
        connectivity_inchikey_block=runtime_key.split("-", 1)[0],
        observation_count=1,
        measured_log_s_values=(float(record.measured_log_s_mol_l),),
        stereo_specified=stereo_specified,
    )


def measurement_transfer_decision(entry: PanelEntry, source: SourceNeighborAudit) -> dict[str, bool]:
    exact = (
        entry.canonical_smiles == source.canonical_isomeric_smiles
        and entry.inchikey == source.active_runtime_inchikey
    )
    same_connectivity = (
        entry.canonical_nonisomeric_smiles == source.canonical_nonisomeric_smiles
        and entry.connectivity_inchikey_block == source.connectivity_inchikey_block
    )
    full_match = entry.inchikey == source.active_runtime_inchikey
    return {
        "exact_canonical_match": exact,
        "same_connectivity_as_recurring_source": same_connectivity,
        "full_inchikey_match_to_recurring_source": full_match,
        "measurement_transfer_allowed": exact,
    }


@dataclass(frozen=True)
class EvidenceProfile:
    candidate_id: str
    variant_id: str
    source_role: str
    canonical_smiles: str
    canonical_nonisomeric_smiles: str
    inchikey: str
    connectivity_inchikey_block: str
    heavy_atom_count: int
    chemistry_status: str
    esol_status: str
    predicted_log_s_mol_l: float | None
    esol_max_training_tanimoto: float | None
    esol_interpretation: str
    aqsoldb_nearest_similarity: float
    aqsoldb_similarity_bin: str
    neighbors_ge_0_4: int
    neighbors_ge_0_6: int
    neighbors_ge_0_8: int
    top_neighbor_smiles: str | None
    top_neighbor_inchikey: str | None
    top_neighbor_source_ids: tuple[str, ...]
    top_neighbor_observation_count: int | None
    top_neighbor_log_s_median: float | None
    top_neighbor_log_s_min: float | None
    top_neighbor_log_s_max: float | None
    exact_canonical_match: bool
    same_connectivity_as_recurring_source: bool
    full_inchikey_match_to_recurring_source: bool
    measurement_transfer_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "top_neighbor_source_ids": list(self.top_neighbor_source_ids),
        }


def _evidence_payload(run: Any, kind: str) -> dict[str, Any] | None:
    for evidence in reversed(tuple(getattr(run, "evidence", ()) )):
        if getattr(evidence, "kind", None) == kind:
            return dict(evidence.payload)
    return None


def _characterize_panel(
    entries: Sequence[PanelEntry],
    predictor: FrozenESOLSolubilityPredictor,
    coverage: AqSolDBCoverageReport,
    source: SourceNeighborAudit,
) -> tuple[tuple[EvidenceProfile, ...], dict[str, Any]]:
    coverage_by_id = {item.candidate_id: item for item in coverage.candidates}
    lab = MoleculeLab()
    profiles: list[EvidenceProfile] = []
    characterization_payload: list[dict[str, Any]] = []
    for entry in entries:
        run = lab.run(
            {
                "id": entry.candidate_id,
                "name": entry.variant_id,
                "smiles": entry.canonical_smiles,
                "source": "moldisc-014-source-directed-interpolation",
            },
            experiment="molecular_discovery_characterization",
        )
        chemistry_status = "PASS" if run.passed else "FAIL"
        molecule_properties = _evidence_payload(run, "deterministic_molecular_properties")
        prediction = predictor.predict(entry.canonical_smiles) if run.passed else None
        local = coverage_by_id.get(entry.candidate_id)
        if local is None or not local.top_neighbors:
            raise MOLDISC014Error(f"AqSolDB coverage missing for {entry.candidate_id}")
        top = local.top_neighbors[0]
        transfer = measurement_transfer_decision(entry, source)
        profile = EvidenceProfile(
            candidate_id=entry.candidate_id,
            variant_id=entry.variant_id,
            source_role=entry.source_role,
            canonical_smiles=entry.canonical_smiles,
            canonical_nonisomeric_smiles=entry.canonical_nonisomeric_smiles,
            inchikey=entry.inchikey,
            connectivity_inchikey_block=entry.connectivity_inchikey_block,
            heavy_atom_count=entry.heavy_atom_count,
            chemistry_status=chemistry_status,
            esol_status=prediction.domain_status if prediction else "NOT_REQUESTED",
            predicted_log_s_mol_l=prediction.predicted_log_s_mol_l if prediction else None,
            esol_max_training_tanimoto=prediction.max_training_tanimoto if prediction else None,
            esol_interpretation=(
                "unsupported extrapolative model output"
                if prediction is not None and prediction.domain_status == "OUT_OF_DOMAIN"
                else "frozen E1_ML model output; not an experimental measurement"
            ),
            aqsoldb_nearest_similarity=local.nearest_similarity,
            aqsoldb_similarity_bin=local.similarity_bin,
            neighbors_ge_0_4=local.neighbors_ge_0_4,
            neighbors_ge_0_6=local.neighbors_ge_0_6,
            neighbors_ge_0_8=local.neighbors_ge_0_8,
            top_neighbor_smiles=top.canonical_smiles,
            top_neighbor_inchikey=top.inchikey,
            top_neighbor_source_ids=top.source_ids,
            top_neighbor_observation_count=top.observation_count,
            top_neighbor_log_s_median=top.median_measured_log_s_mol_l,
            top_neighbor_log_s_min=top.minimum_measured_log_s_mol_l,
            top_neighbor_log_s_max=top.maximum_measured_log_s_mol_l,
            **transfer,
        )
        profiles.append(profile)
        characterization_payload.append({
            "candidate_id": entry.candidate_id,
            "chemistry_status": chemistry_status,
            "molecule_properties": molecule_properties,
            "esol": None if prediction is None else prediction.to_dict(),
        })
    return tuple(profiles), {
        "schema": "moldisc-014.frozen-esol-characterization.v1",
        "profiles": characterization_payload,
        "solubility_capability": predictor.evidence_manifest(),
    }


@dataclass(frozen=True)
class MOLDISC014Result:
    program_id: str
    config_hash: str
    generation_scientific_hash: str
    source_audit_scientific_hash: str
    workflow_scientific_summary_hash: str
    coverage_scientific_hash: str
    program_scientific_hash: str
    panel: tuple[PanelEntry, ...]
    source_audit: SourceNeighborAudit
    profiles: tuple[EvidenceProfile, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "program_version": PROGRAM_VERSION,
            "config_hash": self.config_hash,
            "generation_scientific_hash": self.generation_scientific_hash,
            "source_audit_scientific_hash": self.source_audit_scientific_hash,
            "workflow_scientific_summary_hash": self.workflow_scientific_summary_hash,
            "coverage_scientific_hash": self.coverage_scientific_hash,
            "program_scientific_hash": self.program_scientific_hash,
            "panel": [item.to_dict() for item in self.panel],
            "source_audit": self.source_audit.to_dict(),
            "profiles": [item.to_dict() for item in self.profiles],
            "candidate_selection_executed": False,
            "selected_candidate_id": None,
            "docking_executed": False,
            "moldisc010_score_used": False,
            "moldisc012_score_used": False,
            "moldisc013_geometry_used": False,
            "source_measurement_used_for_edit_definition": False,
            "source_measurement_used_for_generation": False,
            "source_measurement_used_for_filtering": False,
            "source_measurement_used_for_ranking": False,
            "evidence_level": "E0_HEURISTIC",
        }


def run_moldisc_014(*, config_path: str | Path, output_root: str | Path, timeout: float = 120.0) -> MOLDISC014Result:
    config = load_program_config_v14(config_path)
    config_hash = sha256_json(config)
    records, row_count, parsed_hash = download_aqsoldb(timeout=timeout)
    source_audit = audit_frozen_source(records, source_row_count=row_count, parsed_source_hash=parsed_hash)
    panel = generate_panel()
    generation_payload = {
        "schema": "moldisc-014.generation.v1",
        "generator_id": GENERATOR_ID,
        "source_structure_used_for_edit_definition": True,
        "source_measurement_used_for_edit_definition": False,
        "source_measurement_used_for_generation": False,
        "source_measurement_used_for_filtering": False,
        "source_measurement_used_for_ranking": False,
        "panel": [item.to_dict() for item in panel],
    }
    generation_hash = sha256_json(generation_payload)
    coverage = assess_aqsoldb_coverage(
        [{"id": item.candidate_id, "smiles": item.canonical_smiles} for item in panel],
        records=records,
        source_row_count=row_count,
        parsed_source_hash=parsed_hash,
    )
    predictor = FrozenESOLSolubilityPredictor.from_public_source(timeout=timeout)
    profiles, workflow_payload = _characterize_panel(panel, predictor, coverage, source_audit)
    workflow_hash = sha256_json(workflow_payload)
    scientific = {
        "program_id": PROGRAM_ID,
        "config_hash": config_hash,
        "generation_scientific_hash": generation_hash,
        "source_audit_scientific_hash": source_audit.scientific_hash,
        "workflow_scientific_summary_hash": workflow_hash,
        "coverage_scientific_hash": coverage.scientific_hash,
        "panel": [item.to_dict() for item in panel],
        "profiles": [item.to_dict() for item in profiles],
        "candidate_selection_executed": False,
        "selected_candidate_id": None,
        "docking_executed": False,
        "moldisc010_score_used": False,
        "moldisc012_score_used": False,
        "moldisc013_geometry_used": False,
        "source_measurement_used_for_edit_definition": False,
        "source_measurement_used_for_generation": False,
        "source_measurement_used_for_filtering": False,
        "source_measurement_used_for_ranking": False,
        "evidence_level": "E0_HEURISTIC",
    }
    program_hash = sha256_json(scientific)
    result = MOLDISC014Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        generation_scientific_hash=generation_hash,
        source_audit_scientific_hash=source_audit.scientific_hash,
        workflow_scientific_summary_hash=workflow_hash,
        coverage_scientific_hash=coverage.scientific_hash,
        program_scientific_hash=program_hash,
        panel=panel,
        source_audit=source_audit,
        profiles=profiles,
    )
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=False)
    (root / "program_manifest.json").write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "generation.json").write_text(json.dumps({**generation_payload, "generation_scientific_hash": generation_hash}, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "source_neighbor_audit.json").write_text(json.dumps(source_audit.to_dict(), indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "evidence_profiles.json").write_text(json.dumps({
        "schema": "moldisc-014.evidence-profiles.v1",
        "coverage_scientific_hash": coverage.scientific_hash,
        "workflow_scientific_summary_hash": workflow_hash,
        "profiles": [item.to_dict() for item in profiles],
        "solubility_capability": workflow_payload["solubility_capability"],
    }, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "program_report.md").write_text(_markdown(result), encoding="utf-8")
    return result


def _markdown(result: MOLDISC014Result) -> str:
    lines = [
        "# MOLDISC-014 — AqSolDB source-directed interpolation panel",
        "",
        "- no docking: YES",
        "- no candidate selection: YES",
        "- source measurement used to define edits/rank/filter/generate: NO/NO/NO/NO",
        f"- source audit hash: {result.source_audit_scientific_hash}",
        f"- generation hash: {result.generation_scientific_hash}",
        f"- workflow hash: {result.workflow_scientific_summary_hash}",
        f"- coverage hash: {result.coverage_scientific_hash}",
        f"- program hash: {result.program_scientific_hash}",
        "",
        "## Evidence profiles",
        "",
        "| Variant | Chemistry | ESOL AD | AqSolDB nearest | Same connectivity | Exact source match | Transfer |",
        "|---|---|---|---:|---|---|---|",
    ]
    for item in result.profiles:
        lines.append(
            f"| {item.variant_id} | {item.chemistry_status} | {item.esol_status} | {item.aqsoldb_nearest_similarity:.6f} | "
            f"{'YES' if item.same_connectivity_as_recurring_source else 'NO'} | "
            f"{'YES' if item.exact_canonical_match else 'NO'} | "
            f"{'YES' if item.measurement_transfer_allowed else 'NO'} |"
        )
    lines.extend([
        "",
        "The AqSolDB measurement remains attached to the immutable source record only.",
        "SOURCE-DELTA-BOTH reproduces the source connectivity layer while preserving a different full stereochemical InChIKey; its measurement is not transferred.",
        "ESOL values are frozen E1_ML outputs. OUT_OF_DOMAIN values are unsupported extrapolative model outputs, not experimental measurements.",
        "",
    ])
    return "\n".join(lines)


__all__ = [
    "CONTEXT_MOLDISC013_HASH",
    "DELTA_BOTH_CANDIDATE_ID",
    "DELTA_BOTH_HEAVY_ATOMS",
    "DELTA_BOTH_INCHIKEY",
    "DELTA_BOTH_SMILES",
    "DELTA_BOTH_VARIANT_ID",
    "DELTA_NSUB_CANDIDATE_ID",
    "DELTA_NSUB_HEAVY_ATOMS",
    "DELTA_NSUB_INCHIKEY",
    "DELTA_NSUB_SMILES",
    "DELTA_NSUB_VARIANT_ID",
    "DELTA_OH_CANDIDATE_ID",
    "DELTA_OH_HEAVY_ATOMS",
    "DELTA_OH_INCHIKEY",
    "DELTA_OH_SMILES",
    "DELTA_OH_VARIANT_ID",
    "GENERATOR_ID",
    "MOLDISC014Error",
    "MOLDISC014Result",
    "PARENT_MOLDISC011_HASH",
    "SEED_CANDIDATE_ID",
    "SEED_HEAVY_ATOMS",
    "SEED_INCHIKEY",
    "SEED_SMILES",
    "SOURCE_CANONICAL_SMILES",
    "SOURCE_CONNECTIVITY_BLOCK",
    "SOURCE_INCHIKEY",
    "SOURCE_MEASURED_LOG_S",
    "SOURCE_RAW_SMILES",
    "SourceNeighborAudit",
    "audit_frozen_source",
    "generate_panel",
    "load_program_config_v14",
    "measurement_transfer_decision",
    "run_moldisc_014",
]
