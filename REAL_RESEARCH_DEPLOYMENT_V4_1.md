# Real Research Deployment v4.1

The v4.1 benchmark asks whether Research OS changes what is known, rather
than merely completing software steps. Prior state is the sealed v4.0
artifact; new state is the fresh v4.1 Ledger and its sealed bundles.

## Program outcomes

| Program | Prior state | New evidence | Claim change | Decision change | Gap change | Impact |
|---|---|---|---|---|---|---|
| COX-2 robustness | Three-seed E2 ranking on murine 1PXX | Existing sealed replicate scores and protocol audit | None; E2 boundary retained | None | Docking gap remains; redundant repeats skipped | `NO_MATERIAL_CHANGE` |
| Solubility reliability | E1 scaffold-split model, no independent test | Frozen replay, MW/LogP/TPSA/OOD segments, residual intervals, failure cases | Existing claim narrowed; v4.1 failure-mode claim added | Prior bounded use remains, external validation still blocked | Calibration/external-test gap refined | `KNOWLEDGE_CHANGED` |
| Combustion boundary | One declared Cantera E3 protocol | Six real gri30 adiabatic-HP runs across modest T0, pressure, phi and fuel variants | Protocol-limited E3 claim recorded | Universalization rejected; bounded conclusion retained | E3↔E4 gap refined | `DECISION_CHANGED` |
| Battery usefulness | NASA PCoE RW3 schema known incomplete | Real archive parsed without executing archive scripts | Descriptive schema claim strengthened and limited | No capacity/resistance decision permitted | Missing metadata gap refined | `GAP_REFINED` |
| Materials search | No condition-complete record | Public discovery of Zenodo 316L, TU Delft De-Hy and Mendeley candidates | No unsupported materials claim | No material comparison decision | File-ingestion/condition-match gap exposed | `BLOCKED_EXTERNAL` |
| Codex-selected molecule boundary | Narrow recalculation gap | Registered MoleculeLab CCO calculation | Deterministic result remains computational only | No efficacy or clinical decision | Narrow recalculation gap closed | `KNOWLEDGE_CHANGED` |

## Research steps

| Research step | Gap addressed | Expected gain | Redundancy | Executed? | Result |
|---|---|---|---|---|---|
| COX-2 identical repeat | `GAP-DOCKING-E2-ONLY` | Test protocol repeat | High; Vina unavailable and three seeds already exist | No | `SKIP_REDUNDANT` |
| COX-2 exhaustiveness variant | `GAP-DOCKING-E2-ONLY` | Test modest protocol sensitivity | Not executable in current environment | No | Explicitly unavailable; no score guessed |
| Solubility failure segmentation | External validation/model-boundary gap | Identify error/OOD segments | No | Yes | Two high-confidence failure cases recorded |
| Cantera T0/pressure/phi variants | `GAP-E3-E4-COMPARISON` | Bound condition sensitivity | No | Yes | Numeric changes without tested trend reversal |
| Battery capacity inference | `GAP-BATTERY-METADATA` | Capacity trajectory | Invalid without capacity field | No | `NO_EXPECTED_INFORMATION_GAIN` |
| Materials row-level ingestion | `GAP-MATERIALS-CONDITION-COMPLETE` | Condition-matched comparison | External file and license review required | No | `BLOCKED_EXTERNAL` |

## Impact contract

`ResearchOutcomeImpact` is immutable and content-addressed. It preserves prior
claim, decision and gap IDs alongside new source, dataset, run, evidence,
claim, decision and gap IDs. It has qualitative statuses only; there is no
universal impact score. The store rejects duplicate impact IDs and invalid
digests.

`ProtocolSensitivityAssessment`, `ConfidenceFailureCase` and
`ConditionDependentDecision` preserve the relevant details without promoting
simulation to experiment or hiding uncertainty/OOD.

## External findings

The materials search found promising public datasets, including a 316L
hydrogen-charging dataset and a ferritic high-strength-steel project, but the
v4.1 run did not download, hash, parse and condition-match a complete row-level
file. The correct result is therefore `BLOCKED_EXTERNAL`, not a materials
claim. The URLs and reported/unknown fields are retained in the machine
artifact for the next bounded ingestion attempt.

## Reproduction

Run from the repository root:

```text
python tools/benchmark/research_deployment_v41.py --ci-green
```

The run writes only to `.research-os-live-4.1/`, verifies every new bundle,
and never mutates the v3.6–v4.0 artifacts used as prior state.
