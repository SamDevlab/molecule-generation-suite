# MOLDISC-011 — DEMETHYL-03 second terminal-methyl deletion series

MOLDISC-011 enumerates the complete unique neighborhood produced by deleting exactly one additional terminal methyl from the MOLDISC-009-selected `DEMETHYL-03` structure. The protocol is frozen upstream of new AqSolDB and ESOL results.

## Parent evidence

- MOLDISC-009 scientific hash: `75ffaf31d6df6983e7692fca4f0a3fa2277c743dcac2b99cee179c9b39116615`.
- Parent variant: `DEMETHYL-03`.
- Parent candidate: `MOLDISC-009-JE2-5461A4A267`.
- Parent canonical isomeric SMILES: `Cc1ccccc1CNC(=O)[C@H]1N(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)CSC1(C)C`.
- Parent InChIKey: `XBNKKAGGYBXOJG-GMQQYTKMSA-N`.
- MOLDISC-010 scientific hash: `360ef9eb66981287781a971a7e09aebbe2749be765af5b4c6dcb33e3839eb48b`.
- MOLDISC-010 is retained as `PASS / NON_COGNATE_HOLO_CROSSDOCKING / PARTIALLY_VALIDATED / E2_COMPUTATIONAL` evidence only.

The MOLDISC-010 docking score is not used for MOLDISC-011 generation, filtering, ranking or selection. MOLDISC-011 executes no docking.

## Frozen generation

Generator ID: `research-os.molecular-discovery.demethyl03-single-terminal-methyl-deletion.v1`.

The generator parses the exact parent SMILES, identifies every carbon atom with atomic number 6, degree 1 and exactly three hydrogens, deletes exactly one such atom per raw product, sanitizes, canonicalizes to isomeric SMILES, deduplicates by canonical SMILES, sorts the products and assigns IDs in sorted order. It expects 3 raw terminal-methyl sites and 2 unique products. Both products remain `E0_HEURISTIC`.

| Variant | Canonical isomeric SMILES | InChIKey | Structural interpretation |
|---|---|---|---|
| `STEP2-DEMETHYL-01` | `CC1(C)SCN(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)[C@@H]1C(=O)NCc1ccccc1` | `DRIAWXDDGSORDT-KKUQBAQOSA-N` | Remove the remaining peripheral aryl methyl. |
| `STEP2-DEMETHYL-02` | `Cc1ccccc1CNC(=O)[C@@H]1C(C)SCN1C(=O)[C@@H](O)[C@H](Cc1ccccc1)NC(=O)c1cccc(O)c1` | `WKWQZNZXWQKASU-XVJGRJRPSA-N` | Remove one of the symmetry-equivalent remaining gem-dimethyl sites. |

The structural interpretations describe connectivity only; they are not biological interpretations.

## Frozen evidence and selection

The seed and both generated products are assessed through MoleculeLab, the frozen ESOL capability and immutable AqSolDB structural coverage. The selection gate is fixed before downstream results: chemistry `PASS` and AqSolDB nearest Tanimoto `>= 0.4`; eligible products are ranked by higher nearest similarity with exact ties broken by `variant_id` ascending. ESOL is not used for selection.

AqSolDB measurements belong to the source structures. They are not transferred to candidates unless the top neighbor is an exact canonical structure match. Frozen ESOL `OUT_OF_DOMAIN` values are unsupported extrapolative model outputs and are not promoted to reliable solubility estimates.

## First result

The first CI result will be preserved in `validation/moldisc-011-first-run-v1.json` after protocol freeze. This section will then record all profiles, hashes, eligibility and the observed selection without changing the protocol in response to the result.

MOLDISC-011 makes no docking, affinity, potency, efficacy, safety, ADMET or biological claim, and it does not automatically authorize MOLDISC-012.
