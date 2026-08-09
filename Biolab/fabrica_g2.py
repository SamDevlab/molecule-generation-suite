import os
import subprocess
import csv
import sys
import logging
import math
import urllib.request
from concurrent.futures import ProcessPoolExecutor, as_completed
from rdkit import Chem
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestRegressor
from fpdf import FPDF

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "esteira_industrial.log"), encoding="utf-8"), 
        logging.StreamHandler(sys.stdout)
    ]
)

# Configurações de alvos biológicos
ALVOS_COX2 = ["1cx2", "6cox"]
ALVOS_COX1 = ["4cox"]  
ALVOS_OFFTARGET = ["1w0e"] 
TODOS_ALVOS = ALVOS_COX2 + ALVOS_COX1 + ALVOS_OFFTARGET

# Infraestrutura de motores locais
PATH_VINA = os.path.join(BASE_DIR, "vina.exe")
PATH_OBABEL = r"C:\Program Files\OpenBabel-3.1.1\obabel.exe"
logging.info(f"[DIRETÓRIO] Utilizando motor Vina local da pasta Biolab: {PATH_VINA}")

# Parâmetros oficiais de ambiente e simulação científica
MAX_WORKERS = 4
REPLICATAS = 3
GRID_CONFIG = { 
    "center_x": 24.0, "center_y": 24.0, "center_z": 48.0, 
    "size_x": 20.0, "size_y": 20.0, "size_z": 20.0, 
    "exhaustiveness": 8, "cpu": 1 
}

# Arquivos de banco de dados e relatórios
ARQUIVO_MATRIZ_LIMPA = os.path.join(BASE_DIR, "matriz_compostos_filtrados.csv")
ARQUIVO_BRUTO = os.path.join(BASE_DIR, "descobertas_brutas_g2_Final.csv")
ARQUIVO_TOP_HITS = os.path.join(BASE_DIR, "TOP_10_HITS_REFINADOS.csv")

def run_vina(conf_file, out_pdbqt):
    try:
        if not os.path.exists(PATH_VINA):
            logging.error(f"[CRÍTICO] O arquivo executável do Vina não foi encontrado em: {PATH_VINA}")
            return None
            
        cmd_str = f'"{PATH_VINA}" --config "{conf_file}" --out "{out_pdbqt}"'
        proc = subprocess.run(cmd_str, capture_output=True, text=True, shell=True, cwd=BASE_DIR)
        return proc
    except Exception as e:
        logging.exception(f"Falha ao executar subprocesso Vina: {e}")
        return None

# ==========================================================================
# MÓDULOS DE CIÊNCIA DE DADOS E GERAÇÃO REGULATÓRIA
# ==========================================================================

def gerar_graficos_e_pdf(df_hits):
    try:
        df = df_hits.copy()
        df[['Medicamento', 'Fitoterapico']] = df['Par_Molecular'].str.split(r' \+ ', expand=True)
        
        plt.figure(figsize=(10, 6))
        heatmap_data = df.pivot(index='Medicamento', columns='Fitoterapico', values='Delta_G_Consenso_C2')
        sns.heatmap(heatmap_data, annot=True, cmap="YlGnBu_r", fmt=".2f", linewidths=.5)
        plt.title("Mapa de Sinergismo Termodinâmico (ΔG kcal/mol)")
        plt.tight_layout()
        plt.savefig(os.path.join(BASE_DIR, "heatmap_energia.png"))
        plt.close()

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(200, 10, txt="Relatório de Triagem Computacional G2-HPC", ln=True, align='C')
        pdf.set_font("Arial", size=10)
        pdf.cell(200, 10, txt="Validação Estrutural e Docking Molecular", ln=True, align='C')
        pdf.ln(10)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, txt="Top Hits Refinados:", ln=True)
        pdf.set_font("Arial", size=10)
        
        for _, row in df.head(5).iterrows():
            # Remove os símbolos Unicode incompatíveis com o PDF clássico (latin-1)
            veredito_limpo = str(row['Veredito']).replace("★", "*").replace("⚠", "[!]")
            
            linha = f"> {row['Par_Molecular']} | Sinergia C2: {row['Delta_G_Consenso_C2']} | Sel: {row['Índice_Seletividade']} | Veredito: {veredito_limpo}"
            pdf.cell(200, 8, txt=linha, ln=True)
            
        pdf.ln(5)
        if os.path.exists(os.path.join(BASE_DIR, "heatmap_energia.png")):
            pdf.image(os.path.join(BASE_DIR, "heatmap_energia.png"), x=10, w=190)
        pdf.output(os.path.join(BASE_DIR, "Relatorio_Regulatorio_G2.pdf"))
        logging.info("[✓] Relatório Técnico PDF e Mapas de Calor gerados com sucesso.")
    except Exception as e:
        logging.error(f"Erro na geração dos gráficos/PDF: {e}. Os dados CSV continuam seguros.")

def treinar_modelo_ml():
    if not os.path.exists(ARQUIVO_BRUTO): return
    try:
        df = pd.read_csv(ARQUIVO_BRUTO)
        if len(df) < 2: return 
        
        X = df[['E_Isolada', 'LE_Isolado']]
        y = df['Delta_G_Consenso_C2']
        
        modelo = RandomForestRegressor(n_estimators=100, random_state=42)
        modelo.fit(X, y)
        score = modelo.score(X, y)
        logging.info(f"[IA] Modelo de Machine Learning QSAR treinado com sucesso!")
    except Exception as e:
        logging.warning(f"Não foi possível treinar o modelo de IA nesta rodada: {e}")

# ==========================================================================
# MOTOR PRINCIPAL DE TRABALHO
# ==========================================================================

def calcular_ki(delta_g):
    if delta_g >= 0: return 0.0
    return math.exp(delta_g / 0.59248) * 1_000_000 

def buscar_e_filtrar_estruturas():
    if not os.path.exists(ARQUIVO_MATRIZ_LIMPA):
        logging.error("Matriz limpa não encontrada! Execute coletor_admet.py primeiro.")
        sys.exit(1)
        
    meds, nats = [], []
    with open(ARQUIVO_MATRIZ_LIMPA, mode='r', encoding='utf-8') as f:
        leitor = csv.DictReader(f)
        for linha in leitor:
            comp = {"nome": linha["Nome"], "smiles": linha["Smiles"]}
            if linha["Classe"] == "Medicamento": meds.append(comp)
            else: nats.append(comp)
    return meds, nats
    
def baixar_e_preparar_receptores():
    alvos_limpos = {}
    for pdb_id in TODOS_ALVOS:
        pdb_file = os.path.join(BASE_DIR, f"{pdb_id}.pdb")
        limpo = os.path.join(BASE_DIR, f"receptor_{pdb_id}_limpo.pdbqt")
        if os.path.exists(limpo): alvos_limpos[pdb_id] = limpo; continue
            
        if not os.path.exists(pdb_file):
            logging.info(f"Baixando estrutura: {pdb_id}...")
            urls = [f"https://files.rcsb.org/download/{pdb_id}.pdb", f"https://opm-assets.storage.googleapis.com/pdb/{pdb_id}.pdb"]
            sucesso = False
            for url in urls:
                try: urllib.request.urlretrieve(url, pdb_file); sucesso = True; break
                except: continue
            if not sucesso: continue
            
        if os.path.exists(pdb_file):
            raw = os.path.join(BASE_DIR, f"raw_{pdb_id}.pdbqt")
            subprocess.run(f'"{PATH_OBABEL}" "{pdb_file}" -O "{raw}" -xh --delete "water"', shell=True, capture_output=True)
            if os.path.exists(raw):
                with open(raw, "r") as f_in, open(limpo, "w") as f_out:
                    for linha in f_in:
                        if linha.startswith("ATOM") or linha.startswith("HETATM"): f_out.write(linha)
                os.remove(raw)
                alvos_limpos[pdb_id] = limpo
    return alvos_limpos

def executar_docking_core(receptor, ligante_pdbqt, prefixo, id_par, rep):
    conf_file = os.path.join(BASE_DIR, f"conf_{prefixo}_{id_par}_rep{rep}.txt")
    out_pdbqt = os.path.join(BASE_DIR, f"output_{prefixo}_{id_par}_rep{rep}.pdbqt")
    
    conf_content = (f"receptor = {receptor}\nligand = {ligante_pdbqt}\n"
                    f"center_x = {GRID_CONFIG['center_x']}\ncenter_y = {GRID_CONFIG['center_y']}\ncenter_z = {GRID_CONFIG['center_z']}\n"
                    f"size_x = {GRID_CONFIG['size_x']}\nsize_y = {GRID_CONFIG['size_y']}\nsize_z = {GRID_CONFIG['size_z']}\n"
                    f"exhaustiveness = {GRID_CONFIG['exhaustiveness']}\ncpu = {GRID_CONFIG['cpu']}\nseed = {42 + rep}") 
    with open(conf_file, "w") as f: f.write(conf_content)
    
    process = run_vina(conf_file, out_pdbqt)
    
    try:
        if os.path.exists(conf_file): os.remove(conf_file)
    except: pass 
    
    if process and getattr(process, 'stdout', None):
        for linha in process.stdout.split("\n"):
            partes = linha.split()
            if len(partes) > 2 and partes[0] == "1":
                try: return float(partes[1]), out_pdbqt
                except ValueError: continue
    if os.path.exists(out_pdbqt):
        with open(out_pdbqt, "r") as f_out:
            for linha in f_out:
                if línea := linha.startswith("REMARK VINA RESULT:"):
                    try: return float(linha.split()[3]), out_pdbqt
                    except: continue
    return 0.0, None

def calcular_estatisticas(valores):
    if not valores: return 0.0, 0.0
    media = sum(valores) / len(valores)
    variancia = sum((x - media) ** 2 for x in valores) / len(valores)
    return media, math.sqrt(variancia)

def processar_par_industrial(med, nat, id_par):
    med_nome, med_smiles = med["nome"], med["smiles"]
    nat_nome, nat_smiles = nat["nome"], nat["smiles"]
    nome_par = f"{med_nome} + {nat_nome}"
    
    tag_exclusiva = f"{med_nome}_{nat_nome}_{id_par}"
    lig_med = os.path.join(BASE_DIR, f"lig_med_{tag_exclusiva}.pdbqt")
    lig_nat = os.path.join(BASE_DIR, f"lig_nat_{tag_exclusiva}.pdbqt")
    pose_nat = os.path.join(BASE_DIR, f"pose_nat_{tag_exclusiva}.pdbqt")
    
    resultados_por_alvo = {}
    
    try:
        from rdkit.Chem import AllChem
        for smiles, caminho_saida in [(med_smiles, lig_med), (nat_smiles, lig_nat)]:
            mol = Chem.MolFromSmiles(smiles)
            if not mol: continue
            mol = Chem.AddHs(mol) 
            AllChem.EmbedMolecule(mol, AllChem.ETKDG()) 
            AllChem.MMFFOptimizeMolecule(mol) 
            
            pdb_temp = caminho_saida.replace(".pdbqt", ".pdb")
            Chem.MolToPDBFile(mol, pdb_temp)
            subprocess.run(f'"{PATH_OBABEL}" "{pdb_temp}" -O "{caminho_saida}" -xh', shell=True, capture_output=True)
            try:
                if os.path.exists(pdb_temp): os.remove(pdb_temp)
            except: pass

        if not os.path.exists(lig_med) or not os.path.exists(lig_nat): 
            return None
            
        num_atom_pesados = Chem.MolFromSmiles(med_smiles).GetNumHeavyAtoms() if Chem.MolFromSmiles(med_smiles) else 1
        
        for pdb_id in ["1cx2", "6cox", "4cox"]:
            receptor_limpo = os.path.join(BASE_DIR, f"receptor_{pdb_id}_limpo.pdbqt") 
            if not os.path.exists(receptor_limpo): continue

            rec_hibrido = os.path.join(BASE_DIR, f"rec_hibrido_{pdb_id}_{tag_exclusiva}.pdbqt")
            
            iso_runs = []
            for r in range(REPLICATAS):
                e_iso, _ = executar_docking_core(receptor_limpo, lig_med, f"iso_{pdb_id}_{tag_exclusiva}", id_par, r)
                if e_iso != 0.0: iso_runs.append(e_iso)
            
            _, f_nat_out = executar_docking_core(receptor_limpo, lig_nat, f"nat_{pdb_id}_{tag_exclusiva}", id_par, 0)
            if not f_nat_out or not iso_runs: continue
            
            with open(f_nat_out, "r") as f_in, open(pose_nat, "w") as f_out:
                for linha in f_in:
                    f_out.write(linha)
                    if "ENDMDL" in linha: break
            
            with open(receptor_limpo, "r") as f_rec, open(pose_nat, "r") as f_lig, open(rec_hibrido, "w") as f_out:
                for linha in f_rec:
                    if not "END" in linha: f_out.write(linha)
                for linha in f_lig:
                    if linha.startswith("ATOM") or linha.startswith("HETATM"): f_out.write(linha)
                f_out.write("END\n")
            
            sin_runs = []
            for r in range(REPLICATAS):
                e_sin, _ = executar_docking_core(rec_hibrido, lig_med, f"sin_{pdb_id}_{tag_exclusiva}", id_par, r)
                if e_sin != 0.0: sin_runs.append(e_sin)
                
            if not sin_runs: continue
            
            m_iso, dp_iso = calcular_estatisticas(iso_runs)
            m_sin, dp_sin = calcular_estatisticas(sin_runs)
            resultados_por_alvo[pdb_id] = {"med_iso": m_iso, "dp_iso": dp_iso, "med_sin": m_sin, "dp_sin": dp_sin, "delta": m_sin - m_iso}
            
            try:
                for f in [rec_hibrido, f_nat_out]:
                    if os.path.exists(f): os.remove(f)
                for r in range(REPLICATAS):
                    for pfx in [f"iso_{pdb_id}_{tag_exclusiva}", f"sin_{pdb_id}_{tag_exclusiva}"]:
                        f_tmp = os.path.join(BASE_DIR, f"output_{pfx}_{id_par}_rep{r}.pdbqt")
                        if os.path.exists(f_tmp): os.remove(f_tmp)
            except: pass

        if "1cx2" not in resultados_por_alvo or "6cox" not in resultados_por_alvo: return None

        c2_iso = (resultados_por_alvo["1cx2"]["med_iso"] + resultados_por_alvo["6cox"]["med_iso"]) / 2
        c2_sin = (resultados_por_alvo["1cx2"]["med_sin"] + resultados_por_alvo["6cox"]["med_sin"]) / 2
        c2_delta = c2_sin - c2_iso
        c2_dp = (resultados_por_alvo["1cx2"]["dp_sin"] + resultados_por_alvo["6cox"]["dp_sin"]) / 2
        c1_delta = resultados_por_alvo["4cox"]["delta"] if "4cox" in resultados_por_alvo else 0.0
        seletividade = c1_delta - c2_delta
        le_iso, le_sin = -c2_iso / num_atom_pesados, -c2_sin / num_atom_pesados
        delta_le = le_sin - le_iso
        
        veredito = "HIT REFINADO ★" if c2_delta <= -0.5 and seletividade > 0.1 else "NEUTRO"
        
        alerta_tox = "N/A"
        if veredito == "HIT REFINADO ★":
            for off_id in ALVOS_OFFTARGET:
                rec_off = os.path.join(BASE_DIR, f"receptor_{off_id}_limpo.pdbqt") 
                e_off, _ = executar_docking_core(rec_off, lig_med, f"off_{off_id}_{tag_exclusiva}", id_par, 0)
                if e_off < -8.0:
                    alerta_tox = f"ALERTA CYP2C9 ({e_off:.1f})"
                    veredito = "HIT C/ RESSALVA ⚠"
                else:
                    alerta_tox = "Seguro Hepat."
                    
                try:
                    f_off_tmp = os.path.join(BASE_DIR, f"output_off_{off_id}_{tag_exclusiva}_{id_par}_rep0.pdbqt")
                    if os.path.exists(f_off_tmp): os.remove(f_off_tmp)
                except: pass

        try:
            for f in [lig_med, lig_nat, pose_nat]:
                if os.path.exists(f): os.remove(f)
        except: pass
        
        return [nome_par, f"{c2_iso:.2f}", f"{c2_sin:.2f}", f"{c2_delta:.2f}", f"{c2_dp:.3f}", f"{seletividade:.2f}", f"{le_iso:.3f}", f"{delta_le:.3f}", f"{calcular_ki(c2_iso):.2f}", f"{calcular_ki(c2_sin):.2f}", alerta_tox, veredito]
    except Exception as e:
        return None

def processar_relatorio_top_hits():
    if not os.path.exists(ARQUIVO_BRUTO): return
    linhas = []
    with open(ARQUIVO_BRUTO, mode='r', encoding='utf-8') as f:
        leitor = csv.reader(f)
        cabecalho = next(leitor)
        for row in leitor:
            if row: linhas.append(row)
        
    if not linhas: return
    
    linhas_ordenadas = sorted(linhas, key=lambda x: (float(x[3]), -float(x[5])))
    top_10 = linhas_ordenadas[:10]

    arquivo_temp = ARQUIVO_TOP_HITS + ".tmp"
    arquivo_backup = ARQUIVO_TOP_HITS + ".bak"

    try:
        with open(arquivo_temp, mode='w', encoding='utf-8', newline='') as f_tmp:
            escritor = csv.writer(f_tmp)
            escritor.writerow(cabecalho)
            escritor.writerows(top_10)

        df_validacao = pd.read_csv(arquivo_temp)
        if df_validacao.empty or len(df_validacao) == 0:
            raise ValueError("O arquivo temporário foi gerado vazio. Abortando substituição.")

        gerar_graficos_e_pdf(df_validacao)
        treinar_modelo_ml()

        if os.path.exists(ARQUIVO_TOP_HITS):
            if os.path.exists(arquivo_backup): os.remove(arquivo_backup)
            os.rename(ARQUIVO_TOP_HITS, arquivo_backup)
            
        os.rename(arquivo_temp, ARQUIVO_TOP_HITS)
        logging.info(f"[✓] Ranking TOP 10 consolidado em: '{ARQUIVO_TOP_HITS}'")
        
    except Exception as e:
        logging.error(f"SISTEMA DE SALVAGUARDA ATIVADO: Falha crítica ao gerar ranking: {e}")
        if os.path.exists(arquivo_temp): os.remove(arquivo_temp)

def main():
    logging.info("==========================================================================")
    logging.info("   PLANTA G2-HPC: TRIAGEM COM DOCKING REVERSO, MACHINE LEARNING E PDF     ")
    logging.info("==========================================================================")
    
    baixar_e_preparar_receptores()
    meds, nats = buscar_e_filtrar_estruturas()
    
    pares_calc = set()
    if os.path.exists(ARQUIVO_BRUTO):
        with open(ARQUIVO_BRUTO, mode='r', encoding='utf-8') as f:
            try: 
                leitor = csv.reader(f)
                next(leitor) 
                for linha in leitor:
                    if linha: pares_calc.add(linha[0])
            except: pass
    else:
        with open(ARQUIVO_BRUTO, mode='w', encoding='utf-8', newline='') as f:
            csv.writer(f).writerow(["Par_Molecular", "E_Isolada", "E_Sinergica", "Delta_G_Consenso_C2", "Desvio_Padrão_C2", "Índice_Seletividade", "LE_Isolado", "Delta_LE", "Ki_Isolado_uM", "Ki_Sinergico_uM", "Docking_Reverso_Tox", "Veredito"])

    fila_producao = []
    id_atual = 1
    for m in meds:
        for n in nats:
            if f"{m['nome']} + {n['nome']}" not in pares_calc:
                fila_producao.append((m, n, id_atual))
                id_atual += 1
            
    if not fila_producao:
        logging.info("[✓] Todos os pares calculados no banco final!")
        processar_relatorio_top_hits()
        return

    logging.info(f"Disparando HPC ({MAX_WORKERS} Núcleos) | {len(fila_producao)} Novas Rotas...")
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futuros = {executor.submit(processar_par_industrial, p[0], p[1], p[2]): p for p in fila_producao}
        contador = 0
        for futuro in as_completed(futuros):
            linha = futuro.result()
            contador += 1
            if linha:
                with open(ARQUIVO_BRUTO, mode='a', encoding='utf-8', newline='') as f: csv.writer(f).writerow(linha)
                logging.info(f"[HPC] {contador}/{len(fila_producao)} ({ (contador/len(fila_producao))*100:.1f}%) | {linha[0]}")

    logging.info("Fechamento Analítico...")
    processar_relatorio_top_hits()
    logging.info(f"Sucesso! PDF Técnico e CSV gerados na pasta raiz.")

if __name__ == "__main__":
    main()