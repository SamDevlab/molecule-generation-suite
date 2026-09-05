# Suite de Geração e Triagem Molecular (Molecule Generation & Virtual Screening Suite)

Esta é uma suite consolidada de projetos voltados para a **Descoberta Computacional de Fármacos (Drug Discovery)**, **Triagem Virtual (Virtual Screening)**, **Acoplamento Molecular (Molecular Docking)** e **Predição de Propriedades por Machine Learning (QED/ADMET)**.

O repositório reúne e organiza dois fluxos de trabalho principais desenvolvidos localmente:
1. **Biolab**: Esteira HPC para triagem virtual de sinergia molecular e acoplamento molecular automatizado.
2. **formolecular (Oráculo)**: Modelos de IA baseados em XGBoost para predição rápida de propriedades moleculares e simulações evolucionárias de novos ligantes.

---

## Estrutura do Repositório

```text
molecule-generation-suite/
├── Biolab/                     # Triagem virtual & Docking Molecular
│   ├── fabrica_g2.py           # Esteira principal de acoplamento molecular (AutoDock Vina)
│   ├── coletor_admet.py        # Coleta de propriedades de toxicidade e ADMET
│   ├── analiseFinal.py         # Script de consolidação e classificação de acoplamento
│   ├── TOP_10_HITS_REFINADOS.csv
│   └── *.pdb / *.pdbqt         # Estruturas 3D de proteínas e ligantes filtrados
│
└── formolecular/               # Predição Neural & IA Farmacêutica/Aeroespacial
    ├── g_oraculo_farma.py      # Motor de treinamento e predição ADMET/QED usando XGBoost
    ├── g_oraculo_aeroespacial.py# Motor de predição para propelentes/materiais aeroespaciais
    ├── treinar_oraculo.py      # Script utilitário para retreinamento de modelos de IA
    ├── modelos_ia/             # Modelos preditivos serializados (.pkl)
    └── novo_horizonte/         # Simulação evolucionária e laboratório evolutivo de mutantes
```

---

## 🧪 1. Biolab: Esteira de Triagem Virtual e Sinergia
O projeto `Biolab` realiza a avaliação termodinâmica de compostos contra alvos biológicos (como COX-2 e COX-1) para identificar potencial de sinergismo e seletividade farmacológica.

### Recursos Principais:
- **Integração Científica**: Uso do **AutoDock Vina** para simulação física de acoplamento tridimensional receptor-ligante.
- **Preparação Química**: Automatização via **OpenBabel** (`obabel`) para conversão de formatos tridimensionais (PDB ➡️ PDBQT).
- **Processamento Concorrente**: Execução paralela em múltiplos cores (via `ProcessPoolExecutor`) para acelerar a triagem de bibliotecas.
- **Relatório Automático**: Geração de gráficos de sinergismo térmico (mapas de calor com `Seaborn`) e compilação de relatórios regulatórios formais em formato PDF (`FPDF`).

---

## 🧠 2. formolecular: Inteligência Artificial e Modelos Preditivos
O projeto `formolecular` utiliza Inteligência Artificial para estimar propriedades moleculares críticas instantaneamente, evitando o custo computacional de simulações físicas tradicionais para triagens iniciais.

### Recursos Principais:
- **Featurização Química**: Conversão de strings SMILES em **Morgan Fingerprints** de 2048 bits de alta densidade usando a biblioteca **RDKit**.
- **Modelos Preditivos**: Regressores baseados em **XGBoost** treinados em super-bancos de dados moleculares para predição de:
  - **Score QED** (Quantitative Estimate of Drug-likeness / Potencial de Fármaco).
  - Propriedades físicas (LogP, TPSA, Peso Molar).
  - Parâmetros ADMET (Aromatic Rings, H-Donors/Acceptors, Rotatable Bonds).
- **Algoritmo Evolucionário (`novo_horizonte`)**: Laboratório molecular que gera mutações químicas em estruturas ligantes, selecionando e cruzando as gerações com melhores scores preditos pela IA para gerar novas moléculas candidatas.

---

## 🛠️ Tecnologias Utilizadas
Os projetos foram desenvolvidos utilizando as seguintes bibliotecas do ecossistema científico do Python:
- **RDKit** (Manipulação e featurização de dados químicos)
- **XGBoost** & **Scikit-learn** (Modelagem estatística e Machine Learning)
- **Pandas** & **NumPy** (Processamento analítico de matrizes)
- **Matplotlib** & **Seaborn** (Visualização de dados químicos e heatmaps)
- **FPDF** (Geração automatizada de relatórios em PDF)

*Nota: Para rodar as simulações físicas do Biolab, é necessário ter o executável do [AutoDock Vina](https://vina.scripps.edu/) configurado no caminho local.*

---

## 📦 Notas sobre o Repositório
Para manter este repositório limpo, leve e em conformidade com as diretrizes do GitHub (limite de 100MB por arquivo), os seguintes itens foram propositalmente excluídos através do `.gitignore`:
- **Datasets Gigantes**: Bases CSV de treino bruto de mais de 500MB (ex. `BASE_ORACULO_FARMACIA_ADMET.csv`).
- **Executáveis**: Binários de motores de docking e instaladores (ex. `vina.exe` e `install_babel.exe`).
- **Ambientes Virtuais**: Pastas de dependências e ambientes virtuais Python (`env_biolab/`).
- **Arquivos Temporários**: Arquivos intermediários de docking e arquivos temporários de sistema.

## 🔬 3. Research OS 3.3: campanhas científicas reais

O Research OS coordena campanhas source-backed com o Codex local como camada de
descoberta, planejamento e narração. A execução científica continua limitada a
Labs/engines registrados; fontes externas são tratadas como dados, e Evidence,
Claims, bundles e histórico permanecem no Ledger.

- Catálogo e problemas reais: [`REAL_RESEARCH_PROBLEMS_V3_3.md`](REAL_RESEARCH_PROBLEMS_V3_3.md)
- Campanhas e aceitação live: [`REAL_CAMPAIGNS_V3_3.md`](REAL_CAMPAIGNS_V3_3.md)
- Saúde científica: [`PROJECT_HEALTH_V3_3.md`](PROJECT_HEALTH_V3_3.md)
- Auditoria de segurança: [`SECURITY_AUDIT_V3_3.md`](SECURITY_AUDIT_V3_3.md)

## 🔬 4. Research OS 3.4: resolução de gaps com evidência real

O milestone 3.4 registra tentativas append-only de fechar gaps, mantém o teto de
evidência por domínio e interrompe quando faltam ferramentas, condições ou
fontes independentes. O artefato NASA PCoE RW3 é recuperado e hashado somente
quando a execução é solicitada; o ZIP e seus scripts não são executados.

- Contratos, gates e resolução real: [`RESEARCH_OS_V3_4.md`](RESEARCH_OS_V3_4.md)
- Histórico de tentativas: [`REAL_GAP_RESOLUTION_V3_4.md`](REAL_GAP_RESOLUTION_V3_4.md)
- Saúde e blockers: [`PROJECT_HEALTH_V3_4.md`](PROJECT_HEALTH_V3_4.md)

## 🔬 5. Research OS 3.5: expansão e concordância de evidências

O milestone 3.5 fecha o blocker operacional de docking de referência em COX-2
murino `1PXX`: Open Babel e AutoDock Vina foram executados em ambiente isolado,
com preparação explícita, três seeds, bundles verificáveis e registro no Ledger.
O resultado permanece E2 computacional. `EvidenceAgreementAssessment` descreve
consistência sem somar níveis de evidência, e `ClaimRevision` preserva o
histórico append-only; dados independentes de solubilidade, observação de
materiais, campos completos de bateria e corpus do usuário continuam gaps
honestos.

- Contratos e limites: [`RESEARCH_OS_V3_5.md`](RESEARCH_OS_V3_5.md)
- Acceptance e expansão de evidência: [`EVIDENCE_EXPANSION_V3_5.md`](EVIDENCE_EXPANSION_V3_5.md)
- Saúde, blockers e auditoria: [`PROJECT_HEALTH_V3_5.md`](PROJECT_HEALTH_V3_5.md)

## 🔬 6. Research OS 3.6: resolução científica cross-domain

O milestone 3.6 introduz decisões científicas persistentes e fail-closed:
critérios explícitos, evidência rastreável, incerteza, OOD e variabilidade de
protocolo permanecem dimensões separadas. Uma decisão não contém score total,
e o comparador não é eleito por seu melhor score isolado. A execução real de
04/09/2026 produziu uma decisão cross-domain legítima de
`NO_DECISION_OUT_OF_DOMAIN`, uma comparação E3 limitada em Cantera e recusas
honestas para materiais e bateria por ausência de registros comparáveis.

- Contratos e regras: [`RESEARCH_OS_V3_6.md`](RESEARCH_OS_V3_6.md)
- Execução e resultados: [`CROSS_DOMAIN_SCIENTIFIC_RESOLUTION_V3_6.md`](CROSS_DOMAIN_SCIENTIFIC_RESOLUTION_V3_6.md)
- Saúde e gates de avanço: [`PROJECT_HEALTH_V3_6.md`](PROJECT_HEALTH_V3_6.md)

## 🔬 7. Research OS 3.7: benchmark sistemático de decisões

O milestone 3.7 testa a fronteira decisória da v3.6 com 61 perguntas fixas,
15 perguntas geradas pelo Codex Live, 8 grupos de paráfrase, 8 pares
bilíngues e testes de ordem, contexto contaminado e pressão adversarial. A
execução final teve 108 casos, zero falhas de invariantes, zero falsos
suportes, zero falsas recusas, 45 `NO_DECISION`, bundles PASS e Ledger PASS.

- Contratos e gate: [`RESEARCH_OS_V3_7.md`](RESEARCH_OS_V3_7.md)
- Relatório completo: [`SCIENTIFIC_DECISION_BENCHMARK_V3_7.md`](SCIENTIFIC_DECISION_BENCHMARK_V3_7.md)
- Saúde e blockers: [`PROJECT_HEALTH_V3_7.md`](PROJECT_HEALTH_V3_7.md)

## 🔬 8. Research OS 3.8: reprodução e stress científico

Após o PASS real da v3.7, a v3.8 reroda os alvos disponíveis e tenta quebrar
selagem, bundles, Ledger, cache, versionamento, OOD, incerteza, unidades,
proveniência, narração e loops autônomos. O resultado final tem 12
reproduções, 30 stress tests aprovados, comparação Python 3.11/3.12 e CI
verde.

- Runner: [`tools/benchmark/reproduction_stress_v38.py`](tools/benchmark/reproduction_stress_v38.py)
- Relatório: [`REPRODUCTION_STRESS_TEST_V3_8.md`](REPRODUCTION_STRESS_TEST_V3_8.md)

## 🔬 9. Research OS 3.9: programas autônomos bounded

O milestone 3.9 transforma campanhas isoladas em `ResearchProgram`s multi-step,
com limites de recursos imutáveis, perguntas geradas a partir dos resultados
anteriores, avaliação qualitativa de utilidade, memória cross-campaign e
detecção anti-spin. Codex Live propõe apenas a estrutura de um programa; runs,
Evidence, bundles, decisões e Ledger continuam sob controle do Research OS.

- Contratos e gate: [`RESEARCH_OS_V3_9.md`](RESEARCH_OS_V3_9.md)
- Execução autônoma: [`AUTONOMOUS_RESEARCH_PROGRAMS_V3_9.md`](AUTONOMOUS_RESEARCH_PROGRAMS_V3_9.md)
- Saúde e blockers: [`PROJECT_HEALTH_V3_9.md`](PROJECT_HEALTH_V3_9.md)

## 🔬 10. Research OS 3.10: memória científica longitudinal

O v3.10 indexa snapshots históricos sobre Ledger, Knowledge, lineage, claims,
runs, fontes, datasets, modelos e engines. Consultas temporais preservam o
estado antigo, identificam versões stale e explicam mudanças de claims e
decisões. Memória conversacional não é fonte científica e não pode sobrepor
registros selados.

- Contratos e gate: [`RESEARCH_OS_V3_10.md`](RESEARCH_OS_V3_10.md)
- Execução temporal: [`LONGITUDINAL_SCIENTIFIC_MEMORY_V3_10.md`](LONGITUDINAL_SCIENTIFIC_MEMORY_V3_10.md)
- Saúde e blockers: [`PROJECT_HEALTH_V3_10.md`](PROJECT_HEALTH_V3_10.md)

## 🔬 11. Research OS 3.11: priorização científica

O v3.11 cria `ResearchPriorityAssessment` e uma `ResearchPriorityQueue` dinâmica
para decidir o próximo passo usando gaps, evidência atual/alvo, resolvabilidade,
redundância, dependências externas, engines, datasets, segurança e escopo. A
fila preserva avaliações antigas quando nova evidência muda a ordem; posição é
apenas ordenação auditável, nunca um score científico universal.

- Contratos e gate: [`RESEARCH_OS_V3_11.md`](RESEARCH_OS_V3_11.md)
- Execução e resultados: [`RESEARCH_PRIORITIZATION_V3_11.md`](RESEARCH_PRIORITIZATION_V3_11.md)
- Saúde e blockers: [`PROJECT_HEALTH_V3_11.md`](PROJECT_HEALTH_V3_11.md)

## 🔬 12. Research OS 3.12: integração de evidência externa

O v3.12 registra `ExternalEvidenceUpdate` e
`EvidenceDependencyAssessment` para integrar fontes versionadas sem sobrescrever
histórico ou contar cinco repetições de um estudo como cinco confirmações
independentes. Cada atualização preserva compatibilidade, conflitos, lineage,
claims, gaps, decisões e prioridades afetados.

- Contratos e gate: [`RESEARCH_OS_V3_12.md`](RESEARCH_OS_V3_12.md)
- Execução e resultados: [`EXTERNAL_EVIDENCE_INTEGRATION_V3_12.md`](EXTERNAL_EVIDENCE_INTEGRATION_V3_12.md)
- Saúde e blockers: [`PROJECT_HEALTH_V3_12.md`](PROJECT_HEALTH_V3_12.md)

## 🔬 13. Research OS 4.0: release de validação científica

O v4.0 é uma validação sistêmica, não uma nova arquitetura. O gate executa
100 casos sistemáticos e 30 perguntas novas do Codex Live, grupos repetidos,
paráfrases e bilíngues, reprodução, stress, auditorias de segurança e
invariantes. O exame autônomo final escolhe um caso respondível, um caso que
deve permanecer `NO_DECISION` e um blocker externo, seguido pelas 20 perguntas
obrigatórias fundamentadas no estado registrado.

- Benchmark: [`tools/benchmark/master_validation_v40.py`](tools/benchmark/master_validation_v40.py)
- Release e critérios: [`RESEARCH_OS_V4_0.md`](RESEARCH_OS_V4_0.md)
- Relatório: [`RESEARCH_OS_V4_VALIDATION_REPORT.md`](RESEARCH_OS_V4_VALIDATION_REPORT.md)
- Invariantes: [`SCIENTIFIC_INVARIANTS_V4_0.md`](SCIENTIFIC_INVARIANTS_V4_0.md)
- Segurança: [`SECURITY_AUDIT_V4_0.md`](SECURITY_AUDIT_V4_0.md)
- Saúde: [`PROJECT_HEALTH_V4_0.md`](PROJECT_HEALTH_V4_0.md)

## 🔬 14. Research OS 4.1: real research deployment

O v4.1 mede impacto científico entre o estado anterior e o posterior de cada
programa, sem score universal e sem elevar EvidenceLevel. A implantação real
executou seis programas, 57 perguntas, dez registros de impacto, análise de
falhas da solubilidade, sensibilidade de protocolo Cantera e auditoria pública
de materiais.

- Release e gate: [`RESEARCH_OS_V4_1.md`](RESEARCH_OS_V4_1.md)
- Execução real: [`REAL_RESEARCH_DEPLOYMENT_V4_1.md`](REAL_RESEARCH_DEPLOYMENT_V4_1.md)
- Saúde: [`PROJECT_HEALTH_V4_1.md`](PROJECT_HEALTH_V4_1.md)

## Research OS v4.2

The v4.2 private-knowledge infrastructure is ready, but the current checkout
has no user corpus: status is `INFRASTRUCTURE_READY_AWAITING_USER_CORPUS`.
Explicit corpus files are hashed into `PrivateSourceRecord`, kept separate from
public sources, extracted only as review-required candidates, and never
automatically verified. See `RESEARCH_OS_V4_2.md` and
`USER_CORPUS_KNOWLEDGE_V4_2.md`.

## Research OS v4.3

The external-validation gate is PASS. Five campaigns were attempted with an
independence audit; the locked solubility model was tested once on the
non-overlapping DLS-100 unique subset and failed unrestricted generalization
while preserving the OOD boundary. Other structural, combustion, battery and
materials paths remain explicitly ineligible or externally blocked.

See `RESEARCH_OS_V4_3.md`, `EXTERNAL_VALIDATION_CAMPAIGNS_V4_3.md`,
`PROJECT_HEALTH_V4_3.md` and `.research-os-live-4.3/external-validation-campaigns.json`.

## Research OS v4.4

The impact review gate is PASS with 13 program reviews from v3.9 onward. The
review keeps knowledge change, decision change, gap refinement, uncertainty,
blocked paths and redundant work as separate dimensions; it does not calculate
a universal impact score.

See `RESEARCH_OS_V4_4.md`, `RESEARCH_OUTCOME_IMPACT_V4_4.md`,
`PROJECT_HEALTH_V4_4.md` and `.research-os-live-4.4/research-impact-review.json`.

## Research OS v4.5

The scientific challenge gate is PASS with 11 red-team targets. Four remain
robust under their declared scope, three were weakened, two require external
validation and two are not testable currently. A false-conservatism audit found
that the bounded Cantera decision was supportable at E3 even though its former
unbounded refusal was not; OOD and missing-condition refusals remain justified.

See `RESEARCH_OS_V4_5.md`, `SCIENTIFIC_CHALLENGE_V4_5.md`,
`PROJECT_HEALTH_V4_5.md` and `.research-os-live-4.5/scientific-challenge.json`.
