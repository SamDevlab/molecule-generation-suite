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
