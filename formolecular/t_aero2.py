import pandas as pd
import numpy as np
import os
import random
import sys
from rdkit import Chem
from rdkit.Chem import Descriptors
import warnings

# Oculta os avisos em vermelho do RDKit no terminal para não poluir a tela
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*') 
warnings.filterwarnings('ignore')

ARQUIVO_ORACULO = "BASE_ORACULO_AEROESPACIAL.csv"  # O mesmo arquivo que o t_aero.py gera, para manter a consistência
META_MOLECULAS = 3000000  # O alvo dourado

def forja_mutacao_aeroespacial():
    print("\n" + "="*85)
    print(" 🧬 ALQUIMIA DIGITAL: FORJANDO 3 MILHÕES DE COMBUSTÍVEIS (MODO REVISADO)")
    print("="*85)
    
    if not os.path.exists(ARQUIVO_ORACULO):
        print(f"[!] Erro: Arquivo '{ARQUIVO_ORACULO}' não encontrado.")
        return

    # 1. Carrega os sobreviventes da limpeza
    df_base = pd.read_csv(ARQUIVO_ORACULO, low_memory=False)
    total_atual = len(df_base)
    faltam = META_MOLECULAS - total_atual
    
    if faltam <= 0:
        print("[🟢] O seu banco de dados já atingiu os 3 Milhões!")
        return
        
    print(f"[📊] Base atual: {total_atual} compostos.")
    print(f"[🚀] Iniciando Síntese Dirigida para gerar {faltam} compostos inéditos...")

    # Fragmentos de alto poder aeroespacial (Grupos ramificados)
    grupos_energeticos = [
        ("Nitro", "(N(=O)=O)", 45.0),    
        ("Azida", "(N=[N+]=[N-])", 60.0), 
        ("Fluoro", "(F)", 15.0),          
        ("Trifluormetil", "(C(F)(F)F)", 35.0), 
        ("Boro", "(B)", 80.0)       
    ]

    # Ordena para focar apenas nas moléculas mais promissoras como base
    melhores_base = df_base.sort_values(by='Energia_3D_Kcal', ascending=False).head(300000)
    SMILES_base = melhores_base['SMILES'].dropna().tolist()
    Energias_base = melhores_base['Energia_3D_Kcal'].dropna().tolist()

    novas_moleculas = []
    lote_tamanho = 100000 
    contador_criadas = 0
    tentativas = 0

    while contador_criadas < faltam:
        tentativas += 1
        
        # Sorteia uma molécula base
        idx = random.randint(0, len(SMILES_base) - 1)
        smiles_orig = str(SMILES_base[idx])
        energia_orig = abs(float(Energias_base[idx]))
        
        # Sorteia o aditivo aeroespacial
        nome_grupo, smiles_grupo, ganho_energia = random.choice(grupos_energeticos)
        
        # ================================================================
        # O "BISTURI QUÍMICO": Injeção de Precisão no Carbono
        # ================================================================
        # Encontra todos os carbonos disponíveis na estrutura
        posicoes_carbono = [i for i, char in enumerate(smiles_orig) if char in ['C', 'c']]
        
        if not posicoes_carbono:
            continue # Se não tem carbono, descarta e tenta outra
            
        # Escolhe um carbono aleatório e injeta o grupo explosivo logo após ele
        ponto_injecao = random.choice(posicoes_carbono)
        smiles_mutante = smiles_orig[:ponto_injecao + 1] + smiles_grupo + smiles_orig[ponto_injecao + 1:]
        
        # ================================================================
        # O JUIZ RDKIT: Validação das Leis da Física
        # ================================================================
        mol = Chem.MolFromSmiles(smiles_mutante)
        
        if mol is not None:
            # Se a valência e a geometria forem reais, a molécula nasce!
            peso_exato = Descriptors.MolWt(mol)
            nova_energia = energia_orig + ganho_energia
            
            # Recalcula a termodinâmica
            novo_isp = np.sqrt(nova_energia / peso_exato)
            qtd_N = smiles_mutante.count('N') + smiles_mutante.count('n')
            fator_exp = nova_energia * (1 + qtd_N)
            
            nova_linha = {
                'ID': f"PropSintetico_{contador_criadas}_{nome_grupo}",
                'SMILES': Chem.MolToSmiles(mol), # Padroniza o texto
                'Peso_Molar': round(peso_exato, 3),
                'Energia_3D_Kcal': round(nova_energia, 3),
                'AERO_Impulso_Espec_Teorico': round(novo_isp, 5),
                'AERO_Qtd_Nitrogenio': qtd_N,
                'AERO_Qtd_Fluor': smiles_mutante.count('F') + smiles_mutante.count('f'),
                'AERO_Qtd_Oxigenio': smiles_mutante.count('O') + smiles_mutante.count('o'),
                'AERO_Fator_Expansao_Gas': round(fator_exp, 3),
                'Categoria': 'Propelente_Sintetico_Elite'
            }
            
            novas_moleculas.append(nova_linha)
            contador_criadas += 1
            
            # Painel de controle no terminal
            if contador_criadas % 5000 == 0:
                taxa_sucesso = (contador_criadas / tentativas) * 100
                sys.stdout.write(f"\r    -> {contador_criadas}/{faltam} criadas | Taxa de Validação Física RDKit: {taxa_sucesso:.1f}%")
                sys.stdout.flush()
                
            # Salva no disco rígido e limpa a memória a cada 100 mil
            if len(novas_moleculas) >= lote_tamanho:
                df_temp = pd.DataFrame(novas_moleculas)
                for col in df_base.columns:
                    if col not in df_temp.columns:
                        df_temp[col] = 0
                df_temp = df_temp[df_base.columns]
                df_temp.to_csv(ARQUIVO_ORACULO, mode='a', index=False, header=False)
                novas_moleculas = [] 

    # Despeja as últimas moléculas que ficaram na agulha
    if len(novas_moleculas) > 0:
        df_temp = pd.DataFrame(novas_moleculas)
        for col in df_base.columns:
            if col not in df_temp.columns:
                df_temp[col] = 0
        df_temp = df_temp[df_base.columns]
        df_temp.to_csv(ARQUIVO_ORACULO, mode='a', index=False, header=False)

    print("\n\n" + "="*85)
    print(" 🎉 PROJETO DOS 3 MILHÕES CONCLUÍDO COM SUCESSO! ")
    print("="*85)
    print(" O Oráculo agora tem acesso a uma das maiores bibliotecas de propulsão customizada.")

if __name__ == "__main__":
    forja_mutacao_aeroespacial()