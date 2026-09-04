# External Evidence Integration — v3.12

## Resultado

Foram registradas 21 atualizações: cinco buscas reais bloqueadas por
incompatibilidade ou falta de ingestão verificável, uma integração de evidência
real já versionada do NASA PCoE RW3 e 15 fixtures controladas. Os fixtures
exercitam compatibilidade, conflito, duplicata, dependência, versão stale,
unidades incompatíveis, metadata ausente, supersession de fonte, revisão de
claim, revisão de decisão e revisão de prioridade.

A dependência compartilhada de fonte/dataset/modelo/run é marcada como
`DEPENDENT`; ela não é contada como confirmação independente. Conflitos são
preservados. As revisões apontam para evidência e predecessores, enquanto os
bundles v3.6/v3.9 permanecem byte-a-byte inalterados.

## Busca pública e limites

Foram avaliadas rotas públicas de dataset de solubilidade, bateria, materiais e
propriedades termofísicas. A rota de solubilidade independente não é compatível
com a avaliação congelada por domínio/unidade; as rotas de bateria e materiais
não foram promovidas sem ingestão, hash e schema/condições completos; a rota
termofísica não fornece experimento E4 compatível com o protocolo Cantera.

Assim, o benchmark não declara nova descoberta experimental. O caso real
integrado é a evidência RW3 já registrada na versão v3.9, usada para validar o
fluxo de update/impact sem falsear independência.

## Artefato

O JSON contém buscas, updates, dependências, revisões, guards de nível,
hashes históricos, contagens e aceitação. `ci_green` é obrigatório para PASS.
