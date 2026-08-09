import os
import subprocess
from openbabel import openbabel 
from rdkit import Chem
from rdkit.Chem import AllChem
from Bio.PDB import PDBParser, PDBIO, Select
import uuid # Novo import necessário



CAMINHO_VINA = "vina.exe"  
SMILES_CAMPEAO = "O=C(C(F)(F)F)C1CCCC1c1cnccc1Cl"
LIGANTE_PREPARADO = "ligante_cerebral.pdbqt"

# =========================================================================
# DICIONÁRIO DE ALVOS (BATERIA MULTI-DOENÇA COM CENTROS CALCULADOS)
# =========================================================================
ALVOS_FARMACEUTICOS = {
    "5W8K": {"arquivo": "5W8K.pdb", "x": 28.43, "y": -0.91, "z": 26.85, "tamanho": 80.0}, # hERG (Coração)
    "1TQN": {"arquivo": "1TQN.pdb", "x": -19.29, "y": -23.63, "z": -14.17, "tamanho": 80.0}, # Fígado
    "6OIJ": {"arquivo": "6OIJ.pdb", "x": 118.18, "y": 102.26, "z": 113.22, "tamanho": 80.0}, # Receptor M1
    "4D82": {"arquivo": "4D82.pdb", "x": -1.09, "y": 214.84, "z": -17.81, "tamanho": 80.0}  # BACE-1
}
# =========================================================================
# FUNÇÕES CORE DE PREPARAÇÃO
# =========================================================================

def preparar_ligante_3d(smiles):
    print(f"\n[🧬] Preparando Molécula de IA...")
    
    # Gerar um nome único (UUID) para cada vez que rodar, evitando conflitos
    id_unico = str(uuid.uuid4())[:8]
    temp_pdb = f"temp_ligante_{id_unico}.pdb"
    
    mol = Chem.MolFromSmiles(smiles)
    mol = Chem.AddHs(mol)  
    AllChem.EmbedMolecule(mol, AllChem.ETKDG())
    AllChem.MMFFOptimizeMolecule(mol)  
    
    Chem.MolToPDBFile(mol, temp_pdb)
    
    obConversion = openbabel.OBConversion()
    obConversion.SetInAndOutFormats("pdb", "pdbqt")
    obMol = openbabel.OBMol()
    
    if obConversion.ReadFile(obMol, temp_pdb):
        obMol.StripSalts()
        obConversion.WriteFile(obMol, LIGANTE_PREPARADO)
        obConversion.CloseOutFile()
        obMol.Clear()
        print(f"    -> Ficheiro do ligante gerado: '{LIGANTE_PREPARADO}'")
    
    # Tentativa de remoção com tratamento de erro mais resiliente
    try:
        if os.path.exists(temp_pdb):
            os.remove(temp_pdb)
    except OSError:
        # Se falhar, deixamos o ficheiro lá (ele será sobrescrito ou ignorado)
        pass


def forcar_rigidez_receptor(filepath):
    with open(filepath, 'r') as f: linhas = f.readlines()
    with open(filepath, 'w') as f:
        for linha in linhas:
            if not linha.startswith(("ROOT", "ENDROOT", "BRANCH", "ENDBRANCH", "TORSDOF")):
                f.write(linha)




def preparar_proteina(nome_alvo, arquivo_pdb, proteina_saida_pdbqt):
    print(f"  [🏛️] Limpando proteína {nome_alvo}...")
    if not os.path.exists(arquivo_pdb):
        return False
    
    # Criar um nome único para este alvo nesta execução específica
    id_unico = str(uuid.uuid4())[:8]
    temp_pdb_limpo = f"temp_{nome_alvo}_{id_unico}.pdb"
    
    try:
        class FiltroProteinaLimpa(Select):
            def accept_residue(self, residue):
                if residue.id[0] != " ": return 0
                return 1

        parser = PDBParser(QUIET=True)
        estrutura = parser.get_structure(nome_alvo, arquivo_pdb)
        io = PDBIO()
        io.set_structure(estrutura)
        io.save(temp_pdb_limpo, FiltroProteinaLimpa())
        
        obConversion = openbabel.OBConversion()
        obConversion.SetInAndOutFormats("pdb", "pdbqt")
        obMol = openbabel.OBMol()
        
        # Leitura com verificação de sucesso
        if obConversion.ReadFile(obMol, temp_pdb_limpo):
            obConversion.WriteFile(obMol, proteina_saida_pdbqt)
            obConversion.CloseOutFile()
            obMol.Clear()
            forcar_rigidez_receptor(proteina_saida_pdbqt)
            
            # Limpeza segura
            try:
                if os.path.exists(temp_pdb_limpo): os.remove(temp_pdb_limpo)
            except: pass 
            return True
        else:
            return False
    except Exception as e:
        print(f"  [❌] Erro ao preparar {nome_alvo}: {e}")
        return False


# =========================================================================
# O MOTOR PRINCIPAL (LOOP MULTI-TARGET)
# =========================================================================
def executar_bateria_docking():
    preparar_ligante_3d(SMILES_CAMPEAO)
    
    print("\n" + "="*60)
    print(" INICIANDO BATERIA DE TESTES MULTI-ALVO (BLIND DOCKING)")
    print("="*60)
    
    for alvo, config in ALVOS_FARMACEUTICOS.items():
        print(f"\n🧪 TESTANDO ALVO: {alvo} ({config['arquivo']})")
        print("-" * 50)
        
        receptor_pdbqt = f"receptor_{alvo}.pdbqt"
        arquivo_saida = f"resultado_{alvo}.pdbqt"
        arquivo_config = f"config_{alvo}.txt"
        
        # 1. Limpa a proteína
        if not preparar_proteina(alvo, config['arquivo'], receptor_pdbqt):
            continue
            
        # 2. Cria configuração específica para esta proteína
        conteudo_config = f"""receptor = {receptor_pdbqt}
ligand = {LIGANTE_PREPARADO}
center_x = {config['x']}
center_y = {config['y']}
center_z = {config['z']}
size_x = {config['tamanho']}
size_y = {config['tamanho']}
size_z = {config['tamanho']}
exhaustiveness = 8
"""
        with open(arquivo_config, "w") as f: f.write(conteudo_config)
        
        # 3. Roda o AutoDock Vina silenciosamente
        print(f"  [🔥] Calculando termodinâmica (isto pode demorar vários minutos)...")
        comando = [CAMINHO_VINA, "--config", arquivo_config, "--out", arquivo_saida]
        
        try:
            # capture_output esconde os 100% da tela para não poluir o terminal, mostrando só o fim
            resultado = subprocess.run(comando, capture_output=True, text=True, check=True)
            
            # 4. Lê o resultado final e imprime a melhor energia
            with open(arquivo_saida, "r") as f:
                for line in f:
                    if "REMARK VINA RESULT:" in line:
                        energia = line.split()[3]
                        print(f"  [✅] SUCESSO! Melhor Afinidade em {alvo}: {energia} kcal/mol")
                        break # Pega só a energia top 1
        except Exception as e:
             print(f"  [❌] Falha na simulação de {alvo}.")

    print("\n" + "="*60)
    print(" BATERIA CONCLUÍDA! Verifique os ficheiros 'resultado_*.pdbqt'")
    print("="*60)


    

if __name__ == "__main__":
    executar_bateria_docking()