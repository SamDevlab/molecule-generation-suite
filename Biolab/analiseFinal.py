import subprocess
import os
from rdkit import Chem
from rdkit.Chem import AllChem
from meeko import MoleculePreparation

def preparar_e_rodar_docking(smiles, receptor_file):
    # 1. Preparar a molécula (Converter SMILES para 3D)
    print(f"--- Preparando a molécula: {smiles} ---")
    mol = Chem.MolFromSmiles(smiles)
    mol = Chem.AddHs(mol)
    AllChem.EmbedMolecule(mol, randomSeed=42)
    AllChem.MMFFOptimizeMolecule(mol)

    # 2. Converter para PDBQT (formato do Vina)
    preparator = MoleculePreparation()
    preparator.prepare(mol)
    ligand_file = "meu_ligante.pdbqt"
    preparator.write_pdbqt_file(ligand_file)
    print(f"Ficheiro '{ligand_file}' gerado com sucesso.")

    # 3. Configurar comando para o vina.exe
    # NOTA: Ajuste as coordenadas (center) para o centro do sítio ativo da sua proteína
    cmd = [
        "./vina.exe",
        "--receptor", receptor_file,
        "--ligand", ligand_file,
        "--out", "resultado_docking.pdbqt",
        "--center_x", "15.0", "--center_y", "20.0", "--center_z", "10.0",
        "--size_x", "20.0", "--size_y", "20.0", "--size_z", "20.0",
        "--exhaustiveness", "8",
        "--log", "docking.log"
    ]

    # 4. Executar simulação
    print("A executar o Vina (isto pode demorar alguns minutos)...")
    try:
        subprocess.run(cmd, check=True)
        print("Docking terminado com sucesso!")
        
        # 5. Ler e exibir o resumo da afinidade
        if os.path.exists("docking.log"):
            print("\n--- RESULTADO DE AFINIDADE (kcal/mol) ---")
            with open("docking.log", "r") as f:
                log_content = f.readlines()
                # Mostra as últimas linhas do log onde está a tabela de afinidade
                for line in log_content[-15:]:
                    print(line.strip())
        else:
            print("Erro: O ficheiro docking.log não foi criado.")
            
    except Exception as e:
        print(f"Erro durante a execução: {e}")

if __name__ == "__main__":
    # A sua molécula campeã
    meu_smiles = "O=C(C(F)(F)F)C1CCCC1c1cnccc1Cl"
    meu_receptor = "proteina_alvo.pdbqt"
    
    if os.path.exists(meu_receptor):
        preparar_e_rodar_docking(meu_smiles, meu_receptor)
    else:
        print(f"Erro: Ficheiro '{meu_receptor}' não encontrado na pasta.")