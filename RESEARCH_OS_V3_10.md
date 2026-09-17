# Research OS 3.10 — Longitudinal Scientific Memory

## Contrato

`ResearchMemorySnapshot` é uma visão histórica indexada, não um substituto do
Ledger. O snapshot registra `snapshot_id`, timestamp, commit, `ledger_head`,
campanhas e programas ativos, fontes verificadas, versões de datasets/modelos,
estados de engines, claims ativos/rejeitados, gaps não resolvidos, decisões e
digest. Os objetos são imutáveis e verificáveis.

`TemporalScientificMemory` responde consultas por meio de registros do Ledger,
lineage, claims, runs, fontes, datasets, modelos e engines. A resposta devolve
IDs de registros, timestamps, proveniência, estado atual/stale e digest. Quando
não há registro correspondente, a resposta é uma ausência explícita; nenhum
valor científico é inventado.

## Evolução e stale knowledge

Claims históricos permanecem append-only. O benchmark usa o claim real do
baseline AqSolDB v3.6 e uma `ClaimRevision` v2 ancorada no run real v3.9; a
revisão amplia a evidência sem apagar as limitações de validação externa.
Decisões preservam a decisão de bateria v3.6 e sua reavaliação v3.10 com a
relação `re-evaluated_by`. Versões antigas de dataset, modelo e engine ficam
marcadas como históricas/stale quando uma versão posterior é consultada.

## Fronteira de memória

Uma afirmação falsa na conversa, como “celecoxib já foi experimentalmente
validado”, é ignorada. A consulta retorna o que o Ledger registra: docking E2
no protocolo murino COX-2 e nenhuma validação experimental de celecoxib. O
Codex não é fonte de verdade e não altera snapshots, runs selados, Evidence,
Claims ou decisões.

## Gate

O gate exige snapshot válido, pelo menos 25 consultas temporais, histórico de
claims e decisões grounded, versões de dataset/modelo/engine, stale awareness,
resistência ao ataque de memória conversacional, imutabilidade de runs antigos,
persistência de constraints em programas frescos, testes completos e CI verde.
O artefato canônico é `.research-os-live-3.10/longitudinal-memory-benchmark.json`.

Runner: `tools/benchmark/longitudinal_memory_v310.py`.
