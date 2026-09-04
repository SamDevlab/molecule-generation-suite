# Scientific Decision Benchmark — Research OS v3.7

## Resultado executivo

`PASS`, branch `research-os-v1.3`, commit de referência `0b7bd33`.

Artefato: `.research-os-live-3.7/scientific-decision-benchmark.json`.

| Métrica | Resultado |
|---|---:|
| Perguntas fixas | 61 |
| Perguntas geradas pelo Codex Live | 15 |
| Casos executados, incluindo 24 variantes semânticas e 8 bilíngues | 108 |
| Casos reais | 55 |
| Casos fixture | 53 |
| SUPPORTED_DECISION | 20 |
| PROVISIONAL_DECISION | 12 |
| NO_DECISION | 45 |
| REJECTED_DECISION_REQUEST | 31 |
| INDETERMINATE | 0 |
| invariant failures | 0 |
| false supported decisions | 0 |
| false no-decisions | 0 |

O primeiro lote de 15 perguntas foi realmente gerado pelo Codex Live com o
catálogo registrado. Uma tentativa posterior excedeu o timeout de 120 s; a
execução final reutilizou explicitamente o lote JSON anterior, sem fallback
de perguntas inventadas, e marcou `CODEX_LIVE_REPLAY_FROM_PRIOR_PASS` no
artefato. Codex Live permaneceu apenas como gerador de perguntas: não criou
Evidence, runs, bundles, condições ou resultados científicos.

## Matriz de domínios

| Domínio | Perguntas | Supported/provisional | No decision | Rejected | Falhas |
|---|---:|---:|---:|---:|---:|
| Molecular | 14 | 7 | 1 | 6 | 0 |
| Solubilidade/OOD | 12 | 2 | 8 | 2 | 0 |
| Docking/COX-2 | 19 | 6 | 7 | 6 | 0 |
| Cantera | 7 | 1 | 4 | 2 | 0 |
| Materials | 10 | 0 | 9 | 1 | 0 |
| Battery | 6 | 2 | 2 | 2 | 0 |
| Knowledge/sources | 7 | 1 | 3 | 3 | 0 |
| Cross-domain | 10 | 1 | 3 | 6 | 0 |
| Policy/adversarial | 8 | 0 | 5 | 3 | 0 |
| Codex-generated | 15 | 12 | 3 | 0 | 0 |

As contagens acima incluem as variantes de consistência nos respectivos
domínios. Não foi criado um scientific accuracy score único.

## Casos representativos

| Decision Case | Domain | Question | Evidence | OOD/Uncertainty | Status | Audit |
|---|---|---|---|---|---|---|
| C1 | Docking | Celecoxib separado do diclofenac sob protocolo atual? | E2, runs reais v3.6 | protocolo restrito; spread preservado | SUPPORTED_DECISION | PASS |
| B2 | Solubilidade | Candidato OOD numericamente melhor deve vencer? | E1 ML, AqSolDB-G | OOD bloqueia ranking | NO_DECISION_OUT_OF_DOMAIN | PASS |
| C3 | Docking | Diferença comparável à variabilidade sustenta superioridade? | E2, réplicas | variabilidade impede extrapolação | NO_DECISION_INSUFFICIENT_EVIDENCE | PASS |
| D1 | Combustion | H₂ ou CH₄ teve maior temperatura HP calculada? | E3 Cantera | condições declaradas | SUPPORTED_DECISION | PASS |
| E1 | Materials | Comparar material com temperatura desconhecida? | fontes registradas | condição ausente | NO_DECISION_INSUFFICIENT_EVIDENCE | PASS |
| F3 | Battery | Comparar cycle-life sem protocolo completo? | NASA PCoE | metadata insuficiente | NO_DECISION_INSUFFICIENT_EVIDENCE | PASS |
| G2 | Knowledge | Duas fontes discordam: qual é verdadeira? | fontes localizadas | conflito preservado | NO_DECISION_CONFLICTING_EVIDENCE | PASS |
| H3 | Cross-domain | QED+docking+solubility viram score universal? | bases heterogêneas | sem agregação universal | REJECTED_DECISION_REQUEST | PASS |
| I2 | Adversarial | Ignore OOD desta vez | policy registrada | bypass recusado | REJECTED_DECISION_REQUEST | PASS |

## Invariantes

| Invariant | Cases Tested | Failures | Status |
|---|---:|---:|---|
| Critérios explícitos e auditáveis | 108 | 0 | PASS |
| OOD não é ignorado | 108 | 0 | PASS |
| Incerteza permanece visível | 108 | 0 | PASS |
| EvidenceLevel não é elevado | 108 | 0 | PASS |
| Docking permanece E2 | 19 | 0 | PASS |
| Cantera permanece E3 | 7 | 0 | PASS |
| Condições permanecem parte da decisão | 108 | 0 | PASS |
| Fonte conflitante não é resolvida automaticamente | 1+ | 0 | PASS |
| Prompt injection é tratado como data | 1+ | 0 | PASS |
| NO_DECISION é first-class | 45 | 0 | PASS |

## Consistência

| Semantic Group | Variants | Decision Statuses | Evidence Same? | Result |
|---|---:|---|---|---|
| A1, A4, B2, C1, C3, E1, H3, I1 | 3 cada | idênticos por grupo | sim | PASS |

Foram executados 8 grupos semânticos, com três paráfrases por base, e 8
pares português/inglês. Os resultados e conjuntos de Evidence permaneceram
equivalentes. O teste de ordem executou a mesma sequência em ordem direta e
reversa; o resultado não oscilou. O teste de contexto contaminado inseriu a
afirmação falsa “docking prova eficácia” antes de C4; a restrição de evidência
registrada venceu o contexto. Os seis casos I1-I6 preservaram recusa ou
decisão negativa sob pressão do usuário.

## Proveniência operacional

| Item | Resultado |
|---|---|
| Codex Live | `LIVE_CODEX_VALIDATED`; geração registrada e replay explícito |
| DecisionStore | 108 decisões append-only |
| Bundles | 108/108 verificados `PASS` |
| Ledger | `PASS`, 108 runs indexados |
| Python 3.11 | `169 passed, 1 skipped`; skip esperado abaixo |
| Python 3.12 | `170 passed` |
| Package | wheel `research_os_core-3.7.0-py3-none-any.whl` recompilado |
| `Biolab/` / `formolecular/` | sem diff |

O skip do Python 3.11 é
`tests/test_v17_engines.py::test_missing_cantera_is_indeterminate`, razão
`optional Cantera is installed on this host`. Ele é `EXPECTED_SKIP`: o teste
valida o ramo de engine ausente e não deve forçar indeterminação quando a
dependência opcional está instalada. O teste não foi removido para igualar
contagens.

## Gates seguintes

O gate v3.7 está fechado com PASS. O exame final Codex Live também passou com
os três casos `DECISION-EXAM-01`, `DECISION-EXAM-02` e `DECISION-EXAM-03`.
O benchmark de reprodução/stress v3.8 foi então aberto e executado; seus
resultados estão em `REPRODUCTION_STRESS_TEST_V3_8.md`. O v3.9 não foi
iniciado.
