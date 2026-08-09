import pandas as pd
import os
import glob
import gc

PASTA_TEMP = "lotes_farmacia_temp"
ARQUIVO_BASE = "BASE_ORACULO_FARMACIA.csv"
ARQUIVO_FINAL = "BASE_ORACULO_FARMACIA_FINAL.csv"

def executar_grande_fusao():
    print("\n" + "="*85)
    print(" 🛠️ A GRANDE FUSÃO: UNINDO 3 MILHÕES DE FÁRMACOS NA MEMÓRIA RAM")
    print("="*85)
    
    # 1. Lendo a base inicial
    print(f"[📂] Carregando a base original '{ARQUIVO_BASE}'...")
    try:
        df_base = pd.read_csv(ARQUIVO_BASE, low_memory=False)
        print(f"    -> Base original carregada: {len(df_base)} compostos.")
    except Exception as e:
        print(f"[❌] Erro ao ler a base original: {e}")
        return

    # 2. Lendo os 44 lotes gerados
    arquivos_lotes = glob.glob(os.path.join(PASTA_TEMP, "*.csv"))
    if not arquivos_lotes:
        print(f"[ℹ️] Nenhum lote encontrado na pasta '{PASTA_TEMP}'.")
        return
        
    print(f"\n[📦] Encontrados {len(arquivos_lotes)} lotes temporários. Carregando...")
    lista_dfs = [df_base]
    
    for lote in arquivos_lotes:
        try:
            df_temp = pd.read_csv(lote, low_memory=False)
            lista_dfs.append(df_temp)
        except Exception as e:
            print(f"    [!] Erro ao ler o lote {lote}: {e}")

    # 3. Concatenando tudo de uma vez só na RAM
    print("\n[🧠] Fundindo todos os dados na memória do computador...")
    df_super = pd.concat(lista_dfs, ignore_index=True)
    
    # Limpando a RAM velha
    del lista_dfs
    del df_base
    gc.collect()

    print(f"    -> Total na memória: {len(df_super)} compostos farmacêuticos!")

    # 4. Salvando em um ARQUIVO NOVO (Bypassa o bloqueio do Windows)
    print(f"\n[💾] Salvando o Titã Farmacêutico no novo arquivo: '{ARQUIVO_FINAL}'...")
    try:
        df_super.to_csv(ARQUIVO_FINAL, index=False, encoding='utf-8')
        print("    -> Salvamento concluído com sucesso!")
        
        # 5. Limpeza da pasta temporária
        print("\n[🧹] Limpando os lotes temporários...")
        for lote in arquivos_lotes:
            os.remove(lote)
        print("    -> Pasta temporária limpa.")
        
        print("\n" + "="*85)
        print(f" 🎉 VITÓRIA! O SEU BANCO DE 3 MILHÕES ESTÁ PRONTO EM: {ARQUIVO_FINAL}")
        print("="*85)
        
    except Exception as e:
        print(f"\n[❌] Erro Crítico ao salvar o arquivo final: {e}")
        print("Tente pausar o OneDrive e rode este script novamente.")

if __name__ == "__main__":
    executar_grande_fusao()