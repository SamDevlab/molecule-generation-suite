# MOLDISC-009 — JE2 single-terminal-methyl deletion series

Status: **protocol frozen before first generated-candidate evidence is inspected**

## Why this program exists

MOLDISC-008 established that the crystallographic JE2 seed from
`ATX-007 / PDB 1KZK` is chemically valid and has measured-source structural
coverage in immutable AqSolDB, while remaining outside the frozen ESOL
applicability domain.

Its frozen follow-up gate explicitly allowed a separately frozen generation
study. MOLDISC-009 is that study.

It does not retrain ESOL and does not dock.

## Frozen parent

MOLDISC-008:

- program scientific hash:
  `fd2adf5923ba0ad822d14ee8a4c1199aa3bf6732b8c70cb396940951126d2b90`
- seed: `ATX-007 / 1KZK / JE2`
- seed InChIKey: `CUFQBQOBLVLKRF-RZDMPUFOSA-N`
- AqSolDB nearest similarity: `0.569620253164557`
- frozen ESOL status: `OUT_OF_DOMAIN`
- generation-source ready: `true`

The out-of-domain ESOL number is not used by the generator or selection rule.

## Frozen generator

Generator identity:

`research-os.molecular-discovery.je2-single-terminal-methyl-deletion.v1`

The rule is deliberately small:

1. parse the exact frozen canonical JE2 SMILES;
2. identify every carbon with degree 1 and exactly three hydrogens;
3. delete exactly one such terminal methyl carbon per raw product;
4. sanitize each product;
5. canonicalize with isomeric SMILES;
6. deduplicate symmetry-equivalent products;
7. sort by canonical product SMILES;
8. assign `DEMETHYL-01` through `DEMETHYL-03`.

The frozen JE2 seed has four terminal methyl sites. Two are symmetry-equivalent
under this operation, so the complete unique neighborhood contains exactly
three generated structures.

No AqSolDB, ESOL, docking, potency, affinity or biological output participates
in generation.

Every generated molecule is `E0_HEURISTIC`.

## Evidence profile

The seed and all three generated structures pass through the existing:

- MoleculeLab molecular validation;
- frozen ESOL predictor and applicability-domain rule;
- immutable AqSolDB measured-source coverage capability.

For each candidate the program records chemistry, ESOL AD status, the numeric
ESOL model output, AqSolDB nearest similarity, neighbor counts and top
measured-source neighbor.

A neighboring measured logS is not transferred to the generated molecule
unless the canonical structure is an exact source match.

## Frozen selection rule

A generated structure is follow-up eligible only if:

1. chemistry status is `PASS`; and
2. AqSolDB nearest Tanimoto is >= `0.4`.

Among eligible generated structures:

1. highest AqSolDB nearest similarity wins;
2. exact tie -> ascending variant ID.

ESOL status and predicted logS do not enter this rule.

## Explicitly out of scope

MOLDISC-009 performs no:

- docking;
- affinity ranking;
- model training;
- hyperparameter tuning;
- potency or efficacy scoring;
- safety inference;
- clinical inference.

A selected structure, if one exists, is only the measured-source-coverage
choice for a separately frozen follow-up. It is not a biological winner.
