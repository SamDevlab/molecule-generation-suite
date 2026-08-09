import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Configuração premium
sns.set_theme(style="whitegrid")
plt.rcParams['figure.figsize'] = [16, 8]

# O arquivo que a IA acabou de exportar
ARQUIVO_ELITE = os.path.join("csv_elite_farma", "RANKING_FARMACOS_ELITE_ADMET.csv")

def gerar_dashboard_clinico():
    print("\n[📊] Inicializando o renderizador do relatório clínico...")
    
    if not os.path.exists(ARQUIVO_ELITE):
        print(f"[!] Ficheiro '{ARQUIVO_ELITE}' não encontrado.")
        return

    df = pd.read_csv(ARQUIVO_ELITE)
    
    # Sepera os sintéticos dos reaproveitados para cores diferentes
    df['Origem'] = df['Categoria'].apply(lambda x: 'Sintetizado por IA (RDKit)' if 'Sintetico' in str(x) else 'Reposicionamento (Mineração)')
    
    fig, (ax1, ax2) = plt.subplots(1, 2, gridspec_kw={'width_ratios': [1.5, 1]})
    fig.suptitle('Descoberta de Fármacos In Silico (XGBoost + RDKit ADMET)', 
                 fontsize=18, fontweight='bold', y=0.98, color='#1e3d59')

    # =========================================================================
    # GRÁFICO 1: O "DRUG-LIKENESS" (Dispersão Csp3 vs Polaridade)
    # =========================================================================
    # Uma molécula 3D (alto Csp3) e com boa polaridade (TPSA 50-100) é o Santo Graal
    scatter = sns.scatterplot(
        data=df.head(60),
        x='TPSA', 
        y='ADMET_FractionCSP3', 
        hue='Origem',
        size='Peso_Molar', 
        sizes=(100, 500), 
        palette=['#ff6e40', '#1e3d59'],
        alpha=0.8,
        edgecolor='black',
        ax=ax1
    )
    
    # Zona Verde de Ouro (Regra dos Livros de Farmacologia)
    ax1.axhspan(0.5, 1.0, color='lightgreen', alpha=0.15, label='Zona de Absorção Otimizada (Csp3 > 0.5)')
    ax1.axvspan(40, 100, color='lightblue', alpha=0.15, label='Zona de Polaridade Ideal (TPSA 40-100)')
    
    ax1.set_title('Mapeamento Biológico (Top 60 Seguros via PAINS/BRENK)', fontsize=14, pad=15)
    ax1.set_xlabel('Polaridade da Superfície (TPSA) [Acesso Sanguíneo]', fontsize=11)
    ax1.set_ylabel('Complexidade 3D (Fração Csp3) [Encaixe Proteico]', fontsize=11)
    ax1.legend(loc='lower left', bbox_to_anchor=(0, 1), ncol=2, frameon=False)

    # Anotar um campeão sintético para destaque
    campeao = df[df['Categoria'] == 'Candidato_Farmaceutico_Sintetico'].iloc[0]
    ax1.annotate('Bisturi Químico\n(Sucesso Mutante)', 
                 (campeao['TPSA'], campeao['ADMET_FractionCSP3']),
                 xytext=(20, -30), textcoords='offset points',
                 arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=.2", color='red'),
                 bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.6), fontweight='bold')

    # =========================================================================
    # GRÁFICO 2: RADAR DE TOXICIDADE / METABOLISMO (Barras)
    # =========================================================================
    # Mostrar que os selecionados têm pouquíssimos anéis aromáticos
    top_7 = df.head(7).copy()
    top_7['Nome Curto'] = top_7['ID'].apply(lambda x: str(x).replace("FarmaSintetico_", "Sint. ").replace("Molecula_Util_", "Min. ")[:15])
    
    sns.barplot(
        data=top_7, 
        y='Nome Curto', 
        x='ADMET_AromaticRings', 
        color='#ffc13b', 
        edgecolor='black',
        ax=ax2
    )
    
    ax2.set_title('Perfil de Segurança Hepática', fontsize=14, pad=15)
    ax2.set_xlabel('Qtd. Anéis Aromáticos (Ideal: Menor que 3)', fontsize=11)
    ax2.set_ylabel('')
    
    # Linha Vermelha de Alerta de Toxicidade
    ax2.axvline(x=3, color='red', linestyle='--', linewidth=2, label='Risco de Toxicidade Hepática (>3)')
    ax2.legend(loc='upper right')

    # Ajustes finais
    plt.tight_layout(pad=3.0)
    nome_imagem = "Dashboard_DrugDiscovery_Elite.png"
    plt.savefig(nome_imagem, dpi=300, bbox_inches='tight')
    
    print(f"\n🎉 Relatório Visual Renderizado! Imagem salva como: '{nome_imagem}'")
    plt.show()

if __name__ == '__main__':
    gerar_dashboard_clinico()