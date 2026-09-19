# MOLDISC-008 — JE2 source-backed solubility evidence profile

Status: **executed and closed; JE2 source-ready by coverage, ESOL out-of-domain**

## Why this program exists

MOLDISC-007 selected `ATX-007 / PDB 1KZK / JE2` as the sole operational
fallback seed satisfying both:

- the pre-existing AqSolDB structural-coverage boundary; and
- the frozen REDOCK-003 rank-1 localization criterion.

MOLDISC-008 does not generate another molecule and does not dock JE2 or any
analog. It first asks what evidence actually supports the JE2 seed.

## Frozen parent

MOLDISC-007:

- program scientific hash:
  `92ca1d06d3d1c01466d284910854f36f35949bf4ce8031cf10f869373ed419de`
- selected case: `ATX-007`
- PDB: `1KZK`
- CCD ligand: `JE2`
- AqSolDB nearest similarity:
  `0.569620253164557`

The RCSB chemical-component identity is retrieved again at execution time and
canonicalized with the active RDKit runtime. Identity drift fails closed.

## Frozen evidence layers

### MoleculeLab

JE2 must pass the existing deterministic molecular-validity capability.

### Frozen ESOL

The existing product-facing ESOL model is reconstructed with the accepted:

- dataset hash:
  `6de39771743dc4f15b191cffc27e1e02eb474457cc841afda565f31aff198e85`
- training hash:
  `300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b`
- applicability threshold:
  `0.26684684684684684`

The program records:

- predicted aqueous logS;
- maximum training Tanimoto;
- `IN_DOMAIN` / `OUT_OF_DOMAIN`.

ESOL output is not a candidate-selection score.

MOLDISC-004 already demonstrated why this matters: an `IN_DOMAIN` seed can
still have a large absolute measured-anchor error.

### Immutable AqSolDB coverage

The source remains the pinned AqSolDB commit and parsed-source identity already
used by MOLDISC-002 through MOLDISC-005.

MOLDISC-008 records:

- nearest Tanimoto similarity;
- descriptive similarity bin;
- counts of neighbors at >=0.4, >=0.6 and >=0.8;
- the top measured-source neighbor;
- its observation count and measured-logS range;
- whether the JE2 canonical structure is an exact AqSolDB match.

A neighboring measured logS is not transferred to JE2 unless the canonical
structure matches exactly.

## Frozen follow-up gate

The program may report `generation_source_ready = true` only when:

1. chemistry status is `PASS`; and
2. nearest AqSolDB similarity is >= `0.4`.

ESOL `IN_DOMAIN` is deliberately **not** required for this source-readiness
flag. The ESOL result remains an independent evidence field.

This flag does not generate molecules automatically.

## Explicitly out of scope

MOLDISC-008 performs no:

- molecular generation;
- docking;
- model training;
- hyperparameter tuning;
- affinity inference;
- potency or efficacy scoring;
- safety or clinical inference.

The only purpose is to characterize the JE2 seed evidence envelope before a
separately frozen follow-up makes a new scientific move.


## First execution

The first frozen execution completed successfully in GitHub Actions run
`35416888562`.

Scientific identities:

- workflow scientific hash:
  `32de7d2b8d95ac0dd1a06020e1a3dbfc2a5fa6122e7852045b72be4ae2698a8e`
- AqSolDB coverage scientific hash:
  `03e9cd9ddc33a21276f4c4fb6a1cde458dc1389b98a968138ad2c3e7b22f600b`
- frozen predictor model identity:
  `2127d2aaa87cb83255f41ee2881a5691ccf63974c12e6cfb7502f6f24ed3ce61`
- program scientific hash:
  `fd2adf5923ba0ad822d14ee8a4c1199aa3bf6732b8c70cb396940951126d2b90`

### RCSB identity

The active RCSB/RDKit identity resolved to:

- InChIKey: `CUFQBQOBLVLKRF-RZDMPUFOSA-N`
- formula: `C32 H37 N3 O5 S`
- formula weight: `575.718`
- RCSB-reported InChIKey match: yes

### Frozen ESOL result

JE2 is:

`OUT_OF_DOMAIN`

Observed maximum training Tanimoto:

`0.21052631578947367`

Frozen AD threshold:

`0.26684684684684684`

The model emitted:

`predicted logS = -4.715111341269841`

Because JE2 is outside the frozen applicability domain, that numeric value is
retained as an extrapolative model output and is **not** promoted to a reliable
JE2 solubility estimate.

### Immutable AqSolDB coverage

JE2 reproduced the parent nearest similarity:

`0.569620253164557`

Observed coverage:

- neighbors >=0.4: `8`
- neighbors >=0.6: `0`
- neighbors >=0.8: `0`
- exact canonical AqSolDB match: `false`

The nearest measured-source structure has:

- InChIKey: `URHJIBSBOJFXDI-UHFFFAOYSA-N`
- one recorded observation
- measured logS: `-3.62`

That measurement belongs to the neighboring structure, **not JE2**.

### Frozen follow-up result

`generation_source_ready = true`

This passes only because:

1. JE2 chemistry is `PASS`; and
2. AqSolDB nearest similarity is >= `0.4`.

The out-of-domain ESOL result neither blocks nor promotes the seed under the
predeclared gate.

No molecule was generated in MOLDISC-008.

## Closure

MOLDISC-008 is closed on this evidence profile.

A new program may now generate a bounded JE2 neighborhood, but it must preserve
all of these boundaries:

- no measured logS transfer from the nearest AqSolDB neighbor;
- no use of the out-of-domain ESOL value as a generation or ranking score;
- no automatic docking;
- no biological interpretation from structural coverage.
