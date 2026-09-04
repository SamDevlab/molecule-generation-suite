# Project Health — Research OS 3.7

## Estado

`PASS` no benchmark sistemático final em 04/09/2026, na branch
`research-os-v1.3`, commit científico de referência `26d999d`; o exame final
Codex Live foi fechado no commit `9d74d2a`.

| Gate | Estado | Evidência |
|---|---|---|
| 40+ perguntas fixas | PASS | 61 executadas |
| 15+ perguntas Codex-generated | PASS | 15 geradas por Codex Live; replay auditável na validação final |
| 55+ perguntas totais | PASS | 108 casos, incluindo variantes |
| Semântica e idioma | PASS | 8 grupos semânticos e 8 bilíngues |
| Ordem/contexto/pressão | PASS | testes executados |
| False supported / false no-decision | PASS | 0 / 0 |
| Evidence inflation / OOD bypass / uncertainty bypass | PASS | 0 / 0 / 0 |
| Docking / Cantera ceiling | PASS | E2 / E3 preservados |
| NO_DECISION | PASS | 45 totais; 32 casos reais |
| Decisões reais suportadas/provisionais | PASS | 22 casos reais |
| Bundles / Ledger | PASS | 108 bundles; Ledger PASS com 108 runs |
| Python 3.11 / 3.12 | PASS | skip esperado documentado; 169/170 testes |

## Limites preservados

- docking continua computacional E2 e não prova afinidade medida, eficácia ou
  segurança;
- Cantera continua simulação física E3 e não vira evidência experimental;
- OOD, incerteza, condições incompatíveis e campos ausentes permanecem
  visíveis;
- múltiplas fontes/reviews não são contadas como evidências independentes sem
  análise de dependência;
- nenhum score universal foi criado;
- Codex Live continua incapaz de criar Evidence ou alterar EvidenceLevel;
- `Biolab/` e `formolecular/` permanecem preservados.

## Próximo gate

`v3.8`: executado no relatório de reprodução/stress. `v3.9`: não aberto.
Não há justificativa científica para avançar por roadmap.
