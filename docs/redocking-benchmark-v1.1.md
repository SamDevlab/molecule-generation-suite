# REDOCK-001 — redocking benchmark v1.1 (invalidated pose-localization endpoint)

**Status:** executed, audited, and **invalidated for docking pose-localization interpretation**.

**Protocol ID:** `research-os.redocking.v1.1`

## Audit status

v1.1 was the first real five-complex Vina execution. It is retained as a complete audit artifact, but its primary RMSD evaluator used RDKit `GetBestRMS`, which performs an optimal rigid-body superposition of the predicted ligand onto the crystallographic ligand before reporting RMSD.

That measures conformation similarity after fitting, not docking pose localization in the receptor coordinate frame. Because a docking benchmark must retain translational and orientational error relative to the receptor, the v1.1 `5/5 <= 2 Å` result **must not be cited as evidence that five native binding poses were reproduced**.

This defect was found during post-run review before PR #10 was merged. No v1.1 files or raw outcomes are deleted. The corrected, prospectively frozen endpoint is `research-os.redocking.v1.2` in `docs/redocking-benchmark-v1.2.md`.

## Why v1.1 existed

The original v1 protocol was superseded before execution after review found that `1HVR` requires HIV-1 protease receptor chains A+B. v1.1 corrected that receptor-chain ambiguity before any docking result and froze the following cases:

| Case | PDB | Ligand | Receptor chains |
| --- | --- | --- | --- |
| RDK-001 | `1STP` | `BTN` | A |
| RDK-002 | `3PTB` | `BEN` | A |
| RDK-003 | `1HVR` | `XK2` | A+B |
| RDK-004 | `1M17` | `AQ4` | A |
| RDK-005 | `1IEP` | `STI` | A |

The docking protocol itself used AutoDock Vina 1.2.7, seed 42, CPU 1, exhaustiveness 16, up to 20 modes, rigid receptors, an independently generated RDKit ETKDG starting conformer, Open Babel preparation, and a deterministic native-ligand-centered box rule.

## Raw v1.1 execution — GitHub Actions run 239

These values are preserved **only as invalidated diagnostic history**:

| Case | Aligned pose-1 RMSD (Å) | Aligned minimum RMSD (Å) | Poses | Vina pose-1 score |
| --- | ---: | ---: | ---: | ---: |
| RDK-001 `1STP/BTN` | 0.5225 | 0.5225 | 20 | -7.411 |
| RDK-002 `3PTB/BEN` | 0.1616 | 0.0767 | 20 | -5.929 |
| RDK-003 `1HVR/XK2` | 1.3516 | 1.2187 | 13 | -12.764 |
| RDK-004 `1M17/AQ4` | 1.2456 | 1.2019 | 20 | -7.138 |
| RDK-005 `1IEP/STI` | 0.6298 | 0.6298 | 4 | -13.615 |

Invalidated aggregate diagnostic:

- aligned RMSD <=2 Å: `5/5`;
- aligned mean: `0.7822 Å`;
- aligned median: `0.6298 Å`;
- scientific result hash: `5e56ddfc88ff1d1441539b3207b0a3aed70fb3bcc13cd4a2e8c996be5e308173`;
- execution hash: `ee2625f2d374cf4dbbeef5bfdd2e54ea4ae47c2ec0e7d22740c1ef8195594a1c`;
- artifact `redock-001-v1.1`, ID `10134340358`, ZIP SHA-256 `ee36de9023625fa0e74ae3023f5c24dd2a48b2f979c5e347374b5fdec4ab8a8e`.

Execution environment:

- Python 3.12.14;
- Open Babel 3.1.1;
- AutoDock Vina v1.2.7;
- Vina binary SHA-256 `f31f774f723bba7bbe6e9d1c47577020eea9a8da16424284c043d22593570644`.

## What remains valid from v1.1

The run remains useful evidence that the public structures could be acquired, the frozen receptor/ligand preparation pipeline executed, Vina 1.2.7 ran on all five cases, poses were produced, provenance was captured, and the audit system exposed a methodological flaw before merge.

The following claim is **not valid** from v1.1: that the docking protocol reproduced the crystallographic pose in all five cases. That question is answered only by v1.2 or later with a same-frame no-alignment RMSD endpoint.

## Scientific boundary

Neither v1.1 nor later redocking results establish measured binding affinity, potency, biological activity, selectivity, toxicity, safety, efficacy, clinical performance, or universal docking accuracy. Vina scores remain engine scores only.

## Preservation

v1.1 is closed and immutable as audit history. Its evaluator is not silently corrected under the same protocol identity. The correction is explicitly versioned as v1.2.