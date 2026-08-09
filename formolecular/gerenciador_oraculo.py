import os
import sys
import json
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import multiprocessing
from joblib import Parallel, delayed
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem import FilterCatalog
from rdkit.Chem import Descriptors
from rdkit import RDLogger
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score
import shutil
from datetime import datetime

# Desativa os avisos do RDKit para não poluir o terminal
RDLogger.DisableLog('rdApp.*')

PASTA_MODELOS = "modelos_ia"
PASTA_CSV = "csv"
CAMINHO_CSV = os.path.join(PASTA_CSV, "universo_utilidade_filtrada.csv")
METADADOS_PATH = os.path.join(PASTA_MODELOS, "metadados_treino.json")

os.makedirs(PASTA_MODELOS, exist_ok=True)
NUM_CORES = multiprocessing.cpu_count()

# ==========================================================================
# 1. FUNÇÕES AUXILIARES, MULTIPROCESSAMENTO E FÍSICA (NASA)
# ==========================================================================

def _gerar_fp_unico(args):
    """Função isolada para permitir a paralelização em vários núcleos"""
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
    """Gera fingerprints utilizando 100% da capacidade do CPU do computador"""
    # Utiliza o Joblib para distribuir a tarefa por todos os núcleos (n_jobs=-1)
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

def calcular_entalpia_combustao_mj_kg(smiles):
    """Estima o Calor de Combustão usando aditividade de grupos (Módulo NASA)"""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if not mol: return 0.0
        
        mol = Chem.AddHs(mol)
        num_c = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 6)
        num_h = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 1)
        num_o = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 8)
        num_n = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 7)
        peso_molar = Descriptors.MolWt(mol)
        
        # Calor de Combustão Inferior (Regra aproximada)
        calor_kcal_mol = (106 * num_c) + (26 * num_h) - (50 * num_o) + (10 * num_n)
        
        for bond in mol.GetBonds():
            if bond.GetBondType() == Chem.rdchem.BondType.TRIPLE:
                calor_kcal_mol += 60
                
        if peso_molar > 0:
            mj_kg = (calor_kcal_mol * 4.184) / peso_molar * 10
            return round(mj_kg, 2)
        return 0.0
    except:
        return 0.0

def carregar_metadados():
    if os.path.exists(METADADOS_PATH):
        with open(METADADOS_PATH, 'r') as f:
            return json.load(f)
    return {"tamanho_ultimo_treino": 0, "r2_qed": 0.0, "r2_aero": 0.0, "r2_food": 0.0, "r2_agro": 0.0, "r2_mat": 0.0, "complexidade_modelo": 150}

def salvar_metadados(tamanho, r2_q, r2_a, r2_f, r2_ag, r2_m, n_estimators):
    metadados = {
        "tamanho_ultimo_treino": int(tamanho),
        "r2_qed": float(r2_q),
        "r2_aero": float(r2_a),
        "r2_food": float(r2_f),
        "r2_agro": float(r2_ag),
        "r2_mat": float(r2_m),
        "complexidade_modelo": int(n_estimators)
    }
    with open(METADADOS_PATH, 'w') as f:
        json.dump(metadados, f, indent=4)

# ==========================================================================
# 2. TREINAMENTO MULTI-ALVO COM 5 CABEÇAS
# ==========================================================================
def treinar_sistema_oraculo():
    print("\n" + "="*85)
    print(" [⏳] CARREGANDO O BIG DATA PARA A MATRIZ NEURAL... ")
    print("="*85)
    
    if not os.path.exists(CAMINHO_CSV):
        print("[!] Erro: Ficheiro não encontrado.")
        return

    df = pd.read_csv(CAMINHO_CSV, low_memory=False)
    df = df[df["ID"] != "ID"].dropna(subset=["SMILES"]).copy()
    
    df["Score_QED"] = pd.to_numeric(df["Score_QED"], errors='coerce').fillna(0.0)
    df["OB_Pct"] = pd.to_numeric(df["OB_Pct"], errors='coerce').fillna(0.0)
    df["Peso_Molar"] = pd.to_numeric(df["Peso_Molar"], errors='coerce').fillna(0.0)
    
    col_tpsa = "TPSA" if "TPSA" in df.columns else "tpsa" if "tpsa" in df.columns else None
    df["TPSA_Superficie"] = pd.to_numeric(df[col_tpsa], errors='coerce').fillna(0.0) if col_tpsa else 0.0

    if "Num_N" not in df.columns: df["Num_N"] = 0.0
    if "Num_P" not in df.columns: df["Num_P"] = 0.0
        
    df["Num_N"] = pd.to_numeric(df["Num_N"], errors='coerce').fillna(0.0)
    df["Num_P"] = pd.to_numeric(df["Num_P"], errors='coerce').fillna(0.0)
    df["Eficiencia_Nutricional"] = (df["Num_N"] + df["Num_P"]) / df["Peso_Molar"].replace(0, 1)

    df_pharma = df[df["Categoria"] == "Biologia/Farmácia"].copy()
    df_aero = df[df["Categoria"] == "Energia/Aeroespacial"].copy()
    df_food = df[df["Categoria"] == "Alimentos/Aromas"].copy()
    df_agro = df[df["Categoria"] == "Agroquímicos/Fertilizantes"].copy()
    df_mat = df[df["Categoria"] == "Química de Materiais"].copy()
    
    tamanho_atual = len(df)
    metadados = carregar_metadados()
    tamanho_anterior = metadados.get("tamanho_ultimo_treino", 0)
    n_estimators = metadados.get("complexidade_modelo", 150)
    
    print(f" -> Volume de dados atual: {tamanho_atual} moléculas.")
    
    if tamanho_atual >= (tamanho_anterior * 1.5) and tamanho_anterior > 0:
        print("\n[🚀 AUTO-UPGRADE DETECTADO! 🚀]")
        n_estimators += 50
    
    def treinar_modelo(df_alvo, coluna_alvo, nome_modulo):
        print(f"[{nome_modulo}] Analisando dados (usando {NUM_CORES} núcleos)...")
        if not df_alvo.empty:
            df_sub = df_alvo.sample(n=min(50000, len(df_alvo)), random_state=42)
            X, idx = smiles_para_fingerprint(df_sub["SMILES"])
            y = df_sub[coluna_alvo].iloc[idx].values
            X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
            mod = xgb.XGBRegressor(n_estimators=n_estimators, max_depth=7, learning_rate=0.1, n_jobs=-1, random_state=42)
            mod.fit(X_tr, y_tr)
            return mod, r2_score(y_te, mod.predict(X_te)) if len(X_te) > 0 else 0.0
        return xgb.XGBRegressor(), 0.0

    print("\n[Iniciando Treinamento Neural Distribuído]")
    mod_qed, r2_q = treinar_modelo(df_pharma, "Score_QED", "💊 Farmácia")
    mod_aero, r2_a = treinar_modelo(df_aero, "OB_Pct", "🚀 Aeroespacial")
    mod_food, r2_f = treinar_modelo(df_food, "Peso_Molar", "🍓 Alimentos")
    mod_agro, r2_ag = treinar_modelo(df_agro, "Eficiencia_Nutricional", "🌿 Agroquímica")
    mod_mat, r2_m = treinar_modelo(df_mat, "TPSA_Superficie", "💎 Materiais")

    joblib.dump(mod_qed, os.path.join(PASTA_MODELOS, "oraculo_qed.pkl"))
    joblib.dump(mod_aero, os.path.join(PASTA_MODELOS, "oraculo_aero.pkl"))
    joblib.dump(mod_food, os.path.join(PASTA_MODELOS, "oraculo_food.pkl"))
    joblib.dump(mod_agro, os.path.join(PASTA_MODELOS, "oraculo_agro.pkl"))
    joblib.dump(mod_mat, os.path.join(PASTA_MODELOS, "oraculo_mat.pkl"))
    
    salvar_metadados(tamanho_atual, r2_q, r2_a, r2_f, r2_ag, r2_m, n_estimators)
    print("\n ✨ ORÁCULO DE 5 CABEÇAS COMPILADO COM SUCESSO! ")


# ==========================================================================
# 3. TRIAGEM DE ALTA PERFORMANCE (AVALIAÇÃO PREGUIÇOSA + NASA)
# ==========================================================================
def rodar_triagem_automatica():
    paths = ["oraculo_qed.pkl", "oraculo_aero.pkl", "oraculo_food.pkl", "oraculo_agro.pkl", "oraculo_mat.pkl"]
    if not all(os.path.exists(os.path.join(PASTA_MODELOS, p)) for p in paths):
        print("\n[!] Erro: Treine o Oráculo Expandido (Opção 1) primeiro.")
        return
        
    print("\n" + "="*85)
    print(f" 🎛️  PAINEL DE TRIAGEM INDUSTRIAL TURBO ({NUM_CORES} NÚCLEOS ATIVOS) ")
    print("="*85)
    
    limite_input = input("\n -> Quantos campeões deseja ver listados por indústria? [Padrão: 5]: ").strip()
    limite_podio = int(limite_input) if limite_input.isdigit() else 5
    
    print("[🧠] A carregar 5 redes preditivas do disco...")
    mod_q = joblib.load(os.path.join(PASTA_MODELOS, "oraculo_qed.pkl"))
    mod_a = joblib.load(os.path.join(PASTA_MODELOS, "oraculo_aero.pkl"))
    mod_f = joblib.load(os.path.join(PASTA_MODELOS, "oraculo_food.pkl"))
    mod_ag = joblib.load(os.path.join(PASTA_MODELOS, "oraculo_agro.pkl"))
    mod_m = joblib.load(os.path.join(PASTA_MODELOS, "oraculo_mat.pkl"))
    
    print("[🛡️] A inicializar Sistema Imunológico: Carregando bibliotecas toxicológicas...")
    params = FilterCatalog.FilterCatalogParams()
    params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
    params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.BRENK)
    catalogo_tox = FilterCatalog.FilterCatalog(params)

    def passa_filtro_biologico(smiles):
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None: return False
            return not catalogo_tox.HasMatch(mol)
        except:
            return False

    print("\n[📂] A minerar o Big Data com Lógica de Funil (Lazy Evaluation)...")
    
    top_p, top_a, top_f, top_ag, top_m = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    total_processado = 0
    
    for chunk in pd.read_csv(CAMINHO_CSV, chunksize=50000, low_memory=False):
        chunk = chunk[chunk["ID"] != "ID"].dropna(subset=["SMILES"]).copy()
        if chunk.empty: continue
        
        # A IA processa rapidamente (Multicore)
        X_chunk, idx_validos = smiles_para_fingerprint(chunk["SMILES"])
        chunk_valido = chunk.iloc[idx_validos].copy()
        if chunk_valido.empty: continue
            
        chunk_valido["IA_Pred_QED"] = np.clip(mod_q.predict(X_chunk), 0.0, 1.0)
        chunk_valido["IA_Pred_OB"] = mod_a.predict(X_chunk)
        chunk_valido["IA_Pred_Vol"] = mod_f.predict(X_chunk)
        chunk_valido["IA_Pred_Nutri"] = mod_ag.predict(X_chunk)
        chunk_valido["IA_Pred_TPSA"] = mod_m.predict(X_chunk)
        
        # Filtro Estrutural Rápido (Operação Vetorizada de Texto)
        tem_carbono = chunk_valido["SMILES"].str.contains("C|c")
        tem_silicio = chunk_valido["SMILES"].str.contains("Si")
        tem_boro = chunk_valido["SMILES"].str.contains(r"B[^r]|B$", regex=True)
        chunk_org = chunk_valido[tem_carbono & (~tem_silicio) & (~tem_boro)].copy()
        
        # 🚀 AVALIAÇÃO PREGUIÇOSA (O Segredo da Otimização)
        
        # -- FARMÁCIA --
        cand_p = chunk_org[chunk_org["IA_Pred_QED"] >= 0.60]
        if not cand_p.empty:
            cand_p = cand_p.nlargest(limite_podio * 10, "IA_Pred_QED")
            temp_p = cand_p[cand_p["SMILES"].apply(passa_filtro_biologico)].head(limite_podio)
            top_p = pd.concat([top_p, temp_p]).sort_values(by="IA_Pred_QED", ascending=False).head(limite_podio)
        
        # -- AROMAS --
        cand_f = chunk_org[chunk_org["IA_Pred_Vol"] < 160]
        if not cand_f.empty:
            cand_f = cand_f.nsmallest(limite_podio * 10, "IA_Pred_Vol")
            temp_f = cand_f[cand_f["SMILES"].apply(passa_filtro_biologico)].head(limite_podio)
            top_f = pd.concat([top_f, temp_f]).sort_values(by="IA_Pred_Vol", ascending=True).head(limite_podio)

        # -- AEROESPACIAL --
        cand_a = chunk_org[(chunk_org["IA_Pred_OB"] > -30.0) & (chunk_org["IA_Pred_OB"] < 20.0)].copy()
        if not cand_a.empty:
            cand_a["Abs_OB"] = cand_a["IA_Pred_OB"].abs()
            cand_a = cand_a.nsmallest(limite_podio * 10, "Abs_OB")
            # Módulo NASA restrito apenas à elite
            cand_a["Energia_Combustao_MJ_kg"] = cand_a["SMILES"].apply(calcular_entalpia_combustao_mj_kg)
            top_a = pd.concat([top_a, cand_a]).sort_values(by="Abs_OB").head(limite_podio)
        
        # -- AGROQUÍMICA --
        cand_ag = chunk_org[chunk_org["IA_Pred_Nutri"] > 0]
        if not cand_ag.empty:
            temp_ag = cand_ag.nlargest(limite_podio, "IA_Pred_Nutri")
            top_ag = pd.concat([top_ag, temp_ag]).sort_values(by="IA_Pred_Nutri", ascending=False).head(limite_podio)
        
        # -- MATERIAIS --
        temp_m = chunk_valido[~(tem_carbono & (~tem_silicio) & (~tem_boro)) | (~chunk_valido["ID"].isin(top_p["ID"]) & ~chunk_valido["ID"].isin(top_a["ID"]))]
        if not temp_m.empty:
            temp_m = temp_m.nlargest(limite_podio, "IA_Pred_TPSA")
            top_m = pd.concat([top_m, temp_m]).sort_values(by="IA_Pred_TPSA", ascending=False).head(limite_podio)
        
        total_processado += len(chunk)
        sys.stdout.write(f"\r     -> Progresso: {total_processado} estruturas processadas em Modo Turbo...")
        sys.stdout.flush()
        
    print("\n\n" + "="*85)
    print(" 🎉 VARREDURA DE ALTA PERFORMANCE CONCLUÍDA! OS TITÃS DA INDÚSTRIA: ")
    print("="*85)

    print(f"\n🏆 TOP {limite_podio} - FARMÁCIA (Maior Score QED - Livre de Toxicidade)")
    for _, r in top_p.iterrows(): print(f"   ↳ {r['ID']} | SMILES: {r['SMILES']} | QED: {r['IA_Pred_QED']:.3f}")

    print(f"\n🏆 TOP {limite_podio} - AEROESPACIAL (Módulo NASA Ativo)")
    for _, r in top_a.iterrows(): 
        print(f"   ↳ {r['ID']} | SMILES: {r['SMILES']} | OB%: {r['IA_Pred_OB']:.1f}% | Calor: {r.get('Energia_Combustao_MJ_kg', 0.0)} MJ/kg")

    print(f"\n🏆 TOP {limite_podio} - AROMAS (Maior Volatilidade / Livre de Toxicidade)")
    for _, r in top_f.iterrows(): print(f"   ↳ {r['ID']} | SMILES: {r['SMILES']} | Peso IA: {r['IA_Pred_Vol']:.1f} g/mol")

    print(f"\n🏆 TOP {limite_podio} - AGROQUÍMICA (Densidade Nutricional N/P)")
    for _, r in top_ag.iterrows(): print(f"   ↳ {r['ID']} | SMILES: {r['SMILES']} | N/P Index: {r['IA_Pred_Nutri']:.4f}")

    print(f"\n🏆 TOP {limite_podio} - MATERIAIS AVANÇADOS E POLÍMEROS (Maior TPSA)")
    for _, r in top_m.iterrows(): print(f"   ↳ {r['ID']} | SMILES: {r['SMILES']} | TPSA IA: {r['IA_Pred_TPSA']:.1f} Å²")

    # =====================================================================
    # 💾 BLOCO DE EXPORTAÇÃO SEGURO COM BACKUP
    # =====================================================================
    print("\n[💾] A iniciar rotina de exportação segura...")
    
    PASTA_BACKUP = os.path.join(PASTA_CSV, "backups")
    os.makedirs(PASTA_BACKUP, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    subpasta_rodada = os.path.join(PASTA_BACKUP, f"rodada_{timestamp}")
    
    mapeamento = {
        "FARMACIA": (top_p, "ORACULO_ELITE_FARMACIA.csv"),
        "AEROESPACIAL": (top_a, "ORACULO_ELITE_AEROESPACIAL.csv"),
        "AROMAS": (top_f, "ORACULO_ELITE_AROMAS.csv"),
        "AGROQUIMICA": (top_ag, "ORACULO_ELITE_AGROQUIMICA.csv"),
        "MATERIAIS": (top_m, "ORACULO_ELITE_MATERIAIS.csv")
    }
    
    for _, (df_elite, nome_arq) in mapeamento.items():
        if not df_elite.empty:
            caminho_producao = os.path.join(PASTA_CSV, nome_arq)
            if os.path.exists(caminho_producao):
                os.makedirs(subpasta_rodada, exist_ok=True)
                shutil.copy2(caminho_producao, os.path.join(subpasta_rodada, f"PRE_{nome_arq}"))
            df_elite.to_csv(caminho_producao, index=False, encoding="utf-8")
            
    print(f"\n" + "-"*60)
    print(f" 🛡️  SEGURANÇA DE DADOS ATIVADA. Ficheiros guardados em '{PASTA_CSV}/'.")
    print("="*85)

# ==========================================================================
# 4. MICRO MENU NO PROMPT
# ==========================================================================
def painel_controle_principal():
    while True:
        metadados = carregar_metadados()
        r2_q, r2_a = metadados.get("r2_qed", 0.0), metadados.get("r2_aero", 0.0)
        r2_f, r2_ag = metadados.get("r2_food", 0.0), metadados.get("r2_agro", 0.0)
        r2_m = metadados.get("r2_mat", 0.0)
        
        print("\n" + "═"*70)
        print(f"    🔮 CONSOLE DO ORÁCULO QUÍMICO V5.5 (MODO MULTI-CORE TURBO) 🔮")
        print("═"*70)
        print(f"  [Núcleos de CPU Ativos]: {NUM_CORES}")
        print(f"  [Status] Último treino: {metadados.get('tamanho_ultimo_treino', 0)} mol")
        print(f"  [Precisão] QED: {r2_q:.2f} | OB%: {r2_a:.2f} | Mat: {r2_m:.2f}")
        print("-" * 70)
        print("  (1) Rodar Treinamento Expandido / Atualizar Redes Neurais")
        print("  (2) Executar Varredura Turbo (Ranking Global em Lotes Paralelos)")
        print("  (3) Sair do Painel")
        print("═"*70)
        
        opcao = input(" Escolha uma opção (1-3): ").strip()
        if opcao == "1": treinar_sistema_oraculo()
        elif opcao == "2": rodar_triagem_automatica()
        elif opcao == "3": sys.exit()

if __name__ == '__main__':
    painel_controle_principal()