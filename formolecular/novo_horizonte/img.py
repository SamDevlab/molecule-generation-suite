import os
import pandas as pd
import matplotlib.pyplot as plt

# Configuração rigorosa de estilo Preto e Branco (Padrão exigido pelo INPI)
plt.rcParams.update({
    'font.size': 11,
    'axes.edgecolor': 'black',
    'axes.linewidth': 1.2,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white'
})

pasta_atual = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else '.'
csv_path = os.path.join(pasta_atual, "ranking_ultralote_completo.csv")

if not os.path.exists(csv_path):
    print(f"[❌] ERRO: O arquivo '{csv_path}' não foi encontrado na pasta.")
    print("Verifique se o nome do CSV gerado pelo Motor 14 está correto nesta pasta.")
else:
    df = pd.read_csv(csv_path)
    
    fig, ax = plt.subplots(figsize=(9, 6.5))
    
    # Aplicar a cor preta nas marcações dos eixos (correção direta via eixos)
    ax.tick_params(axis='both', colors='black')
    
    # 1. Plotar a nuvem cinza de fundo (Todos os 450 compostos do espaço químico)
    ax.scatter(df["Afinidade_1EVE (AChE)"], df["Afinidade_5W8K (hERG)"], 
               color="#D3D3D3", alpha=0.6, s=35, label="Compostos da Matriz (450 total)", 
               edgecolors='#A9A9A9', linewidths=0.5)
    
    # 2. Linha de Segurança Crítica do hERG em -6.0 (Fronteira de toxicidade)
    ax.axhline(y=-6.0, color='black', linestyle='--', linewidth=1.5, label="Limiar Crítico hERG (-6.0 kcal/mol)")
    
    # 3. Dados das Concretizações Preferenciais extraídos da tabela da patente
    elites = [
        {"ache": -8.790, "herg": -5.610, "label": "Invenção 1 (Trans-Fluorovinil)"},
        {"ache": -9.064, "herg": -5.899, "label": "Invenção 2 (Flúor Central)"},
        {"ache": -8.696, "herg": -5.535, "label": "Invenção 3 (Ciano Original)"},
        {"ache": -8.943, "herg": -5.841, "label": "Invenção 4 (Epóxido)"}
    ]
    
    # Marcadores geométricos pretos bem visíveis
    marcadores = ['o', 's', '^', 'D']
    for i, item in enumerate(elites):
        ax.scatter(item["ache"], item["herg"], color='black', marker=marcadores[i], s=90, 
                   edgecolors='black', linewidths=1.5, label=item["label"])
        # Injeta o número da invenção ao lado do ponto correspondente
        ax.annotate(f" {i+1}", (item["ache"], item["herg"]), textcoords="offset points", 
                    xytext=(4,4), ha='left', fontweight='bold', color='black')

    # Configuração dos eixos (Invertidos: valores mais negativos = maior afinidade/força)
    ax.set_xlabel("Afinidade de Ancoragem AChE (kcal/mol) → Maior Eficácia")
    ax.set_ylabel("Afinidade de Ancoragem hERG (kcal/mol) → Maior Toxicidade")
    
    # Limites estritos para focar no cluster de dados útil
    ax.set_xlim(-6.0, -10.0)
    ax.set_ylim(-4.5, -7.5)
    
    # Textos indicativos das regiões termodinâmicas no gráfico
    ax.text(-6.5, -7.1, "ZONA DE CARDIOTOXICIDADE\n(Risco de Arritmia)", color='black', fontsize=9, ha='center', va='center', fontstyle='italic')
    ax.text(-9.3, -5.0, "ZONA DE ELITE\n(Alta Eficácia / Segura)", color='black', fontsize=9, ha='center', fontweight='bold')
    
    # Legenda estruturada com moldura preta limpa
    ax.legend(loc="lower left", frameon=True, edgecolor='black', facecolor='white')
    ax.grid(True, linestyle=':', alpha=0.4, color='gray')
    
    plt.tight_layout()
    caminho_fig2 = os.path.join(pasta_atual, "figura2_final.png")
    plt.savefig(caminho_fig2, dpi=300, facecolor='white')
    plt.close()
    
    print(f"[✅] SCRIPT COMPILADO COM SUCESSO!")
    print(f"[-] Figura 2 (Gráfico de Seletividade) salva em: {caminho_fig2}")