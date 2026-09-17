# Research OS 3.9 — Autonomous Research Programs

## Escopo

O v3.9 introduz um controlador imutável para programas de pesquisa bounded.
Cada programa registra objetivo, motivação, problema inicial, perguntas,
gaps, campanhas, decisões, fontes, datasets, modelos, engines, digest e
limites máximos de campanhas, iterações, runs, fontes, candidatos e falhas.
As perguntas são obrigadas a declarar `gap_it_attempts_to_resolve`.

Os estados válidos são `CREATED`, `PLANNING`, `RUNNING`,
`PAUSED_EXTERNAL_BLOCKER`, `NO_PROGRESS`, `COMPLETED`, `FAILED` e
`INDETERMINATE`. Os limites são parte do estado imutável e qualquer tentativa
de ampliá-los levanta erro.

## Decisão de utilidade

Cada passo produz um `ResearchStepUtilityAssessment` com recomendação
qualitativa: `EXECUTE`, `DEFER`, `SKIP_REDUNDANT`, `BLOCKED_EXTERNAL`,
`NO_EXPECTED_INFORMATION_GAIN`, `REJECT_UNSAFE` ou `REJECT_OUT_OF_SCOPE`.
Não existe score universal de ganho informacional. O runner preserva
justificativa, risco, dependências externas e evidência existente.

Após duas iterações consecutivas sem nova evidência, fonte, dataset, revisão de
claim, resolução de gap, melhoria de incerteza/comparabilidade ou nova decisão,
o programa entra em `NO_PROGRESS`. O encerramento é sempre bounded; não há
loop autônomo infinito.

## Fronteira Codex/Research OS

O Codex Live é consultado para propor a estrutura do Programa 06 a partir do
estado científico registrado. O provider retorna metadados auditáveis e cria
zero Evidence. Somente Labs registrados criam resultados científicos. Fontes
externas e dados públicos continuam sujeitos a hash, proveniência e limites de
interpretação.

## Gate

O gate exige pelo menos seis programas reais e 30 perguntas autônomas, dez
perguntas dinamicamente derivadas de resultados prévios, memória
cross-campaign, `KnowledgeGainAssessment`, resultados negativos preservados,
Ledger PASS, limites imutáveis, zero Evidence criado pelo Codex e CI verde.
O artefato canônico é
`.research-os-live-3.9/autonomous-research-programs.json`.

Runner: `tools/benchmark/autonomous_programs_v39.py`.
