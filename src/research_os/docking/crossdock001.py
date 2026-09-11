from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib

from research_os.docking import astex20
from research_os.docking import redocking_holdout
from research_os.docking import redocking_v12


BENCHMARK_ID = "CROSSDOCK-001"
PROTOCOL_ID = "research-os.crossdocking.rigid.v1.0"
SOURCE_NAME = "Rueda et al. 2009 holo-holo cross-docking pairs"
SOURCE_URL = "https://doi.org/10.1021/ci8003732"
SOURCE_LIST_SHA256 = "ad7beb91a1508c2d73f5c0a9b82fda182a19ca6fcd814099834fd2435a475169"
SELECTION_SALT = "research-os.crossdock001.v1.0"
TARGET_PAIR_COUNT = 5
DIRECTED_CASE_COUNT = 10
POCKET_CUTOFF_ANGSTROM = 10.0
MIN_ALIGNMENT_CA_PAIRS = 8


@dataclass(frozen=True)
class PublishedPair:
    target: str
    pdb_a: str
    chain_a: str
    pdb_b: str
    chain_b: str

    @property
    def pair_id(self) -> str:
        return f"{self.pdb_a}-{self.pdb_b}"

    def source_row(self) -> str:
        return f"{self.target}|{self.pdb_a}|{self.chain_a}|{self.pdb_b}|{self.chain_b}"


@dataclass(frozen=True)
class SelectedStructure:
    pdb_id: str
    receptor_author_chain: str
    ligand_id: str
    ligand_author_chain: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class SelectedPair:
    target: str
    first: SelectedStructure
    second: SelectedStructure

    @property
    def pair_id(self) -> str:
        return f"{self.first.pdb_id}-{self.second.pdb_id}"

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "pair_id": self.pair_id,
            "first": self.first.to_dict(),
            "second": self.second.to_dict(),
        }


PUBLISHED_HOLO_HOLO_PAIRS: tuple[PublishedPair, ...] = (
    PublishedPair("CDK2", "1AQ1", "A", "1DM2", "A"),
    PublishedPair("COX2", "1CX2", "A", "3PGH", "A"),
    PublishedPair("ESTROGEN_RECEPTOR", "1ERR", "A", "3ERT", "A"),
    PublishedPair("FACTOR_XA", "1KSN", "A", "1XKA", "C"),
    PublishedPair("GSK3B", "1Q4L", "A", "1UV5", "A"),
    PublishedPair("HIV1_RT", "1C1C", "A", "1RTH", "A"),
    PublishedPair("JNK3", "1PMN", "A", "1PMV", "A"),
    PublishedPair("LXRB", "1P8D", "A", "1PQ6", "B"),
    PublishedPair("NEURAMINIDASE", "1A4Q", "A", "1NSC", "A"),
    PublishedPair("P38", "1BMK", "A", "1DI9", "A"),
    PublishedPair("PKA", "1STC", "E", "1YDS", "E"),
    PublishedPair("PPARG", "1FM9", "D", "2PRG", "A"),
    PublishedPair("THYMIDINE_KINASE", "1KI4", "A", "1KIM", "A"),
    PublishedPair("TRYPSIN", "1PPC", "E", "1PPH", "E"),
)


# Ligand CCD/auth-chain metadata are frozen before any CROSSDOCK-001 docking.
# Each pair was selected by the deterministic rule below, not by docking outcome.
FROZEN_SELECTED_PAIRS: tuple[SelectedPair, ...] = (
    SelectedPair(
        "THYMIDINE_KINASE",
        SelectedStructure("1KI4", "A", "BTD", "A"),
        SelectedStructure("1KIM", "A", "THM", "A"),
    ),
    SelectedPair(
        "CDK2",
        SelectedStructure("1AQ1", "A", "STU", "A"),
        SelectedStructure("1DM2", "A", "HMD", "A"),
    ),
    SelectedPair(
        "LXRB",
        SelectedStructure("1P8D", "A", "CO1", "A"),
        SelectedStructure("1PQ6", "B", "965", "B"),
    ),
    SelectedPair(
        "COX2",
        SelectedStructure("1CX2", "A", "S58", "A"),
        SelectedStructure("3PGH", "A", "FLP", "A"),
    ),
    SelectedPair(
        "FACTOR_XA",
        SelectedStructure("1KSN", "A", "FXV", "A"),
        SelectedStructure("1XKA", "C", "4PP", "C"),
    ),
)


EXPECTED_SELECTED_PAIR_IDS: tuple[str, ...] = tuple(pair.pair_id for pair in FROZEN_SELECTED_PAIRS)
EXPECTED_SELECTION_KEYS: tuple[str, ...] = (
    "267bf3b2352ed634390c0964873230777b37676ae8a148b115c01d60664eca19",
    "2f4249fbc1716556a5340a42034fafca3b31f67337cc0ff66b358b440b78ad68",
    "32e6742f5d742cff9621990bfb75fd9fcd3b4dc8bbdb06e70b2abe75fb8f75c1",
    "4304ca658f7b9efc857586e66128a34e2a707463c055c23c335467e4c64fa42e",
    "7b7e674542233075001705f8a62ece2a4f9062e14cd506ad5283f734b8962f5e",
)


def source_list_sha256() -> str:
    payload = "\n".join(pair.source_row() for pair in PUBLISHED_HOLO_HOLO_PAIRS) + "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


def selection_key(pair: PublishedPair) -> str:
    return hashlib.sha256(f"{SELECTION_SALT}:{pair.pair_id}".encode()).hexdigest()


def previously_observed_pdb_ids() -> frozenset[str]:
    cases = (
        tuple(redocking_v12.FROZEN_REDOCKING_CASES)
        + tuple(redocking_holdout.FROZEN_HOLDOUT_CASES)
        + tuple(astex20.FROZEN_PROSPECTIVE_CASES)
    )
    return frozenset(case.pdb_id for case in cases)


def eligible_published_pairs() -> tuple[PublishedPair, ...]:
    observed = previously_observed_pdb_ids()
    return tuple(
        pair
        for pair in PUBLISHED_HOLO_HOLO_PAIRS
        if pair.pdb_a not in observed and pair.pdb_b not in observed
    )


def ranked_eligible_pairs() -> tuple[PublishedPair, ...]:
    return tuple(sorted(eligible_published_pairs(), key=selection_key))


def selected_published_pairs() -> tuple[PublishedPair, ...]:
    return ranked_eligible_pairs()[:TARGET_PAIR_COUNT]


def directed_case_specs() -> tuple[dict[str, object], ...]:
    cases: list[dict[str, object]] = []
    for pair_index, pair in enumerate(FROZEN_SELECTED_PAIRS, start=1):
        directions = ((pair.first, pair.second), (pair.second, pair.first))
        for direction_index, (source, target) in enumerate(directions, start=1):
            cases.append(
                {
                    "case_id": f"XDK-{pair_index:02d}-{direction_index}",
                    "target_name": pair.target,
                    "pair_id": pair.pair_id,
                    "source": source.to_dict(),
                    "target": target.to_dict(),
                }
            )
    return tuple(cases)
