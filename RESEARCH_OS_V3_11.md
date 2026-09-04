# Research OS 3.11 — Research Prioritization

## Contratos

`ResearchPriorityAssessment` registra pergunta e gap candidatos, relevância,
evidência atual/alvo, resolvabilidade, ganho informacional qualitativo,
redundância, estado de engine/dataset/fonte, dependência externa, escopo,
segurança, recomendação e rationale. As recomendações são
`PRIORITIZE_NOW`, `SECONDARY`, `DEFER`, `BLOCKED`, `LOW_INFORMATION_GAIN`,
`UNSAFE` e `OUT_OF_SCOPE`.

`ResearchPriorityQueue` ordena avaliações por política declarada e fornece uma
razão para cada posição. A posição da fila não é uma pontuação científica e o
contrato rejeita campos universais `score`, `value` ou `priority` no ganho
informacional.

## Estado atual e reordenação

O v3.11 reavalia gaps reais do v3.10: busca por dataset externo independente de
solubilidade, registros condição-completos de materiais, dataset complementar
de bateria, corpus do usuário, aprofundamento COX-2 e oportunidade E3/E4.
Após a observação real do schema de bateria no v3.9, a avaliação antiga
`BLOCKED` é preservada e uma nova avaliação `SECONDARY` é adicionada; nenhuma
história é apagada.

O teste explícito apresenta as opções de 50 replicações docking, dataset
externo, repetição RDKit e comparação de materiais sem registros. A fila
prioriza a busca de solubilidade porque pode mudar uma decisão; rejeita o
comparativo de materiais por segurança; e marca repetições idênticas como baixo
ganho.

## Gate

O gate exige fila traceável, pelo menos 20 perguntas grounded, reconhecimento
de redundância e blockers, distinção entre importância e ação, reordenação sem
perda histórica, ausência de score oculto, proteção dos gates de segurança e
evidência, uma computação corretamente pulada e um gap potencialmente decisivo
priorizado. CI verde também é obrigatório.

Artefato: `.research-os-live-3.11/research-prioritization-benchmark.json`.
Runner: `tools/benchmark/research_prioritization_v311.py`.
