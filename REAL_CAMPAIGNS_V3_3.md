# Research OS 3.3 — real scientific campaigns

The campaign layer separates four roles: live Codex discovery/ranking,
registered Labs, immutable bundles/Ledger, and cross-campaign memory. A
campaign can stop at a useful gate with `INSUFFICIENT_EVIDENCE`; absence of a
result is recorded rather than filled by narration.

## Selected campaign contract

The live acceptance selects exactly three primary and two secondary problem IDs
from the registered catalog. The deterministic `CodexTestProvider` fixture
selects `P-MOL-01`, `P-COMB-01`, `P-MAT-01` as primary and `P-BATT-01`,
`P-PHARMA-01` as secondary for CI. The verified live result is recorded in the
ignored `.research-os-live-3.3-final7/real-campaign-acceptance.json` file. It
used `gpt-5.6-luna`, selected the required five IDs, and completed five bounded
campaigns.

| Campaign | Protocol | Expected/recorded result | Scientific boundary |
|---|---|---|---|
| CAMPAIGN-REAL-01 / P-MOL-01 | pinned AqSolDB-G sample → scaffold split → NumPy Morgan/ridge → residual interval + Tanimoto AD | `PARTIALLY_SUPPORTED` (live run sealed/verified); promotion rejected without an independent external test | E1 model analysis only; OOD entries are audit-only and not rankable |
| CAMPAIGN-REAL-02 / P-COMB-01 | Cantera 3.2 `gri30.yaml`, H2/CH4 at phi 1.0, 300 K, 101325 Pa, air oxidizer, plus H2 rerun | `SUPPORTED`; H2 2380.4487 K, CH4 2225.1321 K, rerun `REPRODUCED`; three bounded E3 claims are linked to run evidence | E3 physics simulation; not a hardware, safety or universal mechanism claim |
| CAMPAIGN-REAL-03 / P-MAT-01 | registered NASA source synthesis and condition matrix | `INSUFFICIENT_EVIDENCE` after source gate | no alloy approval; no condition-matched degradation measurement |
| Secondary / P-BATT-01 | DOE Battery Data Hub availability/schema gate | `INSUFFICIENT_EVIDENCE` | no local public record is silently fabricated |
| Secondary / P-PHARMA-01 | RCSB PDB 1PXX target identity gate | `INDETERMINATE` after target gate | `Mus musculus`, `PTGS2/COX-2`, and `1PXX` are retained; no docking/affinity/clinical claim |

## Required campaign report fields

Each persisted campaign includes problem, question, status, source records,
dataset/model/engine IDs, workflow/run/bundle/evidence/claim IDs, explicit
conditions, first loss, gaps, source conflicts, negative results, OOD policy,
uncertainty policy, and reproducibility metadata. `ResearchCampaignBundle`
links the campaign report to a verified ResearchBundle hash.

The molecular report retains MAE, RMSE, bias, segment counts, OOD fraction,
observed interval coverage and notable failures. It never promotes an
out-of-domain molecule. The combustion report retains all H2/CH4 conditions,
engine provenance, mechanism and Ledger comparison, including
`FIRST_DIVERGENCE` when a rerun is not comparable.

## Execution

```powershell
.\.venv\Scripts\python.exe tools\campaigns\real_campaigns.py
```

The script uses the local Codex CLI live boundary, not an external LLM API. Its
final reasoning call uses this exact open-ended prompt:

> Com as ferramentas, dados e fontes que temos agora, encontre um problema científico real que ainda não investigamos e faça a melhor pesquisa possível sem ultrapassar os limites da evidência.

No problem ID is hardcoded into that final prompt. Invalid live output fails
closed, and campaign execution is limited to registered protocols.

The same final live researcher selected a new source-backed equivalence-ratio
question under `P-COMB-01`, extending the single-phi campaign protocol. It
returned a next-step recommendation only; it created no Evidence, run, claim
or bundle, so this suggested sweep is not reported as executed evidence.

The live molecular failure analysis recorded 10 held-out molecules, MAE
1.826266, RMSE 2.314557, bias 1.008771, OOD fraction 0.80 and observed
interval coverage 0.70. The live campaign summary contains one
`PARTIALLY_SUPPORTED`, one `SUPPORTED`, two `INSUFFICIENT_EVIDENCE` and one
`INDETERMINATE` result; the latter statuses are intentional evidence ceilings,
not substituted scientific values.
