# Research OS 3.6 — Cross-Domain Scientific Resolution

## Escopo

O v3.6 permite registrar uma decisão científica somente como consequência de
critérios declarados e evidência existente. O objeto `ScientificDecision` é
append-only e contém `decision_id`, campanha/pergunta, opções, critérios,
evidência requerida/disponível, claims de suporte/conflito, condições,
incertezas, flags OOD, opção selecionada/rejeitada, status, racional,
limitações e timestamp.

Os status suportados são:

`SUPPORTED_DECISION`, `PROVISIONAL_DECISION`,
`NO_DECISION_INSUFFICIENT_EVIDENCE`, `NO_DECISION_CONFLICTING_EVIDENCE`,
`NO_DECISION_OUT_OF_DOMAIN` e `REJECTED_DECISION_REQUEST`.

## Regras que não podem ser contornadas

- `DecisionCriterion` registra métrica, direção, obrigatoriedade, nível mínimo,
  limite opcional de incerteza, política OOD, condições e protocolo.
- `weight_optional` é apenas metadado; não eleva evidência e não há `total_score`.
- propriedades moleculares, solubilidade, OOD, incerteza, docking e sua
  variabilidade são dimensões separadas.
- `DockingProtocolVariability` aceita no máximo três réplicas e registra média,
  desvio, mínimo, máximo e faixa. Não autoriza inferência de distribuição ou
  significância formal.
- O guard de separação retorna `CLEARLY_SEPARATED_UNDER_PROTOCOL`,
  `POSSIBLY_SEPARATED`, `WITHIN_PROTOCOL_VARIABILITY`,
  `INSUFFICIENT_REPLICATES` ou `NOT_COMPARABLE`.
- previsões OOD permanecem na auditoria, mas nunca são rankeadas como se fossem
  in-domain; a incerteza não é uma certeza.
- `EvidenceAgreementAssessment` descreve concordância entre tipos heterogêneos
  sem somá-los; `INSUFFICIENT_EVIDENCE` é um resultado válido.
- `ClaimRevision` preserva o histórico anterior e expõe também os aliases
  `previous_revision_id`, `new_status`, `new_evidence_ids`, `conditions` e
  `timestamp`.

## Persistência e interface

`DecisionStore` usa SQLite append-only em `decisions.sqlite`. A API expõe:

- `GET /api/decisions`
- `GET /api/decisions/{decision_id}`
- `GET /api/campaigns/{campaign_id}/decisions`

As respostas incluem a matriz critério→evidência e uma timeline científica.
O painel **Decisions** da interface não apresenta um vencedor implícito.

## Gate de evolução

O v3.7 só pode começar depois de decisões reais executadas e auditadas; o v3.8
exige ainda um benchmark real do v3.7. Adicionar classes ou testes sintéticos
não abre nenhum desses gates.
