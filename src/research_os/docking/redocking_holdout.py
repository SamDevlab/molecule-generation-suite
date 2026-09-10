from __future__ import annotations

from research_os.docking.redocking import RedockingCase


PROTOCOL_ID = "research-os.redocking.holdout.v1.0"
BENCHMARK_ID = "REDOCK-002"
SOURCE_SET = "Astex Diverse Set"
POSE_SUCCESS_THRESHOLD_ANGSTROM = 2.0


# Prospectively selected before any REDOCK-002 Vina execution. None of these
# complexes appear in REDOCK-001. The set deliberately spans distinct target
# classes rather than selecting near-neighbours of the first benchmark.
FROZEN_HOLDOUT_CASES: tuple[RedockingCase, ...] = (
    RedockingCase(
        "HLD-001",
        "1V0P",
        "PVB",
        "A",
        ("A",),
        "Plasmodium falciparum PfPK5 kinase",
        2.00,
        "https://www.rcsb.org/structure/1V0P",
    ),
    RedockingCase(
        "HLD-002",
        "1W1P",
        "GIO",
        "B",
        ("B",),
        "Serratia marcescens chitinase B",
        2.10,
        "https://www.rcsb.org/structure/1W1P",
    ),
    RedockingCase(
        "HLD-003",
        "2BM2",
        "PM2",
        "B",
        ("B",),
        "human beta-II tryptase",
        2.20,
        "https://www.rcsb.org/structure/2BM2",
    ),
    RedockingCase(
        "HLD-004",
        "1VCJ",
        "IBA",
        "A",
        ("A",),
        "influenza B neuraminidase",
        2.40,
        "https://www.rcsb.org/structure/1VCJ",
    ),
    RedockingCase(
        "HLD-005",
        "1TT1",
        "KAI",
        "A",
        ("A",),
        "GluR6 ligand-binding core",
        1.93,
        "https://www.rcsb.org/structure/1TT1",
    ),
)
