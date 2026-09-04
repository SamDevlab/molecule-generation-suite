# Research OS 3.8 — Reproduction & Stress Benchmark

## Escopo

O benchmark só foi aberto depois do PASS da v3.7. Ele tenta quebrar decisões
reais já registradas, preservando a separação entre execução fresca e replay
de bundle selado. Nenhum replay é descrito como nova evidência científica.

Runner: `tools/benchmark/reproduction_stress_v38.py`.

Artefato machine-readable: `.research-os-live-3.8/reproduction-stress-benchmark.json`.

## Resultado final

`PASS` na branch `research-os-v1.3`, após o commit `9d74d2a` e o commit de
implementação da v3.8. O relatório final registra:

| Medida | Resultado |
|---|---:|
| Reproduction targets | 12 |
| Stress tests | 30 |
| Stress tests aprovados | 30/30 |
| Reproductions `REPRODUCED` | 5 |
| Reproductions `REPRODUCED_WITH_ENVIRONMENT_CHANGE` | 5 |
| Reproductions `NOT_COMPARABLE` | 2 |
| `DIVERGED` sem `FIRST_DIVERGENCE` | 0 |
| Sealed mutation / bundle tamper / Ledger tamper | PASS / PASS / PASS |
| Cache protocol / engine / model invalidation | PASS |
| Dataset/source version tracking | PASS |
| Engine disappearance | `INDETERMINATE` + `FIRST_DIVERGENCE` |
| Unidades, source injection e evidence ceiling | PASS |
| Narrator overconfidence | detectado e reparado |
| Loop pressure / no progress | bounded stop |
| Repeated question / paraphrase / language | estável / equivalente |
| Python | 3.11 PASS; 3.12.10 PASS |
| Ledger final | PASS |
| CI | PASS |

Os alvos frescos foram RDKit, AqSolDB-G (modelo e OOD), Cantera H₂/CH₄ e a
campanha de φ, além da análise do arquivo NASA PCoE RW3. Celecoxib/diclofenac
mantiveram `NOT_COMPARABLE` porque o benchmark revalidou os bundles Vina
selados sem executar um novo docking; a decisão cross-domain, materials
`NO_DECISION` e o caso Codex-generated foram rechecados por replay explícito.

## Matriz de stress

Foram executados os 30 IDs `STRESS-01` a `STRESS-30`: mutação de run selado,
tampering de bundle e Ledger, mudanças de protocolo/engine/dataset/source/model,
schema incompatível, engine ausente, unidades erradas, remoção de condições,
OOD e incerteza, elevação indevida de docking/Cantera, prompt injection,
overconfidence do narrador, pressão de usuário/autoridade, duplicação de
fonte, leakage train/test, shell/path traversal, pressão de loop, no-progress,
repetição, paráfrase, idioma e contexto falso.

O caso de shell testou somente a fronteira: pedido arbitrário é bloqueado; o
bridge limitado do provider Codex não é tratado como capacidade geral de
shell. O caso de engine desaparecida não inventa uma nova versão: usa fixture
isolada e registra a primeira divergência.

## Gate

O gate v3.8 exige simultaneamente 12+ reproduções, 25+ stress tests aprovados,
integridade de run/bundle/Ledger, invalidação de cache, versionamento de
dataset/source/model, fail-closed para engine ausente, segurança de unidade,
proveniência sem injection/elevation, reparo ou rejeição de narração,
limites de loop, estabilidade semântica e passagem em Python 3.11/3.12. Todos
os itens passaram; v3.9 permanece fechado.
