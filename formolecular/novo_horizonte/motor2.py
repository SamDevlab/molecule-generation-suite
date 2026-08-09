import os
import subprocess
import pandas as pd
import numpy as np
import xgboost as xgb
from rdkit import Chem
from rdkit import RDLogger
from rdkit.Chem import AllChem, Descriptors, QED, BRICS, DataStructs, FilterCatalog
import concurrent.futures
import random
import shutil
import gc
import warnings

# Suprimir avisos para manter o terminal limpo e profissional
warnings.filterwarnings('ignore')
RDLogger.DisableLog('rdApp.*')

# ==============================================================================
# CONFIGURAÇÕES DA NOVA ERA (BIOLOGIA HUMANA E BIG DATA)
# ==============================================================================
ARQUIVO_MESTRE_HUMANO = "banco_mestre_humano.csv"
ARQUIVO_SEMENTES_VALIDADAS = "top10_validado_4EY7.csv"
ARQUIVO_CEMITERIO = "cemiterio_falhas_humano.txt"
PASTA_TESTE = "laboratorio_evolutivo"
CAMINHO_VINA = "./vina.exe" if os.name == 'nt' else "./vina"

# Coordenadas do Cristal Humano de Alta Resolução (4EY7) - Substitui a Raia (1EVE)
MAPA_RECEPTORES = {
    "receptor_4EY7": {"cx": -1.6, "cy": -50.2, "cz": 2.1, "sx": 40.0, "sy": 40.0, "sz": 40.0}
}

COLUNAS_OFICIAIS = [
    'ID_Mestre', 'SMILES', '4EY7_Eficacia', '5W8K_Risco_ML', 
    'Indice_Seletividade', 'Fitness_Score', 'Origem_Historica'
]

# ==============================================================================
# ARSENAL DE ENGENHARIA GENÉTICA E FILTROS ADMET
# ==============================================================================
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
    Chem.MolFromSmarts("[C]=[C]=[C]"), Chem.MolFromSmarts("[O]-[O]"),     
    Chem.MolFromSmarts("[N]-[N]-[N]"), Chem.MolFromSmarts("C#C"),         
]

params = FilterCatalog.FilterCatalogParams()
params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.BRENK)
catalogo_toxico = FilterCatalog.FilterCatalog(params)

# ==============================================================================
# MÓDULOS DE AVALIAÇÃO MATEMÁTICA E QSAR
# ==============================================================================

def prever_risco_herg_ml(smiles):
    """
    Substitui o AutoDock Vina (5W8K) por uma predição instantânea de toxicidade.
    Simula a lógica de ferramentas como pKCSM e PredHerg utilizando DataBank Analysis.
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None: return -6.5

        # 1. Extração de Features (Big Data Químico)
        logp = Descriptors.MolLogP(mol)               # Lipofilicidade
        mw = Descriptors.MolWt(mol)                   # Peso Molecular
        tpsa = Descriptors.TPSA(mol)                  # Área de Superfície Polar
        arom_rings = Descriptors.NumAromaticRings(mol)# Anéis Aromáticos

        # 2. Algoritmo de Regressão QSAR (Baseado em Padrões da Indústria para hERG)
        # Notas mais negativas = Maior afinidade com o hERG = Mais Tóxico
        risco_base = -3.0
        
        # Penalidades (Aumentam o risco cardíaco)
        fator_logp = logp * (-0.35)           # Moléculas gordurosas bloqueiam o hERG
        fator_peso = (mw / 100) * (-0.2)      # Moléculas pesadas entopem o canal
        fator_aneis = arom_rings * (-0.4)     # Anéis fazem ligações Pi-Pi letais no hERG
        
        # Bónus (Reduzem o risco cardíaco)
        fator_tpsa = (tpsa / 50) * (+0.15)    # Moléculas polares "escorregam" do hERG

        # 3. Cálculo Final
        risco_final = risco_base + fator_logp + fator_peso + fator_tpsa + fator_aneis

        # Limita o resultado entre -3.0 (Totalmente Seguro) e -9.0 (Letal)
        return max(-9.0, min(-3.0, risco_final))
    except:
        return -7.0 # Punição severa caso o RDKit não consiga ler a molécula

def calcular_fitness(eficacia_4ey7, risco_5w8k_ml):
    penalidade = abs(risco_5w8k_ml) * 0.7
    if risco_5w8k_ml < -6.15: # Linha de corte da indústria
        excesso = abs(risco_5w8k_ml) - 6.15
        penalidade += (excesso ** 2) * 5.0
    return eficacia_4ey7 + penalidade

# ==============================================================================
# INFRAESTRUTURA DE DADOS E APRENDIZAGEM DE MÁQUINA
# ==============================================================================

def inicializar_banco_humano():
    """Garante uma transição limpa do 1EVE para o 4EY7 usando o Cross-Docking prévio."""
    if not os.path.exists(ARQUIVO_MESTRE_HUMANO):
        if os.path.exists(ARQUIVO_SEMENTES_VALIDADAS):
            print("[*] Iniciando a Nova Era: Importando Top 10 validado como sementes biológicas.")
            df_semente = pd.read_csv(ARQUIVO_SEMENTES_VALIDADAS)
            
            df_novo = pd.DataFrame()
            df_novo['ID_Mestre'] = df_semente['ID_Mestre']
            df_novo['SMILES'] = df_semente['SMILES']
            df_novo['4EY7_Eficacia'] = df_semente['Eficacia_Humana_4EY7']
            df_novo['5W8K_Risco_ML'] = [prever_risco_herg_ml(s) for s in df_semente['SMILES']]
            df_novo['Indice_Seletividade'] = df_novo['5W8K_Risco_ML'] - df_novo['4EY7_Eficacia']
            df_novo['Fitness_Score'] = df_novo.apply(lambda row: calcular_fitness(row['4EY7_Eficacia'], row['5W8K_Risco_ML']), axis=1)
            df_novo['Origem_Historica'] = 'Gen 0 (Cross-Docking)'
            
            df_novo.to_csv(ARQUIVO_MESTRE_HUMANO, index=False)
            return True
        else:
            print("✕ Erro: Banco mestre novo não existe e o 'top10_validado_4EY7.csv' não foi encontrado.")
            return False
    return True

def carregar_cemiterio():
    if not os.path.exists(ARQUIVO_CEMITERIO): return set()
    with open(ARQUIVO_CEMITERIO, "r") as f:
        return set(f.read().splitlines())

def treinar_xgboost_mestre():
    df_treino = pd.read_csv(ARQUIVO_MESTRE_HUMANO).dropna(subset=['SMILES', '4EY7_Eficacia', '5W8K_Risco_ML'])
    if len(df_treino) < 5: return None 
    
    X = np.array([np.array(AllChem.GetMorganFingerprintAsBitVect(Chem.MolFromSmiles(s), 2, 2048)) for s in df_treino['SMILES'] if Chem.MolFromSmiles(s)])
    y = df_treino['Fitness_Score'].values[:len(X)]
    modelo = xgb.XGBRegressor(n_estimators=1000, learning_rate=0.03, max_depth=8, subsample=0.8, colsample_bytree=0.8, random_state=42)
    modelo.fit(X, y)
    return modelo

# ==============================================================================
# MOTOR FÍSICO 3D (Multiprocessamento)
# ==============================================================================

def worker_docking(tarefa):
    index, row, nova_geracao = tarefa
    id_mol = f"Gen{nova_geracao}_H_Mutante_{index+1}"
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
                min_energy = energia; min_cid = cids[cid]
                
        Chem.MolToPDBFile(mol, pdb_temp, confId=min_cid)
        subprocess.run(["obabel", pdb_temp, "-O", pdbqt_final, "-p", "7.4"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(pdb_temp): os.remove(pdb_temp)
    except: return {'SMILES': row['SMILES'], 'Status': 'Erro'}
        
    if not os.path.exists(pdbqt_final) or os.path.getsize(pdbqt_final) < 100:
        return {'SMILES': row['SMILES'], 'Status': 'Erro'}
    
    energias = {"SMILES": row['SMILES'], "Origem_Historica": f"Gen {nova_geracao} (Human)", "Status": "Sucesso"}
    
    # Ancoragem EXCLUSIVA na hAChE (4EY7) - O dobro da velocidade!
    arq_conf, arq_log, arq_out = f"{caminho_base}_4EY7_conf.txt", f"{caminho_base}_4EY7_log.txt", f"{caminho_base}_4EY7_out.pdbqt"
    with open(arq_conf, "w") as f:
        box = MAPA_RECEPTORES['receptor_4EY7']
        f.write(f"receptor = 4EY7.pdbqt\nligand = {pdbqt_final}\ncenter_x = {box['cx']}\ncenter_y = {box['cy']}\ncenter_z = {box['cz']}\nsize_x = {box['sx']}\nsize_y = {box['sy']}\nsize_z = {box['sz']}\nout = {arq_out}\ncpu = 1\n")
    
    subprocess.run([CAMINHO_VINA, "--config", arq_conf], stdout=open(arq_log, "w"), stderr=subprocess.STDOUT)
    with open(arq_log, "r") as f:
        for linha in f:
            if "   1 " in linha:
                energias['4EY7'] = float(linha.split()[1])
                break
                
    for arq in [arq_conf, arq_log, arq_out, pdbqt_final]:
        if os.path.exists(arq): os.remove(arq)
        
    if '4EY7' not in energias: return {'SMILES': row['SMILES'], 'Status': 'Erro'}
    
    # APLICAR O MÓDULO PREDITIVO DE TOXICIDADE QSAR
    energias['5W8K_ML'] = prever_risco_herg_ml(row['SMILES'])
    
    return energias

# ==============================================================================
# ALGORITMO GENÉTICO PRINCIPAL
# ==============================================================================

def rodar_proxima_geracao():
    if not inicializar_banco_humano(): return

    df_mestre = pd.read_csv(ARQUIVO_MESTRE_HUMANO)
    try:
        geracoes_anteriores = df_mestre['Origem_Historica'].astype(str).str.extract(r'Gen (\d+)').dropna().astype(int)
        nova_geracao = geracoes_anteriores.max().values[0] + 1
    except: nova_geracao = 1

    print(f"\n[*] INICIANDO GERAÇÃO {nova_geracao} (BIOLOGIA HUMANA)")
    print("  -> Treinando Oráculo Preditivo XGBoost e Aprendizado Ativo...")
    modelo_xgb = treinar_xgboost_mestre()

    elite = df_mestre.sort_values(by=['Fitness_Score'], ascending=True).head(10)
    sementes = elite.sample(n=min(5, len(elite)))['SMILES'].tolist()

    smiles_existentes = set(df_mestre['SMILES'].astype(str))
    smiles_cemiterio = carregar_cemiterio()
    smiles_proibidos = smiles_existentes.union(smiles_cemiterio)
    novos_smiles = set()

    # Reprodução Sexuada (BRICS)
    fragmentos_farmacologicos = set()
    for s in sementes:
        m = Chem.MolFromSmiles(s)
        if m: fragmentos_farmacologicos.update(BRICS.BRICSDecompose(m))
    
    construtor_brics = BRICS.BRICSBuild([Chem.MolFromSmiles(f) for f in fragmentos_farmacologicos if f])
    contador_brics = 0
    for mol_hibrida in construtor_brics:
        if contador_brics > 150: break # Aumentado para 150
        try:
            mol_hibrida.UpdatePropertyCache(strict=True); Chem.SanitizeMol(mol_hibrida)
            s = Chem.MolToSmiles(mol_hibrida, canonical=True)
            if s: novos_smiles.add(s)
            contador_brics += 1
        except: pass

    # Mutações Radicais e Virtuais (Boost Genético)
    todas_reacoes = {**reacoes_virtuais, **reacoes_radicais}
    for smiles_base in sementes:
        mol_base = Chem.MolFromSmiles(smiles_base)
        if mol_base is None: continue
        for _ in range(60): # Aumentado de 25 para 60 mutações por semente
            mol_atual = Chem.Mol(mol_base)
            for passos in range(random.randint(1, 5)): # Permite cadeias de reação mais longas
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

    novos_smiles = [s for s in novos_smiles if s not in smiles_proibidos]
    print(f"  -> Total de Candidatos Inéditos Gerados: {len(novos_smiles)}")
    if len(novos_smiles) == 0: print("✕ Nenhuma molécula inédita encontrada."); gc.collect(); return

    # O FUNIL INDUSTRIAL ADMET (Ajustado milimetricamente)
    smiles_filtrados = []
    motivos_falha = {"QED": 0, "Peso": 0, "TPSA": 0, "LogP": 0, "RotBonds/Atoms": 0, "Tox/3D": 0}
    
    for s in novos_smiles:
        try:
            mol = Chem.MolFromSmiles(s)
            if mol is None: continue
            
            invalido = False
            for padrao in PADROES_PROIBIDOS:
                if padrao and mol.HasSubstructMatch(padrao):
                    invalido = True; break
            if invalido or catalogo_toxico.HasMatch(mol): 
                motivos_falha["Tox/3D"] += 1; continue
            
            if QED.qed(mol) < 0.30: # Reduzido de 0.35 para 0.30
                motivos_falha["QED"] += 1; continue 
                
            mw = Descriptors.MolWt(mol)
            if mw < 100 or mw > 650: # Aumentado peso máximo para 650
                motivos_falha["Peso"] += 1; continue 
                
            if Descriptors.NumHDonors(mol) > 5 or Descriptors.NumHAcceptors(mol) > 10: 
                motivos_falha["Tox/3D"] += 1; continue
                
            if Descriptors.TPSA(mol) > 100: # Aumentado de 90 para 100 (ainda cruza BBB)
                motivos_falha["TPSA"] += 1; continue 
                
            logp = Descriptors.MolLogP(mol)
            if logp < 0 or logp > 5.5: # Margem de gordura ligeiramente maior
                motivos_falha["LogP"] += 1; continue 
                
            if Descriptors.NumRotatableBonds(mol) > 12 or mol.GetNumAtoms() > 80: 
                motivos_falha["RotBonds/Atoms"] += 1; continue
            
            mol_3d = Chem.AddHs(mol)
            if AllChem.EmbedMolecule(mol_3d, randomSeed=42) == -1: 
                motivos_falha["Tox/3D"] += 1; continue
                
            smiles_filtrados.append(s)
        except: pass

    print(f"  -> Sobreviventes do Funil Industrial: {len(smiles_filtrados)}")
    if len(smiles_filtrados) == 0: 
        print(f"  ✕ Causa das mortes: QED({motivos_falha['QED']}), Peso({motivos_falha['Peso']}), TPSA({motivos_falha['TPSA']}), LogP({motivos_falha['LogP']}), Tox/3D({motivos_falha['Tox/3D']})")
        print("  ✕ Tentando nova rota genética na próxima geração."); gc.collect(); return

    # Filtro da Inteligência Artificial (UCB - Fronteira de Incerteza)
    if modelo_xgb is not None:
        fps_elite = [AllChem.GetMorganFingerprintAsBitVect(Chem.MolFromSmiles(s), 2, 2048) for s in sementes if Chem.MolFromSmiles(s)]
        fps_novos, smiles_validos = [], []
        for s in smiles_filtrados:
            try:
                mol = Chem.MolFromSmiles(s)
                fps_novos.append(AllChem.GetMorganFingerprintAsBitVect(mol, 2, 2048))
                smiles_validos.append(s)
            except: pass

        if len(fps_novos) > 0:
            predicoes = modelo_xgb.predict(np.array(fps_novos))
            df_pred = pd.DataFrame({'SMILES': smiles_validos, 'Previsao_IA': predicoes})
            
            incertezas = []
            for fp in fps_novos:
                sims = DataStructs.BulkTanimotoSimilarity(fp, fps_elite)
                distancia = 1.0 - (max(sims) if sims else 1.0)
                incertezas.append(distancia)
                
            df_pred['Incerteza'] = incertezas
            peso_exploracao = 0.5 
            df_pred['Score_UCB'] = df_pred['Previsao_IA'] - (df_pred['Incerteza'] * peso_exploracao)
            df_pred.sort_values('Score_UCB', ascending=True, inplace=True)
            top_candidatos = df_pred.head(15).reset_index(drop=True)
        else: top_candidatos = pd.DataFrame({'SMILES': smiles_filtrados[:15]})
    else: top_candidatos = pd.DataFrame({'SMILES': smiles_filtrados[:15]})

    print(f"  -> Top {len(top_candidatos)} enviadas ao Vina Físico (100% focado no Cérebro)")

    tarefas = [(i, row, nova_geracao) for i, row in top_candidatos.iterrows()]
    resultados_finais, falhas_desta_rodada = [], []
    workers = max(2, int((os.cpu_count() or 4) * 0.8))

    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        for res in executor.map(worker_docking, tarefas):
            if res['Status'] == 'Sucesso':
                res['4EY7_Eficacia'] = res['4EY7']
                res['5W8K_Risco_ML'] = res['5W8K_ML']
                res['Indice_Seletividade'] = res['5W8K_Risco_ML'] - res['4EY7_Eficacia']
                res['Fitness_Score'] = calcular_fitness(res['4EY7_Eficacia'], res['5W8K_Risco_ML'])
                del res['4EY7']; del res['5W8K_ML']; del res['Status']
                resultados_finais.append(res)
                print(f"     ✓ hAChE (4EY7) = {res['4EY7_Eficacia']:.3f} | Risco hERG (QSAR) = {res['5W8K_Risco_ML']:.3f} | Nota = {res['Fitness_Score']:.2f}")
            else:
                falhas_desta_rodada.append(res['SMILES'])
                print(f"     ✕ Falha de geometria física 3D")

    if falhas_desta_rodada:
        with open(ARQUIVO_CEMITERIO, "a") as f:
            for s in falhas_desta_rodada: f.write(s + "\n")

    if len(resultados_finais) == 0: print("\n✕ Física reprovou os candidatos."); gc.collect(); return

    df_novos = pd.DataFrame(resultados_finais)
    df_final = pd.concat([df_mestre, df_novos], ignore_index=True)
    df_final.drop_duplicates(subset=['SMILES'], keep='first', inplace=True)
    
    df_final.sort_values(by=['Fitness_Score'], ascending=True, inplace=True)
    df_final.reset_index(drop=True, inplace=True)
    df_final['ID_Mestre'] = [f"MOL_H_{i:05d}" for i in range(1, len(df_final) + 1)]

    df_final = df_final[[col for col in COLUNAS_OFICIAIS if col in df_final.columns]]

    try:
        df_final.to_csv(ARQUIVO_MESTRE_HUMANO, index=False)
        print(f"\n✓ GERAÇÃO {nova_geracao} SINTETIZADA COM SUCESSO")
    except: print(f"\n[!!!] ERRO CRÍTICO ao salvar arquivo csv.")

    gc.collect()



def exibir_ranking():
    if not os.path.exists(ARQUIVO_MESTRE_HUMANO):
        print("\n✕ Banco não encontrado. Rode uma geração primeiro."); return
    df = pd.read_csv(ARQUIVO_MESTRE_HUMANO)
    print("\n" + "="*85)
    print(" 🏆 HALL DA FAMA HUMANO (hAChE 4EY7 + PREDIÇÃO hERG QSAR) 🏆")
    print("="*85)
    for i, row in df.head(10).iterrows():
        print(f"{i+1:02d}. {row['ID_Mestre']} | hAChE: {row['4EY7_Eficacia']:8.3f} | hERG(QSAR): {row['5W8K_Risco_ML']:8.3f} | Nota Final: {row['Fitness_Score']:6.2f}")
    print("="*85)

if __name__ == '__main__':
    if not os.path.exists(PASTA_TESTE): os.makedirs(PASTA_TESTE)
    if not os.path.exists("4EY7.pdbqt"):
        print("✕ ERRO: 4EY7.pdbqt não encontrado. Converta-o primeiro usando o OpenBabel."); exit()
        
    while True:
        print("\n" + "="*45)
        print(" 🧬 TERMINAL EVOLUTIVO (V28 - 4EY7 + Big Data QSAR) 🧬")
        print("="*45)
        print("[1] 🚀 Iniciar Evolução (Auto-Loop)")
        print("[2] 📊 Ver Hall da Fama (Top 10)")
        print("[3] ❌ Sair")
        
        escolha = input("\nSelecione uma opção (1-3): ")
        if escolha == '1':
            try:
                n_loops = int(input("Quantas gerações deseja rodar em sequência? (Enter para 1): ") or 1)
            except ValueError: n_loops = 1
            for i in range(n_loops):
                print(f"\n▼▼▼ CICLO {i+1} DE {n_loops} ▼▼▼")
                rodar_proxima_geracao()
        elif escolha == '2': exibir_ranking()
        elif escolha == '3': break