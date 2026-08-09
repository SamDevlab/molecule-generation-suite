import os
import subprocess
import pandas as pd
from rdkit import Chem
from rdkit.Chem import AllChem
import warnings

# Suprimir avisos do Pandas
warnings.filterwarnings('ignore')

ARQUIVO_MESTRE = "banco_mestre_unificado.csv"
CSV_TOP10 = "top10_isolado.csv"
CSV_VALIDADO = "top10_validado_4EY7.csv"
CAMINHO_VINA = "./vina.exe" if os.name == 'nt' else "./vina"

# Coordenadas do cristal humano
MAPA_4EY7 = {"cx": -1.6, "cy": -50.2, "cz": 2.1, "sx": 40.0, "sy": 40.0, "sz": 40.0}

def isolar_e_redock():
    if not os.path.exists(ARQUIVO_MESTRE):
        print(f"✕ Erro: O arquivo '{ARQUIVO_MESTRE}' não foi encontrado.")
        return

    df = pd.read_csv(ARQUIVO_MESTRE)
    
    # Deteta inteligentemente o nome da coluna para evitar o KeyError
    col_eficacia = '1EVE_Eficacia' if '1EVE_Eficacia' in df.columns else '4EY7_Eficacia'
    
    if 'Fitness_Score' not in df.columns:
        print("✕ Erro: Coluna 'Fitness_Score' não encontrada no banco de dados.")
        return
        
    # Ordena e isola o Top 10
    df.sort_values('Fitness_Score', ascending=True, inplace=True)
    top10 = df.head(10).copy()
    
    # Cria o novo CSV separado apenas com a Elite
    top10.to_csv(CSV_TOP10, index=False)
    print(f"\n[✓] Top 10 isolado com sucesso no ficheiro: {CSV_TOP10}")

    print("\n" + "="*85)
    print(" 🔬 INICIANDO CROSS-DOCKING (RAIA -> HUMANO 4EY7) NO CSV ISOLADO 🔬")
    print("="*85)

    resultados_validados = []

    for i, row in top10.iterrows():
        id_mol = row['ID_Mestre']
        smiles = row['SMILES']
        nota_antiga = row[col_eficacia]
        risco_herg = row['5W8K_Risco']
        
        pdb_temp = f"{id_mol}_temp.pdb"
        pdbqt_final = f"{id_mol}_temp.pdbqt"
        arq_conf = f"{id_mol}_conf.txt"
        arq_log = f"{id_mol}_log.txt"
        arq_out = f"{id_mol}_out.pdbqt"

        try:
            # Prepara a molécula 3D
            mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
            AllChem.EmbedMolecule(mol, randomSeed=42)
            AllChem.MMFFOptimizeMolecule(mol)
            Chem.MolToPDBFile(mol, pdb_temp)
            subprocess.run(["obabel", pdb_temp, "-O", pdbqt_final, "-p", "7.4"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Ancoragem exclusiva no 4EY7
            with open(arq_conf, "w") as f:
                f.write(f"receptor = 4EY7.pdbqt\nligand = {pdbqt_final}\ncenter_x = {MAPA_4EY7['cx']}\ncenter_y = {MAPA_4EY7['cy']}\ncenter_z = {MAPA_4EY7['cz']}\nsize_x = {MAPA_4EY7['sx']}\nsize_y = {MAPA_4EY7['sy']}\nsize_z = {MAPA_4EY7['sz']}\nout = {arq_out}\ncpu = 1\n")
            
            subprocess.run([CAMINHO_VINA, "--config", arq_conf], stdout=open(arq_log, "w"), stderr=subprocess.STDOUT)
            
            nova_nota_4ey7 = None
            with open(arq_log, "r") as f:
                for linha in f:
                    if "   1 " in linha:
                        nova_nota_4ey7 = float(linha.split()[1])
                        break
            
            # Avalia a diferença
            if nova_nota_4ey7:
                diferenca = nova_nota_4ey7 - nota_antiga
                sinal = "Piorou" if diferenca > 0 else "Melhorou"
                print(f"[{id_mol}] Raia (Antigo): {nota_antiga:7.3f} | Humano (Novo): {nova_nota_4ey7:7.3f} -> {sinal} ({diferenca:+.3f})")
                
                # Guarda os dados corrigidos
                row_validada = row.copy()
                row_validada['Eficacia_Humana_4EY7'] = nova_nota_4ey7
                row_validada['Diferenca_Bio'] = diferenca
                
                # Recalcula a nota final de forma justa
                penalidade = abs(risco_herg) * 0.7
                if risco_herg < -6.15:
                    penalidade += ((abs(risco_herg) - 6.15) ** 2) * 5.0
                row_validada['Novo_Fitness_Score'] = nova_nota_4ey7 + penalidade
                
                resultados_validados.append(row_validada)
            else:
                print(f"[{id_mol}] Falha no ancoramento com 4EY7.")

        except Exception as e:
            print(f"[{id_mol}] Erro de processamento: {e}")
        
        # Limpeza de ficheiros temporários
        for arq in [pdb_temp, pdbqt_final, arq_conf, arq_log, arq_out]:
            if os.path.exists(arq): os.remove(arq)

    print("="*85)
    
    if resultados_validados:
        # Cria o DataFrame final com as notas validadas e reordena
        df_final = pd.DataFrame(resultados_validados)
        
        # Reorganiza as colunas para o ficheiro final ficar limpo
        colunas_ordenadas = ['ID_Mestre', 'SMILES', 'Eficacia_Humana_4EY7', '5W8K_Risco', 'Novo_Fitness_Score', 'Diferenca_Bio']
        df_final = df_final[colunas_ordenadas]
        
        df_final.sort_values('Novo_Fitness_Score', ascending=True, inplace=True)
        df_final.to_csv(CSV_VALIDADO, index=False)
        print(f"[✓] Processo finalizado! A tabela com as pontuações biológicas reais foi salva em: {CSV_VALIDADO}")

if __name__ == "__main__":
    if not os.path.exists("4EY7.pdbqt"):
        print("✕ Erro: O arquivo '4EY7.pdbqt' não foi encontrado. Execute 'obabel 4EY7.pdb -O 4EY7.pdbqt -xr' primeiro.")
    else:
        isolar_e_redock()