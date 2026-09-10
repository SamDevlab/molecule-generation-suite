# REDOCK-001 — corrected redocking benchmark v1.2

**Status:** frozen before the first v1.2 docking execution.

**Protocol ID:** `research-os.redocking.v1.2`

## Why v1.2 exists

REDOCK-001 v1.1 completed a real five-complex Vina execution, but post-run scientific review found that its evaluator used RDKit `GetBestRMS`. That routine performs an optimal rigid-body superposition of the predicted ligand onto the crystallographic ligand before returning RMSD.

That operation is appropriate for comparing molecular conformations, but it is not a valid primary endpoint for **docking pose localization** when the receptor already defines a shared coordinate frame: translating/rotating the docked ligand after docking can remove exactly the positional/orientational error the benchmark is supposed to measure.

Therefore the v1.1 5/5 <=2 Å result is retained as an audit artifact but is **invalidated for pose-localization interpretation**. It is not used as evidence that the docking protocol reproduced five native poses.

v1.2 is frozen before any corrected v1.2 outcome is read.

## Frozen benchmark set

The case list is unchanged from v1.1:

| Case | PDB | Native ligand | Ligand author chain | Receptor author chains | Target |
| --- | --- | --- | --- | --- | --- |
| RDK-001 | `1STP` | `BTN` | `A` | `A` | streptavidin |
| RDK-002 | `3PTB` | `BEN` | `A` | `A` | beta-trypsin |
| RDK-003 | `1HVR` | `XK2` | `A` | `A,B` | HIV-1 protease |
| RDK-004 | `1M17` | `AQ4` | `A` | `A` | EGFR kinase domain |
| RDK-005 | `1IEP` | `STI` | `A` | `A` | c-Abl kinase domain |

No case may be removed because of a corrected RMSD outcome.

## Frozen docking protocol

All docking/search/preparation choices remain unchanged from v1.1:

- AutoDock Vina `1.2.7`;
- rigid receptor;
- Vina default scoring;
- `seed = 42`;
- `cpu = 1`;
- `exhaustiveness = 16`;
- `num_modes = 20`;
- no flexible residues;
- same RCSB source/extraction policy;
- same independently generated RDKit ETKDG starting conformer with seed 42 and UFF optimization when available;
- same Open Babel preparation policy;
- same native-ligand-centered search-box rule: heavy-atom span + 12 Å, minimum side 20 Å, maximum side 30 Å;
- same five-case denominator;
- same descriptive success threshold of RMSD `<= 2.0 Å`.

No docking parameter is being tuned in response to the v1.1 values.

## Corrected primary endpoint

**Pose-1 symmetry-aware heavy-atom RMSD in the receptor coordinate frame, with no independent rigid-body alignment of the predicted ligand.**

Evaluation procedure:

1. remove hydrogens from reference and predicted molecules while preserving coordinates;
2. normalize bond-order/aromatic/protonation annotations only as needed for exact element-labeled connectivity matching after PDBQT round-tripping;
3. require equal heavy-atom counts and an exact normalized connectivity graph;
4. enumerate graph-isomorphic atom mappings, including symmetry-equivalent mappings;
5. for each mapping, calculate raw Cartesian RMSD directly from the crystallographic and predicted coordinates already expressed in the receptor frame;
6. choose the minimum RMSD over allowed atom mappings;
7. **do not translate, rotate, superpose, or otherwise fit the predicted ligand to the reference ligand during evaluation**.

If exact graph-aware mapping cannot be established, the pose is `INDETERMINATE`; there is no index-only or coordinate-nearest-neighbor fallback.

The atom-mapping search is bounded. If the configured enumeration limit is exhausted such that exhaustive symmetry handling cannot be guaranteed, the pose fails closed as `INDETERMINATE` rather than reporting an uncertain minimum.

## Secondary diagnostics

Unchanged:

- minimum corrected RMSD among declared Vina poses;
- Vina scores by rank;
- pose count.

Vina scores are docking-engine scores, not measured affinity.

## Aggregate endpoints

- full five-case pose-1 corrected RMSD vector;
- mean/median over cases with valid corrected RMSD;
- count/fraction with corrected pose-1 RMSD <=2.0 Å using all five frozen cases as denominator;
- PASS / FAIL / INDETERMINATE / OUT_OF_DOMAIN counts;
- per-case FIRST_LOSS;
- deterministic scientific-result hash for v1.2;
- separate execution/environment hash.

## Regression tests required before first v1.2 execution

The corrected evaluator must demonstrate all of the following before the first v1.2 CI outcome is interpreted:

- an identical pose in the same coordinate frame gives approximately 0 Å;
- atom renumbering/symmetry-equivalent mappings do not create artificial RMSD;
- a rigid translation of the whole predicted ligand **increases** RMSD instead of being aligned away;
- a rigid rotation around an external origin can increase RMSD instead of being aligned away;
- graph mismatch fails closed;
- failed cases remain in the denominator.

## Provenance

v1.2 retains the same provenance requirements as v1.1: raw RCSB hashes, extracted receptor/reference hashes, starting conformer hash, prepared PDBQT hashes, Vina output, per-pose artifacts, Vina/Open Babel identities, exact grid and parameters, status/first-loss and runtime environment.

## Interpretation boundary

A successful v1.2 result can support only **pose-reproduction performance for these five frozen complexes under the frozen protocol**. It cannot establish binding affinity, potency, biological activity, selectivity, toxicity, safety, efficacy, clinical performance or universal docking accuracy.

## Change control

Once the first real v1.2 execution starts, the following are frozen against outcome-driven changes:

- case list and chain selections;
- native ligand identities;
- source/extraction policy;
- starting-conformer generation;
- box rule;
- Open Babel preparation choices;
- Vina version/seed/CPU/exhaustiveness/mode count;
- corrected no-alignment primary endpoint;
- graph/symmetry mapping policy and enumeration limit;
- 2 Å descriptive threshold;
- five-case denominator.

Any methodological change after first execution requires a new protocol version.