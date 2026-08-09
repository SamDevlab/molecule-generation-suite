import os
import pandas as pd
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit import RDLogger
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_squared_error
import xgboost as xgb

# Silencia avisos do RDKit
RDLogger.DisableLog('rdApp.*')

print("="*85)
print("   🔮 TREINAMENTO DO ORÁCULO V1.0: INTELIGÊNCIA QUÍMICA PREDITIVA   ")
print("="*85)

CAMINHO_CSV = os.path.join("csv", "universo_utilidade_filtrada.csv")

if not os.path.exists(CAMINHO_CSV):
    print("[!] Arquivo CSV não encontrado. Execute o motor ou a análise antes.")
    exit()

# 1. CARREGAMENTO E LIMPEZA DOS DADOS
print("[⏳] Carregando e limpando o dataset massivo...")
df = pd.read_csv(CAMINHO_CSV, low_memory=False)
df = df[df["ID"] != "ID"].copy()
df = df.dropna(subset=["SMILES"]).copy()

# Garantir tipagem numérica
df["Score_QED"] = pd.to_numeric(df["Score_QED"], errors='coerce').fillna(0.0)
df["OB_Pct"] = pd.to_numeric(df["OB_Pct"], errors='coerce').fillna(0.0)

# Filtrar para treinar apenas com dados que fazem sentido para cada alvo
df_pharma = df[df["Categoria"] == "Biologia/Farmácia"].copy()
df_aero = df[df["Categoria"] == "Energia/Aeroespacial"].copy()

print(f"[📊] Dados disponíveis para treino:")
print(f"     -> Farmácia (Alvo: QED): {len(df_pharma)} exemplos")
print(f"     -> Aeroespacial (Alvo: OB%): {len(df_aero)} exemplos")

# 2. FUNÇÃO PARA TRANSFORMAR SMILES EM VETORES NUMÉRICOS (FINGERPRINTS)
def smiles_para_fingerprint(smiles_series):
    fps = []
    indices_validos = []
    for idx, smiles in enumerate(smiles_series):
        mol = Chem.MolFromSmiles(smiles)
        if mol:
            # Gera o Morgan Fingerprint (Raio 2, equivalente ao ECFP4 da indústria)
            fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
            arr = np.zeros((1,))
            Chem.DataStructs.ConvertToNumpyArray(fp, arr)
            fps.append(arr)
            indices_validos.append(idx)
    return np.array(fps), indices_validos

# ==========================================================================
# 3. TREINAMENTO - MÓDULO 1: PREDITOR DE QED (FARMÁCIA)
# ==========================================================================
if len(df_pharma) > 1000:
    print("\n[💊] Iniciando extração de feições para a gaveta de Farmácia (Top 50k)...")
    # CORREÇÃO AQUI: random_seed alterado para random_state
    df_pharma_sub = df_pharma.sample(n=min(50000, len(df_pharma)), random_state=42)
    
    X_pharma, idx_validos = smiles_para_fingerprint(df_pharma_sub["SMILES"])
    y_pharma = df_pharma_sub["Score_QED"].iloc[idx_validos].values

    X_train, X_test, y_train, y_test = train_test_split(X_pharma, y_pharma, test_size=0.2, random_state=42)

    print("[🧠] Treinando o cérebro do XGBoost para prever Score QED...")
    modelo_qed = xgb.XGBRegressor(n_estimators=150, max_depth=7, learning_rate=0.1, n_jobs=-1, random_state=42)
    modelo_qed.fit(X_train, y_train)

    # Avaliação do Respaldo Real
    preds = modelo_qed.predict(X_test)
    r2 = r2_score(y_test, preds)
    mse = mean_squared_error(y_test, preds)

    print(f"🥇 RESULTADO DO MODELO QED (FARMÁCIA):")
    print(f"     -> Coeficiente de Determinação (R² Score): {r2:.4f}")
    print(f"     -> Erro Quadrático Médio (MSE): {mse:.6f}")
    if r2 > 0.85:
        print("     -> [VERIFICAÇÃO]: RESPALDO REAL CONFIRMADO! O modelo aprendeu a química estrutural.")
    else:
        print("     -> [VERIFICAÇÃO]: Padrão estatístico fraco ou inconclusivo.")
else:
    print("\n[⚠️] Dados insuficientes na gaveta de Farmácia para um treino robusto.")

# ==========================================================================
# 4. TREINAMENTO - MÓDULO 2: PREDITOR DE BALANÇO DE OXIGÊNIO (AEROESPACIAL)
# ==========================================================================
if len(df_aero) > 1000:
    print("\n[🚀] Iniciando extração de feições para a gaveta Aeroespacial (Top 50k)...")
    # CORREÇÃO AQUI: random_seed alterado para random_state
    df_aero_sub = df_aero.sample(n=min(50000, len(df_aero)), random_state=42)
    
    X_aero, idx_validos_aero = smiles_para_fingerprint(df_aero_sub["SMILES"])
    y_aero = df_aero_sub["OB_Pct"].iloc[idx_validos_aero].values

    X_train_a, X_test_a, y_train_a, y_test_a = train_test_split(X_aero, y_aero, test_size=0.2, random_state=42)

    print("[🧠] Treinando o cérebro do XGBoost para prever Balanço de Oxigênio...")
    modelo_aero = xgb.XGBRegressor(n_estimators=150, max_depth=7, learning_rate=0.1, n_jobs=-1, random_state=42)
    modelo_aero.fit(X_train_a, y_train_a)

    preds_a = modelo_aero.predict(X_test_a)
    r2_a = r2_score(y_test_a, preds_a)
    mse_a = mean_squared_error(y_test_a, preds_a)

    print(f"🥇 RESULTADO DO MODELO OB% (AEROESPACIAL):")
    print(f"     -> Coeficiente de Determinação (R² Score): {r2_a:.4f}")
    print(f"     -> Erro Quadrático Médio (MSE): {mse_a:.4f}")
    if r2_a > 0.85:
        print("     -> [VERIFICAÇÃO]: RESPALDO REAL CONFIRMADO! Previsões termodinâmicas validadas.")
else:
    print("\n[⚠️] Dados insuficientes na gaveta Aeroespacial para treino.")

print("\n" + "="*85)
print("   PROCESSO CONCLUÍDO. SEUS MODELOS ESTÃO PRONTOS PARA OPERAR EM LARGA ESCALA   ")
print("="*85)