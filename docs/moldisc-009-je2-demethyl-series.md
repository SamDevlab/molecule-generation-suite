# MOLDISC-009 — JE2 single-terminal-methyl deletion series

Status: **executed and closed; DEMETHYL-03 selected by frozen measured-source coverage rule**

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


## First execution

The first frozen execution completed successfully in GitHub Actions run
`35448228979`.

Scientific identities:

- generation: `fcb80f20df6c7d283b84e902d4970036994490e13495ce22fdb51519d30b4334`
- workflow: `305e2275869101fea148da4cb817414c49258c95ca2c711b0c707ec04f762824`
- AqSolDB coverage: `bf21f32a3ba5927dc87ae77bed811640da2edd5239bea01b22b7cc1afb57b69d`
- program: `75ffaf31d6df6983e7692fca4f0a3fa2277c743dcac2b99cee179c9b39116615`

All three generated structures passed molecular validation.

### Frozen coverage result

| Variant | AqSolDB nearest | >=0.4 neighbors | ESOL AD | follow-up |
|---|---:|---:|---|---|
| JE2 seed | 0.5696202532 | 8 | OUT_OF_DOMAIN | seed only |
| DEMETHYL-01 | 0.6081081081 | 8 | OUT_OF_DOMAIN | YES |
| DEMETHYL-02 | 0.3977272727 | 0 | OUT_OF_DOMAIN | NO |
| DEMETHYL-03 | 0.6315789474 | 8 | OUT_OF_DOMAIN | YES |

The selected structure is:

- variant: `DEMETHYL-03`
- candidate: `MOLDISC-009-JE2-5461A4A267`
- operation: right peripheral aryl methyl deletion
- canonical SMILES:
  `Cc1ccccc1CNC(=O)[C@H]1N(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)CSC1(C)C`
- AqSolDB nearest similarity: `0.631578947368421`

DEMETHYL-03 was selected only because it had the highest AqSolDB nearest
similarity among generated candidates above the frozen 0.4 boundary.

### ESOL boundary retained

JE2 and all three generated analogs remained `OUT_OF_DOMAIN` for the frozen
ESOL model. No numeric ESOL prediction was used in generation or selection,
and none is promoted to a reliable solubility estimate.

### Closure

MOLDISC-009 is closed on the preserved DEMETHYL-03 selection.

Any docking, further molecule generation, or stronger solubility inference
must be opened as a new frozen program. The AqSolDB neighbor measurement of
`-3.62` belongs to the neighboring source structure and is not transferred
to DEMETHYL-03.
