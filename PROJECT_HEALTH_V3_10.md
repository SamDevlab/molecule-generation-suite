# Project Health — Research OS 3.10

## Estado

O v3.10 está construído sobre o v3.9 PASS e adiciona memória científica
longitudinal grounded. A implementação é executada no branch
`research-os-v1.3`; `main`, `Biolab/` e `formolecular/` permanecem preservados.

## Validação

- v3.9: PASS, seis programas, 30 perguntas e 29 perguntas dinâmicas.
- v3.10: 25 consultas temporais, snapshot válido, histórico de claims e
  decisões, versões de datasets/modelos/engines e stale awareness.
- O Codex não é fonte de Evidence nem de memória científica; a conversa falsa
  não sobrepõe o Ledger.

## Blockers preservados

Validação externa independente de solubilidade, dados condição-completos de
materiais, metadados ausentes de bateria e limites E2/E3 continuam explícitos.
Memória histórica não transforma esses gaps em resultados positivos.

## Próximo gate

O v3.11 só deve iniciar após o artefato v3.10 PASS e CI verde. O próximo
escopo é priorização de gaps e seleção do próximo passo por ganho informacional
qualitativo, sem permitir que prioridade ultrapasse segurança ou evidência.
