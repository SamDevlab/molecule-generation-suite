# REDOCK-001 — frozen redocking benchmark v1

**Status:** protocol frozen before any REDOCK-001 docking outcome is inspected.

**Protocol ID:** `research-os.redocking.v1`

**Purpose:** evaluate whether a fixed AutoDock Vina preparation/docking workflow can reproduce experimentally resolved ligand poses. This is a pose-reproduction benchmark, not an affinity, efficacy, safety, clinical, or universal docking-validation claim.

## Scientific question

For a predeclared set of experimentally resolved protein–ligand complexes, what heavy-atom pose RMSD is obtained after removing the native ligand, preparing receptor/ligand inputs, redocking the ligand with a fixed protocol, and comparing predicted poses with the crystallographic reference?

## Frozen benchmark set

The cases were selected before docking outcomes using public RCSB entries, target diversity, an explicitly identified non-polymer ligand, X-ray structure availability, and practical small-molecule redocking scope. No case may be removed because its result is poor.

| Case | PDB | Native ligand | Selected author chain | Target | X-ray resolution |
| --- | --- | --- | --- | --- | ---: |
| RDK-001 | `1STP` | `BTN` | `A` | streptavidin | 2.60 Å |
| RDK-002 | `3PTB` | `BEN` | `A` | beta-trypsin | 1.70 Å |
| RDK-003 | `1HVR` | `XK2` | `A` | HIV-1 protease | 1.80 Å |
| RDK-004 | `1M17` | `AQ4` | `A` | EGFR kinase domain | 2.60 Å |
| RDK-005 | `1IEP` | `STI` | `A` | c-Abl kinase domain | 2.10 Å |

Public entry provenance:

- `https://www.rcsb.org/structure/1STP`
- `https://www.rcsb.org/structure/3PTB`
- `https://www.rcsb.org/structure/1HVR`
- `https://www.rcsb.org/structure/1M17`
- `https://www.rcsb.org/structure/1IEP`

Coordinate acquisition uses the RCSB/wwPDB programmatic file-download service. Raw files are not treated as immutable by URL alone: every acquired coordinate file must be content-hashed and the hash recorded with the run.

## Engine and preparation identity

- docking engine: **AutoDock Vina 1.2.7**;
- canonical executable contract: `RESEARCH_OS_VINA_EXECUTABLE` or `vina` on `PATH`;
- ligand/receptor preparation must record the exact preparation engine(s), versions, command/options, and content hashes;
- no machine-specific absolute developer path is part of the protocol;
- Python Vina bindings are not assumed to provide the Vina executable; executable availability is an explicit capability gate.

The official Vina workflow recommends Meeko for receptor/ligand preparation. If Meeko is used by the implementation, its version and exact preparation contract must be recorded. A preparation failure is a benchmark failure/indeterminate case, not a reason to silently switch chemistry tools.

## Frozen docking parameters

- scoring function: Vina default scoring function;
- rigid receptor;
- `seed = 42`;
- `cpu = 1`;
- `exhaustiveness = 16`;
- `num_modes = 20`;
- `energy_range = 3 kcal/mol` when the execution interface exposes it;
- no flexible residues;
- no post-result per-complex parameter tuning.

### Search box

The search box is derived from the **native ligand coordinates only**, which is appropriate for redocking but must not be described as blind docking.

For each Cartesian axis:

1. center = midpoint of the minimum and maximum heavy-atom native-ligand coordinate on that axis;
2. size = native-ligand heavy-atom span on that axis + `12.0 Å` (6 Å padding each side);
3. minimum box side = `20.0 Å`;
4. maximum box side = `30.0 Å`;
5. a case whose required unclamped size exceeds `30.0 Å` is `OUT_OF_DOMAIN` for v1 rather than silently enlarging the protocol.

The resulting center/size and a deterministic grid hash are recorded per case.

## Receptor extraction boundary

For the selected author chain:

- retain standard protein atoms;
- remove the benchmark ligand itself;
- remove crystallographic waters for v1;
- remove unselected polymer chains;
- remove non-polymer ions/solvent/other small molecules by default;
- no cofactor is silently invented or substituted.

If removing a chemically essential cofactor makes a case scientifically inappropriate, the case remains visible and may become `INDETERMINATE`/`OUT_OF_DOMAIN`; changing cofactor policy requires a new benchmark protocol version.

## Ligand preparation boundary

The reference pose is the experimentally resolved native ligand instance from the selected author chain. The docking ligand is generated from the same chemical identity but must not retain the crystallographic pose as a starting-coordinate advantage in the search protocol.

Preparation must therefore generate or randomize a starting conformer independently of the native coordinates using a fixed seed when supported. The crystallographic coordinates remain isolated as evaluation reference and search-box source.

If stereochemistry/bond order/atom mapping cannot be established unambiguously, the case fails closed.

## Primary endpoint

**Symmetry-aware heavy-atom RMSD (Å)** between each predicted pose and the crystallographic reference after molecular-identity validation and optimal atom correspondence/alignment.

The evaluator must not assume raw atom-index correspondence for symmetric molecules. If graph-aware atom mapping cannot be established, it returns an explicit non-pass state rather than a misleading RMSD.

For each case report:

- best-pose-by-Vina-rank RMSD (pose 1) — **primary per-case endpoint**;
- minimum RMSD across the declared 20 returned modes — secondary diagnostic;
- Vina score(s) as computational metadata only;
- number of poses actually produced;
- preparation/execution/evaluation status and `FIRST_LOSS` when non-passing.

## Aggregate endpoints

Primary aggregate reporting:

- median pose-1 heavy-atom RMSD;
- mean pose-1 heavy-atom RMSD;
- full per-case pose-1 RMSD values;
- count/fraction with pose-1 RMSD `<= 2.0 Å`;
- count of PASS / FAIL / INDETERMINATE / OUT_OF_DOMAIN cases.

Secondary diagnostics may report minimum-across-modes RMSD, but may not replace pose-1 RMSD as the primary endpoint after results are known.

The `2.0 Å` threshold is a conventional descriptive redocking threshold. Passing it does not establish binding affinity or experimental efficacy.

## Fail-closed gates

A case cannot produce a passing RMSD result unless all applicable gates pass:

1. source coordinate acquisition succeeded and raw SHA-256 is recorded;
2. exact selected ligand instance exists;
3. ligand chemical identity/reference graph is parseable;
4. receptor extraction is non-empty and target ligand is removed;
5. starting ligand coordinates are generated independently from the reference pose;
6. preparation engine(s) execute and outputs are hashed;
7. Vina 1.2.7 capability is attributable and executes successfully;
8. at least one predicted pose is produced;
9. predicted/reference chemical identity permits a valid heavy-atom mapping;
10. RMSD is finite.

No failed case is silently removed from the denominator.

## Reproducibility record

Every real REDOCK-001 execution must record at minimum:

- protocol ID and protocol/document hash;
- PDB ID / ligand ID / selected author chain;
- RCSB source locator and raw source SHA-256;
- reference-ligand SHA-256;
- receptor and docking-ligand prepared hashes;
- grid center/size/hash;
- Vina version and executable identity;
- preparation engine/version/options;
- seed/cpu/exhaustiveness/num_modes;
- per-pose Vina rank/score and RMSD;
- result/evidence hash;
- runtime/platform provenance;
- all exclusions/failures and first-loss codes.

## Interpretation boundary

REDOCK-001 can support statements about pose reproduction **for this frozen protocol and these five complexes only**. It does not establish:

- measured binding affinity;
- inhibitor potency;
- biological activity;
- selectivity;
- toxicity or safety;
- clinical efficacy;
- universal docking accuracy;
- correctness for targets or ligand chemotypes outside this benchmark.

## Change control

After the first real REDOCK-001 run begins, the following cannot be changed in v1 in response to outcomes:

- case list;
- selected ligand/chain;
- search-box rule;
- seed;
- exhaustiveness;
- mode count;
- primary endpoint;
- 2 Å descriptive threshold;
- failure-denominator policy.

A scientifically motivated change is allowed only under a new protocol ID/version with the original v1 result preserved.
