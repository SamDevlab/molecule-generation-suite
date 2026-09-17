# Autonomous Research Programs — v3.9

## Resultado

O benchmark foi executado no branch `research-os-v1.3` a partir do checkpoint
v3.8 PASS. A execução abriu seis programas, completou 30 perguntas e produziu
29 perguntas derivadas do resultado anterior. Foram realizados três runs
científicos frescos por Labs registrados: AqSolDB com split scaffold e ridge
NumPy, uma execução H2/Cantera e uma análise do artefato NASA PCoE RW3. O
programa proposto pelo Codex foi executado, quando aplicável, somente através
do `MoleculeLab`.

O benchmark registrou 30 avaliações de utilidade: 25 `EXECUTE`, 2
`SKIP_REDUNDANT`, 2 `BLOCKED_EXTERNAL`, 1
`NO_EXPECTED_INFORMATION_GAIN`. Resultados negativos e dependências externas
foram mantidos, e três programas demonstraram a parada `NO_PROGRESS` após duas
iterações sem progresso local.

O `KnowledgeGainAssessment` é qualitativo: a execução registra observações,
claims parciais, gaps parcialmente resolvidos e incertezas restantes, sem
converter conhecimento científico em uma pontuação universal.

## Limitações preservadas

- A predição de solubilidade permanece E1 e sem validação externa independente.
- Cantera permanece simulação E3, não validação experimental.
- O RW3 fornece schema e observações de arquivo real, mas não inventa campos de
  capacidade, resistência ou incerteza.
- Materiais e dependências externas permanecem bloqueados quando o registro
  condição-completo não está disponível.
- Codex Live não é fonte de Evidence, Claims, runs, datasets ou valores
  científicos.

## Artefato e verificação

O relatório JSON canônico contém programas, perguntas, utilidades, memória
cross-campaign, KnowledgeGain, resultados negativos, metadados do provider,
contagens, aceitação e verificação do Ledger. O gate só é PASS quando o CI do
commit final está verde; execuções preliminares com `ci_green=false` não são
apresentadas como release.
