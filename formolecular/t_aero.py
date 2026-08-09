import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Configuração de estilo para os gráficos
sns.set_theme(style="darkgrid")
plt.rcParams['figure.figsize'] = [11, 7]

# Mantém o nome do teu arquivo gigante
ARQUIVO_ELEMENTOS = "csv/universo_utilidade_filtrada.csv" 

def analisar_propelentes():
    print("\n" + "="*80)
    print(" 🚀 INICIANDO TRIAGEM DO ORÁCULO AEROESPACIAL: IGNIÇÃO E PERFORMANCE")
    print("="*80)
    
    if not os.path.exists(ARQUIVO_ELEMENTOS):
        print(f"[!] Erro: O arquivo '{ARQUIVO_ELEMENTOS}' não foi encontrado na pasta raiz.")
        return

    print("[📂] Carregando a base de dados de 2.7 Milhões de moléculas (Aguarde alguns segundos)...")
    # low_memory=False elimina o DtypeWarning das colunas mistas
    df = pd.read_csv(ARQUIVO_ELEMENTOS, low_memory=False)
    print(f"[🟢] Sucesso! {len(df)} moléculas carregadas com sucesso na memória.")
    
    # 🛠️ CORREÇÃO 1: Remove espaços em branco invisíveis no início ou fim dos nomes das colunas
    df.columns = df.columns.str.strip()
    
    # 🛠️ CORREÇÃO 2: Motor de Auto-Detecção de Colunas Mismatch
    col_energia = None
    col_peso = None
    
    # Busca por palavras-chave em minúsculo para não errar
    for col in df.columns:
        if 'combustao' in col.lower() or ('energia' in col.lower() and 'mj' in col.lower()):
            col_energia = col
        if 'peso' in col.lower() or 'molar' in col.lower() or 'mw' in col.lower():
            col_peso = col
            
    # Fallback secundário caso a busca rigorosa falhe
    if col_energia is None:
        for col in df.columns:
            if 'energia' in col.lower() or 'comb' in col.lower():
                col_energia = col
                break
                
    # Se mesmo assim não encontrar nada, avisa o usuário e mostra o mapa de colunas
    if col_energia is None or col_peso is None:
        print("\n[❌] Erro Crítico: Não foi possível mapear as colunas de Energia ou Peso no arquivo.")
        print(f"📋 Colunas reais encontradas no seu arquivo para te ajudar a checar:\n{df.columns.tolist()}")
        return
        
    print(f"[🎯] Sensor do Oráculo alinhado com sucesso:")
    print(f"    -> Coluna de Energia ativa: '{col_energia}'")
    print(f"    -> Coluna de Peso ativa:    '{col_peso}'")

    # Garante que os dados são tratados como números (limpa textos perdidos na coluna)
    df[col_energia] = pd.to_numeric(df[col_energia], errors='coerce')
    df[col_peso] = pd.to_numeric(df[col_peso], errors='coerce')
    df = df.dropna(subset=[col_energia, col_peso])

    # Ordenação pelo critério de maior Densidade Energética Global
    df_aero = df.sort_values(by=col_energia, ascending=False).copy()
    
    # Cálculo do Índice de Eficiência Teórica (Energia / Peso Molar)
    df_aero['Indice_Eficiencia'] = df_aero[col_energia] / df_aero[col_peso]
    
    print("\n🏆 TOP 10 CANDIDATOS GLOBAIS DE ALTA PERFORMANCE AEROESPACIAL:")
    top_10 = df_aero.head(10)
    
    # Identifica a coluna identificadora (ID ou similar)
    col_id = 'ID' if 'ID' in df_aero.columns else df_aero.columns[0]
    print(top_10[[col_id, col_peso, col_energia, 'Indice_Eficiencia']].to_string(index=False))
    
    # 3. GERAÇÃO DO GRÁFICO DE DISPERSÃO GIGANTE (2.7M de pontos)
    print("\n[📊] Renderizando mapa de nuvem molecular completa... Isto pode levar uns 15 segundos...")
    
    plt.figure()
    # Usamos alpha menor (0.4) e pontos menores (s=4) porque 2.7 milhões de pontos criam uma nuvem densa
    scatter = plt.scatter(
        df_aero[col_peso], 
        df_aero[col_energia], 
        c=df_aero['Indice_Eficiencia'], 
        cmap='plasma', 
        alpha=0.4, 
        edgecolors='none', 
        s=4
    )
    
    # Adicionar anotações balísticas para os 3 melhores combustíveis do mundo
    for i, row in top_10.head(3).iterrows():
        label_nome = str(row[col_id]).split('_')[-1]
        plt.annotate(
            label_nome, 
            (row[col_peso], row[col_energia]),
            textcoords="offset points", 
            xytext=(0,12), 
            ha='center', 
            fontsize=9, 
            weight='bold',
            bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.8)
        )
        
    plt.colorbar(scatter, label='Índice de Eficiência (Velocidade de Exaustão Estimada)')
    plt.title('🔍 MAPA DE TRIAGEM PROPELENTE: 2.7 MILHÕES DE MOLÉCULAS', fontsize=14, weight='bold')
    plt.xlabel('Peso Molar (g/mol) -> Menor gera gases mais velozes na saída do bocal', fontsize=11)
    plt.ylabel('Energia de Combustão (MJ/kg) -> Maior gera maior empuxo por kg', fontsize=11)
    
    # Linha de referência comercial
    plt.axhline(y=43.5, color='r', linestyle='--', alpha=0.7, label='Referência Comercial: Querosene de Foguete RP-1 (43.5 MJ/kg)')
    plt.legend(loc='upper right')
    
    nome_grafico = "mapa_propelentes_elite.png"
    plt.savefig(nome_grafico, dpi=300, bbox_inches='tight')
    print(f"\n🎉 Análise concluída com sucesso absoluto! Mapa salvo como: {nome_grafico}")

if __name__ == "__main__":
    analisar_propelentes()