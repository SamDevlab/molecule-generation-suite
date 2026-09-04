# Project Health — Research OS 3.12

## Estado

O v3.12 está construído sobre v3.11 PASS e adiciona integração externa
versionada com dependência explícita. O branch de trabalho é
`research-os-v1.3`; `main`, `Biolab/` e `formolecular/` permanecem preservados.

## Validação

- v3.11: PASS, 20 perguntas de priorização e fila com histórico de reorder.
- v3.12: 21 updates, cinco buscas reais bloqueadas honestamente, um update real
  versionado, 15 fixtures, cinco dependency assessments e guards E2/E3→E4.
- Bundles históricos foram verificados antes/depois sem alteração.

## Blockers preservados

Nenhuma fonte nova foi promovida sem ingestão local verificável. Solubilidade
externa, bateria complementar, materiais condição-completos e comparação E3/E4
continuam dependências e não são tratados como sucesso científico.

## Próximo gate

O v4.0 só deve iniciar após o artefato v3.12 PASS e CI verde. Ele será a
validação sistêmica final, incluindo o exame autônomo Codex Live e perguntas de
follow-up, sem reabrir a arquitetura histórica.
