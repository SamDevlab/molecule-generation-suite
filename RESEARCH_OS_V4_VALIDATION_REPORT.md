# Research OS 4.0 validation report

## Result

The completed v4.0 gate recorded PASS after the previous v3.9–v3.12 artifacts
were verified as PASS. The final replayable record was produced from a real
Codex Live run using `gpt-5.6-luna`; replay is marked explicitly and is used
only to consolidate the already completed live examination.

| Area | Result |
|---|---:|
| Fixed/systematic questions | 100 |
| New Codex Live questions | 30 |
| Total decision cases | 130 |
| Supported / no-decision / rejected | 33 / 69 / 28 |
| Repeated / paraphrase / bilingual groups | 15 / 15 / 15 |
| Reproduction cases | 20 (14 reproduced, 3 environment change, 3 diverged) |
| Stress tests | 50 PASS |
| False supported / false no-decision | 0 / 0 |
| Evidence inflation / OOD / uncertainty bypass | 0 / 0 / 0 |
| Ledger / bundle / scientific audit / security audit | PASS / PASS / PASS / PASS |

## Final autonomous exam

Codex Live received the exact high-level task required by the v4.0 protocol.
The selected A question executed a registered deterministic `MoleculeLab`
run and reached a bounded supported decision. B reached
`NO_DECISION_OUT_OF_DOMAIN` without ranking through OOD evidence. C reached
`NO_DECISION_INSUFFICIENT_EVIDENCE` and was `NOT_ATTEMPTED_BY_DESIGN` because
the required condition-complete external measurement is absent. All 20 exact
follow-up questions returned answers with valid registered grounding IDs.

## Domain and legacy review

The fixed matrix contains 15 molecular, 15 ML/OOD/uncertainty, 15
docking/pharma, 15 Cantera/physics, 10 battery/materials, 10
Knowledge/source/evidence, 10 cross-domain and 10 adversarial cases.

| Legacy component | Current replacement | Recommendation |
|---|---|---|
| `formolecular/g_oraculo_farma.py` | MoleculeLab + ML/evidence gates | MIGRATING |
| `formolecular/g_oraculo_aeroespacial.py` | FuelLab → CombustionLab → PropulsionLab | MIGRATING |
| `formolecular/t_aero2.py` | FuelLab → CombustionLab → PropulsionLab | MIGRATING |
| `Biolab/fabrica_g2.py` | typed receptor/ligand + Vina pipeline | MIGRATING |

Legacy files remain present. No deletion, retirement or main-branch change was
performed.

## Evidence and blockers

The v3.12 external search remains honest: the searched solubility, Oxford
battery, Nature aging, NASA and NIST sources were not ingested as compatible,
condition-complete local evidence. Existing versioned NASA PCoE evidence is
integrated without raising its evidence level. The highest-value next work is
therefore an independent condition-complete external validation dataset,
especially for the solubility and battery gaps.

See `.research-os-live-4.0/master-validation.json` and its companion JSON
artifacts for the complete case-level provenance.
