import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Configuração de estilo visual premium
sns.set_theme(style="darkgrid")
plt.rcParams['figure.figsize'] = [16, 8]

# Caminho do ficheiro que a tua IA gerou
ARQUIVO_ELITE = os.path.join("csv_elite_aero", "RANKING_COMBUSTIVEIS_ELITE.csv")

def gerar_dashboard_portfolio():
    print("\n[📊] A iniciar o motor de renderização gráfica...")
    
    if not os.path.exists(ARQUIVO_ELITE):
        print(f"[!] Erro: Ficheiro '{ARQUIVO_ELITE}' não encontrado. Certifica-te de que rodaste a varredura.")
        return

    # Lê os dados da elite
    df = pd.read_csv(ARQUIVO_ELITE)
    top_plot = df.head(50) # Focamos no Top 50 para o gráfico não ficar uma "nuvem" confusa
    
    # Criar um painel com 2 gráficos lado a lado
    fig, (ax1, ax2) = plt.subplots(1, 2, gridspec_kw={'width_ratios': [2, 1.2]})
    fig.suptitle('Análise Preditiva de Propelentes Aeroespaciais (Pipeline XGBoost + RDKit)', 
                 fontsize=18, fontweight='bold', y=0.98)

    # =========================================================================
    # GRÁFICO 1: O MAPA DO IMPULSO ESPECÍFICO (Dispersão)
    # =========================================================================
    scatter = ax1.scatter(
        top_plot['Peso_Molar'], 
        top_plot['IA_Pred_ISP_Teorico'], 
        c=top_plot['AERO_Fator_Expansao_Gas'], 
        cmap='plasma', 
        s=(top_plot['AERO_Qtd_Nitrogenio'] + 1) * 60, # Tamanho da bolha reflete o Nitrogénio expansivo
        alpha=0.8,
        edgecolors='w',
        linewidth=1.5
    )
    
    ax1.set_title('Top 50 Sintéticos: A "Zona de Ouro" da Propulsão', fontsize=14)
    ax1.set_xlabel('Peso Molar (g/mol) [← Moléculas mais leves geram maior velocidade]', fontsize=11)
    ax1.set_ylabel('Impulso Específico Relativo (Previsto pela IA)', fontsize=11)
    
    # Anotar os 3 campeões absolutos para se destacarem no gráfico
    for i, row in df.head(3).iterrows():
        nome_curto = row['ID'].replace("PropSintetico_", "")
        ax1.annotate(nome_curto, 
                     (row['Peso_Molar'], row['IA_Pred_ISP_Teorico']),
                     xytext=(15, 10), textcoords='offset points',
                     bbox=dict(boxstyle="round,pad=0.4", fc="yellow", alpha=0.7),
                     fontweight='bold', fontsize=9)

    # Barra lateral de cor para mostrar o Fator de Expansão
    cbar = fig.colorbar(scatter, ax=ax1)
    cbar.set_label('Fator de Expansão de Gás (Densidade Energética)', rotation=270, labelpad=15)

    # =========================================================================
    # GRÁFICO 2: RANKING DIRETO (Barras Horizontais)
    # =========================================================================
    top_7 = df.head(7)
    nomes_limpos = [nome.replace("PropSintetico_", "").replace("_", " ") for nome in top_7['ID']]
    
    # Criar barras com cores que combinam com o tema 'plasma'
    ax2.barh(nomes_limpos, top_7['IA_Pred_ISP_Teorico'], color='#8c2981', edgecolor='black')
    ax2.set_title('Top 7: Liderança Global de Performance', fontsize=14)
    ax2.set_xlabel('Score de I_sp Teórico', fontsize=11)
    ax2.invert_yaxis() # Inverte para o 1º lugar ficar no topo da lista

    # Linha de base da Hidrazina/Querosene (Aproximada na mesma escala para efeito visual)
    baseline_tradicional = 0.85 
    ax2.axvline(x=baseline_tradicional, color='red', linestyle='--', linewidth=2, 
                label='Baseline: Propelentes Tradicionais Est.')
    ax2.legend(loc='lower right')
    
    # Ajusta o limite X para a barra não colar no limite do ecrã
    ax2.set_xlim(0.8, top_7['IA_Pred_ISP_Teorico'].max() + 0.05)

    # =========================================================================
    # FINALIZAÇÃO E EXPORTAÇÃO
    # =========================================================================
    plt.tight_layout(pad=3.0)
    nome_imagem = "Dashboard_Oraculo_Aeroespacial.png"
    plt.savefig(nome_imagem, dpi=300, bbox_inches='tight') # dpi=300 garante qualidade 4K
    print(f"\n🎉 Dashboard renderizado com sucesso! Ficheiro salvo como: '{nome_imagem}'")
    
    # Abre a janela para tu veres imediatamente
    plt.show()

if __name__ == '__main__':
    gerar_dashboard_portfolio()