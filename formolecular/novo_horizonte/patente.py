import os
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Canvas customizado para adicionar paginação automática no rodapé"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 10)
        self.setFillColor(colors.black)
        texto_pagina = f"{self._pageNumber}"
        self.drawRightString(letter[0] - 70.8, 40, texto_pagina)
        self.restoreState()

def extrair_dados_tabela_markdown(texto_md):
    """Interpreta as linhas da Tabela do Markdown manualmente para o ReportLab"""
    linhas_tabela = []
    for linha in texto_md.split('\n'):
        if '|' in linha:
            if '---' in linha:
                continue
            dados = [celula.strip().replace('**', '') for celula in linha.split('|')[1:-1]]
            if dados:
                linhas_tabela.append(dados)
        elif linhas_tabela:
            break
    return linhas_tabela

def converter_negritos_markdown(texto):
    """Substitui marcações de negrito Markdown (**) por tags HTML válidas (<b>) de forma pareada"""
    # Substitui pares de ** por <b> e </b> de forma segura usando regex
    texto_formatado = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', texto)
    return texto_formatado

def compilar_pdf_limpo(arquivo_md, arquivo_pdf):
    pasta = os.path.dirname(os.path.abspath(arquivo_md))
    
    with open(arquivo_md, 'r', encoding='utf-8') as f:
        conteudo = f.read()

    margem = 70.8 
    doc = SimpleDocTemplate(arquivo_pdf, pagesize=letter,
                            rightMargin=margem, leftMargin=margem,
                            topMargin=margem, bottomMargin=margem)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Estilos de parágrafos oficiais
    estilo_titulo = ParagraphStyle(
        'TituloINPI', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=14, 
        leading=18, alignment=0, spaceAfter=20, spaceBefore=10, textColor=colors.black
    )
    estilo_sub = ParagraphStyle(
        'SubINPI', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, 
        leading=16, spaceBefore=15, spaceAfter=8, textColor=colors.black
    )
    estilo_corpo = ParagraphStyle(
        'CorpoINPI', parent=styles['Normal'], fontName='Helvetica', fontSize=11, 
        leading=16, alignment=4, spaceAfter=10, firstLineIndent=40
    )
    
    # Quebra o arquivo em blocos por linhas vazias
    blocos = conteudo.split('\n\n')
    
    for bloco in blocos:
        bloco = bloco.strip()
        if not bloco:
            continue
            
        # Remove quebras de linha brutas em HTML <br> para evitar travamentos
        bloco = re.sub(r'<br\s*/?>', '', bloco, flags=re.IGNORECASE)
        bloco = bloco.strip()
        if not bloco:
            continue

        # 1. Identifica Títulos Principais (#)
        if bloco.startswith('#'):
            texto = bloco.replace('#', '').strip()
            story.append(Paragraph(converter_negritos_markdown(texto), estilo_titulo))
            continue
            
        # 2. Identifica Subtítulos (##)
        if bloco.startswith('##'):
            texto = bloco.replace('##', '').strip()
            story.append(Paragraph(converter_negritos_markdown(texto), estilo_sub))
            continue
            
        # 3. Processamento estruturado da tabela
        if '|' in bloco:
            if 'Compostos' in bloco:
                dados_brutos = extrair_dados_tabela_markdown(conteudo)
                if dados_brutos:
                    tabela_data = []
                    for r_idx, linha in enumerate(dados_brutos):
                        linha_formatada = []
                        for c_idx, celula in enumerate(linha):
                            f_name = 'Helvetica-Bold' if r_idx == 0 else 'Helvetica'
                            f_size = 10 if r_idx == 0 else 9
                            p_style = ParagraphStyle('cell', fontName=f_name, fontSize=f_size, alignment=1)
                            linha_formatada.append(Paragraph(celula, p_style))
                        tabela_data.append(linha_formatada)
                    
                    t = Table(tabela_data, colWidths=[170, 75, 75, 80, 75])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F2F2F2')),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('GRID', (0,0), (-1,-1), 1, colors.black),
                        ('TOPPADDING', (0,0), (-1,-1), 6),
                        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                    ]))
                    story.append(Spacer(1, 10))
                    story.append(t)
                    story.append(Spacer(1, 10))
            continue
            
        # 4. Manipulação das seções de imagens
        if 'figura1_final.png' in bloco or 'Figura 1' in bloco:
            img_path = os.path.join(pasta, 'figura1_final.png')
            if os.path.exists(img_path):
                story.append(Image(img_path, width=400, height=320))
                story.append(Spacer(1, 5))
            story.append(Paragraph("<b>Figura 1</b>", ParagraphStyle('f1', fontName='Helvetica-Bold', alignment=1)))
            continue
            
        if 'figura2_final.png' in bloco or 'Figura 2' in bloco:
            img_path = os.path.join(pasta, 'figura2_final.png')
            if os.path.exists(img_path):
                story.append(Image(img_path, width=420, height=280))
                story.append(Spacer(1, 5))
            story.append(Paragraph("<b>Figura 2</b>", ParagraphStyle('f2', fontName='Helvetica-Bold', alignment=1)))
            continue
            
        # 5. Tratamento de parágrafos normais (converte ** de forma segura)
        texto_limpo = converter_negritos_markdown(bloco)
        texto_limpo = texto_limpo.replace('***', '')
        
        # Ignora linhas de legendas duplicadas
        if texto_limpo.strip() in ['<b>Figura 1</b>', '<b>Figura 2</b>', 'Figura 1', 'Figura 2']:
            continue
            
        story.append(Paragraph(texto_limpo, estilo_corpo))

    # Salva o arquivo final
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[✅] PDF gerado com correções de negrito aplicadas: {arquivo_pdf}")

if __name__ == "__main__":
    pasta_atual = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else '.'
    input_md = os.path.join(pasta_atual, "patente.md")
    output_pdf = os.path.join(pasta_atual, "patente_oficial.pdf")
    
    if not os.path.exists(input_md):
        print(f"[❌] ERRO: O arquivo '{input_md}' não existe na pasta.")
    else:
        compilar_pdf_limpo(input_md, output_pdf)