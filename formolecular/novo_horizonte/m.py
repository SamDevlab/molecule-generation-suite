import os
import subprocess
import pandas as pd
import numpy as np
import xgboost as xgb
from rdkit import Chem
from rdkit import RDLogger
from rdkit.Chem import AllChem, Descriptors, QED, BRICS, DataStructs
from rdkit.Chem import FilterCatalog
import concurrent.futures
import random
import shutil
import gc

# Silenciar avisos do RDKit
RDLogger.DisableLog('rdApp.*')

# --- CONFIGURAÇÕES GLOBAIS E ALVOS ---
ARQUIVO_MESTRE = "banco_mestre_unificado.csv"
ARQUIVO_CEMITERIO = "cemiterio_falhas.txt"
PASTA_TESTE = "laboratorio_evolutivo"
CAMINHO_VINA = "./vina.exe" if os.name == 'nt' else "./vina"

# Atualizado para o Cristal Humano 4EY7 (Sugestão Prof. Samuel Pita)
MAPA_RECEPTORES = {
    "receptor_4EY7": {"cx": -1.6, "cy": -50.2, "cz": 2.1, "sx": 40.0, "sy": 40.0, "sz": 40.0},
    "receptor_5W8K": {"cx": 0.0, "cy": 0.0,  "cz": 0.0,  "sx": 50.0, "sy": 50.0, "sz": 50.0}
}

# --- ARSENAL DE MUTAÇÕES ---
reacoes_virtuais = {
    "Extender": "[CX4H3;!R:1]>>[CX4H2:1]C",
    "Ramificar": "[CX4H2;!R:1]>>[CX4H1:1](C)",
    "Metilar_Anel": "[c;H1:1]>>[c:1](C)",
    "Encurtar": "[CX4H2;!R:1][CX4H3;!R:2]>>[CX4H3:1]",
    "Oxima_Cetona": "[C:1]=NO>>[C:1](=O)C",
    "Cetona_Amida": "[C:1](=O)C>>[C:1](=O)N",
    "Adicionar_Fluor": "[c;H1:1]>>[c:1](F)",
    "Trocar_Fluor_Cloro": "[F:1]>>[Cl:1]",
    "Adicionar_Metoxi": "[c;H1:1]>>[c:1](OC)",
    "Adicionar_OH": "[c;H1:1]>>[c:1](O)"
}

reacoes_radicais = {
    "Adicionar_Trifluormetil": "[c;H1:1]>>[c:1](C(F)(F)F)",
    "Adicionar_Ciclopropil": "[c;H1:1]>>[c:1](C1CC1)",
    "Aromatizar_Alifatico": "C1CCCCC1>>c1ccccc1"
}

PADROES_PROIBIDOS = [
    Chem.MolFromSmarts("[C]=[C]=[C]"), 
    Chem.MolFromSmarts("[O]-[O]"),     
    Chem.MolFromSmarts("[N]-[N]-[N]"), 
    Chem.MolFromSmarts("C#C"),         
]

COLUNAS_OFICIAIS = [
    'ID_Mestre', 'SMILES', '4EY7_Eficacia', '5W8K_Risco', 
    'Indice_Seletividade', 'Fitness_Score', 'Origem_Historica'
]

# --- INICIALIZAÇÃO DOS FILTROS DA INDÚSTRIA (PAINS E BRENK) ---
params = FilterCatalog.FilterCatalogParams()
params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.BRENK)
catalogo_toxico = FilterCatalog.FilterCatalog(params)

# --- FÓRMULA DE FITNESS (MURALHA CARDÍACA) ---
def calcular_fitness(eficacia_4ey7, risco_5w8k):
    penalidade = abs(risco_5w8k) * 0.7
    if risco_5w8k < -6.15: # Ajuste logístico sugerido
        excesso = abs(risco_5w8k) - 6.15
        penalidade += (excesso ** 2) * 5.0
    return eficacia_4ey7 + penalidade

def carregar_cemiterio():
    if not os.path.exists(ARQUIVO_CEMITERIO): return set()
    with open(ARQUIVO_CEMITERIO, "r") as f:
        return set(f.read().splitlines())

def adicionar_ao_cemiterio(smiles_falhos):
    if not smiles_falhos: return
    with open(ARQUIVO_CEMITERIO, "a") as f:
        for s in smiles_falhos: f.write(s + "\n")

def treinar_xgboost_mestre():
    if not os.path.exists(ARQUIVO_MESTRE): return None
    df_treino = pd.read_csv(ARQUIVO_MESTRE)
    
    # Módulo de Migração Automática (1EVE -> 4EY7)
    if '1EVE_Eficacia' in df_treino.columns:
        df_treino.rename(columns={'1EVE_Eficacia': '4EY7_Eficacia'}, inplace=True)
        print("  [!] Banco de dados atualizado automaticamente para o padrão hAChE (4EY7).")
        
    df_treino = df_treino.dropna(subset=['SMILES', '4EY7_Eficacia', '5W8K_Risco'])
    X = np.array([np.array(AllChem.GetMorganFingerprintAsBitVect(Chem.MolFromSmiles(s), 2, 2048)) for s in df_treino['SMILES'] if Chem.MolFromSmiles(s)])
    df_treino['Fitness_Score'] = df_treino.apply(lambda row: calcular_fitness(row['4EY7_Eficacia'], row['5W8K_Risco']), axis=1)
    y = df_treino['Fitness_Score'].values[:len(X)]
    
    modelo = xgb.XGBRegressor(n_estimators=1000, learning_rate=0.03, max_depth=8, subsample=0.8, colsample_bytree=0.8, random_state=42)
    modelo.fit(X, y)
    return modelo

def worker_docking(tarefa):
    index, row, nova_geracao = tarefa
    id_mol = f"Gen{nova_geracao}_Mutante_{index+1}"
    caminho_base = os.path.join(PASTA_TESTE, id_mol)
    pdb_temp, pdbqt_final = f"{caminho_base}.pdb", f"{caminho_base}.pdbqt"
    
    try:
        mol = Chem.AddHs(Chem.MolFromSmiles(row['SMILES']))
        cids = AllChem.EmbedMultipleConfs(mol, numConfs=10, randomSeed=42)
        if not cids: return {'SMILES': row['SMILES'], 'Status': 'Erro'}
        
        res_mmff = AllChem.MMFFOptimizeMoleculeConfs(mol)
        min_energy, min_cid = float('inf'), cids[0]
        
        for cid, (nao_convergiu, energia) in enumerate(res_mmff):
            if nao_convergiu == 0 and energia < min_energy:
                min_energy = energia
                min_cid = cids[cid]
                
        Chem.MolToPDBFile(mol, pdb_temp, confId=min_cid)
        subprocess.run(["obabel", pdb_temp, "-O", pdbqt_final, "-p", "7.4"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(pdb_temp): os.remove(pdb_temp)
    except: return {'SMILES': row['SMILES'], 'Status': 'Erro'}
        
    if not os.path.exists(pdbqt_final) or os.path.getsize(pdbqt_final) < 100:
        return {'SMILES': row['SMILES'], 'Status': 'Erro'}
    
    energias = {"SMILES": row['SMILES'], "Origem_Historica": f"Gen {nova_geracao}", "Status": "Sucesso"}
    
    for receptor, box in MAPA_RECEPTORES.items():
        arq_conf, arq_log, arq_out = f"{caminho_base}_{receptor}_conf.txt", f"{caminho_base}_{receptor}_log.txt", f"{caminho_base}_{receptor}_out.pdbqt"
        with open(arq_conf, "w") as f:
            f.write(f"receptor = {receptor}.pdbqt\nligand = {pdbqt_final}\ncenter_x = {box['cx']}\ncenter_y = {box['cy']}\ncenter_z = {box['cz']}\nsize_x = {box['sx']}\nsize_y = {box['sy']}\nsize_z = {box['sz']}\nout = {arq_out}\ncpu = 1\n")
        
        subprocess.run([CAMINHO_VINA, "--config", arq_conf], stdout=open(arq_log, "w"), stderr=subprocess.STDOUT)
        with open(arq_log, "r") as f:
            for linha in f:
                if "   1 " in linha:
                    energias[receptor.replace('receptor_', '')] = float(linha.split()[1])
                    break
                    
        if os.path.exists(arq_conf): os.remove(arq_conf)
        if os.path.exists(arq_log): os.remove(arq_log)
        if os.path.exists(arq_out): os.remove(arq_out)
        
    if os.path.exists(pdbqt_final): os.remove(pdbqt_final)
    if '4EY7' not in energias or '5W8K' not in energias: return {'SMILES': row['SMILES'], 'Status': 'Erro'}
    return energias

def rodar_proxima_geracao():
    if not os.path.exists(ARQUIVO_MESTRE):
        print("✕ Banco Mestre não encontrado!"); return

    df_mestre = pd.read_csv(ARQUIVO_MESTRE)
    if len(df_mestre) == 0:
        print("✕ Banco Mestre vazio."); return

    if '1EVE_Eficacia' in df_mestre.columns:
        df_mestre.rename(columns={'1EVE_Eficacia': '4EY7_Eficacia'}, inplace=True)

    try:
        geracoes_anteriores = df_mestre['Origem_Historica'].astype(str).str.extract(r'Gen (\d+)').dropna().astype(int)
        nova_geracao = geracoes_anteriores.max().values[0] + 1
    except: nova_geracao = 1

    print(f"\n[*] INICIANDO GERAÇÃO {nova_geracao}")
    print("  -> Treinando IA e Aprendizado Ativo (Focado no Cérebro Humano)...")
    modelo_xgb = treinar_xgboost_mestre()
    if modelo_xgb is None: return

    df_mestre['Fitness_Score'] = df_mestre.apply(lambda row: calcular_fitness(row['4EY7_Eficacia'], row['5W8K_Risco']), axis=1)
    elite = df_mestre.sort_values(by=['Fitness_Score'], ascending=True).head(10)
    sementes = elite.sample(n=min(5, len(elite)))['SMILES'].tolist()

    print(f"  -> Sementes extraídas da Elite Segura: {len(sementes)}")

    smiles_existentes = set(df_mestre['SMILES'].astype(str))
    smiles_cemiterio = carregar_cemiterio()
    smiles_proibidos = smiles_existentes.union(smiles_cemiterio)
    novos_smiles = set()

    # OTIMIZAÇÃO: REPRODUÇÃO SEXUADA (ALGORITMO BRICS)
    fragmentos_farmacologicos = set()
    for s in sementes:
        m = Chem.MolFromSmiles(s)
        if m: fragmentos_farmacologicos.update(BRICS.BRICSDecompose(m))
    
    frags_mols = [Chem.MolFromSmiles(f) for f in fragmentos_farmacologicos if f]
    construtor_brics = BRICS.BRICSBuild(frags_mols)
    
    contador_brics = 0
    for mol_hibrida in construtor_brics:
        if contador_brics > 100: break 
        try:
            mol_hibrida.UpdatePropertyCache(strict=True)
            Chem.SanitizeMol(mol_hibrida)
            s = Chem.MolToSmiles(mol_hibrida, canonical=True)
            if s: novos_smiles.add(s)
            contador_brics += 1
        except: pass

    # Mutações Radicais e Virtuais
    todas_reacoes = {**reacoes_virtuais, **reacoes_radicais}
    for smiles_base in sementes:
        mol_base = Chem.MolFromSmiles(smiles_base)
        if mol_base is None: continue
        for _ in range(25):
            mol_atual = Chem.Mol(mol_base)
            for passos in range(random.randint(1, 4)):
                try:
                    nome, smarts = random.choice(list(todas_reacoes.items()))
                    rxn = AllChem.ReactionFromSmarts(smarts)
                    if rxn:
                        prods = rxn.RunReactants((mol_atual,))
                        if prods:
                            mol_atual = prods[0][0]; Chem.SanitizeMol(mol_atual)
                            s = Chem.MolToSmiles(mol_atual, canonical=True)
                            if s: novos_smiles.add(s)
                except: break

    print(f"  -> Mutações e Híbridos BRICS gerados: {len(novos_smiles)}")
    novos_smiles = [s for s in novos_smiles if s not in smiles_proibidos]
    print(f"  -> Novos candidatos inéditos brutos: {len(novos_smiles)}")

    if len(novos_smiles) == 0:
        print("✕ Nenhuma molécula inédita encontrada."); gc.collect(); return

    # O FUNIL INDUSTRIAL (ADMET)
    smiles_filtrados = []
    for s in novos_smiles:
        try:
            mol = Chem.MolFromSmiles(s)
            if mol is None: continue
            
            invalido = False
            for padrao in PADROES_PROIBIDOS:
                if padrao and mol.HasSubstructMatch(padrao):
                    invalido = True; break
            if invalido: continue
            if catalogo_toxico.HasMatch(mol): continue
            if QED.qed(mol) < 0.35: continue 
            
            mw = Descriptors.MolWt(mol)
            if mw < 100 or mw > 600: continue 
            if Descriptors.NumHDonors(mol) > 5: continue
            if Descriptors.NumHAcceptors(mol) > 10: continue
            if Descriptors.TPSA(mol) > 90: continue 
            logp = Descriptors.MolLogP(mol)
            if logp < 0 or logp > 5: continue 
            if Descriptors.NumRotatableBonds(mol) > 10: continue 
            if mol.GetNumAtoms() > 80: continue
            
            mol_3d = Chem.AddHs(mol)
            if AllChem.EmbedMolecule(mol_3d, randomSeed=42) == -1: continue
                
            smiles_filtrados.append(s)
        except: pass

    print(f"  -> Sobreviventes do Funil Industrial (Aprovados SNC): {len(smiles_filtrados)}")

    if len(smiles_filtrados) == 0:
        print("✕ Choque de Realidade: Nenhuma molécula passou nos critérios BBB/Tox. Tentando novamente na próxima."); gc.collect(); return

    # APRENDIZADO ATIVO (UCB)
    fps_elite = [AllChem.GetMorganFingerprintAsBitVect(Chem.MolFromSmiles(s), 2, 2048) for s in sementes if Chem.MolFromSmiles(s)]
    fps_novos, smiles_validos = [], []
    
    for s in smiles_filtrados:
        try:
            mol = Chem.MolFromSmiles(s)
            fps_novos.append(AllChem.GetMorganFingerprintAsBitVect(mol, 2, 2048))
            smiles_validos.append(s)
        except: pass

    if len(fps_novos) == 0: gc.collect(); return

    X_novos = np.array(fps_novos)
    predicoes = modelo_xgb.predict(X_novos)

    df_pred = pd.DataFrame({'SMILES': smiles_validos, 'Previsao_IA': predicoes})
    
    incertezas = []
    for fp in fps_novos:
        sims = DataStructs.BulkTanimotoSimilarity(fp, fps_elite)
        distancia = 1.0 - (max(sims) if sims else 1.0)
        incertezas.append(distancia)
        
    df_pred['Incerteza_Alienigena'] = incertezas
    
    # Ajuste fino da IA para focar mais em otimização do que exploração caótica
    peso_exploracao = 0.5 
    df_pred['Score_UCB'] = df_pred['Previsao_IA'] - (df_pred['Incerteza_Alienigena'] * peso_exploracao)
    df_pred.sort_values('Score_UCB', ascending=True, inplace=True)

    top_candidatos = df_pred.head(15).reset_index(drop=True)
    print(f"  -> Top {len(top_candidatos)} enviadas ao Vina Físico (hAChE Humana)")

    tarefas = [(i, row, nova_geracao) for i, row in top_candidatos.iterrows()]
    resultados_finais, falhas_desta_rodada = [], []
    workers = max(2, int((os.cpu_count() or 4) * 0.8))

    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        for res in executor.map(worker_docking, tarefas):
            if res['Status'] == 'Sucesso':
                # Renomeando as chaves para bater com as colunas oficiais
                res['4EY7_Eficacia'] = res['4EY7']
                res['5W8K_Risco'] = res['5W8K']
                res['Indice_Seletividade'] = res['5W8K_Risco'] - res['4EY7_Eficacia']
                res['Fitness_Score'] = calcular_fitness(res['4EY7_Eficacia'], res['5W8K_Risco'])
                
                del res['4EY7']; del res['5W8K']; del res['Status']
                resultados_finais.append(res)
                print(f"     ✓ Validado Fisicamente: 4EY7 (hAChE) = {res['4EY7_Eficacia']} | hERG = {res['5W8K_Risco']} | Nota: {res['Fitness_Score']:.2f}")
            else:
                falhas_desta_rodada.append(res['SMILES'])
                print(f"     ✕ Geometria 3D colapsada na Tensão Física (Cemitério)")

    adicionar_ao_cemiterio(falhas_desta_rodada)

    if len(resultados_finais) == 0:
        print("\n✕ Física reprovou os candidatos."); gc.collect(); return

    df_novos = pd.DataFrame(resultados_finais)
    df_final = pd.concat([df_mestre, df_novos], ignore_index=True)
    df_final.drop_duplicates(subset=['SMILES'], keep='first', inplace=True)
    
    df_final['Fitness_Score'] = df_final.apply(lambda row: calcular_fitness(row['4EY7_Eficacia'], row['5W8K_Risco']), axis=1)
    df_final.sort_values(by=['Fitness_Score'], ascending=True, inplace=True)
    df_final.reset_index(drop=True, inplace=True)
    df_final['ID_Mestre'] = [f"MOL_{i:05d}" for i in range(1, len(df_final) + 1)]

    colunas_presentes = [col for col in COLUNAS_OFICIAIS if col in df_final.columns]
    df_final = df_final[colunas_presentes]

    try:
        df_final.to_csv(ARQUIVO_MESTRE, index=False)
        if os.path.exists(ARQUIVO_MESTRE): shutil.copy2(ARQUIVO_MESTRE, ARQUIVO_MESTRE + ".bak")
        print(f"\n✓ GERAÇÃO {nova_geracao} SINTETIZADA COM SUCESSO (Arquitetura Humana)")
        print(f"✓ {len(df_novos)} novos compostos perfeitamente viáveis adicionados!")
    except PermissionError:
        recuperacao = f"banco_mestre_recuperado_Gen{nova_geracao}.csv"
        df_final.to_csv(recuperacao, index=False)
        print(f"\n[!!!] ERRO CRÍTICO: Feche o Excel. Salvo em: {recuperacao}")

    gc.collect()

def exibir_ranking():
    if not os.path.exists(ARQUIVO_MESTRE):
        print("\n✕ Banco Mestre não encontrado."); return
        
    df = pd.read_csv(ARQUIVO_MESTRE)
    salvar_necessario = False
    
    if '1EVE_Eficacia' in df.columns:
        df.rename(columns={'1EVE_Eficacia': '4EY7_Eficacia'}, inplace=True)
        salvar_necessario = True
        
    if 'Fitness_Score' not in df.columns or salvar_necessario:
        df['Fitness_Score'] = df.apply(lambda row: calcular_fitness(row['4EY7_Eficacia'], row['5W8K_Risco']), axis=1)
        salvar_necessario = True
        
    df.sort_values('Fitness_Score', ascending=True, inplace=True)
    
    if salvar_necessario:
        df.reset_index(drop=True, inplace=True)
        df['ID_Mestre'] = [f"MOL_{i:05d}" for i in range(1, len(df)+1)]
        colunas_presentes = [col for col in COLUNAS_OFICIAIS if col in df.columns]
        df = df[colunas_presentes]
        try: df.to_csv(ARQUIVO_MESTRE, index=False); print("[✓] Banco atualizado para hAChE!")
        except: pass

    print("\n" + "="*85)
    print(" 🏆 HALL DA FAMA (hAChE Humana e MURALHA CARDÍACA) - BANCO MESTRE")
    print("="*85)
    for i, row in df.head(10).iterrows():
        print(f"{i+1:02d}. {row['ID_Mestre']} | Efic(4EY7): {row['4EY7_Eficacia']:8.3f} | Risco hERG: {row['5W8K_Risco']:8.3f} | Nota Final: {row['Fitness_Score']:6.2f}")
    print("="*85)

if __name__ == '__main__':
    if not os.path.exists(PASTA_TESTE): os.makedirs(PASTA_TESTE)
    
    # Preparar o receptor humano se ele ainda não estiver no formato pdbqt
    if not os.path.exists("4EY7.pdbqt") and os.path.exists("4EY7.pdb"):
        print("[*] Convertendo o cristal humano 4EY7.pdb para 4EY7.pdbqt pela primeira vez...")
        subprocess.run(["obabel", "4EY7.pdb", "-O", "4EY7.pdbqt", "-xr"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
    while True:
        print("\n" + "="*45)
        print(" 🧬 TERMINAL EVOLUTIVO (V28 - hAChE Humana) 🧬")
        print("="*45)
        print("[1] 🚀 Sintetizar Próximas Gerações (Auto-Loop)")
        print("[2] 📊 Ver Hall da Fama (Top 10)")
        print("[3] ❌ Sair")
        
        escolha = input("\nSelecione uma opção (1-3): ")
        if escolha == '1':
            try:
                n_loops = input("Quantas gerações deseja rodar em sequência? (Enter para 1): ")
                n_loops = int(n_loops) if n_loops.strip() else 1
            except ValueError:
                print("✕ Entrada inválida. Rodando 1 geração.")
                n_loops = 1
                
            for i in range(n_loops):
                if n_loops > 1:
                    print(f"\n" + "▼"*50)
                    print(f" 🔄 INICIANDO CICLO {i+1} DE {n_loops} ")
                    print("▲"*50)
                rodar_proxima_geracao()
                
        elif escolha == '2': exibir_ranking()
        elif escolha == '3': break
        else: print("Opção inválida.")