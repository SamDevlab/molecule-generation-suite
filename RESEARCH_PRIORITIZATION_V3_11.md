# Research Prioritization — v3.11

## Resultado

Foram executadas 20 perguntas de priorização sobre oito candidatos reais e
seus gaps registrados. A busca de dataset externo de solubilidade ficou em
`PRIORITIZE_NOW`: é acionável como busca/validação e poderia alterar uma
decisão, mas não autoriza fabricar dataset ou resultado. O dataset de bateria
ficou `BLOCKED` na avaliação inicial e `SECONDARY` após a observação real do
schema, preservando ambas as versões.

As repetições idênticas de docking e RDKit ficaram `LOW_INFORMATION_GAIN`; a
comparação de materiais sem registros condição-completos ficou `UNSAFE`; o
corpus do usuário ficou `DEFER` por depender de corpus e permissões. O Codex
Live recebeu as opções A–D para reavaliação, mas não pôde criar evidência,
alterar a fila ou ultrapassar gates científicos/safety.

## Limites preservados

Prioridade não aumenta níveis de evidência: solubilidade externa continua
ausente, docking continua E2, Cantera continua E3, bateria continua com
metadados faltantes e materiais continuam sem observação condição-completa.
Uma fila ordena trabalho; não escolhe um vencedor científico nem converte
interesse em validade.

## Artefato

O JSON contém fila inicial e final, avaliações atuais e históricas, razões de
ordenação, 20 respostas, metadados Codex Live e aceitação. O release só é PASS
quando o CI do commit final está verde.
