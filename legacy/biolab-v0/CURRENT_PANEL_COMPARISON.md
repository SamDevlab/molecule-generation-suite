# Current Panel Comparison

This report compares historical computational records with the frozen BIOEXP-001 panel.
It does not select candidates, rank legacy molecules, create E4, or open generation.

## Evidence boundary

All records are `LEGACY` / `COMPUTATIONAL` with no experimental validation.
Exact, connectivity, and structural-similarity matches are provenance findings only.

## Questions

1. Exact identity in the legacy corpus: **0 panel members**.
2. Same connectivity without exact identity: **0 panel members**.
3. Legacy source coverage is preserved in `legacy_molecular_index.csv` and `source_overlap.csv`.
4. Structural similarity pairs at the declared Morgan/Tanimoto threshold: **0**.
5. Multi-source exact identities: **10**.
6. Any convergence is historical provenance, not current efficacy or potency evidence.

## Per-panel status

| Panel key | InChIKey | Exact matches | Connectivity matches | Structural-similarity pairs |
| --- | --- | ---: | ---: | ---: |
| A0B0 | DRIAWXDDGSORDT-KKUQBAQOSA-N | 0 | 0 | 0 |
| A1B0 | NAZMDUVPQSKJEQ-KKUQBAQOSA-N | 0 | 0 | 0 |
| A0B1 | DMSDTDPQGPRTNA-FDFHNCONSA-N | 0 | 0 | 0 |
| A1B1 | URHJIBSBOJFXDI-FDFHNCONSA-N | 0 | 0 | 0 |

## Similarity protocol

`fingerprint=Morgan`, `radius=2`, `nBits=2048`, `metric=Tanimoto`, `structural_similarity_threshold=0.4`.
All current-panel × legacy-identity pairs, including `NO_MATCH`, are retained in `current_panel_matches.csv`.

## C-2545 / KNI boundary

Status: `NO_EXPLICIT_LEGACY_IDENTITY_FOUND`. The current panel boundary remains `PHENYL-KNI-727` with source stereochemistry `UNRESOLVED` and measurement transfer `False`.
Same connectivity does not imply the same stereochemical identity; no solubility measurement is transferred.

## Invariants

`REAL_EXPERIMENT_EXECUTED=NO`, `E4_CREATED=NO`, `NEXT_GENERATION_ALLOWED=NO`.
