import os
import csv
import logging
import sys
import pubchempy as pcp
from rdkit import Chem
from rdkit.Chem import Descriptors
from rdkit.DataStructs import TanimotoSimilarity

# ==========================================================================
# CONFIGURAÇÕES DO COLETOR
# ==========================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', handlers=[logging.StreamHandler(sys.stdout)])

MEDICAMENTOS_ALVO = ['indomethacin', 'ketoprofen', 'piroxicam', 'celecoxib', 'ibuprofen', 'meloxicam']
FITOTERAPICOS_ALVO = ['thymol', 'carvacrol', 'quercetin', 'sulforaphane', 'curcumin', 'resveratrol', 'genistein', 'eugenol']
SMILES_REFERENCIA = "CC(C1=CC2=C(C=C1)C=C(C=C2)OC)C(=O)O" # Naproxeno
ARQUIVO_MATRIZ_LIMPA = os.path.join(BASE_DIR, "matriz_compostos_filtrados.csv")

# ==========================================================================
# INTEGRAÇÃO DE ALERTAS ESTRUTURAIS (SIMULAÇÃO TOX21 / CHEMBL PAINS)
# ==========================================================================
ALERTAS_TOXICIDADE = {
    "Nitro_Mutagenico": "[N+](=O)[O-]",
    "Acido_Sulfonico_Reativo": "S(=O)(=O)[O-]",
    "Epoxido_Alquilante": "C1OC1", 
    "Quinona_Toxica": "O=C1C=CC(=O)C=C1",
    "Anilina_Hepatotoxica": "c1ccccc1N",
    "Tioester_Reativo": "S=C(O)C"
}

def analisar_admet_local(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if not mol: return False, {}
        
    p_mol = Descriptors.MolWt(mol)
    log_p = Descriptors.MolLogP(mol)
    doadores_h = Descriptors.NumHDonors(mol)
    aceitadores_h = Descriptors.NumHAcceptors(mol)
    lig_rotacionaveis = Descriptors.NumRotatableBonds(mol)
    tpsa = Descriptors.TPSA(mol) 
    
    v_lipinski = sum([p_mol > 500, log_p > 5, doadores_h > 5, aceitadores_h > 10])
    passa_veber = lig_rotacionaveis <= 10 and tpsa <= 140
    
    alertas_encontrados = []
    for nome_alerta, smarts in ALERTAS_TOXICIDADE.items():
        if mol.HasSubstructMatch(Chem.MolFromSmarts(smarts)):
            alertas_encontrados.append(nome_alerta)
            
    aprovado = (v_lipinski <= 1 and passa_veber and len(alertas_encontrados) == 0)
    
    return aprovado, {
        "mw": f"{p_mol:.2f}", "logp": f"{log_p:.2f}", "tpsa": f"{tpsa:.2f}",
        "rot_bonds": lig_rotacionaveis, "lipinski_vio": v_lipinski, 
        "tox_alerts": " | ".join(alertas_encontrados) if alertas_encontrados else "Nenhum"
    }

def main():
    logging.info("==========================================================================")
    logging.info("      MÓDULO ISOLADO G2: COLETA DE DADOS, FILTRAÇÃO ADMET E QSAR LOCAL    ")
    logging.info("==========================================================================")
    
    compostos_aprovados = []
    
    logging.info(f"Varrendo {len(MEDICAMENTOS_ALVO)} AINEs de referência...")
    for nome in MEDICAMENTOS_ALVO:
        try:
            comp = pcp.get_compounds(nome, 'name')[0]
            smiles = comp.canonical_smiles
            aprovado, dados = analisar_admet_local(smiles)
            if not aprovado:
                logging.warning(f"[-] Medicamento REJEITADO (Tox/ADMET): {nome.capitalize()} -> Alertas: {dados['tox_alerts']}")
                continue
            compostos_aprovados.append([nome.capitalize(), "Medicamento", smiles, dados["mw"], dados["logp"], dados["tpsa"], dados["rot_bonds"]])
            logging.info(f"[+] APROVADO: {nome.capitalize()}")
        except Exception as e: logging.error(f"Erro ao coletar {nome}: {e}")

    logging.info(f"Varrendo {len(FITOTERAPICOS_ALVO)} Fitoterápicos Promissores...")
    mol_ref = Chem.MolFromSmiles(SMILES_REFERENCIA)
    
    for nome in FITOTERAPICOS_ALVO:
        try:
            comp = pcp.get_compounds(nome, 'name')[0]
            smiles = comp.canonical_smiles
            
            mol_nat = Chem.MolFromSmiles(smiles)
            if mol_nat and mol_ref:
                if TanimotoSimilarity(Chem.RDKFingerprint(mol_nat), Chem.RDKFingerprint(mol_ref)) > 0.90:
                    logging.warning(f"[-] Fitoterápico DESCARTADO (Redundância estrutural): {nome.capitalize()}")
                    continue
            
            aprovado, dados = analisar_admet_local(smiles)
            if not aprovado:
                logging.warning(f"[-] Fitoterápico REJEITADO (Tox/ADMET): {nome.capitalize()} -> Alertas: {dados['tox_alerts']}")
                continue
                
            compostos_aprovados.append([nome.capitalize(), "Fitoterapico", smiles, dados["mw"], dados["logp"], dados["tpsa"], dados["rot_bonds"]])
            logging.info(f"[+] APROVADO: {nome.capitalize()}")
        except Exception as e: logging.error(f"Erro ao coletar {nome}: {e}")

    with open(ARQUIVO_MATRIZ_LIMPA, mode='w', encoding='utf-8', newline='') as f:
        escritor = csv.writer(f)
        escritor.writerow(["Nome", "Classe", "Smiles", "Peso_Molecular", "logP", "TPSA", "Lig_Rotacionaveis"])
        escritor.writerows(compostos_aprovados)
        
    logging.info(f"[✓] Triagem concluída! Matriz segura gerada com {len(compostos_aprovados)} moléculas.")

if __name__ == "__main__":
    main()