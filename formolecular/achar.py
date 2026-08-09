import numpy as np
import glob
from Bio.PDB import PDBParser

# Encontra automaticamente todos os arquivos .pdb na pasta atual
arquivos_pdb = glob.glob("*.pdb")

def calcular_centro_geometrico(arquivo):
    parser = PDBParser(QUIET=True)
    try:
        estrutura = parser.get_structure("PROT", arquivo)
        # Extrai as coordenadas cartesianas de todos os átomos
        coordenadas = [atomo.coord for atomo in estrutura.get_atoms()]
        
        # Calcula a média (o ponto central exato do volume total da proteína)
        centro = np.mean(coordenadas, axis=0)
        
        print(f"📍 Coordenadas para {arquivo}:")
        print(f"    'x': {round(centro[0], 2)}, 'y': {round(centro[1], 2)}, 'z': {round(centro[2], 2)}")
        print("-" * 40)
    except Exception as e:
        print(f"❌ Erro ao ler {arquivo}: {e}")

print("\n🔍 RASTREADOR DE COORDENADAS 3D (PROCESSAMENTO EM LOTE)")
print("-" * 40)

if not arquivos_pdb:
    print("Nenhum arquivo .pdb encontrado na pasta.")
else:
    for arquivo in arquivos_pdb:
        calcular_centro_geometrico(arquivo)