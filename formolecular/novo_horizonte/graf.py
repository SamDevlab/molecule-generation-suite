import pandas as pd
import matplotlib.pyplot as plt

# 1. Carregar os dados reais do seu Motor Evolutivo
try:
    df = pd.read_csv("banco_mestre_unificado.csv")
except FileNotFoundError:
    print("Erro: O arquivo 'banco_mestre_unificado.csv' não foi encontrado na pasta.")
    exit()

# 2. Configurar a figura e o estilo visual
fig, ax = plt.subplots(figsize=(11, 7.5))

# 3. Plotar o "ruído de fundo" (Todas as moléculas da Matriz)
ax.scatter(df['1EVE_Eficacia'], df['5W8K_Risco'], 
           c='lightgray', alpha=0.6, edgecolors='darkgray', s=45,
           label=f'Compostos da Matriz ({len(df)} total)')

# 4. Isolar e destacar a Zona de Elite (As 4 melhores moléculas)
# Pegamos o Top 4 usando a nota farmacológica (menor é melhor)
if 'Fitness_Score' in df.columns:
    elite = df.sort_values('Fitness_Score', ascending=True).head(4)
else:
    elite = df.sort_values('1EVE_Eficacia', ascending=True).head(4)

markers = ['o', 's', '^', 'D'] # Círculo, Quadrado, Triângulo, Diamante
nomes_elite = ['Invenção 1 (Campeão)', 'Invenção 2 (Vice)', 'Invenção 3 (Top 3)', 'Invenção 4 (Top 4)']

for i, (index, row) in enumerate(elite.iterrows()):
    ax.scatter(row['1EVE_Eficacia'], row['5W8K_Risco'], 
               c='black', s=160, marker=markers[i], 
               label=f"{nomes_elite[i]} - {row['ID_Mestre']}")
               
    # Adicionar o número (1, 2, 3, 4) ligeiramente deslocado do ponto
    ax.annotate(str(i+1), (row['1EVE_Eficacia'], row['5W8K_Risco']), 
                xytext=(12, 6), textcoords='offset points', 
                fontweight='bold', fontsize=12)

# 5. Desenhar o Limiar Crítico (Muralha de Segurança)
ax.axhline(y=-6.0, color='black', linestyle='--', linewidth=1.5, 
           label='Limiar Crítico hERG (-6.0 kcal/mol)')

# 6. INVERTER OS EIXOS (MÁGICA VISUAL)
# Em docking, números mais negativos são mais fortes. 
# Invertemos para que a leitura visual fique "Crescente para a Direita/Cima"
ax.invert_xaxis()
ax.invert_yaxis()

# 7. Adicionar Textos e Zonas
# ZONA DE CARDIOTOXICIDADE (Canto superior esquerdo nos eixos invertidos)
ax.text(0.02, 0.95, 'ZONA DE CARDIOTOXICIDADE\n(Risco de Arritmia)', 
        transform=ax.transAxes, fontsize=10, fontstyle='italic', 
        verticalalignment='top', bbox=dict(facecolor='white', alpha=0.8, edgecolor='none'))

# ZONA DE ELITE (Canto inferior direito nos eixos invertidos)
ax.text(0.98, 0.05, 'ZONA DE ELITE\n(Alta Eficácia / Segura)', 
        transform=ax.transAxes, fontsize=11, fontweight='bold', 
        horizontalalignment='right', verticalalignment='bottom',
        bbox=dict(facecolor='white', alpha=0.8, edgecolor='none'))

# 8. Títulos e Estilização Final
ax.set_xlabel('Afinidade de Ancoragem AChE (kcal/mol) → Maior Eficácia', fontsize=12, labelpad=10)
ax.set_ylabel('Afinidade de Ancoragem hERG (kcal/mol) → Maior Toxicidade', fontsize=12, labelpad=10)

# Grid pontilhado suave
ax.grid(True, linestyle=':', alpha=0.7)

# Legenda com borda preta sólida no canto inferior esquerdo
legend = ax.legend(loc='lower left', framealpha=1, edgecolor='black', fontsize=10)

# Ajustar margens e salvar
plt.tight_layout()
nome_arquivo = 'relatorio_farmacologico.png'
plt.savefig(nome_arquivo, dpi=300)
print(f"Gráfico gerado com sucesso! Abra o arquivo '{nome_arquivo}' para ver o resultado.")

# Descomente a linha abaixo se quiser que a janela do gráfico abra interativamente na tela:
# plt.show()