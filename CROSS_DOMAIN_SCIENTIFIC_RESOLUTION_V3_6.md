# Cross-Domain Scientific Resolution — execução v3.6

Data da execução: 04/09/2026 · branch `research-os-v1.3` · commit de entrada
`46248c3a7c2ea3f7e9de6d555a3c1b3024a8ef5a`.

Artefato completo: `.research-os-live-3.6/v3.6-real-decision.json`.
Cada invocação final produz 16 runs novos (o Ledger é append-only e preserva
as tentativas anteriores); na última verificação, todos os bundles e o Ledger
acumulado estavam `PASS`.

## Decisões registradas

| ID | Pergunta | Resultado | Limite principal |
|---|---|---|---|
| `DECISION-REAL-01-*` | separação de diclofenaco vs celecoxibe sob protocolo idêntico | `SUPPORTED_DECISION` | guard baseado em três réplicas; não é afinidade medida |
| `DECISION-REAL-02-*` | diclofenaco vs celecoxibe com molécula, solubilidade/OOD/incerteza e docking | `NO_DECISION_OUT_OF_DOMAIN` | ambos fora do domínio de aplicabilidade do modelo de solubilidade |
| `DECISION-REAL-03-*` | a incerteza domina a diferença nominal de solubilidade? | `SUPPORTED_DECISION` (recusa) | raio residual somado excede a diferença nominal |
| `DECISION-REAL-04-*` | H2 vs CH4 no mesmo protocolo Cantera | `SUPPORTED_DECISION` | E3 de equilíbrio HP em `gri30.yaml`; não é temperatura de falha |
| `DECISION-REAL-05-*` | combustão→Fourier→materiais | `NO_DECISION_INSUFFICIENT_EVIDENCE` | não há observação de material condition-complete |
| `DECISION-REAL-06-*` | decisão de degradação de bateria | `NO_DECISION_INSUFFICIENT_EVIDENCE` | faltam capacidade/incerteza e segunda fonte comparável |

IDs completos variam se o runner for repetido; a fonte de verdade é o JSON e o
`decisions.sqlite` do mesmo diretório.

## Campanha molécula → solubilidade → docking

Os dois candidatos reais foram identificados pelos registros oficiais do
[PubChem CID 3033 (diclofenac)](https://pubchem.ncbi.nlm.nih.gov/compound/3033)
e [PubChem CID 2662 (celecoxib)](https://pubchem.ncbi.nlm.nih.gov/compound/2662).
O runner recuperou o SMILES canônico e um SDF 3D, preservando hashes de cada
artefato; nenhuma molécula nova foi gerada.

O baseline treinou no sample experimental de 46 registros AqSolDB-G com split
scaffold, Morgan radius 2/2048 e ridge NumPy. As duas previsões foram mantidas
como `OUT_OF_DOMAIN`:

| candidato | previsão logS | incerteza (raio) | OOD score | rankable |
|---|---:|---:|---:|---|
| diclofenaco | −3,097148 | 2,204685 | 0,736842 | não |
| celecoxibe | −3,977259 | 2,204685 | 0,812500 | não |

A diferença nominal de 0,880111 logS é menor que a incerteza residual
calibrada; portanto não foi convertida em seleção.

## Comparação COX-2

O alvo foi o receptor murino PTGS2/COX-2 da estrutura [RCSB PDB
1PXX](https://www.rcsb.org/structure/1PXX), cadeia A, com a mesma preparação
de receptor, mesma caixa derivada do complexo, Open Babel e AutoDock Vina
v1.2.7. O protocolo foi `autodock-vina.v36.cox2.1pxx.same-grid.v1`,
exhaustiveness 4, CPU 2, 9 modos e seeds 42/43/44.

| ligante | três scores kcal/mol | média | desvio populacional | faixa |
|---|---|---:|---:|---:|
| diclofenaco | −8,364; −8,368; −8,388 | −8,373333 | 0,010499 | 0,024 |
| celecoxibe | −9,533; −9,515; −9,521 | −9,523000 | 0,007483 | 0,018 |

A diferença entre médias foi 1,149667 kcal/mol e o guard retornou
`CLEARLY_SEPARATED_UNDER_PROTOCOL`. Isso é uma separação sob o protocolo,
não significância estatística nem afinidade medida. O resultado não anulou os
gates OOD/uncertainty, logo a decisão cross-domain recusou escolher.

## Combustão, térmica e materiais

H2 e CH4 foram executados em Cantera nas mesmas condições: 300 K, 101325 Pa,
φ=1, oxidante `O2:0.21,N2:0.79`, mecanismo `gri30.yaml`. A comparação E3 foi
limitada ao valor calculado de equilíbrio HP. A temperatura de Cantera foi
registrada como condição/resultado do modelo, nunca como temperatura de falha.

O `ThermalLab` foi então chamado com o modelo explícito de Fourier 1-D,
estacionário, planar, k constante, sem convecção, radiação, resistência de
contato, transiente ou geração interna. O gate parou em `conductivity_w_mk` e
`thickness_m` ausentes. Como nenhum registro condition-complete de material foi
recuperado, o resultado correto foi `NO_DECISION_INSUFFICIENT_EVIDENCE`.

## Bateria e E3↔E4

O arquivo NASA PCoE RW3 foi hasheado e seus campos observados foram limitados a
tempo, tensão, corrente e temperatura. Capacidade, resistência e incerteza
permaneceram desconhecidas; scripts do arquivo não foram executados. A busca
no [DOE Battery Data Hub](https://batterydata.energy.gov/) não produziu um
segundo artefato experimental condition-comparable nesta execução, então a
`BatteryProtocolComparability` ficou `UNKNOWN` e a decisão foi recusada.

`SimulationExperimentComparison` foi registrado com os IDs E3 de Cantera e
sem IDs experimentais, `condition_match=UNKNOWN` e status
`INSUFFICIENT_METADATA`; não houve calibração in-place.

## Plano mínimo e fronteira Live Codex

O plano mínimo suficiente contém apenas identidade/propriedades moleculares,
baseline real de solubilidade com OOD/uncertainty e docking com variabilidade.
Combustão, térmica/materiais, bateria e síntese de fontes ficaram opcionais ou
foram gates de resolução; pedidos de score universal, eficácia clínica e
aprovação de material foram rejeitados. Live Codex foi usado para descoberta e
para o problema novo, mas `provider_created_scientific_evidence=false`.
