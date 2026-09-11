from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib

from research_os.core.hashing import sha256_json
from research_os.docking.crossdock_alignment import ProteinResidue, needleman_wunsch_indices


BENCHMARK_ID = "APODOCK-001"
PROTOCOL_ID = "research-os.apodocking.rigid-known-site.v1.0"
SOURCE_NAME = "Seeliger & de Groot 2010 apo/holo large-motion benchmark"
SOURCE_URL = "https://doi.org/10.1371/journal.pcbi.1000634"
SOURCE_LIST_SHA256 = "3eaa3c45732efa05c1e5f4f468275e8f23e7b82ea9632f5c91dac1a30d62ebfc"
CASE_METADATA_SHA256 = "3993dc903927a38e63ca87544a38fa060c10d01e62f99b3616c22ddfe35e7a56"
PUBLISHED_CASE_COUNT = 10
MIN_GLOBAL_ALIGNMENT_CA_PAIRS = 50
LIGAND_GRID_PADDING_ANGSTROM = 6.0
GRID_MIN_SIDE_ANGSTROM = 20.0
GRID_MAX_SIDE_ANGSTROM = 30.0


@dataclass(frozen=True)
class ApoHoloCase:
    case_id: str
    receptor: str
    abbreviation: str
    apo_pdb_id: str
    holo_pdb_id: str
    residue_count: int
    ligand_name: str
    published_backbone_rmsd_angstrom: float
    published_binding_site_rmsd_angstrom: float
    apo_receptor_author_chain: str
    holo_receptor_author_chain: str
    holo_ligand_components: tuple[str, ...]
    holo_ligand_author_chain: str
    ligand_representation: str

    def source_row(self) -> str:
        return (
            f"{self.receptor}|{self.abbreviation}|{self.apo_pdb_id}|{self.holo_pdb_id}|"
            f"{self.residue_count}|{self.ligand_name}|"
            f"{self.published_backbone_rmsd_angstrom:.1f}|"
            f"{self.published_binding_site_rmsd_angstrom:.1f}"
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


# Exact ten apo/holo pairs are taken from Table 1 of Seeliger & de Groot (2010).
# Ligand component IDs and author-chain mappings are frozen before any APODOCK-001
# Vina execution. The final case is a covalently linked two-component glycan.
FROZEN_PUBLISHED_CASES: tuple[ApoHoloCase, ...] = (
    ApoHoloCase(
        "APD-001", "GluR2 ligand binding core", "GLUR2", "1FTO", "1FTM", 257,
        "AMPA", 2.2, 2.0, "A", "A", ("AMQ",), "A", "single_ccd",
    ),
    ApoHoloCase(
        "APD-002", "DNA Beta-Glucosyl-transferase", "GLUCO", "1JEJ", "1JG6", 351,
        "Uridine-5'-diphosphate", 2.1, 2.6, "A", "A", ("UDP",), "A", "single_ccd",
    ),
    ApoHoloCase(
        "APD-003", "D-Allose binding protein", "ALLO", "1GUD", "1RPJ", 288,
        "D-Allose", 4.4, 4.0, "A", "A", ("ALL",), "A", "single_ccd",
    ),
    ApoHoloCase(
        "APD-004", "D-Ribose binding protein", "RIB", "1URP", "2DRI", 271,
        "D-Ribose", 4.3, 3.5, "A", "A", ("RIP",), "A", "single_ccd",
    ),
    ApoHoloCase(
        "APD-005", "L-Leucine binding protein", "LEUB", "1USG", "1USI", 345,
        "Phenylalanine", 7.1, 6.8, "A", "A", ("PHE",), "A", "single_ccd",
    ),
    ApoHoloCase(
        "APD-006", "5-Enolpyruvylshikimate-3-phosphate synthase", "EPSP",
        "1RF5", "1RF4", 427, "SPQ", 3.7, 4.6, "A", "A", ("SPQ",), "A", "single_ccd",
    ),
    ApoHoloCase(
        "APD-007", "Osmo-protection protein", "OSMO", "1SW5", "1SW2", 270,
        "Glycine-betaine", 5.0, 4.4, "A", "A", ("BET",), "A", "single_ccd",
    ),
    ApoHoloCase(
        "APD-008", "Guanylate kinase", "GUA", "1EX6", "1EX7", 186,
        "GMP", 3.6, 3.9, "A", "A", ("5GP",), "A", "single_ccd",
    ),
    ApoHoloCase(
        "APD-009", "Hexokinase", "HEXO", "2E2N", "2E2O", 298,
        "Glucose", 3.0, 1.9, "A", "A", ("BGC",), "A", "single_ccd",
    ),
    ApoHoloCase(
        "APD-010", "Alginate binding protein", "ALGI", "1Y3Q", "1Y3N", 490,
        "Alginate Disaccharide", 4.8, 3.6, "A", "A", ("BEM", "MAV"), "A",
        "branched_glycan",
    ),
)

EXPECTED_CASE_IDS = tuple(f"APD-{index:03d}" for index in range(1, 11))
EXPECTED_PDB_PAIRS = (
    ("1FTO", "1FTM"),
    ("1JEJ", "1JG6"),
    ("1GUD", "1RPJ"),
    ("1URP", "2DRI"),
    ("1USG", "1USI"),
    ("1RF5", "1RF4"),
    ("1SW5", "1SW2"),
    ("1EX6", "1EX7"),
    ("2E2N", "2E2O"),
    ("1Y3Q", "1Y3N"),
)


def source_list_sha256() -> str:
    payload = "\n".join(case.source_row() for case in FROZEN_PUBLISHED_CASES) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def case_metadata_sha256() -> str:
    return sha256_json([case.to_dict() for case in FROZEN_PUBLISHED_CASES])


def matched_global_ca_pairs(
    holo_residues: tuple[ProteinResidue, ...],
    apo_residues: tuple[ProteinResidue, ...],
) -> tuple[tuple[tuple[float, float, float], tuple[float, float, float]], ...]:
    """Return identical globally aligned Cα pairs in holo→apo order."""

    holo_sequence = "".join(residue.one_letter for residue in holo_residues)
    apo_sequence = "".join(residue.one_letter for residue in apo_residues)
    aligned = needleman_wunsch_indices(holo_sequence, apo_sequence)
    pairs = []
    for holo_index, apo_index in aligned:
        if holo_index is None or apo_index is None:
            continue
        holo_residue = holo_residues[holo_index]
        apo_residue = apo_residues[apo_index]
        if holo_residue.one_letter != apo_residue.one_letter:
            continue
        pairs.append((holo_residue.ca_xyz, apo_residue.ca_xyz))
    return tuple(pairs)
