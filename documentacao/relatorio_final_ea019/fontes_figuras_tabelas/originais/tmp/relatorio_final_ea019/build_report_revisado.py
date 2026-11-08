from pathlib import Path
from copy import deepcopy
import json, hashlib, zipfile, re
import pandas as pd
from lxml import etree
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

TMP=Path(__file__).resolve().parent
ROOT=TMP.parents[1]
REF=TMP/'modelo_referencia.docx'
FINAL=ROOT/'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_Revisado.docx'
FINAL.parent.mkdir(parents=True,exist_ok=True)
SHA='aecee899b62d0042f5104d90332a6fb0fd13a90779cb69fb3ea7df4740e3e9d1'
assert hashlib.sha256(REF.read_bytes()).hexdigest()==SHA
E=json.loads((TMP/'evidencias_disciplina.json').read_text(encoding='utf-8'))
BASE=ROOT/'resultados/relatorios/pdfs_resumidos_legiveis_20261027/disciplina'
D=pd.read_csv(BASE/'metricas_teste_modelos_disciplina.csv')
R=pd.read_csv(BASE/'classificacoes_modelos_disciplina.csv')
TASKS=[('hourly_72_extension',72,'Horária 72 h'),('daily_30',30,'Diária 30 d'),('monthly_1',1,'Mensal 1 m'),('monthly_6',6,'Mensal 6 m')]
MODELS=['Transformer','Informer','LSTM']
REGS=[('atual','Atual'),('historico_1998_2022','Histórico longo'),('historico_curto_pareado','Histórico curto')]

def f(x,n=2): return f'{float(x):,.{n}f}'.replace(',','@').replace('.',',').replace('@','.')
def variant(v): return {'sem_quantizacao':'Controle','q64':'64','q128':'128','q256':'256'}[v]
def rr(reg,t,m,H,v):
    s=D[(D.regime==reg)&(D.tarefa==t)&(D.modelo==m)&(D.horizonte==H)&(D.variante==v)]
    assert len(s)==1;return s.iloc[0]
def sel(reg,t,m):
    s=R[(R.regime==reg)&(R.tarefa==t)&(R.modelo==m)];assert len(s)==1;return s.iloc[0]

# Work from the retained template, then preserve its opaque parts byte for byte.
doc=Document(REF)
body=doc._element.body
sect=deepcopy(body.sectPr)
for child in list(body):body.remove(child)
body.append(sect)
styles=doc.styles
def configure(name,size=12,bold=False,align=WD_ALIGN_PARAGRAPH.JUSTIFY,before=0,after=6,first=.75,outline=None):
    s=styles[name] if name in styles else styles.add_style(name,WD_STYLE_TYPE.PARAGRAPH)
    s.font.name='Times New Roman';s.font.size=Pt(size);s.font.bold=bold;s.font.italic=False;s.font.color.rgb=RGBColor(0,0,0)
    fonts=s._element.get_or_add_rPr().find(qn('w:rFonts'))
    if fonts is not None:
        for key in list(fonts.attrib):
            if key.endswith('Theme'):del fonts.attrib[key]
        for key in ['ascii','hAnsi','eastAsia','cs']:fonts.set(qn('w:'+key),'Times New Roman')
    s._element.get_or_add_rPr().append(OxmlElement('w:lang'))
    s._element.rPr[-1].set(qn('w:val'),'pt-BR')
    pf=s.paragraph_format;pf.alignment=align;pf.space_before=Pt(before);pf.space_after=Pt(after);pf.line_spacing=1
    pf.first_line_indent=Cm(first);pf.left_indent=Cm(0);pf.right_indent=Cm(0);pf.widow_control=True
    if outline is not None:
        x=OxmlElement('w:outlineLvl');x.set(qn('w:val'),str(outline));s._element.get_or_add_pPr().append(x)
    # Never retain theme-based heading colors, rules, or inherited numbering.
    for tag in ['w:pBdr','w:numPr']:
        for el in list(s._element.get_or_add_pPr().findall(qn(tag))):el.getparent().remove(el)
    return s
configure('Normal')
configure('Title',18,True,WD_ALIGN_PARAGRAPH.CENTER,0,14,0)
configure('Subtitle',14,False,WD_ALIGN_PARAGRAPH.CENTER,0,14,0)
configure('Heading 1',14,True,WD_ALIGN_PARAGRAPH.LEFT,14,8,0,0)
configure('Heading 2',12,True,WD_ALIGN_PARAGRAPH.LEFT,12,6,0,1)
configure('Heading 3',12,True,WD_ALIGN_PARAGRAPH.LEFT,10,5,0,2)
for n in ['Heading 1','Heading 2','Heading 3']:styles[n].paragraph_format.keep_with_next=True
configure('Caption',10.5,False,WD_ALIGN_PARAGRAPH.CENTER,6,4,0)
configure('Fonte',10,False,WD_ALIGN_PARAGRAPH.LEFT,2,8,0)
configure('Frente',12,False,WD_ALIGN_PARAGRAPH.CENTER,0,8,0)
configure('FrontHeading',14,True,WD_ALIGN_PARAGRAPH.CENTER,0,14,0)
configure('TabelaCorpo',10.5,False,WD_ALIGN_PARAGRAPH.LEFT,0,0,0)
configure('Bibliografia',11,False,WD_ALIGN_PARAGRAPH.LEFT,0,8,0)
for i in range(1,4):
    s=configure('TOC '+str(i),10.5,False,WD_ALIGN_PARAGRAPH.LEFT,0,0,0)
    s._element.find(qn('w:name')).set(qn('w:val'),'toc '+str(i))
    s._element.attrib.pop(qn('w:customStyle'),None)
    s.paragraph_format.left_indent=Cm((i-1)*.5)
    s.paragraph_format.tab_stops.add_tab_stop(Cm(16.7),WD_TAB_ALIGNMENT.RIGHT,WD_TAB_LEADER.DOTS)
if 'Hyperlink' in styles:
    styles['Hyperlink'].font.color.rgb=RGBColor(0,0,0);styles['Hyperlink'].font.underline=False
doc.core_properties.title='Previsão de irradiância solar com Transformer Informer e LSTM'
doc.core_properties.subject='Relatório final de disciplina sobre previsão multirresolução de GHI e quantização das entradas'
doc.core_properties.author='Gustavo de Melo Nascimento'
doc.core_properties.keywords='GHI; NSRDB; LSTM; Transformer; Informer; quantização; previsão solar'
doc.core_properties.comments=''

def p(txt='',style=None,align=None,bold=None):
    txt=txt.replace('combinações modelo tarefa','combinações de modelo e tarefa')
    z=doc.add_paragraph(style=style or 'Normal');run=z.add_run(txt)
    if bold is not None:run.bold=bold
    if align is not None:z.alignment=align
    return z
def paras(txt):
    for s in txt.strip().split('\n\n'):p(' '.join(s.split()))
def h(txt,level=1,new=False):
    z=p(txt,'Heading '+str(level));z.paragraph_format.page_break_before=new;return z
def page():doc.add_page_break()
def spacer(cm):
    z=p('','Frente');z.paragraph_format.space_after=Cm(cm);z.paragraph_format.space_before=Pt(0);return z
def field(par,instr,cache=''):
    r=OxmlElement('w:r');b=OxmlElement('w:fldChar');b.set(qn('w:fldCharType'),'begin');r.append(b);par._p.append(r)
    r=OxmlElement('w:r');t=OxmlElement('w:instrText');t.set(qn('xml:space'),'preserve');t.text=' '+instr+' ';r.append(t);par._p.append(r)
    r=OxmlElement('w:r');s=OxmlElement('w:fldChar');s.set(qn('w:fldCharType'),'separate');r.append(s);par._p.append(r)
    if cache:par.add_run(cache)
    r=OxmlElement('w:r');e=OxmlElement('w:fldChar');e.set(qn('w:fldCharType'),'end');r.append(e);par._p.append(r)

# Retain first-page header behavior. Add unobtrusive page field to default footer only.
footer=doc.sections[0].footer
fp=footer.paragraphs[0];fp.alignment=WD_ALIGN_PARAGRAPH.CENTER
fp.paragraph_format.space_after=Pt(0);fp.paragraph_format.first_line_indent=Cm(0)
field(fp,'PAGE','2')
for r in fp.runs:r.font.name='Times New Roman';r.font.size=Pt(10)
settings=doc.settings.element
upd=OxmlElement('w:updateFields');upd.set(qn('w:val'),'true');settings.append(upd)

tn=0;fn=0;captions=[]
def table(title,heads,rows,widths=None,note='',size=10.5):
    global tn
    tn+=1
    c=p(f'Tabela {tn} — {title}','Caption');c.paragraph_format.keep_with_next=True
    t=doc.add_table(rows=1, cols=len(heads));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    if widths is None:widths=[17/len(heads)]*len(heads)
    for col,w in zip(t.columns,widths):col.width=Cm(w)
    tblPr=t._tbl.tblPr
    borders=OxmlElement('w:tblBorders')
    for side in ['top','left','bottom','right','insideH','insideV']:
        el=OxmlElement('w:'+side)
        for k,v in [('val','single'),('sz','4'),('color','D9D9D9')]:el.set(qn('w:'+k),v)
        borders.append(el)
    tblPr.append(borders)
    margins=OxmlElement('w:tblCellMar')
    for side in ['top','left','bottom','right']:
        el=OxmlElement('w:'+side);el.set(qn('w:w'),'90');el.set(qn('w:type'),'dxa');margins.append(el)
    tblPr.append(margins)
    for j,s in enumerate(heads):t.rows[0].cells[j].text=str(s)
    repeat=OxmlElement('w:tblHeader');repeat.set(qn('w:val'),'true');t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for row in rows:
        cells=t.add_row().cells
        for j,s in enumerate(row):cells[j].text=str(s)
    for i,row in enumerate(t.rows):
        pr=row._tr.get_or_add_trPr();pr.append(OxmlElement('w:cantSplit'))
        for j,cell in enumerate(row.cells):
            cell.width=Cm(widths[j]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if i==0:
                sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'E8ECEF');cell._tc.get_or_add_tcPr().append(sh)
            for par in cell.paragraphs:
                par.style=styles['TabelaCorpo'];par.alignment=WD_ALIGN_PARAGRAPH.LEFT if j==0 else WD_ALIGN_PARAGRAPH.CENTER
                if len(rows)<=6 and i<len(t.rows)-1:par.paragraph_format.keep_with_next=True
                for r in par.runs:r.font.name='Times New Roman';r.font.size=Pt(size);r.bold=i==0
    p('Fonte: elaboração própria a partir dos dados e contratos auditados do projeto.'+(' '+note if note else ''),'Fonte')
    captions.append(('Tabela',tn,title));return t
def fig(name,title,note='',source='elaboração própria',width=16.7):
    global fn
    fn+=1
    c=p(f'Figura {fn} — {title}','Caption');c.paragraph_format.keep_with_next=True
    z=p('',align=WD_ALIGN_PARAGRAPH.CENTER);z.paragraph_format.first_line_indent=Cm(0);z.paragraph_format.space_after=Pt(2);z.paragraph_format.keep_with_next=True
    pic=z.add_run().add_picture(str(TMP/'revisao_artigo/figuras'/f'{name}.png'),width=Cm(width))
    pic._inline.docPr.set('descr',title)
    p('Fonte: '+source+'.'+(' '+note if note else ''),'Fonte')
    captions.append(('Figura',fn,title))

# Native editable Office Math, including fractions, roots, sub/superscripts.
M='http://schemas.openxmlformats.org/officeDocument/2006/math'
def mr(s):
    r=etree.Element('{%s}r'%M);t=etree.SubElement(r,'{%s}t'%M);t.text=s;return r
def frac(a,b):
    z=etree.Element('{%s}f'%M)
    for tag,items in [('num',a),('den',b)]:
        e=etree.SubElement(z,'{%s}%s'%(M,tag))
        for item in (items if isinstance(items,list) else [mr(items)]):e.append(item)
    return z
def rad(items):
    z=etree.Element('{%s}rad'%M);pr=etree.SubElement(z,'{%s}radPr'%M);hide=etree.SubElement(pr,'{%s}degHide'%M);hide.set('{%s}val'%M,'1');etree.SubElement(z,'{%s}deg'%M)
    e=etree.SubElement(z,'{%s}e'%M)
    for it in items:e.append(it)
    return z
def script(base,sub=None,sup=None):
    kind='sSubSup' if sub is not None and sup is not None else ('sSub' if sub is not None else 'sSup')
    z=etree.Element('{%s}%s'%(M,kind));e=etree.SubElement(z,'{%s}e'%M);e.append(mr(base))
    for tag,val in [('sub',sub),('sup',sup)]:
        if val is not None:etree.SubElement(z,'{%s}%s'%(M,tag)).append(mr(val))
    return z
def summation(index,upper,items):
    z=etree.Element('{%s}nary'%M);pr=etree.SubElement(z,'{%s}naryPr'%M)
    ch=etree.SubElement(pr,'{%s}chr'%M);ch.set('{%s}val'%M,'∑')
    loc=etree.SubElement(pr,'{%s}limLoc'%M);loc.set('{%s}val'%M,'subSup')
    etree.SubElement(z,'{%s}sub'%M).append(mr(index));etree.SubElement(z,'{%s}sup'%M).append(mr(upper))
    e=etree.SubElement(z,'{%s}e'%M)
    for it in items:e.append(mr(it) if isinstance(it,str) else it)
    return z
def eq(items,label):
    z=p('',align=WD_ALIGN_PARAGRAPH.CENTER);z.paragraph_format.first_line_indent=Cm(0);z.paragraph_format.space_after=Pt(8)
    math=etree.Element('{%s}oMath'%M)
    for it in items:math.append(mr(it) if isinstance(it,str) else it)
    z._p.append(math);z.add_run('     ('+label+')')

# Cover follows the source's large centered fields and institutional branding.
spacer(2.6)
p('GUSTAVO DE MELO NASCIMENTO','Frente')
spacer(1.9)
p('PREVISÃO DE IRRADIÂNCIA SOLAR\nCOM TRANSFORMER INFORMER E LSTM','Title')
p('Avaliação multirresolução e quantização das entradas','Subtitle')
spacer(.6)
p('Link do vídeo: __________________________________','Frente')
spacer(4.6)
p('CAMPINAS','Frente');p('2026','Frente')
page()
spacer(3)
p('PREVISÃO DE IRRADIÂNCIA SOLAR\nCOM TRANSFORMER INFORMER E LSTM','Title')
p('Avaliação multirresolução e quantização das entradas','Subtitle')
spacer(1.2)
z=p('Relatório final apresentado à Faculdade de Engenharia Elétrica e de Computação da Universidade Estadual de Campinas, no âmbito do trabalho de conclusão de curso em Engenharia Elétrica.');z.paragraph_format.left_indent=Cm(7.3);z.paragraph_format.first_line_indent=Cm(0)
spacer(.7)
for s in ['Aluno: Gustavo de Melo Nascimento','RA: __________________________________','Disciplina: ______________________________','Semestre: ______________________________','Orientador: _____________________________']:p(s,'Frente')
spacer(2.1)
p('CAMPINAS','Frente');p('2026','Frente')
page()
p('RESUMO','FrontHeading')
paras('''Este trabalho avalia a previsão de irradiância global horizontal (GHI) com implementações de LSTM, Transformer e Informer, considerando a resolução temporal dos dados, a duração do histórico disponível e a quantização uniforme das entradas. Utilizam-se estimativas da National Solar Radiation Database em dez localidades associadas a instalações industriais no Brasil, nos Estados Unidos e no México. O protocolo contempla previsão horária de até 72 horas, diária de até 30 dias, mensal de um passo e mensal de seis passos, sendo a última exploratória. Comparam-se entradas contínuas com reconstruções em 64, 128 e 256 níveis, mantendo alvos e pesos contínuos. As decisões de treinamento e de nível são tomadas na validação; o teste é reservado à avaliação da escolha congelada. As métricas são calculadas por localidade e agregadas por média macro.

No teste de 2024, o Transformer apresenta o menor MAE no horizonte horário completo, com 53,2061 W/m², e no diário, com 43,8869 W/m². O Informer apresenta os menores MAEs mensais, com 12,7266 W/m² em um passo e 13,6679 W/m² em seis passos. A quantização escolhida na validação reduz o MAE de teste em cinco combinações modelo tarefa, aumenta-o em quatro e mantém o controle em três. Na comparação histórica pareada, o controle sem quantização melhora com o histórico longo em onze das doze combinações, com exceção da LSTM horária. Os resultados indicam que o efeito da quantização e a ordenação dos modelos dependem da tarefa. A presença de clipping nas variantes quantizadas impede atribuir seus efeitos exclusivamente à discretização. O estudo não mede compressão dos modelos, aceleração computacional ou produção fotovoltaica.''')
p('Palavras-chave: irradiância global horizontal; previsão de séries temporais; LSTM; Transformer; Informer; quantização de entradas.','Normal')
page()
p('SUMÁRIO','FrontHeading')
field(p('','Normal'),'TOC \\o "1-2" \\h \\z \\u','')
page()

h('1 INTRODUÇÃO',new=False)
paras('''A previsão do recurso solar permite antecipar condições que afetam o planejamento de sistemas fotovoltaicos e a operação de sistemas elétricos. Sua utilidade depende tanto do horizonte de decisão quanto da informação disponível na emissão da previsão. Variações de nebulosidade e os ciclos astronômicos produzem comportamentos distintos em escalas horárias, diárias e mensais; por isso, resultados obtidos em uma resolução não devem ser transferidos diretamente para outra [13]. Neste relatório, o objeto previsto é a irradiância global horizontal, expressa em W/m², e não a energia elétrica produzida por uma usina.

O problema estudado é restrito e verificável: avaliar se a resolução de amplitude do histórico de GHI pode ser reduzida sem comprometer a qualidade das previsões de três redes temporais. A entrada histórica é normalizada e, em variantes específicas, projetada sobre 64, 128 ou 256 valores possíveis. Essa operação permite investigar a sensibilidade das redes à precisão da informação de entrada. Não modifica a natureza contínua do alvo e não corresponde, por si só, à implementação de inferência inteira ou à compactação dos pesos da rede.

O trabalho compara uma rede recorrente LSTM com duas arquiteturas baseadas em atenção, Transformer e Informer [3–5]. As três implementações compartilham parâmetros entre as dez localidades e recebem a identidade de cada local por um embedding. A comparação é conduzida sob janelas temporais e regras de avaliação comuns. O compartilhamento de parâmetros caracteriza uma modelagem global, mas não demonstra generalização para localidades ausentes do treinamento [10].

As séries provêm da NSRDB, uma base de estimativas do recurso solar obtidas por modelagem e informações de sensoriamento remoto [1,2]. As coordenadas de instalações industriais servem à seleção de células geográficas. Essa associação oferece um contexto de aplicação, sem representar medições em telhados, cargas industriais ou operação de sistemas fotovoltaicos. A distinção delimita a interpretação dos resultados e evita traduzir diretamente uma redução de erro de irradiância em um ganho energético ou econômico.

Os resultados apresentados correspondem ao recorte de três modelos utilizado na disciplina e provêm dos artefatos auditados do projeto.''')
h('Questões de pesquisa',2)
paras('''A primeira questão é como a quantização das entradas afeta o erro de previsão dentro de cada tarefa. A segunda é se a escolha de um nível na validação preserva seu desempenho no teste. A terceira é como os três modelos se comportam quando o histórico de ajuste é ampliado, mantendo o teste histórico idêntico. Essas questões são respondidas por comparações complementares: avaliação de 2024, análise das quatro condições de entrada e comparação entre históricos longo e curto pareados.

Os resultados não apontam uma arquitetura vencedora em todas as tarefas. No regime atual, o Transformer lidera os horizontes horário e diário completos, enquanto o Informer lidera as duas tarefas mensais. A quantização apresenta ganhos e perdas conforme o modelo e o cenário. Essa dependência orienta a discussão: a análise busca identificar em que condições a redução da resolução de entrada se mostra compatível com a precisão observada, mantendo explícitas as limitações da avaliação.''')
p('As seções seguintes apresentam objetivos, metodologia, fundamentos, resultados e conclusões. Os apêndices detalham os checkpoints, as condições de entrada e a proveniência dos dados.')

h('2 OBJETIVOS',new=True)
h('Objetivo geral',2)
p('Avaliar o efeito da quantização uniforme das entradas históricas sobre a previsão multirresolução de GHI com LSTM, Transformer e Informer, preservando a separação cronológica dos dados, os alvos contínuos e um critério de seleção definido na validação.')
h('Objetivos específicos',2)
for txt in [
'Organizar as séries das dez localidades e caracterizar as tarefas horária, diária e mensais, distinguindo contexto de entrada, horizonte de saída e número de origens de teste.',
'Comparar o controle contínuo com entradas reconstruídas em 64, 128 e 256 níveis, mantendo a mesma formulação de regressão e as regras de pós-processamento.',
'Selecionar épocas e condição de entrada sem consultar as métricas de teste, documentando o refit e a composição das previsões entre sementes.',
'Analisar MAE, MSE, RMSE, nRMSE e R² em unidades e agregações consistentes, com ênfase no macro-MAE cumulativo.',
'Comparar os históricos longo e curto sob validação e teste pareados, separando essa análise da avaliação de 2024.',
'Apresentar resultados rastreáveis, tabelas editáveis e figuras próprias que permitam interpretar os ganhos, perdas e limites da quantização.'
]:p(txt)
h('Delimitação do estudo',2)
paras('''O estudo utiliza somente GHI histórica e identidade da localidade como entradas das redes. Não incorpora previsões numéricas do tempo, imagens de nuvens, temperatura de módulos, demanda fabril ou geração fotovoltaica. O cenário é retrospectivo; não se simulam atrasos de publicação da NSRDB ou custos operacionais de disponibilização dos dados.

Não se pretende demonstrar que a quantização reduz memória ou tempo de execução. Os valores discretizados são reconstruídos em float32 e os pesos não são quantizados. Também não se pretende atribuir diferenças pequenas a uma superioridade estatística ou estabelecer uma comparação universal entre famílias de modelos. As conclusões se aplicam às implementações, aos dados e aos protocolos efetivamente avaliados.''')

h('3 METODOLOGIA',new=True)
h('Dados utilizados',2)
paras('''A base contém dez séries de GHI associadas a coordenadas de referência de instalações industriais nas Américas. A Tabela 1 identifica os pontos e suas coordenadas. O conjunto é geograficamente heterogêneo, porém foi selecionado de forma intencional e não constitui amostra aleatória de fábricas ou climas. As coordenadas selecionam células da NSRDB; não indicam posições de sensores instalados nas unidades industriais.

A documentação da API PSM v4 informa resolução espacial nominal de 4 km e registros nativos de 30 minutos, com possibilidade de consulta em intervalos de 30 ou 60 minutos [2]. No protocolo do projeto, a série horária é formada a partir de registros de 30 minutos. As médias diárias foram obtidas de uma consulta separada em 60 minutos, e as médias mensais são médias aritméticas das diárias. Assim, todas as resoluções mantêm a unidade W/m², mas não derivam necessariamente do mesmo conjunto de registros brutos.''')
sites=[['BYD Camaçari','BR','−12,6734','−38,2812'],['Tesla Nevada','EUA','39,5404','−119,4391'],['Tesla Texas','EUA','30,2219','−97,6188'],['Hyundai Georgia','EUA','32,1605','−81,4510'],['Rivian Normal','EUA','40,5093','−89,0545'],['Tesla Fremont','EUA','37,4927','−121,9415'],['Lucid Casa Grande','EUA','32,8569','−111,7784'],['GM Factory Zero','EUA','42,3815','−83,0453'],['Ford Rouge EV Center','EUA','42,3056','−83,1676'],['BMW San Luis Potosí','MX','21,9683','−100,8492']]
fig('11_mapa','Distribuição geográfica e contexto climático das dez localidades',
    'Mapa reproduzido da Figura 1 do artigo [14]. Os números 1 a 10 seguem a ordem da Tabela 1. Os painéis ampliam os Estados Unidos e a região de Detroit. Cores e códigos climáticos têm função descritiva e não são entradas dos modelos.',
    source='Nascimento, Cabral e Fraidenraich [14]')
page()
table('Localidades e coordenadas de referência',['Localidade','País','Latitude','Longitude'],sites,[7.7,2,3.65,3.65],note='Coordenadas em graus decimais, conforme a tabela de localidades do manuscrito do projeto.')
paras('''A preparação verifica a coerência temporal e a identidade das localidades. Valores de GHI não finitos ou negativos, datas inválidas, duplicatas e lacunas são tratados como condições de falha da validação dos dados; registros fora de ordem são reordenados. Não se pressupõe preenchimento por interpolação ou inserção de zeros. A construção das janelas mantém o histórico estritamente anterior à origem e exige que todo o vetor de alvos esteja dentro da partição admissível.

As origens são os instantes em que se emite um vetor de previsão. Como janelas consecutivas podem compartilhar instantes-alvo, o número de pares origem passo é maior do que o número de timestamps distintos. Essa estrutura é preservada na avaliação e precisa ser considerada ao interpretar a quantidade de pontos e a dependência entre erros.''')
h('Resoluções temporais da GHI',2,new=True)
p('A mesma grandeza física apresenta estruturas diferentes conforme a agregação temporal. Os perfis a seguir mostram a série de referência de BYD Camaçari em intervalos fixos do calendário de 2024. A curva horária evidencia ciclos diurnos; as médias diárias e mensais sintetizam os intervalos correspondentes. As três escalas conservam a unidade W/m². A comparação visual caracteriza os dados e não representa previsões dos modelos.')
fig('10_perfis_dados','Perfis reais da GHI nas resoluções horária diária e mensal',
    'Séries NSRDB de BYD Camaçari. Semana de 1 a 7 de janeiro, médias diárias de janeiro e médias mensais de 2024. Horária e diária provêm de consultas independentes; a mensal é calculada das diárias. Escalas verticais próprias por painel.')
h('Tarefas e janelas temporais',2)
fig('08_janelas','Contextos observados e horizontes de saída nas quatro tarefas',
    'Diagrama esquemático, sem escala de duração. C representa o comprimento do histórico e H o número de valores futuros. As tarefas mensais de um e seis passos utilizam redes treinadas separadamente.')
table('Contextos de entrada e cobertura efetiva de teste',['Tarefa','Contexto C','Saída H','Origens 2024 por local','Origens históricas por local'],[
['Horária','336 horas','72 horas','363','1.368'],['Diária','365 dias','30 dias','337','1.342'],['Mensal um passo','12 meses','1 mês','12','45'],['Mensal seis passos','12 meses','6 meses','7','40']],[4.3,2.8,2.8,3.55,3.55],note='As contagens históricas são iguais no longo e no curto pareado. O horizonte mensal de seis passos é exploratório.')
paras('''O contexto horário corresponde a duas semanas de observações; os contextos diário e mensal abrangem aproximadamente um ciclo anual. As redes produzem o vetor futuro diretamente. Na tarefa mensal de seis passos, os erros cumulativos de um, três e seis meses pertencem à mesma rede de saída H igual a seis. O primeiro passo dessa tarefa não deve ser confundido com a rede treinada separadamente para H igual a um.

Os checkpoints são 24, 48 e 72 horas; 1, 3, 7, 14 e 30 dias; um mês para a tarefa mensal curta; e 1, 3 e 6 meses para a tarefa exploratória. Os valores do corpo do relatório são cumulativos. Por exemplo, o MAE de 72 horas reúne os passos de 1 a 72 de todas as origens válidas e não representa apenas o erro no terceiro dia.''')
h('Separação cronológica e comparação pareada',2)
fig('09_particoes','Partições temporais e comparabilidade entre os regimes',
    'Blocos sem escala proporcional de duração. O refit inclui somente dados anteriores ao teste. Histórico longo e curto pareado compartilham validação e teste; o regime atual avalia outro período.')
table('Regimes temporais de seleção e avaliação',['Regime','Histórico inicial','Validação','Refit antes do teste','Teste'],[
['Atual','jan 2019 a dez 2022','jan a dez 2023','jan 2019 a dez 2023','jan a dez 2024'],
['Histórico longo','jan 1998 a mar 2018','abr 2018 a mar 2019','jan 1998 a mar 2019','abr 2019 a dez 2022'],
['Histórico curto pareado','abr 2014 a mar 2018','abr 2018 a mar 2019','abr 2014 a mar 2019','abr 2019 a dez 2022']],[3.2,3.5,3.1,3.8,3.4])
paras('''Os intervalos da Tabela 3 delimitam a informação admissível. O contexto C desloca a primeira origem válida, e o horizonte H limita a última. No regime atual, 2019 também fornece contexto para as primeiras janelas diárias e mensais com alvos em 2020. Na avaliação deslizante, observações já disponíveis durante o ano de teste podem compor o histórico de uma emissão posterior; isso não implica atualizar pesos, escalas ou níveis selecionados com o teste.

A comparação de duração do histórico usa os regimes longo e curto pareado, que compartilham validação, teste e alvos. A auditoria de pareamento confirma a comparabilidade. A avaliação de 2024 responde a outra pergunta, com outra realização temporal, e não funciona como braço de um experimento causal sobre quantidade de anos de treinamento.

Na tarefa horária histórica, a auditoria registra 1.368 origens efetivas por localidade, em vez das 1.369 previstas genericamente no contrato. O recorte de cobertura UTC e local exclui a origem de 29 de dezembro de 2022. São utilizadas as contagens efetivamente auditadas em ambos os históricos; a diferença de uma origem não é preenchida artificialmente.''')
fig('01_fluxo','Fluxo experimental em etapas de dados seleção e avaliação',
    'Organização em faixas adaptada da Figura 2 do artigo [14] para o recorte com quantização e três modelos. A validação fixa as escolhas; o teste avalia a configuração congelada. Na tarefa horária há uma semente; nas demais, média de cinco sementes.',
    source='elaboração própria, com organização visual adaptada de Nascimento, Cabral e Fraidenraich [14]')
h('Normalização e quantização das entradas',2)
paras('''Para cada localidade, os parâmetros min max são estimados exclusivamente com os dados anteriores ao corte da etapa correspondente. Na seleção atual, a escala usa informação anterior a 2023; no refit, anterior a 2024. Essa regra também se aplica aos cortes históricos. A transformação de um valor x para a escala normalizada u é apresentada na Equação 1, na qual a e b são o mínimo e o máximo admissíveis da localidade.''')
eq(['u = ',frac('x − a','b − a')],'1')
p('As variantes quantizadas aplicam a Equação 2 ao histórico X, com N em {64, 128, 256}. A função rint arredonda para o inteiro mais próximo e utiliza inteiro par em empates exatos. O clipping limita a entrada ao intervalo de zero a um antes da discretização.')
eq([script('Q','N'),'(u) = ',frac('rint[(N − 1) clip(u, 0, 1)]','N − 1')],'2')
table('Condições de entrada e resolução nominal',['Condição','Níveis','Passo normalizado','Erro máximo de arredondamento'],[
['Controle','Contínuo','Não se aplica','Não se aplica'],['Q64','64',f(1/63,6),f(1/126,6)],['Q128','128',f(1/127,6),f(1/254,6)],['Q256','256',f(1/255,6),f(1/510,6)]],[3.5,2.5,4.4,6.6],note='O limite vale somente para entradas já contidas em [0,1], antes da conversão float32. Não limita o erro de previsão.')
paras('''O alvo y permanece contínuo, assim como os pesos e a saída regressiva. O identificador de localidade não é submetido ao quantizador de GHI. Após a projeção nos níveis, os valores continuam representados como float32. Embora 64, 128 e 256 símbolos admitam codificações nominais de 6, 7 e 8 bits, essa possibilidade não constitui uma redução de armazenamento implementada ou medida neste experimento [6,7].

O controle contínuo não aplica clipping. Portanto, uma diferença entre controle e variante quantizada pode resultar tanto do arredondamento quanto da saturação de entradas fora da faixa de treinamento. O experimento não contém um controle independente com apenas clipping; a interpretação deve manter essa limitação. O limite de arredondamento da Tabela 4 descreve a entrada e não se propaga diretamente como um limite de erro da rede.''')
fig('02_quantizador','Quantização uniforme e saturação das entradas','Escada com oito níveis exclusivamente para legibilidade. As execuções avaliadas usam 64, 128 e 256 níveis; a linha tracejada representa o controle sem clipping.')
h('Treinamento seleção e refit',2)
paras('''Os três modelos minimizam MSE na escala normalizada durante o treinamento. As épocas são selecionadas pela perda de validação, separadamente por variante e semente. O nível de entrada é escolhido pelo menor macro-MAE físico da previsão combinada na validação, sempre no horizonte completo da tarefa. A ordenação de desempate é controle, 64, 128 e 256 níveis. Uma vez escolhido o nível, ele permanece fixo nos checkpoints menores; não se realiza uma escolha adicional em cada horizonte de teste.

O refit reinicializa os pesos com a mesma semente e treina nos dados anteriores ao teste pelo número de épocas previamente fixado. Isso incorpora informação pré-teste adicional sem consultar os resultados de teste para decidir a duração do treinamento. Como épocas e nível utilizam a mesma validação, a flexibilidade de seleção não equivale a um procedimento de validação aninhada.''')
table('Parâmetros efetivos de treinamento por tarefa',['Tarefa','Épocas máximas','Paciência','Lote','Sementes','Dispositivo'],[
['Horária','30','5','128','42','GPU'],['Diária','30','5','128','11 23 42 67 89','GPU'],['Mensal um passo','300','30','32','11 23 42 67 89','CPU'],['Mensal seis passos','300','30','32','11 23 42 67 89','CPU']],[3.5,2.5,2.2,1.5,4.1,3.2],note='Adam, taxa de aprendizagem 0,001 e weight decay 0,00001. Configurações conferidas nos contratos das execuções; não representam igualdade de custo computacional entre arquiteturas.')
paras('''Nas tarefas diária e mensais, as previsões brutas das cinco sementes são invertidas para W/m² e combinadas por média aritmética. Somente depois dessa combinação são aplicadas as regras físicas de pós-processamento. Na tarefa horária existe apenas a semente 42. Os números das tabelas principais descrevem essa previsão combinada; não correspondem à média dos MAEs individuais das sementes.

Aplica-se piso zero em todas as resoluções. Na tarefa horária, também se anula a previsão quando a elevação solar no centro do intervalo é não positiva, utilizando a geometria solar implementada com pvlib [11]. Não se aplica um teto físico comum. A geometria atua como regra de pós-processamento e não como covariável meteorológica de treinamento. Essa ordem importa porque a média de previsões antes do piso não é, em geral, igual à média de previsões já truncadas.''')
h('Análise dos dados e métricas',2)
paras('''As métricas são calculadas após a inversão da escala e o pós-processamento. Seja eᵢ igual a yᵢ menos a previsão, e n o número de pares origem passo avaliados em uma localidade. As Equações 3 e 4 definem MAE, MSE e RMSE. O MAE é a medida primária por sua interpretação direta da magnitude média do erro; MSE e RMSE aumentam a influência de desvios grandes [8,9]. As Equações 5 e 6 apresentam nRMSE e R².''')
eq(['MAE = ',frac([summation('i = 1','n',['|',script('e','i'),'|'])],'n')],'3')
eq(['MSE = ',frac([summation('i = 1','n',[script('e','i','2')])],'n'), '     RMSE = ',rad([frac([summation('i = 1','n',[script('e','i','2')])],'n')])],'4')
eq(['nRMSE = ',frac('RMSE','ȳ'),'     nRMSE em % = 100 × nRMSE'],'5')
eq([script('R',sup='2'),' = 1 − ',frac([summation('i = 1','n',[script('e','i','2')])],[summation('i = 1','n',['(',script('y','i'),' − ȳ)²'])])],'6')
paras('''O nRMSE é normalizado pela média da GHI de referência no mesmo vetor avaliado, e não pelo pico ou pela amplitude. Os CSV armazenam uma razão; as tabelas percentuais multiplicam essa razão por cem. O R² compara os erros quadráticos com a variação em torno da média de avaliação. Pode ser negativo e fica indefinido quando o denominador é numericamente nulo. Não se substituem valores indefinidos por zero.

Cada métrica é primeiro calculada por localidade. Depois, faz-se a média simples dos valores finitos, atribuindo peso igual às localidades. Todas as dez contribuem aos resultados cumulativos principais. Para uma métrica M e L localidades válidas, a agregação é dada pela Equação 7. Como a raiz quadrada é não linear, o macro-RMSE não deve ser recalculado a partir da raiz do macro-MSE.''')
eq([script('M','macro'),' = ',frac([summation('l = 1','L',[script('M','l')])],'L')],'7')
paras('''A avaliação cumulativa concatena os passos de um até H em todas as origens válidas. Instantes-alvo repetidos em diferentes janelas são preservados, pois representam previsões emitidas em momentos distintos. Essa dependência impede interpretar o total de pontos como uma amostra independente de igual tamanho. As medidas descrevem o conjunto de trajetórias emitidas, com o peso temporal induzido pelo protocolo de janelas.

Na tarefa horária, as emissões à meia-noite fazem os leads exatos de 24, 48 e 72 horas coincidirem com intervalos noturnos. Erros nulos nesses leads exatos não comprovam capacidade de prever a irradiância diurna. Por esse motivo, os gráficos e rankings deste relatório usam explicitamente o escopo cumulativo. Nenhuma significância estatística é inferida apenas de uma pequena diferença entre médias macro.''')

h('4 DESENVOLVIMENTO',new=True)
FUND=json.loads((TMP/'texto_fundamentacao.json').read_text(encoding='utf-8'))
for block in FUND:
    h(block['heading'],2)
    paragraphs=block['paragraphs'][:2] if block['heading']=='Relação com os artigos do projeto' else block['paragraphs']
    for tx in paragraphs:p(tx)
    if 'Informer' in block['heading']:fig('03_arquiteturas','Estruturas implementadas dos três modelos','Esquemas próprios baseados no código do projeto. Os zeros do decoder marcam posições futuras e não fornecem os valores do alvo.')

h('5 RESULTADOS',new=True)
paras('''Esta seção apresenta os resultados do recorte de três modelos e quatro condições de entrada. As comparações principais utilizam o nível escolhido na validação e o horizonte cumulativo completo. Os apêndices apresentam as curvas em formato tabular e os MAEs das quatro condições nos três regimes. O arredondamento serve à leitura; as escolhas e os gráficos são calculados com a precisão dos arquivos auditados.

Os resultados de 2024 são discutidos primeiro. Em seguida, analisam-se a resposta à quantização, os checkpoints de horizonte e a comparação histórica pareada. A separação dos regimes evita atribuir ao tamanho do histórico diferenças entre testes realizados em anos distintos.''')
h('Desempenho no teste de 2024',2)
rows=[]
for t,H,label in TASKS:
    for m in MODELS:
        a=sel('atual',t,m);rows.append([label,m,variant(a.variante),f(a.MAE_wm2),f(a.RMSE_wm2),f(a.nRMSE*100),f(a.R2,4)])
table('Resultados cumulativos completos no regime atual',['Tarefa','Modelo','Entrada','MAE W/m²','RMSE W/m²','nRMSE %','R²'],rows,[2.9,3.0,1.8,2.35,2.35,2.3,2.3],note='Entrada é o nível escolhido na validação; Controle indica ausência de quantização.')
fig('04_mae_atual','Classificação dos modelos por tarefa no teste de 2024',
    'Horizonte cumulativo completo e nível escolhido na validação. Menor MAE indica menor erro. Escalas horizontais próprias por painel; cores identificam o mesmo modelo ao longo do relatório.')
RES=json.loads((TMP/'texto_resultados.json').read_text(encoding='utf-8'))
for i,block in enumerate(RES):
    if i:h(block['heading'],2)
    for tx in (block['paragraphs'][:3] if i==0 else block['paragraphs']):p(tx)
    if i==0:
        h('Heterogeneidade entre localidades',2,new=True)
        p('A média macro atribui o mesmo peso às dez localidades, mas pode ocultar mudanças de liderança. A matriz apresenta os MAEs de cada local com a mesma condição de entrada utilizada na classificação agregada. Cada painel corresponde a uma tarefa e ao seu horizonte cumulativo completo.')
        fig('12_localidades','Desempenho por localidade nas quatro tarefas',
            'Métricas locais de teste com seleção fixa pela validação. Escala de cor própria por painel. Contorno e negrito indicam o menor MAE local com a precisão integral dos dados; valores arredondados podem parecer empatados. A comparação é descritiva e não indica significância estatística.',width=16.1)
        paras('''O Transformer apresenta o menor MAE em sete localidades na tarefa horária e seis na diária. A LSTM lidera nas três e quatro localidades restantes, respectivamente. Nas tarefas mensais de um e seis passos, o Informer lidera em cinco localidades, a LSTM em três e o Transformer em duas. Logo, o primeiro lugar na média macro não equivale a liderança em todos os locais.

Os resultados mensais também mostram situações distintas para os pontos de Detroit: a LSTM apresenta o menor MAE em GM Factory Zero e Ford Rouge EV Center nas duas tarefas mensais. Esses resultados descrevem a heterogeneidade observada; não identificam sua causa climática nem demonstram generalização para localidades não usadas no ajuste.''')
        h('Escolha por validação e efeito no teste',2)
        rows=[]
        for t,H,label in TASKS:
            for m in MODELS:
                a=sel('atual',t,m);v0=rr('atual',t,m,H,'sem_quantizacao');delta=(a.MAE_wm2/v0.MAE_wm2-1)*100
                case=next(x for x in E['quantizacao_horizonte_completo'] if x['regime']=='atual' and x['tarefa']==t and x['modelo']==m)
                chosen=next(x for x in case['condicoes'] if x['escolhida_na_validacao'])
                rows.append([label,m,variant(a.variante),f(chosen['validacao']['MAE_wm2']),f(v0.MAE_wm2),f(a.MAE_wm2),f(delta)])
        table('Nível escolhido e comparação com o controle no teste de 2024',['Tarefa','Modelo','Escolha','MAE val','MAE controle teste','MAE escolha teste','Δ teste %'],rows,[2.8,3,1.7,2.2,2.6,2.6,2.1],note='Todos os MAEs em W/m². Δ = 100 × (MAE escolha / MAE controle − 1). A escolha usa a validação, não a última coluna.')
    if i==1:fig('05_quantizacao','Sensibilidade do MAE à resolução de amplitude no regime atual','Variações calculadas em relação ao controle do mesmo modelo e tarefa. Estrela indica escolha na validação quando a variante escolhida é quantizada.')
    if i==2:fig('07_horizontes','Perfis cumulativos de erro nos checkpoints de cada tarefa','A condição de entrada permanece fixa pela escolha no horizonte completo da validação. O painel mensal de seis passos é exploratório.')
    if i==3:
        rows=[]
        for t,H,label in TASKS:
            for m in MODELS:
                a=rr('historico_curto_pareado',t,m,H,'sem_quantizacao');b=rr('historico_1998_2022',t,m,H,'sem_quantizacao')
                rows.append([label,m,f(a.MAE_wm2),f(b.MAE_wm2),f((b.MAE_wm2/a.MAE_wm2-1)*100)])
        table('Comparação pareada dos históricos no controle sem quantização',['Tarefa','Modelo','MAE curto','MAE longo','Δ longo %'],rows,[3.6,3.9,3.2,3.2,3.1],note='MAE em W/m². Mesmo teste histórico. Δ negativo indica menor MAE com o histórico longo.')
        fig('06_historico','MAE com histórico curto e longo sob teste pareado',
            'Cada segmento conecta os MAEs do mesmo modelo no controle sem quantização. Validação e teste são comuns aos dois históricos. Δ = 100 × (MAE longo / MAE curto − 1); valores negativos indicam redução do erro. Escalas próprias por tarefa.')
h('Discussão integrada e limitações',2)
paras('''A primeira conclusão é que a resolução temporal altera a comparação entre modelos. O desempenho mensal favorável do Informer não se estende à tarefa horária, e a proximidade entre Transformer e LSTM em determinados cenários não autoriza declarar equivalência. As implementações possuem mecanismos e quantidades de parâmetros diferentes; a comparação mantém dados e protocolo, mas não equaliza capacidade, custo de treinamento ou orçamento computacional.

A segunda conclusão é que a quantização não produz uma melhoria uniforme. Um nível com bom resultado na validação pode aumentar o erro no teste, especialmente diante de mudança na distribuição temporal. A apresentação de todos os níveis nos apêndices permite inspecionar essa sensibilidade, sem escolher retrospectivamente o menor MAE de teste. Uma eventual suavização ou regularização é uma hipótese interpretativa; o desenho não identifica esse mecanismo e não separa seu efeito do clipping.

A terceira conclusão diz respeito ao histórico. O pareamento controla o período avaliado e permite descrever a associação entre mais dados admissíveis e menor erro em grande parte dos casos. Ainda assim, a ampliação altera simultaneamente a quantidade de janelas, a composição dos anos e os extremos usados na escala. A exceção da LSTM horária demonstra que não há garantia de melhora monotônica com a inclusão de anos anteriores.

As tarefas mensais dispõem de poucas origens de teste, sobretudo no horizonte de seis passos. Há sobreposição de alvos e dependência temporal dos erros, além de possível correlação espacial entre localidades. As médias macro não quantificam essa dependência e podem ocultar perdas concentradas em um local. A avaliação por localidade e em novos anos é necessária antes de ampliar as conclusões para outros cenários.

O conjunto representa estimativas modeladas da NSRDB, com escolha geográfica intencional e ausência de medição fotovoltaica operacional. O cenário retrospectivo pressupõe disponibilidade do histórico e não reproduz toda a cadeia de aquisição em tempo real. A máscara noturna ajuda a impor uma restrição física, mas não corrige previsões diurnas excessivas nem substitui uma avaliação de geração elétrica.

Os experimentos horários usam uma única semente; portanto, sua ordenação também pode depender da trajetória específica de otimização. Nas demais tarefas, a combinação de cinco sementes reduz a dependência de uma instância isolada, mas não constitui um intervalo de confiança ou uma previsão probabilística calibrada. Sementes fixas não garantem repetição bit a bit de novos treinamentos em GPU; esta consolidação utiliza os artefatos congelados e auditados. Nenhuma diferença é apresentada como estatisticamente significativa neste relatório.

Finalmente, a representação float32 e a ausência de quantização dos pesos delimitam a contribuição. O resultado demonstra sensibilidade preditiva a entradas discretizadas. Um estudo de eficiência exigiria implementar a codificação compacta ou a aritmética inteira, medir memória e latência sob hardware definido e avaliar novamente o erro sob o novo fluxo. Essas etapas não podem ser substituídas por uma contagem nominal de bits.''')

h('6 CONCLUSÃO',new=True)
paras('''O trabalho avaliou a previsão de GHI com LSTM, Transformer e Informer sob quatro condições de entrada, quatro tarefas e três regimes temporais. O protocolo preservou a causalidade das janelas, ajustou escalas com informação admissível, selecionou épocas e nível na validação e reservou o teste para a avaliação. A consolidação em tabelas e figuras permitiu distinguir efeito de resolução de amplitude, comportamento por horizonte e comparação histórica pareada.

No regime atual, o Transformer apresentou os menores MAEs cumulativos completos nas tarefas horária e diária, enquanto o Informer apresentou os menores nas duas tarefas mensais. A comparação entre essas tarefas exige cautela, pois elas diferem em agregação, contexto, horizonte e número de origens. Os resultados não sustentam uma superioridade universal de uma arquitetura.

A quantização escolhida na validação melhorou o MAE de teste em cinco das doze combinações modelo tarefa de 2024, piorou em quatro e preservou o controle em três. Nos regimes históricos, as escolhas também apresentaram ganhos e perdas. Assim, a resposta à pergunta central é condicional: reduzir a resolução das entradas pode manter ou melhorar o desempenho em cenários específicos, porém não oferece uma regra geral de melhoria nem dispensa seleção e teste temporal adequados.

No teste histórico pareado, o controle sem quantização melhorou com o histórico longo em onze das doze combinações. A exceção da LSTM horária impede tratar a ampliação do histórico como benefício automático. A conclusão é descritiva para os períodos e configurações avaliados; não isola todos os mecanismos responsáveis pelas mudanças.

Como próximos passos, propõe-se acrescentar uma condição com apenas clipping, repetir a avaliação em novos anos e localidades, examinar perdas por localidade e investigar a estabilidade das escolhas em validações temporais sucessivas. Também é pertinente comparar as redes com referências ingênuas e sazonais sob exatamente os mesmos recortes do estudo de quantização. Caso a motivação seja eficiência de implantação, devem ser implementados e medidos armazenamento compacto, quantização de pesos e custos de inferência antes de formular conclusões de engenharia sobre memória ou velocidade.

A contribuição consolidada é uma avaliação rastreável da precisão preditiva sob discretização das entradas, com clipping nas variantes quantizadas. O relatório fornece a base para a discussão acadêmica dos resultados da disciplina e para a continuidade do TCC, mantendo separados o que foi observado, as interpretações possíveis e o que ainda exige novos experimentos.''')

h('7 REFERÊNCIAS BIBLIOGRÁFICAS',new=True)
refs=[
'[1] SENGUPTA, M.; XIE, Y.; LOPEZ, A.; HABTE, A.; MACLAURIN, G.; SHELBY, J. The National Solar Radiation Data Base (NSRDB). Renewable and Sustainable Energy Reviews, v. 89, p. 51–60, 2018. DOI: 10.1016/j.rser.2018.03.003.',
'[2] NATIONAL LABORATORY OF THE ROCKIES. GOES Aggregated PSM v4 Download API. Documentação técnica. Disponível em: https://developer.nlr.gov/docs/solar/nsrdb/nsrdb-GOES-aggregated-v4-0-0-download/. Acesso em: 27 out. 2026.',
'[3] HOCHREITER, S.; SCHMIDHUBER, J. Long short-term memory. Neural Computation, v. 9, n. 8, p. 1735–1780, 1997. DOI: 10.1162/neco.1997.9.8.1735.',
'[4] VASWANI, A. et al. Attention Is All You Need. Advances in Neural Information Processing Systems, v. 30, p. 5998–6008, 2017. Disponível em: https://proceedings.neurips.cc/paper_files/paper/2017/hash/3f5ee243547dee91fbd053c1c4a845aa-Abstract.html.',
'[5] ZHOU, H. et al. Informer: Beyond Efficient Transformer for Long Sequence Time-Series Forecasting. Proceedings of the AAAI Conference on Artificial Intelligence, v. 35, n. 12, p. 11106–11115, 2021. DOI: 10.1609/aaai.v35i12.17325.',
'[6] GRAY, R. M.; NEUHOFF, D. L. Quantization. IEEE Transactions on Information Theory, v. 44, n. 6, p. 2325–2383, 1998. DOI: 10.1109/18.720541.',
'[7] JACOB, B. et al. Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference. In: IEEE/CVF Conference on Computer Vision and Pattern Recognition, 2018, p. 2704–2713. DOI: 10.1109/CVPR.2018.00286.',
'[8] HYNDMAN, R. J.; KOEHLER, A. B. Another look at measures of forecast accuracy. International Journal of Forecasting, v. 22, n. 4, p. 679–688, 2006. DOI: 10.1016/j.ijforecast.2006.03.001.',
'[9] YANG, D. et al. Verification of deterministic solar forecasts. Solar Energy, v. 210, p. 20–37, 2020. DOI: 10.1016/j.solener.2020.04.019.',
'[10] MONTERO-MANSO, P.; HYNDMAN, R. J. Principles and algorithms for forecasting groups of time series: Locality and globality. International Journal of Forecasting, v. 37, n. 4, p. 1632–1653, 2021. DOI: 10.1016/j.ijforecast.2021.03.004.',
'[11] ANDERSON, K. S. et al. pvlib python: 2023 project update. Journal of Open Source Software, v. 8, n. 92, 5994, 2023. DOI: 10.21105/joss.05994.',
'[12] CABRAL, T. W.; FRAIDENRAICH, G.; CAPRETZ, M. A. M. Can large language models predict solar irradiance in the long term? Solar Energy, v. 317, 114964, 2026. DOI: 10.1016/j.solener.2026.114964.',
'[13] DIAGNE, M.; DAVID, M.; LAURET, P.; BOLAND, J.; SCHMUTZ, N. Review of solar irradiance forecasting methods and a proposition for small-scale insular grids. Renewable and Sustainable Energy Reviews, v. 27, p. 65–76, 2013. DOI: 10.1016/j.rser.2013.06.042.',
'[14] NASCIMENTO, G. de M.; CABRAL, T. W.; FRAIDENRAICH, G. Multi-Resolution Global Horizontal Irradiance Forecasting at Electric-Vehicle Manufacturing Locations: TimesNet and Dilated Recurrent Networks. Manuscrito do projeto encaminhado aos orientadores em 7 set. 2026, 19 p. Arquivo: Artigo_Gustavo_Nascimento.pdf.'
]
for tx in refs:p(tx,'Bibliografia')


h('APÊNDICE A RESULTADOS POR HORIZONTE NO REGIME ATUAL',new=True)
p('As tabelas deste apêndice mantêm, em cada modelo e tarefa, a condição escolhida na validação do horizonte completo. MAE e RMSE estão em W/m²; MSE em (W/m²)². Todas as métricas são macro e cumulativas. As tarefas mensais de um e seis passos são redes distintas.')
for t,H,label in TASKS:
    rows=[]
    for m in MODELS:
        v=sel('atual',t,m).variante
        zs=D[(D.regime=='atual')&(D.tarefa==t)&(D.modelo==m)&(D.variante==v)].sort_values('horizonte')
        for a in zs.itertuples():rows.append([m,str(a.horizonte),variant(v),f(a.MAE_wm2),f(a.MSE_w2m4),f(a.RMSE_wm2),f(a.nRMSE*100),f(a.R2,4)])
    table('Detalhamento cumulativo da tarefa '+label.lower(),['Modelo','H','Entrada','MAE','MSE','RMSE','nRMSE %','R²'],rows,[2.6,1,2.3,2.15,2.5,2.15,2.15,2.15],note='H em horas, dias ou meses conforme a tarefa.')

h('APÊNDICE B COMPARAÇÃO DAS QUATRO CONDIÇÕES DE ENTRADA',new=True)
p('Os MAEs a seguir correspondem ao horizonte completo de cada tarefa. O asterisco identifica a condição escolhida na validação, inclusive quando é o controle. A tabela apresenta todas as condições para tornar visível a sensibilidade; o menor erro de teste não altera a escolha registrada. MAE em W/m².')
for idx,(reg,labelreg) in enumerate(REGS):
    if idx:page()
    h(labelreg,2)
    rows=[]
    for t,H,label in TASKS:
        for m in MODELS:
            v=sel(reg,t,m).variante
            vals=[f(rr(reg,t,m,H,q).MAE_wm2,4)+(' *' if v==q else '') for q in ['sem_quantizacao','q64','q128','q256']]
            rows.append([label,m]+vals)
    table('MAE por condição de entrada no regime '+labelreg.lower(),['Tarefa','Modelo','Controle','64 níveis','128 níveis','256 níveis'],rows,[3.3,3.3,2.6,2.6,2.6,2.6],note='* Condição escolhida pelo macro-MAE de validação no horizonte completo.',size=11)
    if reg=='atual':p('O teste deste regime é 2024. As comparações de quantização devem ser feitas dentro da mesma linha, evitando misturar escalas temporais. O controle permanece como escolha válida; quantizar não é uma exigência da seleção.')
    else:p('O teste é comum aos dois regimes históricos, de abril de 2019 a dezembro de 2022. Comparações de duração do histórico devem manter a mesma condição de entrada, ou indicar explicitamente quando cada histórico selecionou um nível diferente.')

h('APÊNDICE C PROVENIÊNCIA E REPRODUÇÃO DA CONSOLIDAÇÃO',new=True)
paras('''Os números deste relatório foram consolidados de artefatos locais já produzidos pelo projeto, sem execução de novos treinamentos. A extração foi filtrada para Transformer, Informer e LSTM. Foram verificadas 432 linhas de teste e suas 432 correspondentes de validação, 36 classificações de horizonte completo e as 48 comparações históricas de mesma variante. Os sete arquivos-fonte abaixo mantiveram os hashes registrados nas auditorias.

Os caminhos são relativos à raiz do repositório. O diretório-base dos registros auditados é resultados/relatorios/quantizacao_todos_modelos_20260929. Os nomes dos arquivos de saída da disciplina ficam em resultados/relatorios/pdfs_resumidos_legiveis_20261027/disciplina. As tabelas do relatório são editáveis, enquanto as figuras foram geradas diretamente das mesmas métricas em precisão integral.''')
for i,src in enumerate(E['integridade']['fontes_originais_verificadas'],1):
    rel=src['caminho'].replace('resultados/relatorios/quantizacao_todos_modelos_20260929/','')
    z=p(f'Fonte {i}: {rel}','Fonte');z.paragraph_format.keep_with_next=True
    p('SHA256: '+src['sha256'],'Fonte')
h('Sequência de verificação',2)
paras('''A consolidação verifica a integridade dos arquivos e o pareamento histórico antes de comparar os resultados. Em cada combinação de regime, tarefa e modelo, recupera as quatro condições, confere a escolha pelo macro-MAE da validação e mantém essa escolha fixa nos demais checkpoints. As métricas de teste são apenas então organizadas em rankings, figuras e tabelas. O arredondamento em casas decimais é aplicado somente na apresentação.

A matriz de desempenho por localidade utiliza os arquivos metricas_por_localidade_teste.csv das doze combinações atuais de modelo e tarefa, na variante escolhida na validação. A média dos dez MAEs locais foi conferida contra o macro-MAE auditado em cada combinação. Os perfis de GHI usam os dados brutos de BYD Camaçari em 2024: dados/brutos/localidades_ev/byd_camacari.csv e dados/brutos/localidades_ev_horario/nsrdb_ghi_horaria_2024.csv.gz. O mapa é reproduzido do artigo [14]; os demais gráficos de resultados foram reconstruídos com dados deste recorte.

''')

# Save once, then put only explicitly editable/new package parts into original ZIP.
working=TMP/'revisao_artigo/authoring_working.docx';doc.save(working)
editable={'word/document.xml','word/styles.xml','word/_rels/document.xml.rels','word/settings.xml','[Content_Types].xml','docProps/core.xml','docProps/app.xml'}
with zipfile.ZipFile(REF) as zr,zipfile.ZipFile(working) as zw:
    orig={n:zr.read(n) for n in zr.namelist()};gen={n:zw.read(n) for n in zw.namelist()}
    parts=dict(orig)
    for n,b in gen.items():
        if n in editable or n not in orig:parts[n]=b
    with zipfile.ZipFile(FINAL,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in parts.items():z.writestr(n,b)
    preserved=[n for n in orig if n not in editable]
    assert all(parts[n]==orig[n] for n in preserved)
audit={'output':str(FINAL),'template_sha256':SHA,'tables':tn,'figures':fn,'paragraphs':len(doc.paragraphs),'words':sum(len(x.text.split()) for x in doc.paragraphs),'preserve_only_unchanged':preserved,'new_parts':[n for n in parts if n not in orig],'captions':captions}
(TMP/'revisao_artigo/authoring_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:audit[k] for k in ['output','tables','figures','paragraphs','words']},ensure_ascii=False))
