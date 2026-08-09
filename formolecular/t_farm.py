import pandas as pd
import numpy as np
import os
import gc
import sys

ARQUIVO_ORIGINAL = "csv/universo_utilidade_filtrada.csv"
ARQUIVO_ORACULO_PHARMA = "BASE_ORACULO_FARMACIA.csv"

def forjar_base_farmaceutica():
    print("\n" + "="*85)
    print(" 💊 INICIANDO A FORJA DO ORÁCULO FARMACÊUTICO (LEITURA EM BLOCOS)")
    print("="*85)
    
    if not os.path.exists(ARQUIVO_ORIGINAL):
        print(f"[!] Erro: Arquivo '{ARQUIVO_ORIGINAL}' não encontrado.")
        return

    # Categorias que são "lixo" para o corpo humano (Tóxicos, Explosivos, Plásticos)
    RESIDUOS_PARA_REMOVER = ['Energia/Aeroespacial', 'Química de Materiais', 'Agroquímicos/Fertilizantes']
    
    if os.path.exists(ARQUIVO_ORACULO_PHARMA):
        os.remove(ARQUIVO_ORACULO_PHARMA)

    chunk_size = 50000
    total_linhas_processadas = 0
    total_moleculas_salvas = 0
    primeiro_bloco = True

    print("[🧠] Varrendo 2.7 Milhões de moléculas, expurgando toxinas e injetando métricas biológicas...\n")

    for chunk in pd.read_csv(ARQUIVO_ORIGINAL, chunksize=chunk_size, low_memory=False):
        chunk.columns = chunk.columns.str.strip()
        
        # Garante que os números são números
        chunk['Peso_Molar'] = pd.to_numeric(chunk['Peso_Molar'], errors='coerce')
        chunk['LogP'] = pd.to_numeric(chunk['LogP'], errors='coerce').fillna(0)
        chunk['Score_QED'] = pd.to_numeric(chunk['Score_QED'], errors='coerce').fillna(0)
        
        # 1. O EXPURGO: Remover categorias tóxicas
        if 'Categoria' in chunk.columns:
            chunk = chunk[~chunk['Categoria'].isin(RESIDUOS_PARA_REMOVER)]
            
        # Filtro de Sanidade Biológica: Ninguém toma um comprimido de 1000g/mol
        chunk = chunk[(chunk['Peso_Molar'] > 100) & (chunk['Peso_Molar'] < 800)]
        
        if len(chunk) > 0:
            # =================================================================
            # 2. A REPOSIÇÃO: INJETANDO ATRIBUTOS DE DRUG DISCOVERY
            # =================================================================
            
            # A) Aprovação na Regra dos 5 de Lipinski (1 = Aprovado, 0 = Reprovado)
            # Regras: Peso < 500 e LogP (Lipofilicidade) < 5
            chunk['PHARMA_Lipinski_Pass'] = np.where(
                (chunk['Peso_Molar'] <= 500) & (chunk['LogP'] <= 5.0), 
                1, 0
            )
            
            # B) Contagem de Átomos Vitais para Fármacos usando SMILES
            # Oxigênio e Nitrogênio formam pontes de hidrogênio com proteínas do corpo
            if 'SMILES' in chunk.columns:
                chunk['PHARMA_Qtd_O'] = chunk['SMILES'].astype(str).str.count('O|o')
                chunk['PHARMA_Qtd_N'] = chunk['SMILES'].astype(str).str.count('N|n')
                # Flúor é muito usado em farmácia para evitar que o fígado destrua o remédio rápido demais
                chunk['PHARMA_Qtd_F'] = chunk['SMILES'].astype(str).str.count('F|f')
            
            # Forçar a nova categoria limpa
            chunk['Categoria'] = 'Candidato_Farmaceutico'

            # 3. SALVAR O BLOCO
            chunk.to_csv(ARQUIVO_ORACULO_PHARMA, mode='a', index=False, header=primeiro_bloco)
            primeiro_bloco = False
            total_moleculas_salvas += len(chunk)

        total_linhas_processadas += chunk_size
        sys.stdout.write(f"\r    -> Processado: {total_linhas_processadas} | Salvos para o Oráculo: {total_moleculas_salvas}")
        sys.stdout.flush()

        del chunk
        gc.collect()

    print("\n\n" + "="*85)
    print(" 🎉 BASE DO ORÁCULO FARMACÊUTICO FORJADA COM SUCESSO! ")
    print("="*85)
    print(f" 🗑️  Explosivos e toxinas eliminados com sucesso.")
    print(f" 💊 Total de moléculas biocompatíveis restando: {total_moleculas_salvas}")
    print(f" 🏆 Arquivo pronto: {ARQUIVO_ORACULO_PHARMA}")

if __name__ == "__main__":
    forjar_base_farmaceutica()