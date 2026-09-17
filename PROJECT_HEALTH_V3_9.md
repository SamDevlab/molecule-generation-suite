# Project Health — Research OS 3.9

## Estado

O v3.9 adiciona programas autônomos bounded sobre o Ledger, bundles selados e
decisões científicas existentes. O trabalho é desenvolvido em
`research-os-v1.3`; `main`, `Biolab/` e `formolecular/` permanecem fora do
escopo de alteração.

## Evidência de validação

- v3.8: PASS, 12 reproduções e 30/30 stress tests.
- v3.9: seis programas, 30 perguntas, 29 dinâmicas, 30 utilidades, três runs
  frescos, KnowledgeGain para todos os programas e Ledger PASS.
- Regressão local: 176 passed, 1 skipped no Python 3.11 do ambiente do projeto.
- Skip esperado: o teste de ausência do Cantera não se aplica porque Cantera
  está instalado no host.

## Blockers honestos

Validação externa independente de solubilidade, execução experimental, dados
condição-completos de materiais e campos ausentes de bateria continuam gaps.
`BLOCKED_EXTERNAL`, `NO_EXPECTED_INFORMATION_GAIN` e `NO_PROGRESS` são estados
de controle, não falhas escondidas nem evidência positiva.

## Próximo gate

O v3.10 só deve iniciar depois de o artefato v3.9 estar PASS e o CI do commit
final estar verde. O próximo escopo é memória longitudinal temporal,
evolução de claims/decisões, conhecimento stale e resistência a ataques de
memória conversacional.
