# Evidence expansion — Research OS 3.5

O acceptance runner live é
[`tools/resolution/real_resolution_v35.py`](tools/resolution/real_resolution_v35.py).
Sua saída canônica é `v3.5-evidence-expansion.json` dentro da raiz operacional
ignorada; ela inclui discovery, cinco campanhas, resoluções, desafio final,
desafio não resolvível, reprobe de engines/datasets/corpus/network, hashes,
bundles, claim revision e memória cross-campaign.

## Resultado factual

O gate que bloqueava o docking foi fechado. O acceptance encontrou Open Babel
e Vina configurados, preparou o receptor/ligante sem ocultar transformações,
executou três seeds do caso de referência e verificou todos os bundles como
`PASS`. A resolução é `RESOLVED` apenas para a execução computacional; o teto
de evidência é `E2_COMPUTATIONAL`.

O resultado foi registrado com:

```text
EvidenceAgreementAssessment.consistency = PARTIALLY_CONSISTENT
EvidenceAgreementAssessment.strongest_supported_level = E2_COMPUTATIONAL
ClaimRevision.previous_status = INSUFFICIENT_EVIDENCE
ClaimRevision.current_status = SUPPORTED
ClaimRevision.supersedes = CLM-COX2-1PXX-V1
```

A classificação parcialmente consistente é intencional: a identidade
estrutural e o docking concordam dentro do escopo declarado, mas o `HEM` foi
removido da preparação PDBQT por incompatibilidade de conversão e os scores
não são medições de afinidade. Essa limitação não é resolvida por repetição de
seeds.

## Reprobe e desafios

No ambiente usado, RDKit, Cantera, SciPy e PyArrow estavam disponíveis;
Pymatgen, Matminer, PyCalphad e DuckDB permaneceram bloqueados. O skip de
Python 3.11 em `tests/test_v17_engines.py` foi classificado como
`VERSION_SPECIFIC`/`ENVIRONMENTAL`: o teste pula deliberadamente a asserção de
ausência quando Cantera está instalada, enquanto Python 3.12 executa o ramo
correspondente em seu ambiente. Não há bug de lógica a remover.

As campanhas de solubilidade, materiais e bateria conservaram seus resultados
negativos/parciais. A bateria possui observações de tensão, corrente,
temperatura e tempo extraídas do arquivo público, mas não capacidade e
incerteza completas. O segundo challenge não foi executado para não fingir que
um gap claramente sem capacidade configurada era resolvível.

## Auditoria de segurança e integridade

As adaptações de Open Babel e Vina usam argv com `shell=False`; caminhos,
seeds, grid, número de modos e hashes ficam nos manifests. O binário Vina e o
wheel Open Babel permanecem fora do commit. Conteúdo de fontes e qualquer
corpus futuro é tratado como DATA, não como instrução. A checagem final deve
confirmar `git diff --check`, compilação Python, `node --check web/app.js`,
ausência de alterações em `Biolab/` e `formolecular/`, e verificação do
Ledger/bundles.
