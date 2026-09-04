# Research OS 3.12 — External Evidence Integration

## Contratos

`ExternalEvidenceUpdate` é append-only e registra update, fonte/versão,
dataset opcional, evidências, claims, gaps, decisões, compatibilidade,
conflitos e revisões resultantes. `EvidenceDependencyAssessment` registra
fontes, datasets, modelos, runs e publicações compartilhados e classifica
`INDEPENDENT`, `PARTIALLY_DEPENDENT`, `DEPENDENT` ou `UNKNOWN`.

Integração nunca altera bundles históricos. A evidência externa permanece DATA
até passar verificação de fonte, proveniência, licença, hash, schema, unidades,
condições, lineage, independência, compatibilidade e auditoria de overlap.

## Limites de promoção

O contrato rejeita promoção E2→E3/E4 sem evidência adequada e rejeita E3→E4
sem experimento real compatível. A reavaliação de claim, decisão ou prioridade
é explícita e append-only; nenhum estado antigo é sobrescrito.

## Gate

O gate exige pelo menos 20 casos update/impact, dependência e dupla contagem
controladas, conflitos preservados, runs históricos intactos, revisão de claim,
revisita de decisão, mudança de prioridade, versões preservadas e blockers
honestos. A busca real foi registrada: fontes públicas relevantes foram
encontradas, mas nenhuma foi promovida sem bytes, hash, schema e compatibilidade
localmente verificáveis. A integração usa a evidência real versionada do RW3 e
fixtures somente para testar invariantes.

Artefato: `.research-os-live-3.12/external-evidence-integration.json`.
Runner: `tools/benchmark/external_evidence_v312.py`.
