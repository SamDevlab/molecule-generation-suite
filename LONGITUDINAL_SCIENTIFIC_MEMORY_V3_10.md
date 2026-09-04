# Longitudinal Scientific Memory — v3.10

## Resultado

O benchmark parte do artefato v3.9 PASS e combina os Ledgers históricos v3.6 e
v3.9 sem reescrever seus bundles. Foram executadas 25 consultas temporais em
dez categorias: claims antes/depois, evidência que alterou claim, evolução de
decisões, versão de fonte/dataset/modelo, disponibilidade de engine, surgimento
de gap, primeiro run de suporte, ausência de run rejeitante, divergência de
reprodução e estado atual versus histórico.

O snapshot preserva o claim AqSolDB real, sua revisão grounded, a decisão de
bateria original e a reavaliação posterior. O dataset AqSolDB, o artefato de
bateria, o modelo de solubilidade e Cantera possuem histórico de versões e
proveniência; versões antigas são explicitamente stale. As constraints de
solubilidade, docking, Cantera, bateria e materiais são reexpostas por um
registro de programa persistente.

## Evidência e limites

O ataque conversacional de falsa validação experimental de celecoxib não
altera a resposta: os registros continuam limitados a docking E2. A ausência
de um primeiro run rejeitante é respondida como ausência registrada, não como
rejeição inventada. Runs selados antigos permanecem byte-a-byte inalterados e
os Ledgers histórico/atual são verificados independentemente.

## Artefato

O JSON contém o snapshot, consultas e seus registros, histórico de claims e
decisões, relações de lineage, contagens, aceitação e estados dos Ledgers. A
liberação só é PASS após CI verde do commit final.
