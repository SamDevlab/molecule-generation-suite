import os
import sys
import json
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import multiprocessing
import shutil
from datetime import datetime
from joblib import Parallel, delayed
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem import Descriptors
from rdkit import RDLogger
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score

# Desativa os avisos do RDKit para não poluir o terminal
RDLogger.DisableLog('rdApp.*')

PASTA_MODELOS = "modelos_ia"
PASTA_EXPORTACAO = "csv_elite_aero"
CAMINHO_CSV = "BASE_ORACULO_AEROESPACIAL.csv"
METADADOS_PATH = os.path.join(PASTA_MODELOS, "metadados_aero.json")

os.makedirs(PASTA_MODELOS, exist_ok=True)
os.makedirs(PASTA_EXPORTACAO, exist_ok=True)
NUM_CORES = multiprocessing.cpu_count()

# ==========================================================================
# 1. FUNÇÕES AUXILIARES E MULTIPROCESSAMENTO
# ==========================================================================

def _gerar_fp_unico(args):
    """Gera a assinatura química da molécula (Fingerprint) para o XGBoost entender"""
    idx, smiles = args
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol:
            fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
            arr = np.zeros((1,))
            Chem.DataStructs.ConvertToNumpyArray(fp, arr)
            return idx, arr
    except:
        pass
    return None

def smiles_para_fingerprint(smiles_series):
    """Distribui a geração de assinaturas por todos os núcleos do CPU"""
    resultados = Parallel(n_jobs=-1, batch_size="auto")(
        delayed(_gerar_fp_unico)(item) for item in enumerate(smiles_series)
    )
    
    fps = []
    indices_validos = []
    for res in resultados:
        if res is not None:
            indices_validos.append(res[0])
            fps.append(res[1])
            
    return np.array(fps), indices_validos

def carregar_metadados():
    if os.path.exists(METADADOS_PATH):
        with open(METADADOS_PATH, 'r') as f:
            return json.load(f)
    return {"tamanho_ultimo_treino": 0, "r2_isp": 0.0, "complexidade_modelo": 200}

def salvar_metadados(tamanho, r2_isp, n_estimators):
    metadados = {
        "tamanho_ultimo_treino": int(tamanho),
        "r2_isp": float(r2_isp),
        "complexidade_modelo": int(n_estimators)
    }
    with open(METADADOS_PATH, 'w') as f:
        json.dump(metadados, f, indent=4)

# ==========================================================================
# 2. MOTOR DE TREINAMENTO NEURAL (FOCO ÚNICO: PROPULSÃO)
# ==========================================================================
def treinar_oraculo_aeroespacial():
    print("\n" + "="*85)
    print(" [⏳] CARREGANDO O BIG DATA AEROESPACIAL PARA A MATRIZ NEURAL... ")
    print("="*85)
    
    if not os.path.exists(CAMINHO_CSV):
        print(f"[!] Erro: Arquivo '{CAMINHO_CSV}' não encontrado.")
        return

    # Lê apenas as colunas necessárias para economizar RAM durante o treino
    print("[📂] Lendo a biblioteca de combustíveis (Isto pode levar alguns segundos)...")
    colunas_necessarias = ['SMILES', 'AERO_Impulso_Espec_Teorico']
    df = pd.read_csv(CAMINHO_CSV, usecols=colunas_necessarias, low_memory=False)
    
    # Limpeza rápida
    df = df.dropna(subset=colunas_necessarias).copy()
    df['AERO_Impulso_Espec_Teorico'] = pd.to_numeric(df['AERO_Impulso_Espec_Teorico'], errors='coerce')
    df = df.dropna()

    tamanho_atual = len(df)
    metadados = carregar_metadados()
    tamanho_anterior = metadados.get("tamanho_ultimo_treino", 0)
    n_estimators = metadados.get("complexidade_modelo", 200)
    
    print(f" -> Volume de dados disponível: {tamanho_atual} moléculas puras.")
    
    if tamanho_atual >= (tamanho_anterior * 1.5) and tamanho_anterior > 0:
        print("\n[🚀 AUTO-UPGRADE DETECTADO: O seu banco de dados cresceu enormemente!]")
        n_estimators += 50
    
    # Amostragem estratégica: Para treinar sem explodir a RAM, pegamos as 150.000 moléculas mais variadas
    tamanho_treino = min(150000, tamanho_atual)
    df_treino = df.sample(n=tamanho_treino, random_state=42)
    
    print(f"\n[🔥] Extraindo Fingerprints de {tamanho_treino} moléculas para ensino da IA...")
    X, idx = smiles_para_fingerprint(df_treino["SMILES"])
    y = df_treino["AERO_Impulso_Espec_Teorico"].iloc[idx].values
    
    print(f"[{NUM_CORES} NÚCLEOS] O XGBoost está estudando a física de foguetes...")
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Regressor focado em adivinhar o valor exato do Impulso Específico
    modelo_isp = xgb.XGBRegressor(n_estimators=n_estimators, max_depth=8, learning_rate=0.05, n_jobs=-1, random_state=42)
    modelo_isp.fit(X_tr, y_tr)
    
    r2_isp = r2_score(y_te, modelo_isp.predict(X_te))
    
    caminho_modelo = os.path.join(PASTA_MODELOS, "oraculo_aero_isp.pkl")
    joblib.dump(modelo_isp, caminho_modelo)
    salvar_metadados(tamanho_atual, r2_isp, n_estimators)
    
    print("\n ✨ ORÁCULO AEROESPACIAL TREINADO E COMPILADO COM SUCESSO! ")
    print(f" -> Precisão (R²): {r2_isp * 100:.2f}% de acerto na previsão termodinâmica.")

# ==========================================================================
# 3. TRIAGEM DE ALTA PERFORMANCE (CAÇADOR DE ELITE)
# ==========================================================================
def rodar_triagem_automatica():
    caminho_modelo = os.path.join(PASTA_MODELOS, "oraculo_aero_isp.pkl")
    if not os.path.exists(caminho_modelo):
        print("\n[!] Erro: Treine o Oráculo Aeroespacial (Opção 1) primeiro.")
        return
        
    print("\n" + "="*85)
    print(f" 🎛️  RADAR DE PROPULSÃO TURBO ATIVADO ({NUM_CORES} NÚCLEOS) ")
    print("="*85)
    
    limite_input = input("\n -> Quantos combustíveis de elite deseja extrair? [Padrão: 100]: ").strip()
    limite_podio = int(limite_input) if limite_input.isdigit() else 100
    
    print("[🧠] Carregando a Mente Neural Aeroespacial do disco...")
    modelo_isp = joblib.load(caminho_modelo)

    print("\n[📂] Minerando o Big Data em Blocos (Avaliando Milhões sem travar a RAM)...")
    
    top_elite = pd.DataFrame()
    total_processado = 0
    
    # Processa de 100 mil em 100 mil linhas
    for chunk in pd.read_csv(CAMINHO_CSV, chunksize=100000, low_memory=False):
        chunk = chunk.dropna(subset=["SMILES"]).copy()
        if chunk.empty: continue
        
        # Gera a assinatura da molécula
        X_chunk, idx_validos = smiles_para_fingerprint(chunk["SMILES"])
        chunk_valido = chunk.iloc[idx_validos].copy()
        if chunk_valido.empty: continue
            
        # A IA prevê o Impulso Específico sem precisar calcular fórmulas
        chunk_valido["IA_Pred_ISP_Teorico"] = modelo_isp.predict(X_chunk)
        
        # Filtramos as moléculas mais eficientes deste bloco
        cand_elite = chunk_valido.nlargest(limite_podio, "IA_Pred_ISP_Teorico")
        
        # Atualiza o ranking global
        top_elite = pd.concat([top_elite, cand_elite]).sort_values(by="IA_Pred_ISP_Teorico", ascending=False).head(limite_podio)
        
        total_processado += len(chunk)
        sys.stdout.write(f"\r     -> Escaneado: {total_processado} estruturas processadas...")
        sys.stdout.flush()
        
    print("\n\n" + "="*85)
    print(f" 🎉 VARREDURA CONCLUÍDA! O TOP {limite_podio} DA ENGENHARIA AEROESPACIAL: ")
    print("="*85)

    for _, r in top_elite.head(10).iterrows(): 
        print(f"   🚀 ID: {r.get('ID', 'N/A')} | ISP Previsto: {r['IA_Pred_ISP_Teorico']:.4f} | SMILES: {r['SMILES'][:40]}...")

    # =====================================================================
    # 💾 EXPORTAÇÃO DO RANKING
    # =====================================================================
    nome_arq = "RANKING_COMBUSTIVEIS_ELITE.csv"
    caminho_producao = os.path.join(PASTA_EXPORTACAO, nome_arq)
    
    # Backup da última rodada
    if os.path.exists(caminho_producao):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(caminho_producao, os.path.join(PASTA_EXPORTACAO, f"BKP_{timestamp}_{nome_arq}"))
        
    top_elite.to_csv(caminho_producao, index=False, encoding="utf-8")
            
    print(f"\n" + "-"*60)
    print(f" 💾 PLANILHA FINAL EXPORTADA COM SUCESSO PARA: '{caminho_producao}'")
    print("="*85)

# ==========================================================================
# 4. MICRO MENU NO PROMPT
# ==========================================================================
def painel_controle_principal():
    while True:
        metadados = carregar_metadados()
        r2_isp = metadados.get("r2_isp", 0.0)
        
        print("\n" + "═"*70)
        print(f"    🚀 CONSOLE DO ORÁCULO AEROESPACIAL (XGBOOST V6.0) 🚀")
        print("═"*70)
        print(f"  [Motor]: XGBoost Regressor | [Núcleos Ativos]: {NUM_CORES}")
        print(f"  [Base de Conhecimento]: {metadados.get('tamanho_ultimo_treino', 0)} compostos")
        print(f"  [Confiabilidade da IA (R²)]: {r2_isp * 100:.2f}%")
        print("-" * 70)
        print("  (1) 🧠 Treinar Inteligência Artificial (Aprender Física de Foguetes)")
        print("  (2) 🎯 Executar Radar de Propulsão (Caçar a Elite Aeroespacial)")
        print("  (3) ❌ Desligar Sistema")
        print("═"*70)
        
        opcao = input(" Escolha uma opção (1-3): ").strip()
        if opcao == "1": treinar_oraculo_aeroespacial()
        elif opcao == "2": rodar_triagem_automatica()
        elif opcao == "3": sys.exit()

if __name__ == '__main__':
    painel_controle_principal()