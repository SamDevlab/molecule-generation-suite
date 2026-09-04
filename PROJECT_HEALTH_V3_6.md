# Project Health — Research OS 3.6

## Estado

`PASS` no runner real `tools/resolution/real_decision_v36.py` em
04/09/2026. A aceitação não significa que os gaps experimentais foram
resolvidos; significa que o sistema executou decisões cross-domain e recusou
inferências que os dados não sustentam.

| Gate | Estado | Evidência |
|---|---|---|
| ScientificDecision real | PASS | 6 decisões da execução final persistidas; tentativas anteriores também permanecem no `DecisionStore` append-only |
| decisão negativa real | PASS | `NO_DECISION_OUT_OF_DOMAIN` cross-domain |
| critérios explícitos / sem score total | PASS | auditoria `PASS`, nenhum `total_score` |
| docking comparável | PASS | 1PXX, cadeia A, mesmo grid/protocolo, Vina 1.2.7 |
| variabilidade/guard | PASS | 3 réplicas por candidato; `CLEARLY_SEPARATED_UNDER_PROTOCOL` |
| molécula→solubilidade→docking | PASS | dois CIDs PubChem + AqSolDB-G real + seis Vina |
| OOD e incerteza influenciam | PASS | ambas previsões OOD e não rankable |
| combustão→térmica→materiais | PASS/limite | Cantera E3; Fourier gate; materiais sem record-level observation |
| bateria | PASS/limite | NASA RW3 E4 descritivo; campos ausentes preservados |
| UI/API de decisões | PASS | decisions, evidence matrix e timeline |
| Live Codex | PASS | discovery/researcher boundary; sem evidência criada pelo provider |

## Integridade

- Ledger final: `PASS` em schema, bundles, lineage, claims, datasets e
  artifacts; 47 runs indexados.
- Bundles da execução final: verificados individualmente como `PASS`.
- `Biolab/` e `formolecular/`: preservados; o diff nesses diretórios deve
  permanecer vazio.
- Testes locais v3.6 adicionados para contratos, guard de docking, aliases,
  persistência e API.

## Gaps que permanecem abertos

- O sample AqSolDB-G é pequeno e não é teste externo independente; o modelo não
  foi promovido.
- Docking continua E2 computacional e não mede afinidade.
- Não há evidência material condition-complete para aprovação/sobrevivência.
- A bateria não possui no registro analisado capacidade, resistência e
  incerteza; não há trajetória de degradação modelada.
- O corpus do usuário continua aguardando ingestão/revisão humana.

## Gates de avanço

`v3.7`: FECHADO — não foi executado benchmark sistemático real de decisões.

`v3.8`: FECHADO — depende de benchmark real do v3.7.

O pacote pode ser fechado em `3.6.0`; não há justificativa científica para
avançar só porque os contratos foram implementados.
