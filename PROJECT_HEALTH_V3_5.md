# Project health — Research OS 3.5

Branch de trabalho: `research-os-v1.3`. `main` não participa do milestone.
O ponto de partida foi o checkpoint 3.4 em `940330d`.

## Estado por área

| Área | Estado | Limite honesto |
|---|---|---|
| RDKit | AVAILABLE | biblioteca determinística; não é experimento |
| Cantera | AVAILABLE | física computacional, não validação de hardware |
| Open Babel | AVAILABLE / EXECUTED | preparação explícita; `HEM` removido por incompatibilidade Fe/PDBQT |
| AutoDock Vina | AVAILABLE / EXECUTED | score computacional E2; não é afinidade medida |
| Pymatgen / Matminer / PyCalphad | BLOCKED | dependências não instaladas/configuradas |
| Solubilidade | NOT ELIGIBLE AS EXTERNAL TEST | AqSolDB disponível não é independente da linhagem de treino |
| Materiais | UNRESOLVED | nenhum registro com condições completas |
| Bateria | PARTIALLY RESOLVED | faltam capacidade e incerteza no schema parseado |
| Corpus do usuário | AWAITING_USER_CORPUS | nenhum arquivo fornecido na pasta de conhecimento |

## Skip audit

Python 3.11 reportou `157 passed, 1 skipped`; Python 3.12 reportou `158
passed`. O skip ocorre porque Cantera está instalado no host 3.11 e o teste é
condicional à ausência dessa dependência. A classificação é
`VERSION_SPECIFIC`/`ENVIRONMENTAL`, não `BUG` nem `TEST_LOGIC_ERROR`.

## Docking real

O caso `1PXX` usou receptor de `Mus musculus`, cadeia A, ligante DIF
co-cristalizado, grid derivado das coordenadas do co-cristal e três seeds
independentes. Os scores registrados foram `-8.372`, `-8.362` e `-8.329
kcal/mol`, com desvio-padrão `0.0183726850`. Todos os bundles de runs passaram
manifest, hash, engine, artefato, step, dataset, FIRST_LOSS e seal gates.

## Regras de parada

Não houve elevação de evidência por concordância, soma de níveis, preenchimento
de campos ausentes, calibração silenciosa, execução de scripts de arquivo
baixado ou inferência humana/clínica. O relatório operacional
`v3.5-evidence-expansion.json` é a fonte de conferência dos IDs e hashes da
execução live.
