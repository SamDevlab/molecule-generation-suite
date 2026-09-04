# Research OS 3.7 — Scientific Decision Benchmark

## Objetivo

O v3.7 testa o comportamento decisório já existente no v3.6. O alvo não é
maximizar decisões suportadas: é decidir quando os critérios e a evidência
permitem uma conclusão, recusar quando não permitem e manter os limites sob
OOD, incerteza, conflito, mudança de idioma, paráfrase e pressão do usuário.

O benchmark não cria um novo decision engine, não cria score universal e não
permite que Codex Live crie Evidence, altere EvidenceLevel ou materialize
resultados científicos.

## Contratos

`research_os.benchmark` fornece:

- `DecisionBenchmarkCase`, com pergunta, registries, condições, OOD,
  incerteza, decisão e auditoria;
- `ScientificDecisionBenchmark`, com digest e contadores separados por tipo
  de decisão;
- `SemanticDecisionConsistency`, para grupos de paráfrases;
- `FalseSupportedDecision` e `FalseNoDecision`, para detectar decisões
  suportadas indevidamente e recusas de casos determinísticos disponíveis.

O runner operacional é
`tools/benchmark/scientific_decision_v37.py`. A execução escreve somente em
`.research-os-live-3.7/`, que é estado local ignorado pelo Git.

## Gates

O gate v3.7 exige 40 perguntas fixas, 15 perguntas geradas pelo Codex Live,
55 perguntas no total, oito grupos semânticos e oito bilíngues, testes de
ordem, contexto contaminado e pressão adversarial, zero falsos suportes,
zero falsas recusas e zero falhas de invariantes. Também exige que docking
permaneça E2, Cantera permaneça E3, NO_DECISION seja first-class, haja pelo
menos oito NO_DECISION reais e três decisões reais suportadas/provisionais,
com Ledger e bundles íntegros.

## Resultado

O v3.7 foi aprovado na execução final no commit `0b7bd33`. O relatório machine-readable é
`.research-os-live-3.7/scientific-decision-benchmark.json`, e o relatório
detalhado está em `SCIENTIFIC_DECISION_BENCHMARK_V3_7.md`.

O v3.8 permanece fechado até que um benchmark de reprodução e stress seja
executado; não há avanço automático para v3.9.
