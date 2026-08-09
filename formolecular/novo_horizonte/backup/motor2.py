import os
import subprocess
import pandas as pd
import numpy as np
import xgboost as xgb
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit import RDLogger
import concurrent.futures
from rdkit.Chem import Descriptors
import random

RDLogger.DisableLog('rdApp.*')

# --- A ÚNICA FONTE DE VERDADE ---
ARQUIVO_MESTRE = "banco_mestre_unificado.csv"
PASTA_TESTE = "laboratorio_evolutivo"
CAMINHO_VINA = "./vina.exe" if os.name == 'nt' else "./vina"

MAPA_RECEPTORES = {
    "receptor_1EVE": {"cx": 2.8, "cy": 64.4, "cz": 67.9, "sx": 50.0, "sy": 50.0, "sz": 50.0},
    "receptor_5W8K": {"cx": 0.0, "cy": 0.0,  "cz": 0.0,  "sx": 50.0, "sy": 50.0, "sz": 50.0}
}

reacoes_virtuais = {
    "Extender": "[CX4H3;!R:1]>>[CX4H2:1]C",
    "Ramificar": "[CX4H2;!R:1]>>[CX4H1:1](C)",
    "Metilar_Anel": "[c;H1:1]>>[c:1](C)",
    "Encurtar": "[CX4H2;!R:1][CX4H3;!R:2]>>[CX4H3:1]",
    "Oxima_Cetona": "[C:1]=NO>>[C:1](=O)C",
    "Cetona_Amida": "[C:1](=O)C>>[C:1](=O)N",
    "Adicionar_Fluor": "[c;H1:1]>>[c:1](F)",
    "Trocar_Fluor_Cloro": "[F:1]>>[Cl:1]"
}

# --- FUNÇÕES INTELIGENTES BASEADAS NO BANCO MESTRE ---
def treinar_xgboost_mestre():
    if not os.path.exists(ARQUIVO_MESTRE): return None
    
    df_treino = pd.read_csv(ARQUIVO_MESTRE)
    df_treino = df_treino.dropna(subset=['SMILES', '1EVE_Eficacia'])
    
    X = np.array([np.array(AllChem.GetMorganFingerprintAsBitVect(Chem.MolFromSmiles(s), 2, 2048)) for s in df_treino['SMILES'] if Chem.MolFromSmiles(s)])
    y = df_treino['1EVE_Eficacia'].values[:len(X)]
    
    # Parâmetros agressivos para maior sensibilidade
    modelo = xgb.XGBRegressor(
        n_estimators=1000, 
        learning_rate=0.03, 
        max_depth=8, 
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42
    )
    modelo.fit(X, y)
    return modelo

def worker_docking(tarefa):
    index, row, nova_geracao = tarefa
    id_mol = f"Gen{nova_geracao}_Mutante_{index+1}"
    caminho_base = os.path.join(PASTA_TESTE, id_mol)
    pdb_temp, pdbqt_final = f"{caminho_base}.pdb", f"{caminho_base}.pdbqt"
    
    try:
        mol = Chem.AddHs(Chem.MolFromSmiles(row['SMILES']))
        AllChem.EmbedMolecule(mol, AllChem.ETKDG())
        AllChem.MMFFOptimizeMolecule(mol)
        Chem.MolToPDBFile(mol, pdb_temp)
        subprocess.run(["obabel", pdb_temp, "-O", pdbqt_final, "-p", "7.4"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(pdb_temp): os.remove(pdb_temp)
    except: return None
    
    energias = {"SMILES": row['SMILES'], "Origem_Historica": f"Gen {nova_geracao}"}
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
                    
        # Limpeza pesada para não lotar o HD
        if os.path.exists(arq_conf): os.remove(arq_conf)
        if os.path.exists(arq_log): os.remove(arq_log)
        if os.path.exists(arq_out): os.remove(arq_out)
        
    return energias if '1EVE' in energias and '5W8K' in energias else None

def rodar_proxima_geracao():

    if not os.path.exists(ARQUIVO_MESTRE):
        print("✕ Banco Mestre não encontrado!")
        return

    df_mestre = pd.read_csv(ARQUIVO_MESTRE)

    if len(df_mestre) == 0:
        print("✕ Banco Mestre vazio.")
        return

    try:
        geracoes_anteriores = (
            df_mestre['Origem_Historica']
            .astype(str)
            .str.extract(r'Gen (\d+)')
            .dropna()
            .astype(int)
        )
        nova_geracao = geracoes_anteriores.max().values[0] + 1
    except:
        nova_geracao = 1

    print(f"\n[*] INICIANDO GERAÇÃO {nova_geracao}")

    # --------------------------------------------------
    # TREINAMENTO IA
    # --------------------------------------------------
    print("  -> Treinando Oráculo XGBoost...")
    modelo_xgb = treinar_xgboost_mestre()

    if modelo_xgb is None:
        print("✕ Falha ao treinar IA.")
        return

    # --------------------------------------------------
    # ELITE GENÉTICA E DIVERSIDADE
    # --------------------------------------------------
    # Sorteia 3 moléculas do Top 10 para evitar loop infinito na mesma estrutura
    elite = df_mestre.sort_values(by=['1EVE_Eficacia', 'Indice_Seletividade'], ascending=[True, False]).head(10)
    sementes = elite.sample(n=min(3, len(elite)))['SMILES'].tolist()

    print(f"  -> Sementes extraídas da Elite para mutação: {len(sementes)}")

    smiles_existentes = set(df_mestre['SMILES'].astype(str))
    novos_smiles = set()

    # --------------------------------------------------
    # MUTAÇÃO EVOLUTIVA
    # --------------------------------------------------
    for smiles_base in sementes:
        mol = Chem.MolFromSmiles(smiles_base)
        if mol is None: continue

        for _ in range(5):
            for nome_reacao, smarts_reacao in reacoes_virtuais.items():
                try:
                    rxn = AllChem.ReactionFromSmarts(smarts_reacao)
                    if rxn is None: continue
                    produtos = rxn.RunReactants((mol,))
                    
                    for prod in produtos:
                        try:
                            filho = prod[0]
                            Chem.SanitizeMol(filho)
                            smiles_filho = Chem.MolToSmiles(filho, canonical=True)
                            if smiles_filho:
                                novos_smiles.add(smiles_filho)
                        except: pass
                except: pass

    print(f"  -> Mutações cruas geradas: {len(novos_smiles)}")

    # --------------------------------------------------
    # REMOVER DUPLICADOS DO BANCO (FILTRO INEDITISMO)
    # --------------------------------------------------
    novos_smiles = [s for s in novos_smiles if s not in smiles_existentes]

    print(f"  -> Novos candidatos inéditos absolutos: {len(novos_smiles)}")

    if len(novos_smiles) == 0:
        print("✕ Nenhuma molécula inédita encontrada. O sistema precisa de mais diversidade nas sementes.")
        return

    # --------------------------------------------------
    # FILTRO QUÍMICO BÁSICO (ADMET)
    # --------------------------------------------------
    smiles_filtrados = []
    
    for s in novos_smiles:
        try:
            mol = Chem.MolFromSmiles(s)
            if mol is None: continue
            
            mw = Descriptors.MolWt(mol)
            if mw < 100 or mw > 700: continue
                
            n_atoms = mol.GetNumAtoms()
            if n_atoms > 80: continue
                
            smiles_filtrados.append(s)
        except: pass

    print(f"  -> Após filtro químico (Lipinski bounds): {len(smiles_filtrados)}")

    if len(smiles_filtrados) == 0:
        print("✕ Nenhuma molécula passou nos filtros químicos.")
        return

    # --------------------------------------------------
    # FINGERPRINTS E IA
    # --------------------------------------------------
    fps = []
    smiles_validos = []

    for s in smiles_filtrados:
        try:
            mol = Chem.MolFromSmiles(s)
            fp = np.array(AllChem.GetMorganFingerprintAsBitVect(mol, 2, 2048))
            fps.append(fp)
            smiles_validos.append(s)
        except: pass

    if len(fps) == 0:
        print("✕ Nenhum fingerprint gerado.")
        return

    X_novos = np.array(fps)
    predicoes = modelo_xgb.predict(X_novos)

    df_pred = pd.DataFrame({'SMILES': smiles_validos, 'Previsao_IA': predicoes})
    df_pred.sort_values('Previsao_IA', ascending=True, inplace=True)

    # Mantém os 10 melhores para não estourar a CPU
    top_candidatos = df_pred.head(10).reset_index(drop=True)
    print(f"  -> Top {len(top_candidatos)} enviados ao Vina Físico")

    # --------------------------------------------------
    # DOCKING
    # --------------------------------------------------
    tarefas = [(i, row, nova_geracao) for i, row in top_candidatos.iterrows()]
    resultados_finais = []
    workers = max(2, int((os.cpu_count() or 4) * 0.8))

    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        for res in executor.map(worker_docking, tarefas):
            if res:
                res['1EVE_Eficacia'] = res['1EVE']
                res['5W8K_Risco'] = res['5W8K']
                res['Indice_Seletividade'] = res['5W8K_Risco'] - res['1EVE_Eficacia']
                del res['1EVE']
                del res['5W8K']
                
                resultados_finais.append(res)
                print(f"     ✓ Vina Finalizado: {res['1EVE_Eficacia']} kcal/mol")

    if len(resultados_finais) == 0:
        print("\n✕ Nenhum candidato validado pela física nesta rodada.")
        return

    # --------------------------------------------------
    # ATUALIZA BANCO MESTRE (COM PROTEÇÃO ANTI-CORRUPÇÃO)
    # --------------------------------------------------
    df_novos = pd.DataFrame(resultados_finais)
    df_final = pd.concat([df_mestre, df_novos], ignore_index=True)
    
    df_final.drop_duplicates(subset=['SMILES'], keep='first', inplace=True)
    
    df_final.sort_values(
        by=['1EVE_Eficacia', 'Indice_Seletividade'],
        ascending=[True, False],
        inplace=True
    )
    
    df_final.reset_index(drop=True, inplace=True)
    df_final['ID_Mestre'] = [f"MOL_{i:05d}" for i in range(1, len(df_final) + 1)]

    try:
        # Tenta salvar
        df_final.to_csv(ARQUIVO_MESTRE, index=False)
        
        # Faz um backup automático a cada geração de sucesso
        if os.path.exists(ARQUIVO_MESTRE):
            import shutil
            shutil.copy2(ARQUIVO_MESTRE, ARQUIVO_MESTRE + ".bak")
            
        print(f"\n✓ GERAÇÃO {nova_geracao} FINALIZADA E SALVA COM SUCESSO")
        print(f"✓ {len(df_novos)} novos compostos validados fisicamente adicionados")
        print(f"✓ Banco Mestre: {len(df_final)} moléculas")
        
    except PermissionError:
        # Se o Windows travar o arquivo (ex: aberto no Excel), ele não perde os dados!
        recuperacao = f"banco_mestre_recuperado_Gen{nova_geracao}.csv"
        df_final.to_csv(recuperacao, index=False)
        print(f"\n[!!!] ERRO CRÍTICO: O Windows bloqueou o arquivo '{ARQUIVO_MESTRE}' (Ele está aberto em outro programa?)")
        print(f"[!!!] Mas seus dados estão a salvo! Eles foram gravados no arquivo: {recuperacao}")

    melhor = df_final.iloc[0]
    print(f"\n🏆 Campeão Atual:")
    print(f"   {melhor['ID_Mestre']} | Origem: {melhor['Origem_Historica']}")
    print(f"   1EVE = {melhor['1EVE_Eficacia']} kcal/mol")
    print(f"   Seletividade = {melhor['Indice_Seletividade']:.2f}\n")

def exibir_ranking():
    if not os.path.exists(ARQUIVO_MESTRE):
        print("\n✕ Banco Mestre não encontrado.")
        return
    df = pd.read_csv(ARQUIVO_MESTRE).sort_values('1EVE_Eficacia', ascending=True)
    print("\n" + "="*60)
    print(" 🏆 HALL DA FAMA (TOP 10) - BANCO MESTRE UNIFICADO")
    print("="*60)
    top_10 = df.head(10)
    for i, row in top_10.iterrows():
        print(f"{i+1:02d}. {row['ID_Mestre']} | 1EVE: {row['1EVE_Eficacia']} | Sel: {row['Indice_Seletividade']:.2f} | {row['Origem_Historica']}")
    print("="*60)

if __name__ == '__main__':
    if not os.path.exists(PASTA_TESTE): os.makedirs(PASTA_TESTE)
    
    while True:
        print("\n" + "="*40)
        print(" 🧬 TERMINAL EVOLUTIVO UNIFICADO (V16) 🧬")
        print("="*40)
        print("[1] 🚀 Mudar e Testar o Campeão Atual")
        print("[2] 📊 Ver Hall da Fama (Top 10)")
        print("[3] ❌ Sair")
        
        escolha = input("\nSelecione uma opção (1-3): ")
        
        if escolha == '1': rodar_proxima_geracao()
        elif escolha == '2': exibir_ranking()
        elif escolha == '3': break
        else: print("Opção inválida.")