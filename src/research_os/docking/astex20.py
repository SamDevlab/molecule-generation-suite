from __future__ import annotations

from collections import defaultdict
import hashlib
import math
import re

from research_os.docking import redocking as base


BENCHMARK_ID = "REDOCK-003"
PROTOCOL_ID = "research-os.redocking.astex20.v1.0"
SOURCE_SET = "Astex Diverse Set"
SOURCE_LIST_URL = "https://github.com/oxpig/RLDiff/blob/main/data/astex_diverse_85_ids.txt"
SOURCE_LIST_SHA256 = "7c2bc6702b62abe282bbd6f67146ec071c623cc3bd17d4683c1afd898b2df5ef"
SELECTION_SALT = "research-os.astex20.v1.0"
TARGET_PROSPECTIVE_COUNT = 15
CONTACT_CUTOFF_ANGSTROM = 8.0

PREFLIGHT_RUN_ID = 34544166868
PREFLIGHT_ARTIFACT_ID = 10178395083
PREFLIGHT_ARTIFACT_SHA256 = "56240b2eb1493190e7902ac26a026183a906d0e4a5b0f1068cdd43f185b62314"
PREFLIGHT_SELECTION_MANIFEST_HASH = "8119f2ece8bd1be2612e74520871cbeddb5fa9be7951d23c88db478e122a1690"

ASTEX_DIVERSE_85: tuple[str, ...] = (
    "1G9V_RQ3", "1GKC_NFH", "1GM8_SOX", "1GPK_HUP", "1HNN_SKF", "1HP0_AD3",
    "1HQ2_PH2", "1HVY_D16", "1HWI_115", "1HWW_SWA", "1IA1_TQ3", "1IG3_VIB",
    "1J3J_CP6", "1JD0_AZM", "1JJE_BYS", "1JLA_TNK", "1K3U_IAD", "1KE5_LS1",
    "1KZK_JE2", "1L2S_STC", "1L7F_BCZ", "1LPZ_CMB", "1LRH_NLA", "1M2Z_DEX",
    "1MEH_MOA", "1MMV_3AR", "1MZC_BNE", "1N1M_A3M", "1N2J_PAF", "1N2V_BDI",
    "1N46_PFA", "1NAV_IH5", "1OF1_SCT", "1OF6_DTY", "1OPK_P16", "1OQ5_CEL",
    "1OWE_675", "1OYT_FSN", "1P2Y_NCT", "1P62_GEO", "1PMN_984", "1Q1G_MTI",
    "1Q41_IXM", "1Q4G_BFL", "1R1H_BIR", "1R55_097", "1R58_AO5", "1R9O_FLP",
    "1S19_MC9", "1S3V_TQD", "1SG0_STL", "1SJ0_E4D", "1SQ5_PAU", "1SQN_NDR",
    "1T40_ID5", "1T46_STI", "1T9B_1CS", "1TOW_CRZ", "1TT1_KAI", "1TZ8_DES",
    "1U1C_BAU", "1U4D_DBQ", "1UML_FR4", "1UNL_RRC", "1UOU_CMU", "1V0P_PVB",
    "1V48_HA1", "1V4S_MRK", "1VCJ_IBA", "1W1P_GIO", "1W2G_THM", "1X8X_TYR",
    "1XM6_5RM", "1XOQ_ROF", "1XOZ_CIA", "1Y6B_AAX", "1YGC_905", "1YQY_915",
    "1YV3_BIT", "1YVF_PH7", "1YWR_LI9", "1Z95_198", "2BM2_PM2", "2BR1_PFP",
    "2BSM_BSM",
)

PRIOR_OBSERVED_ASTEX: tuple[str, ...] = (
    "1V0P_PVB",
    "1W1P_GIO",
    "2BM2_PM2",
    "1VCJ_IBA",
    "1TT1_KAI",
)

INITIAL_HASH_RANKED_15: tuple[str, ...] = (
    "1R1H_BIR", "1SJ0_E4D", "1MEH_MOA", "1Q41_IXM", "1T9B_1CS",
    "1MMV_3AR", "1JJE_BYS", "1V4S_MRK", "1T40_ID5", "1PMN_984",
    "1KZK_JE2", "1W2G_THM", "1HQ2_PH2", "1S3V_TQD", "1HVY_D16",
)

PREFLIGHT_REJECTED_BEFORE_COHORT_FILLED: tuple[tuple[int, str, str], ...] = (
    (4, "1Q41_IXM", "multiple ligand instances"),
    (5, "1T9B_1CS", "multiple ligand instances"),
    (6, "1MMV_3AR", "multiple ligand instances"),
    (7, "1JJE_BYS", "multiple ligand instances"),
    (12, "1W2G_THM", "multiple ligand instances"),
    (15, "1HVY_D16", "multiple ligand instances"),
    (16, "1JD0_AZM", "multiple ligand instances"),
    (17, "1XM6_5RM", "multiple ligand instances"),
    (23, "1L2S_STC", "multiple ligand instances"),
)

# Frozen from the successful no-docking structural preflight in Actions run 275
# (workflow run id PREFLIGHT_RUN_ID). These values must not be changed in
# response to any later Vina score, pose or RMSD without a new protocol version.
FROZEN_PROSPECTIVE_CASES: tuple[base.RedockingCase, ...] = (
    base.RedockingCase(
        "ATX-001", "1R1H", "BIR", "A", ("A",), "NEPRILYSIN", 1.95,
        "https://www.rcsb.org/structure/1R1H",
    ),
    base.RedockingCase(
        "ATX-002", "1SJ0", "E4D", "A", ("A",), "ESTROGEN RECEPTOR", 1.90,
        "https://www.rcsb.org/structure/1SJ0",
    ),
    base.RedockingCase(
        "ATX-003", "1MEH", "MOA", "A", ("A",),
        "INOSINE-5'-MONOPHOSPHATE DEHYDROGENASE", 1.95,
        "https://www.rcsb.org/structure/1MEH",
    ),
    base.RedockingCase(
        "ATX-004", "1V4S", "MRK", "A", ("A",), "GLUCOKINASE ISOFORM 2", 2.30,
        "https://www.rcsb.org/structure/1V4S",
    ),
    base.RedockingCase(
        "ATX-005", "1T40", "ID5", "A", ("A",), "ALDOSE REDUCTASE", 1.80,
        "https://www.rcsb.org/structure/1T40",
    ),
    base.RedockingCase(
        "ATX-006", "1PMN", "984", "A", ("A",),
        "MITOGEN-ACTIVATED PROTEIN KINASE 10", 2.20,
        "https://www.rcsb.org/structure/1PMN",
    ),
    base.RedockingCase(
        "ATX-007", "1KZK", "JE2", "A", ("A", "B"), "PROTEASE", 1.09,
        "https://www.rcsb.org/structure/1KZK",
    ),
    base.RedockingCase(
        "ATX-008", "1HQ2", "PH2", "A", ("A",),
        "6-HYDROXYMETHYL-7,8-DIHYDROPTERIN PYROPHOSPHOKINASE", 1.25,
        "https://www.rcsb.org/structure/1HQ2",
    ),
    base.RedockingCase(
        "ATX-009", "1S3V", "TQD", "A", ("A",), "DIHYDROFOLATE REDUCTASE", 1.80,
        "https://www.rcsb.org/structure/1S3V",
    ),
    base.RedockingCase(
        "ATX-010", "1Z95", "198", "A", ("A",), "ANDROGEN RECEPTOR", 1.80,
        "https://www.rcsb.org/structure/1Z95",
    ),
    base.RedockingCase(
        "ATX-011", "1UNL", "RRC", "A", ("A",), "CYCLIN-DEPENDENT KINASE 5", 2.20,
        "https://www.rcsb.org/structure/1UNL",
    ),
    base.RedockingCase(
        "ATX-012", "1TOW", "CRZ", "A", ("A",),
        "FATTY ACID-BINDING PROTEIN, ADIPOCYTE", 2.00,
        "https://www.rcsb.org/structure/1TOW",
    ),
    base.RedockingCase(
        "ATX-013", "1UOU", "CMU", "A", ("A",), "THYMIDINE PHOSPHORYLASE", 2.11,
        "https://www.rcsb.org/structure/1UOU",
    ),
    base.RedockingCase(
        "ATX-014", "1P2Y", "NCT", "A", ("A",), "CYTOCHROME P450-CAM", 2.30,
        "https://www.rcsb.org/structure/1P2Y",
    ),
    base.RedockingCase(
        "ATX-015", "1L7F", "BCZ", "A", ("A",), "NEURAMINIDASE", 1.80,
        "https://www.rcsb.org/structure/1L7F",
    ),
)


def source_list_sha256() -> str:
    return hashlib.sha256(("\n".join(ASTEX_DIVERSE_85) + "\n").encode()).hexdigest()


def selection_rank_key(complex_id: str) -> str:
    return hashlib.sha256(f"{SELECTION_SALT}:{complex_id}".encode()).hexdigest()


def ranked_unseen_candidates() -> tuple[str, ...]:
    prior = set(PRIOR_OBSERVED_ASTEX)
    return tuple(sorted((item for item in ASTEX_DIVERSE_85 if item not in prior), key=selection_rank_key))


def split_complex_id(complex_id: str) -> tuple[str, str]:
    pdb_id, ligand_id = complex_id.split("_", 1)
    return pdb_id, ligand_id


def _xyz(line: str) -> tuple[float, float, float]:
    return float(line[30:38]), float(line[38:46]), float(line[46:54])


def _resolution(pdb_text: str) -> float:
    match = re.search(r"^REMARK\s+2\s+RESOLUTION\.\s+([0-9.]+)\s+ANGSTROMS", pdb_text, re.MULTILINE)
    if not match:
        raise ValueError("PDB resolution could not be parsed")
    return float(match.group(1))


def _target_name(pdb_text: str, pdb_id: str) -> str:
    for line in pdb_text.splitlines():
        if line.startswith("COMPND") and "MOLECULE:" in line:
            value = line.split("MOLECULE:", 1)[1].strip().rstrip(";")
            if value:
                return value
    return f"Astex Diverse complex {pdb_id}"


def discover_structural_case(pdb_text: str, pdb_id: str, ligand_id: str) -> dict[str, object]:
    protein: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    ligands: dict[tuple[str, int, str], list[tuple[float, float, float]]] = defaultdict(list)

    for line in pdb_text.splitlines():
        if len(line) < 54 or not base._primary_altloc(line):
            continue
        record = line[:6].strip()
        element = base._element_from_pdb_line(line)
        if element in {"H", "D"}:
            continue
        chain = line[21].strip()
        if record == "ATOM":
            if chain:
                protein[chain].append(_xyz(line))
            continue
        if record != "HETATM" or line[17:20].strip() != ligand_id:
            continue
        try:
            seq = int(line[22:26].strip())
        except ValueError:
            continue
        ligands[(chain, seq, line[26].strip())].append(_xyz(line))

    if len(ligands) != 1:
        raise ValueError(f"expected exactly one {ligand_id} ligand instance, found {len(ligands)}")
    (ligand_chain, auth_seq_id, insertion_code), ligand_xyz = next(iter(ligands.items()))
    if not ligand_chain:
        raise ValueError("ligand author chain is blank")
    if not protein:
        raise ValueError("no polymer ATOM chains found")

    cutoff2 = CONTACT_CUTOFF_ANGSTROM ** 2
    contact_chains: list[str] = []
    minimum_distances: dict[str, float] = {}
    for chain, atoms in protein.items():
        min2 = min(
            (ax - lx) ** 2 + (ay - ly) ** 2 + (az - lz) ** 2
            for ax, ay, az in atoms
            for lx, ly, lz in ligand_xyz
        )
        minimum_distances[chain] = math.sqrt(min2)
        if min2 <= cutoff2:
            contact_chains.append(chain)
    contact_chains.sort()
    if not contact_chains:
        raise ValueError(f"no protein chain lies within {CONTACT_CUTOFF_ANGSTROM:g} Å of ligand")

    return {
        "pdb_id": pdb_id,
        "ligand_id": ligand_id,
        "ligand_author_chain": ligand_chain,
        "ligand_auth_seq_id": auth_seq_id,
        "ligand_insertion_code": insertion_code,
        "ligand_heavy_atoms_from_pdb": len(ligand_xyz),
        "receptor_author_chains": contact_chains,
        "protein_chain_min_distance_angstrom": {
            chain: round(distance, 6) for chain, distance in sorted(minimum_distances.items())
        },
        "resolution_angstrom": _resolution(pdb_text),
        "target": _target_name(pdb_text, pdb_id),
        "source_url": f"https://www.rcsb.org/structure/{pdb_id}",
    }
