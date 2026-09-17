# Research OS 3.5 — expansão de evidências

Milestone executado na branch `research-os-v1.3`, a partir do checkpoint
3.4 (`940330d`). O objetivo foi resolver um blocker operacional real e
consolidar a memória entre campanhas sem transformar uma simulação em
validação experimental.

## Gate que abriu

O alvo é `PTGS2 / COX-2`, `Mus musculus`, estrutura RCSB `1PXX`. O registro
RCSB identifica uma estrutura de difração de raios X a 2,90 Å, com quatro
cadeias de 604 resíduos, diclofenac (`DIF`) co-cristalizado e um componente
`HEM`. Fonte primária: [RCSB 1PXX](https://www.rcsb.org/structure/1PXX).

Open Babel `3.1.1.23` (`obabel` reportando 3.1.0) e AutoDock Vina `1.2.7`
foram executados dentro do ambiente isolado do projeto. As referências de
instalação e uso são a [documentação oficial do Open Babel](https://openbabel.org/docs/Installation/install.html)
e a [documentação oficial de instalação do Vina](https://autodock-vina.readthedocs.io/en/latest/installation.html).
O binário Vina não foi empacotado no repositório; seu SHA-256 e o SHA-256 do
executável Open Babel ficam no acceptance manifest local.

O receptor foi reduzido explicitamente à cadeia `A`; `DIF`, `BOG`, `NAG`,
`HOH` e `HEM` não foram tratados como receptor. A conversão do componente
contendo Fe para PDBQT foi incompatível com o conversor utilizado, portanto
`HEM` foi registrado como removido, não inferido como ausente. Ligante e
receptor receberam hidrogênios e cargas parciais Gasteiger conforme as opções
registradas nos manifests. O grid foi derivado dos átomos do `DIF` da cadeia A,
com 8 Å de padding:

```text
center = (27.1155, 24.0900, 14.9360) Å
size   = (21.4270, 22.6640, 22.5330) Å
```

O protocolo foi `autodock-vina.docking.v1`, exhaustiveness 4, CPU 2,
`num_modes=9`, seeds 42, 43 e 44. Os melhores scores foram `-8.372`,
`-8.362` e `-8.329 kcal/mol`; o desvio-padrão registrado foi
`0.0183726850 kcal/mol`. Cada replicate tem output PDBQT próprio, hashes de
entrada/saída, manifest selado e bundle verificado no Ledger.

## Contratos novos

- `EvidenceAgreementAssessment` classifica a relação entre evidências como
  consistente, parcialmente consistente, conflitante ou não comparável. Ele
  registra o nível mais alto efetivamente sustentado; nunca soma níveis.
- `ClaimRevision` preserva a versão anterior, status anterior, evidências
  anteriores, motivo, limitações e linhagem. A revisão é append-only.
- `ScientificClaim` aceita `supersedes` e `derived_from`, sem alterar claims
  selados existentes.

O claim revisado sobre 1PXX é `SUPPORTED` somente no nível
`E2_COMPUTATIONAL`: trata-se de uma afirmação sobre a execução computacional
reproduzida sob o protocolo declarado, não sobre afinidade medida, eficácia,
segurança, terapêutica ou resultado clínico.

## Gaps que continuam abertos

- O artefato AqSolDB disponível continua na mesma linhagem do treino e não foi
  aceito como teste externo independente; nenhum split falso, calibração
  silenciosa ou promoção de modelo foi criado.
- As fontes de materiais não produziram observação de nível de registro com
  composição, processamento, microestrutura e condições completas.
- O NASA PCoE RW3 foi hashado e seus campos medidos foram resumidos, mas a
  análise ainda não tem campos completos de capacidade e incerteza; não foi
  ajustado um modelo de degradação.
- A pasta de conhecimento não contém corpus do usuário; o estado é
  `AWAITING_USER_CORPUS`.

O segundo desafio não resolvível foi registrado como
`NOT_ATTEMPTED_BY_DESIGN`, com o bloqueio preservado. O Codex Live atuou
somente como seleção, planejamento e narração estruturada; não criou
Evidence, runs, bundles, condições ou claims científicos.
