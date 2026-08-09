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
from rdkit.Chem import FilterCatalog
from rdkit import RDLogger
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score

# Silenciar RDKit
RDLogger.DisableLog('rdApp.*')

PASTA_MODELOS = "modelos_ia_farma"
PASTA_EXPORTACAO = "csv_elite_farma"
CAMINHO_CSV = "BASE_ORACULO_FARMACIA_ADMET.csv" # <--- APONTANDO PARA O SEU NOVO SUPER BANCO
METADADOS_PATH = os.path.join(PASTA_MODELOS, "metadados_farma_admet.json")

os.makedirs(PASTA_MODELOS, exist_ok=True)
os.makedirs(PASTA_EXPORTACAO, exist_ok=True)
NUM_CORES = multiprocessing.cpu_count()

# As colunas numéricas ricas que vamos injetar na IA junto com os Fingerprints
COLUNAS_NUMERICAS = [
    'Peso_Molar', 'LogP', 'TPSA', 'PHARMA_Qtd_O', 'PHARMA_Qtd_N', 'PHARMA_Qtd_F',
    'ADMET_FractionCSP3', 'ADMET_RotatableBonds', 'ADMET_AromaticRings',
    'ADMET_HDonors', 'ADMET_HAcceptors'
]

# ==========================================================================
# 1. FUNÇÕES DE PROCESSAMENTO NEURAL
# ==========================================================================
def _gerar_fp_unico(args):
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
    resultados = Parallel(n_jobs=-1, batch_size="auto")(
        delayed(_gerar_fp_unico)(item) for item in enumerate(smiles_series)
    )
    fps, indices_validos = [], []
    for res in resultados:
        if res is not None:
            indices_validos.append(res[0])
            fps.append(res[1])
    return np.array(fps), indices_validos

def carregar_metadados():
    if os.path.exists(METADADOS_PATH):
        with open(METADADOS_PATH, 'r') as f:
            return json.load(f)
    return {"tamanho_ultimo_treino": 0, "r2_qed": 0.0, "complexidade_modelo": 200}

def salvar_metadados(tamanho, r2_qed, n_estimators):
    with open(METADADOS_PATH, 'w') as f:
        json.dump({
            "tamanho_ultimo_treino": int(tamanho),
            "r2_qed": float(r2_qed),
            "complexidade_modelo": int(n_estimators)
        }, f, indent=4)

# ==========================================================================
# 2. MOTOR DE TREINAMENTO (COM FUSÃO DE DADOS ADMET)
# ==========================================================================
def treinar_oraculo_farmaceutico():
    print("\n" + "="*85)
    print(" [⏳] CARREGANDO A BIBLIOTECA ADMET PARA A MATRIZ NEURAL... ")
    print("="*85)
    
    if not os.path.exists(CAMINHO_CSV):
        print(f"[!] Erro: Arquivo '{CAMINHO_CSV}' não encontrado.")
        return

    print("[📂] Lendo os dados clínicos (Isso pode levar alguns segundos)...")
    colunas_leitura = ['SMILES', 'Score_QED'] + COLUNAS_NUMERICAS
    df = pd.read_csv(CAMINHO_CSV, usecols=colunas_leitura, low_memory=False)
    
    # Limpeza rápida
    df = df.dropna(subset=['SMILES', 'Score_QED']).copy()
    for col in COLUNAS_NUMERICAS + ['Score_QED']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    tamanho_atual = len(df)
    metadados = carregar_metadados()
    n_estimators = metadados.get("complexidade_modelo", 200)
    
    print(f" -> Volume de dados disponível: {tamanho_atual} moléculas farmacêuticas.")
    
    # Amostramos 150.000 para aprender sem estourar a RAM
    tamanho_treino = min(150000, tamanho_atual)
    df_treino = df.sample(n=tamanho_treino, random_state=42)
    
    print(f"\n[🔥] Extraindo Fingerprints e fundindo com métricas ADMET...")
    
    # 1. Matriz de Estrutura (Fingerprints 2048 bits)
    X_fp, idx_validos = smiles_para_fingerprint(df_treino["SMILES"])
    
    # 2. Matriz Tabular (Os seus 11 parâmetros físicos)
    X_tabular = df_treino[COLUNAS_NUMERICAS].iloc[idx_validos].values
    
    # 3. A FUSÃO SUPREMA: Estrutura + Física = 2059 colunas de inteligência
    X_final = np.hstack((X_fp, X_tabular))
    y_final = df_treino["Score_QED"].iloc[idx_validos].values
    
    print(f"[{NUM_CORES} NÚCLEOS] O XGBoost está estudando {X_final.shape[1]} atributos por molécula...")
    X_tr, X_te, y_tr, y_te = train_test_split(X_final, y_final, test_size=0.2, random_state=42)
    
    # Modelo otimizado para não dar overfitting com tantas colunas
    modelo_qed = xgb.XGBRegressor(n_estimators=n_estimators, max_depth=7, learning_rate=0.08, 
                                  subsample=0.8, colsample_bytree=0.8, n_jobs=-1, random_state=42)
    modelo_qed.fit(X_tr, y_tr)
    
    r2_qed = r2_score(y_te, modelo_qed.predict(X_te))
    
    caminho_modelo = os.path.join(PASTA_MODELOS, "oraculo_farma_admet_qed.pkl")
    joblib.dump(modelo_qed, caminho_modelo)
    salvar_metadados(tamanho_atual, r2_qed, n_estimators)
    
    print("\n ✨ ORÁCULO CLÍNICO TREINADO COM SUCESSO! ")
    print(f" -> Confiabilidade (R²): {r2_qed * 100:.2f}% (A IA agora domina a biologia química!)")

# ==========================================================================
# 3. RADAR DE TRIAGEM (CAÇANDO FÁRMACOS DE ELITE)
# ==========================================================================
def rodar_triagem_automatica():
    caminho_modelo = os.path.join(PASTA_MODELOS, "oraculo_farma_admet_qed.pkl")
    if not os.path.exists(caminho_modelo):
        print("\n[!] Erro: Treine o Oráculo Farmacêutico (Opção 1) primeiro.")
        return
        
    print("\n" + "="*85)
    print(f" 🎛️  RADAR DE DRUG DISCOVERY ATIVADO ({NUM_CORES} NÚCLEOS) ")
    print("="*85)
    
    limite_podio = int(input("\n -> Quantos fármacos de elite deseja extrair? [Padrão: 100]: ") or 100)
    
    print("[🧠] Carregando a Mente Neural Farmacêutica...")
    modelo_qed = joblib.load(caminho_modelo)

    print("[🛡️] Ativando Sistema Imunológico: Toxinas PAINS & BRENK...")
    params = FilterCatalog.FilterCatalogParams()
    params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
    params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.BRENK)
    catalogo_tox = FilterCatalog.FilterCatalog(params)

    def passa_filtro_toxicologico(smiles):
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None: return False
            return not catalogo_tox.HasMatch(mol)
        except: return False

    print("\n[📂] Escaneando o Banco de Dados em Modo Turbo...")
    top_elite = pd.DataFrame()
    total_processado = 0
    
    for chunk in pd.read_csv(CAMINHO_CSV, chunksize=100000, low_memory=False):
        chunk = chunk.dropna(subset=["SMILES"]).copy()
        
        # Só deixa entrar moléculas que passam na Regra de Lipinski
        if 'PHARMA_Lipinski_Pass' in chunk.columns:
            chunk = chunk[chunk['PHARMA_Lipinski_Pass'] == 1]
            
        if chunk.empty: continue
        for col in COLUNAS_NUMERICAS:
            chunk[col] = pd.to_numeric(chunk[col], errors='coerce').fillna(0.0)
        
        # Fusão de Atributos no momento da previsão
        X_chunk_fp, idx_v = smiles_para_fingerprint(chunk["SMILES"])
        chunk_v = chunk.iloc[idx_v].copy()
        X_chunk_tab = chunk_v[COLUNAS_NUMERICAS].values
        
        X_chunk_final = np.hstack((X_chunk_fp, X_chunk_tab))
        
        # O Oráculo dá o seu veredito!
        chunk_v["IA_Pred_Score_QED"] = np.clip(modelo_qed.predict(X_chunk_final), 0.0, 1.0)
        
        # Filtro Tóxico
        cand_bloco = chunk_v.nlargest(limite_podio * 2, "IA_Pred_Score_QED")
        cand_seguros = cand_bloco[cand_bloco["SMILES"].apply(passa_filtro_toxicologico)]
        
        top_elite = pd.concat([top_elite, cand_seguros]).sort_values(by="IA_Pred_Score_QED", ascending=False).head(limite_podio)
        
        total_processado += 100000
        sys.stdout.write(f"\r     -> Analisados: {total_processado} candidatos a fármaco...")
        sys.stdout.flush()
        
    print("\n\n" + "="*85)
    print(f" 🎉 VARREDURA CLÍNICA CONCLUÍDA! O TOP {limite_podio} DOS LABORATÓRIOS: ")
    print("="*85)

    for _, r in top_elite.head(10).iterrows(): 
        print(f"   💊 ID: {r.get('ID', 'N/A')} | Score QED: {r['IA_Pred_Score_QED']:.4f} | SMILES: {r['SMILES'][:40]}...")

    nome_arq = "RANKING_FARMACOS_ELITE_ADMET.csv"
    caminho_producao = os.path.join(PASTA_EXPORTACAO, nome_arq)
    if os.path.exists(caminho_producao):
        shutil.copy2(caminho_producao, os.path.join(PASTA_EXPORTACAO, f"BKP_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{nome_arq}"))
        
    top_elite.to_csv(caminho_producao, index=False, encoding="utf-8")
    print(f"\n 💾 RELATÓRIO CLÍNICO EXPORTADO PARA: '{caminho_producao}'")

# ==========================================================================
# 4. MICRO MENU
# ==========================================================================
def painel_controle_principal():
    while True:
        metadados = carregar_metadados()
        r2_qed = metadados.get("r2_qed", 0.0)
        
        print("\n" + "═"*70)
        print(f"    🧬 CONSOLE DO ORÁCULO FARMACÊUTICO ADMET (V8.0) 🧬")
        print("═"*70)
        print(f"  [Motor]: XGBoost Bio-Regressor | [Atributos]: 2059 por molécula")
        print(f"  [Confiabilidade Clínica (R²)]: {r2_qed * 100:.2f}%")
        print("-" * 70)
        print("  (1) 🧠 Treinar Inteligência Artificial (Aprender ADMET)")
        print("  (2) 🎯 Executar Radar Clínico (Caçar a Cura)")
        print("  (3) ❌ Desligar Sistema")
        print("═"*70)
        
        opcao = input(" Escolha uma opção (1-3): ").strip()
        if opcao == "1": treinar_oraculo_farmaceutico()
        elif opcao == "2": rodar_triagem_automatica()
        elif opcao == "3": sys.exit()

if __name__ == '__main__':
    painel_controle_principal()