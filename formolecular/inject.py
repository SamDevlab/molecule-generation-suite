import pandas as pd
import os
import sys
import time
from rdkit import Chem
from rdkit.Chem import Descriptors
import warnings
from rdkit import RDLogger

# Silenciar RDKit
RDLogger.DisableLog('rdApp.*') 
warnings.filterwarnings('ignore')

ARQUIVO_ORIGINAL = "BASE_ORACULO_FARMACIA_FINAL.csv"
ARQUIVO_ATUALIZADO = "BASE_ORACULO_FARMACIA_ADMET.csv"

def extrair_parametros_admet(smiles_list):
    """Calcula os parâmetros vitais do SwissADME para um lote de moléculas"""
    resultados = []
    for smiles in smiles_list:
        try:
            mol = Chem.MolFromSmiles(str(smiles))
            if mol:
                resultados.append({
                    'ADMET_FractionCSP3': round(Descriptors.FractionCSP3(mol), 3),
                    'ADMET_RotatableBonds': Descriptors.NumRotatableBonds(mol),
                    'ADMET_AromaticRings': Descriptors.NumAromaticRings(mol),
                    'ADMET_HDonors': Descriptors.NumHDonors(mol),
                    'ADMET_HAcceptors': Descriptors.NumHAcceptors(mol)
                })
            else:
                raise ValueError
        except:
            # Em caso de falha química, preenche com zeros (segurança)
            resultados.append({
                'ADMET_FractionCSP3': 0.0,
                'ADMET_RotatableBonds': 0,
                'ADMET_AromaticRings': 0,
                'ADMET_HDonors': 0,
                'ADMET_HAcceptors': 0
            })
    return pd.DataFrame(resultados)

def forjar_banco_admet():
    print("\n" + "="*85)
    print(" 🔬 ATUALIZAÇÃO ADMET: INJETANDO PARÂMETROS SWISS-ADME NOS 3 MILHÕES")
    print("="*85)
    
    if not os.path.exists(ARQUIVO_ORIGINAL):
        print(f"[!] Erro: Arquivo '{ARQUIVO_ORIGINAL}' não encontrado.")
        return

    # Garante que começa limpo
    if os.path.exists(ARQUIVO_ATUALIZADO):
        print(f"[!] O ficheiro '{ARQUIVO_ATUALIZADO}' já existe. Apagando versão antiga...")
        os.remove(ARQUIVO_ATUALIZADO)

    chunk_size = 50000
    total_processado = 0
    primeiro_bloco = True

    print("[⚙️] Iniciando motor de extração termodinâmica e espacial...\n")
    start_time = time.time()

    # Leitura em lotes para proteger a RAM do computador
    for chunk in pd.read_csv(ARQUIVO_ORIGINAL, chunksize=chunk_size, low_memory=False):
        
        # O Motor RDKit calcula os novos parâmetros para o lote
        df_admet = extrair_parametros_admet(chunk['SMILES'].tolist())
        
        # Funde as novas colunas ADMET com o lote original
        # O reset_index garante que as linhas casem perfeitamente
        chunk = chunk.reset_index(drop=True)
        df_admet = df_admet.reset_index(drop=True)
        chunk_atualizado = pd.concat([chunk, df_admet], axis=1)

        # Salva no novo ficheiro
        chunk_atualizado.to_csv(ARQUIVO_ATUALIZADO, mode='a', index=False, header=primeiro_bloco, encoding='utf-8')
        primeiro_bloco = False
        
        total_processado += len(chunk)
        sys.stdout.write(f"\r    -> Upgrade Concluído: {total_processado} moléculas enriquecidas...")
        sys.stdout.flush()

    tempo_total = round((time.time() - start_time) / 60, 1)
    
    print("\n\n" + "="*85)
    print(f" 🎉 ATUALIZAÇÃO CLÍNICA CONCLUÍDA EM {tempo_total} MINUTOS! ")
    print("="*85)
    print(" Os parâmetros SwissADME (FractionCsp3, H-Donors, etc) foram injetados com sucesso.")
    print(f" 🏆 Novo Super Banco de Dados criado: {ARQUIVO_ATUALIZADO}")
    
    # Mostrando um "Gostinho" do resultado
    print("\n📋 PRÉVIA DA NOVA ELITE (Primeiras 3 linhas):")
    df_previa = pd.read_csv(ARQUIVO_ATUALIZADO, nrows=3)
    colunas_mostrar = ['SMILES', 'Score_QED', 'ADMET_FractionCSP3', 'ADMET_RotatableBonds', 'ADMET_AromaticRings']
    print(df_previa[colunas_mostrar].to_string(index=False))

if __name__ == "__main__":
    forjar_banco_admet()