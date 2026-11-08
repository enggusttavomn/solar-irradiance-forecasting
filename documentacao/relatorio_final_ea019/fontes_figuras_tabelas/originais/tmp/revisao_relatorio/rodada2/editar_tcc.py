"""Apply the approved TCC corrections without changing experimental results."""
from pathlib import Path
from copy import deepcopy
from zipfile import ZipFile
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
from lxml import etree as E
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT

sys.stdout.reconfigure(encoding='utf-8')
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC.docx'
OUTPUT = SOURCE.with_name('Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC_Corrigido.docx')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W, 'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
sha = lambda b: hashlib.sha256(b).hexdigest()
with ZipFile(SOURCE) as z:
    original = {i.filename: z.read(i.filename) for i in z.infolist()}
assert sha(SOURCE.read_bytes()) == '8c8c9f4888ce611b9f0d63bc55bf3f1d019cbb0352a3c5df7e1b1a959a8600d7'
doc = Document(SOURCE)
P = list(doc.paragraphs)
assert len(P) == 314
original_cells = [[c.text for row in table.rows for c in row.cells] for table in doc.tables]
original_equations = [''.join(e.xpath('.//m:t/text()', namespaces=NS)) for e in E.fromstring(original['word/document.xml']).findall('.//m:oMath', NS)]
literature = json.loads((HERE / 'literatura.json').read_text(encoding='utf-8'))
repro = json.loads((HERE / 'reprodutibilidade.json').read_text(encoding='utf-8'))
diagnosis = json.loads((HERE / 'figuras/sugestao_caption_treinamento.json').read_text(encoding='utf-8'))
changes = []

def replace(index, value):
    p = P[index]
    assert not p._p.xpath('.//m:oMath')
    assert not p._p.xpath('.//w:fldChar')
    old = p.text
    if old == value:
        return
    # Retain paragraph properties and bookmarks used by the table of contents.
    nodes = p._p.xpath('.//w:t')
    assert nodes
    nodes[0].text = value
    nodes[0].set(qn('xml:space'), 'preserve')
    for node in nodes[1:]:
        node.text = ''
    changes.append({'paragraph': index, 'before': old, 'after': value})

def paragraph(text, style='Normal', before=None, after=None, keep=None):
    p = doc.add_paragraph(text, style)
    if keep is not None:
        p.paragraph_format.keep_with_next = keep
    if before is not None:
        before.addprevious(p._p)
    if after is not None:
        after.addnext(p._p)
    return p

def block_before(anchor, entries):
    result = []
    for style, text in entries:
        result.append(paragraph(text, style, before=anchor._p))
    return result

def add_table(title, headers, rows, widths):
    caption = paragraph(title, 'Caption', keep=True)
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for col, width in zip(t.columns, widths):
        col.width = Cm(width)
    for cell, text in zip(t.rows[0].cells, headers):
        cell.text = text
    for values in rows:
        for cell, value in zip(t.add_row().cells, values):
            cell.text = str(value)
    borders = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        e = OxmlElement('w:' + side)
        for k, v in [('val', 'single'), ('sz', '4'), ('color', 'D9D9D9')]:
            e.set(qn('w:' + k), v)
        borders.append(e)
    t._tbl.tblPr.append(borders)
    padding = OxmlElement('w:tblCellMar')
    for side in ('top', 'bottom', 'left', 'right'):
        e = OxmlElement('w:' + side)
        e.set(qn('w:w'), '90')
        e.set(qn('w:type'), 'dxa')
        padding.append(e)
    t._tbl.tblPr.append(padding)
    repeat = OxmlElement('w:tblHeader')
    repeat.set(qn('w:val'), 'true')
    t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for i, row in enumerate(t.rows):
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        for j, cell in enumerate(row.cells):
            cell.width = Cm(widths[j])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if i == 0:
                fill = OxmlElement('w:shd')
                fill.set(qn('w:fill'), 'E8ECEF')
                cell._tc.get_or_add_tcPr().append(fill)
            for p in cell.paragraphs:
                p.style = doc.styles['TabelaCorpo']
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.keep_with_next = i == 0
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.space_before = Pt(2)
                for run in p.runs:
                    run.font.name = 'Times New Roman'
                    run.font.size = Pt(10.5)
                    run.bold = i == 0
    return t

# Academic presentation and normal grammatical punctuation requested by the author.
for index in (5, 14):
    replace(index, 'Transformer, Informer e LSTM sob quantização das entradas')
replace(16, 'Trabalho apresentado como requisito para conclusão do curso de ENGENHARIA ELÉTRICA da Universidade Estadual de Campinas, no âmbito da disciplina EA019, orientado pelo Prof. Gustavo Fraidenraich.')
replace(75, 'A previsão do recurso solar auxilia o planejamento de sistemas fotovoltaicos e a operação de sistemas elétricos. Os ciclos astronômicos e as variações de nebulosidade produzem comportamentos distintos nas escalas horária, diária e mensal. Por isso, o desempenho depende do horizonte e das informações disponíveis na emissão [13]. A variável prevista é a irradiância global horizontal (GHI), em W/m².')
replace(77, 'O recorte reúne mecanismos distintos de representação temporal: memória recorrente na LSTM, atenção completa no Transformer e atenção esparsa no Informer [3–5]. Essa escolha permite comparar três implementações sob regras comuns, sem pressupor que sejam os melhores modelos para qualquer tarefa. As redes compartilham parâmetros entre as dez localidades e representam sua identidade por um embedding, vetor aprendido durante o treinamento. Essa organização caracteriza uma modelagem global, avaliada nas localidades incluídas no ajuste [10].')
replace(78, 'As séries provêm da National Solar Radiation Database (NSRDB), que fornece estimativas do recurso solar por modelagem e sensoriamento remoto [1,2]. As coordenadas de instalações associadas à fabricação de veículos elétricos definem as células geográficas consultadas. Esse contexto motiva a aplicação, mas o objeto avaliado é a GHI; geração fotovoltaica, carga industrial e ganhos econômicos exigiriam dados adicionais.')
paragraph(literature['motivation']['paragraph'], after=P[76]._p)
replace(79, 'A contribuição do TCC é comparar a sensibilidade dessas três implementações às condições de entrada em quatro tarefas de previsão de GHI. A análise combina desempenho agregado e local com uma comparação pareada da duração do histórico de ajuste. Os resultados são apresentados com rastreabilidade aos dados, às configurações e às versões de código utilizadas.')
replace(83, 'As seções seguintes apresentam objetivos, metodologia, fundamentos, resultados e conclusões. Os apêndices detalham os horizontes, as condições de entrada, as configurações e a proveniência dos resultados.')
P[82]._element.getparent().remove(P[82]._element)
P[83]._element.getparent().remove(P[83]._element)
replace(110, 'Figura 2 — Perfis de referência da GHI nas resoluções horária, diária e mensal')
replace(119, P[119].text.replace('Como sintetiza a Figura 3,', 'Como sintetizam a Figura 3 e a Tabela 2,'))
paragraph('Na tarefa horária, emite-se um vetor de 72 previsões uma vez por dia, às 00:00 no horário local fixo informado pela NSRDB, sem aplicação de horário de verão. Assim, o horizonte de saída é de 72 horas, mas o espaçamento entre origens consecutivas é de 24 horas.', after=P[113]._p)
paragraph('Denomina-se regime temporal a combinação dos períodos de ajuste inicial, validação, novo ajuste anterior ao teste e teste. São considerados o regime atual, o histórico longo e o histórico curto pareado, cujas datas aparecem na Tabela 3.', after=P[121]._p)
replace(130, 'Figura 5 — Fluxo experimental em etapas de dados, seleção e avaliação')
replace(145, 'Treinamento, seleção e refit')
replace(146, P[146].text + ' As estruturas das redes são descritas nas Seções 4.2 a 4.4; as configurações e quantidades de parâmetros estão nas Tabelas 16 e 17 do Apêndice C.')
replace(153, 'As métricas são calculadas após a inversão da escala e o pós-processamento. Seja eᵢ = yᵢ − ŷᵢ o erro, em que yᵢ é o valor de referência, ŷᵢ é a previsão e n é o número de pares de origem e passo previsto em uma localidade. As Equações 3 e 4 definem o erro absoluto médio (MAE), o erro quadrático médio (MSE) e sua raiz quadrada (RMSE). O MAE é a medida principal por expressar diretamente a magnitude média do erro; MSE e RMSE atribuem maior influência a desvios grandes [8,9]. As Equações 5 e 6 apresentam o RMSE normalizado (nRMSE) e o coeficiente de determinação (R²).')
replace(162, 'Na tarefa horária, as emissões à meia-noite fazem os passos exatos de 24, 48 e 72 horas coincidirem com intervalos noturnos. Por isso, os gráficos e as classificações utilizam métricas cumulativas. Essas métricas incluem horas diurnas e noturnas, e a máscara solar impõe previsão zero à noite. A inclusão de períodos com referência e previsão nulas reduz o MAE agregado em relação a um recorte apenas diurno. O nRMSE, porém, também depende da média da referência e não sofre necessariamente a mesma redução. Comparações com outros estudos exigem o mesmo recorte de horas avaliadas [9].')
replace(181, P[181].text.replace('distilação', 'destilação'))
replace(182, P[182].text.replace('distilação', 'destilação'))
replace(188, 'Trabalhos relacionados e posicionamento')
replace(189, 'Cabral, Fraidenraich e Capretz investigaram previsão mensal de longo prazo de GHI da NSRDB com GPT-Neo [12]. Esse antecedente aproxima-se do cenário de históricos solares, mas diferenças de localidades, horizontes, processamento e modelos impedem a comparação direta de seus erros com os deste TCC.')
lit_paras = literature['subsection']['paragraphs']
for value in lit_paras[:4]:
    value = value.replace('examinam a influência de componentes do desenho experimental e da arquitetura', 'examinam a influência de elementos das arquiteturas na extração de relações temporais')
    paragraph(value, before=P[189]._p)
for value in lit_paras[4:]:
    paragraph(value, before=P[190]._p)
replace(192, 'Primeiro, discutem-se o teste de 2024, a heterogeneidade entre localidades, a resposta à quantização e o comportamento por horizonte. Em seguida, compara-se a duração do histórico sob validação e teste pareados. Os registros de treinamento ajudam a interpretar as diferenças observadas. Todas as classificações e curvas de perda desta seção se restringem a Transformer, Informer e LSTM.')
replace(222, 'Figura 11 — Perfis cumulativos de erro nos horizontes de cada tarefa')
replace(241, 'O alcance da comparação é interno às três implementações avaliadas: seus resultados não estabelecem uma classificação geral dos métodos de previsão solar [9]. Também não avaliam eficiência computacional. Os valores discretizados continuam representados em float32, e os pesos não são quantizados. Conclusões sobre memória ou velocidade exigiriam uma representação compacta ou aritmética inteira, acompanhada de medições sob hardware definido.')
replace(243, 'O TCC comparou Transformer, Informer e LSTM sob quatro condições de entrada, quatro tarefas e três regimes temporais. Entre as três implementações avaliadas, o Transformer apresentou os menores MAEs cumulativos completos nas tarefas horária e diária de 2024, e o Informer, nas duas tarefas mensais. A análise local mostrou que essa ordenação agregada não se mantém em todos os pontos. As conclusões são descritivas para os dados e configurações utilizados.')
replace(244, 'Quanto à primeira questão de pesquisa, a resposta à quantização depende da tarefa e do modelo. Reduzir a resolução de amplitude das entradas pode produzir erros próximos ou inferiores aos do controle em determinadas configurações, mas não oferece benefício uniforme. As variantes incluem clipping, e sua baixa incidência no teste de 2024 não elimina a influência possível na seleção. O experimento avalia a transformação executada, sem atribuir todo o efeito observado exclusivamente ao arredondamento.')
replace(245, 'A segunda questão trata da transferência da escolha realizada na validação para o teste. Nas doze combinações de modelo e tarefa de 2024, a condição quantizada selecionada reduziu o MAE em cinco e o elevou em quatro; nas três restantes, foi escolhido o controle contínuo. Portanto, o resultado favorável na validação não garante vantagem posterior. Preservar essa escolha no teste, inclusive quando outro nível apresenta menor erro observado, é essencial à interpretação do protocolo.')
replace(246, 'A terceira questão refere-se à ampliação do histórico sob validação e teste pareados. Nos controles contínuos, o histórico longo reduziu o MAE em onze das doze combinações. A exceção da LSTM horária mostra que incluir anos anteriores não garante melhora. A ampliação também modifica as janelas disponíveis, a composição dos anos e os extremos usados na normalização, e os registros de treinamento mostram trajetórias de ajuste diferentes. O resultado não isola um mecanismo causal único.')
replace(247, 'As extensões prioritárias dentro desse recorte são avaliar um controle com apenas clipping, repetir as tarefas horárias com mais sementes e examinar a sensibilidade ao orçamento de épocas, mantendo regras de validação anteriores ao teste. Novos anos de avaliação e diagnósticos por estação podem aprofundar a análise de estabilidade. Estudos de eficiência de implantação exigem outra etapa de implementação e medição, além da precisão preditiva avaliada neste TCC.')
replace(263, '[14] NASCIMENTO, G. de M.; CABRAL, T. W.; FRAIDENRAICH, G. Multi-Resolution Global Horizontal Irradiance Forecasting at Electric-Vehicle Manufacturing Locations: TimesNet and Dilated Recurrent Networks. Manuscrito do projeto encaminhado aos orientadores em 7 set. 2026, 19 p.')
replace(265, P[265].text + ' As Tabelas 9 a 12 correspondem, respectivamente, às tarefas horária, diária, mensal de um passo e mensal de seis passos.')
replace(275, P[275].text + ' As Tabelas 13 a 15 apresentam os regimes atual, histórico longo e histórico curto pareado, respectivamente.')
replace(288, 'APÊNDICE C — CONFIGURAÇÕES E PROVENIÊNCIA DOS RESULTADOS')
replace(307, 'A matriz local usa metricas_por_localidade_teste.csv das doze combinações atuais; suas médias conferem com os macro-MAEs auditados. Os perfis de BYD Camaçari utilizam dados/brutos/localidades_ev/byd_camacari.csv e dados/brutos/localidades_ev_horario/nsrdb_ghi_horaria_2024.csv.gz. O mapa é reproduzido de [14]. As trajetórias de perda da Figura 13 provêm dos CSVs de seleção horária dos controles contínuos, semente 42, com hashes conferidos nos metadados das respectivas execuções.')
replace(264, 'APÊNDICE A — RESULTADOS POR HORIZONTE NO REGIME ATUAL')
replace(274, 'APÊNDICE B — COMPARAÇÃO DAS QUATRO CONDIÇÕES DE ENTRADA')

# Consistent presentation precision; retain table values and small configuration constants.
for i in range(74, 249):
    p = P[i]
    if p.style.name != 'Normal' or p._p.xpath('.//m:oMath'):
        continue
    def rounded(match):
        value = Decimal(match.group(0).replace(',', '.')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return format(value, '.2f').replace('.', ',')
    new = re.sub(r'(?<![\d,])\d{1,3},\d{4}(?!\d)', rounded, p.text)
    if new != p.text:
        replace(i, new)

# Physical quantization scale, without interpreting an assumed noise model as a measurement.
paragraph('Em unidades físicas, o espaçamento entre níveis é Δ = (b − a)/(N − 1), em que b − a é a amplitude ajustada para a localidade. No refit horário anterior a 2024, Q64 corresponde a passos entre 16,24 e 18,04 W/m² nas dez localidades. Sob a hipótese idealizada de erro de arredondamento uniforme em cada intervalo, o RMS seria Δ/√12, entre 4,69 e 5,21 W/m² [6]. Essa aproximação descreve a entrada, não um erro empírico medido nem um limite para a saída da rede; a propagação depende da função aprendida.', before=P[142]._p)
paragraph('Os diagnósticos do teste de 2024 registram clipping em 14 de 1.219.680 entradas horárias (0,0011%) e 328 de 1.230.050 diárias (0,0267%); nas duas tarefas mensais, não há saturação no teste. Essas contagens se referem a valores escalares nas janelas de entrada, que podem se sobrepor, e não a observações independentes ou erros de previsão. Na validação de 2023, porém, há 24 de 1.440 entradas saturadas na tarefa mensal de um passo (1,67%) e nove de 840 na de seis passos (1,07%). A baixa incidência no teste caracteriza essa etapa, mas não exclui influência anterior na escolha de épocas e níveis nem mede a magnitude de seu efeito nas previsões.', before=P[215]._p)

# Loss diagnosis uses only the same three models, from already completed training.
paragraph('Diagnóstico dos registros de treinamento', 'Heading 2', before=P[234]._p)
paragraph('A Figura 13 apresenta as trajetórias de seleção horária dos controles contínuos. Elas complementam a comparação da Tabela 8, sem alterar as condições selecionadas na validação utilizadas nas tabelas principais. Nos controles do regime atual, as épocas escolhidas foram 30 para Transformer, quatro para Informer e 25 para LSTM.', before=P[234]._p)
paragraph('Figura 13 — Trajetórias de validação dos controles contínuos na tarefa horária', 'Caption', before=P[234]._p, keep=True)
picture = paragraph('', before=P[234]._p, keep=True)
picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
picture.paragraph_format.first_line_indent = Cm(0)
pic = picture.add_run().add_picture(str(HERE / 'figuras/diagnostico_treinamento_horario_controles.png'), width=Cm(17))
pic._inline.docPr.set('descr', 'Perda de validação por época de Transformer, Informer e LSTM, controles contínuos horários nos três regimes temporais.')
paragraph('Fonte: elaboração própria com os registros de seleção dos três modelos, semente 42. MSE de validação normalizado em eixo vertical logarítmico; círculos indicam as épocas escolhidas. O regime atual avalia 2023; os históricos compartilham a validação, mas usam escalas ajustadas em períodos distintos. As curvas incluem as épocas registradas até a parada antecipada ou o teto de 30 épocas e não isolam o efeito da duração do histórico.', 'Fonte', before=P[234]._p)
paragraph(diagnosis['short_discussion'], before=P[234]._p)
paragraph(diagnosis['epoch_budget_paragraph'], before=P[234]._p)

# Replace the external-model appendix, retaining its cited map source in the bibliography.
old_curve_rids = P[311]._p.xpath('.//a:blip/@r:embed')
for p in P[308:]:
    p._element.getparent().remove(p._element)
for rid in old_curve_rids:
    doc.part.drop_rel(rid)

# Institutional front matter: preserve each complete block and its page-break paragraph.
body = doc._element.body
children = list(body)
i_summary, i_toc, i_intro = (children.index(P[i]._p) for i in (29, 34, 74))
summary_block = children[i_summary:i_toc]
toc_block = children[i_toc:i_intro]
for element in summary_block + toc_block:
    body.remove(element)
for offset, element in enumerate(toc_block + summary_block):
    body.insert(i_summary + offset, element)

# Add the verified references before Appendix A.
for reference in literature['new_references']:
    paragraph(reference['reference'], 'Bibliografia', before=P[264]._p)
for p in doc.paragraphs:
    if p.style.name == 'Bibliografia':
        p.paragraph_format.space_after = Pt(2)
        for run in p.runs:
            run.font.size = Pt(10.5)

# The old project jargon is unnecessary in each caption; keep precise provenance in Appendix C.
for p in doc.paragraphs:
    if p.text.startswith('Fonte: elaboração própria a partir dos dados e contratos auditados do projeto.'):
        tail = p.text.split('Fonte: elaboração própria a partir dos dados e contratos auditados do projeto.', 1)[1]
        p.text = 'Fonte: elaboração própria com dados e registros de execução do projeto (Apêndice C).' + tail

# All new technical details are placed in the existing appendix.
paragraph('Configurações e parâmetros treináveis', 'Heading 2')
paragraph('As configurações abaixo descrevem a implementação efetivamente executada, conferida nas fontes preservadas cujos hashes coincidem com os registros dos experimentos. Em todas as tarefas há uma entrada de GHI por instante e uma representação aprendida de oito dimensões para cada uma das dez localidades. C indica o comprimento do histórico e H, o horizonte de saída.')
add_table('Tabela 16 — Configurações das três arquiteturas',
          ['Componente', 'LSTM', 'Transformer', 'Informer'], [
              ['Estado ou dimensão interna', '32 unidades', '16', '16'],
              ['Camadas recorrentes ou de encoder', '1 recorrente', '2 encoders', '2 encoders'],
              ['Camadas de decoder', 'Não se aplica', '1', '1'],
              ['Cabeças de atenção', 'Não se aplica', '2', '2'],
              ['Dimensão feedforward', 'Não se aplica', '32', '32'],
              ['Dropout', '0', '0,1', '0,1'],
              ['Contexto observado no decoder', 'Não se aplica', '⌊C/2⌋', '⌊C/2⌋'],
              ['Fator ProbSparse', 'Não se aplica', 'Não se aplica', '5'],
          ], [5.5, 3.8, 3.85, 3.85])
paragraph('Fonte: elaboração própria a partir das fontes executadas identificadas neste apêndice. No Informer, ProbSparse atua nas autoatenções; a atenção cruzada permanece completa. O dropout indicado atua nos blocos residuais e feedforward; os pesos da atenção ProbSparse não recebem dropout nesta implementação.', 'Fonte')
paragraph('O decoder das redes de atenção recebe 168 valores observados no horário, 182 no diário e seis nas tarefas mensais, seguidos de H zeros. O Informer aplica uma etapa de destilação entre os encoders: convolução de 16 para 16 canais, kernel 3 e padding circular de 1, seguida de BatchNorm, ELU e max-pooling de kernel 3, passo 2 e padding 1. A saída de atenção usa uma projeção linear de 16 para um compartilhada entre os passos. Na LSTM, o estado de 32 dimensões é concatenado ao embedding de oito e projetado de 40 para H.')
fmt = lambda n: f'{n:,}'.replace(',', '.')
add_table('Tabela 17 — Quantidade de parâmetros treináveis por tarefa',
          ['Tarefa', 'LSTM', 'Transformer', 'Informer'],
          [[r['tarefa'], fmt(r['LSTM']), fmt(r['Transformer']), fmt(r['Informer'])] for r in repro['tabela_parametros']],
          [6.4, 3.4, 3.6, 3.6])
paragraph('Fonte: elaboração própria. Soma das dimensões dos pesos e biases das implementações auditadas, para dez localidades. Buffers não treináveis são excluídos. A contagem é igual nas quatro condições de entrada e nos três regimes temporais.', 'Fonte')
paragraph('Transformer e Informer compartilham a projeção de saída entre posições, mantendo suas quantidades em todas as tarefas. A LSTM possui 4.560 + 41H parâmetros por causa da cabeça linear que produz o vetor inteiro. As contagens documentam o tamanho das redes, mas não equalizam sua capacidade efetiva nem demonstram igualdade de custo de treinamento.')
paragraph('Ambiente registrado nas execuções', 'Heading 2')
paragraph('Os 36 registros canônicos de configuração informam NumPy 2.4.4, pandas 3.0.3 e PyTorch 2.12.0+cu126. As tarefas horária e diária utilizam CUDA 12.6, enquanto as mensais utilizam CPU. Nos registros de Transformer e Informer horários e diários, o ambiente também identifica a GPU NVIDIA GeForce GTX 1650 with Max-Q Design e o código cuDNN 91002. Os registros da LSTM informam CUDA, sem especificar o modelo da GPU.')
paragraph('O modelo da CPU e a versão de Python não estão registrados diretamente nesses arquivos canônicos. Esses campos permanecem sem especificação, em vez de serem inferidos de um ambiente posterior. O sufixo cu126 identifica a distribuição instalada do PyTorch; não indica uso de GPU nas tarefas mensais. As fontes, versões e dispositivos declarados devem ser considerados em uma tentativa de reprodução, juntamente com as regras de determinismo e as sementes descritas na metodologia.')
paragraph('Repositório e identificação do código executado', 'Heading 2')
p_repo = paragraph('Repositório do projeto: ')
link = OxmlElement('w:hyperlink')
rid = doc.part.relate_to(repro['repositorio']['url'], RT.HYPERLINK, is_external=True)
link.set(qn('r:id'), rid)
r = OxmlElement('w:r')
pr = OxmlElement('w:rPr')
u = OxmlElement('w:u'); u.set(qn('w:val'), 'single'); pr.append(u)
r.append(pr)
t = OxmlElement('w:t'); t.text = repro['repositorio']['url']; r.append(t)
link.append(r); p_repo._p.append(link)
paragraph('O retrato consultado do repositório corresponde ao commit 3abe546cc217aff2c95a3a12bd1411c9e29c553e, de 29 de outubro de 2026. Esse identificador é posterior aos treinamentos e não é apresentado como versão de execução de todos eles. Para identificar as fontes executadas, utilizam-se os hashes SHA256 registrados em contrato_execucao.json, juntamente com os hashes das entradas e configurações. Os metadados de seleção e refit vinculam cada resultado ao conteúdo do respectivo registro.')
paragraph('As quatro fontes abaixo foram conferidas no arquivo documentacao/organizacao/fontes_antes_reorganizacao_20261027.zip e seus hashes coincidem com os registrados nos 36 contratos. Os caminhos indicam os membros internos do arquivo de preservação, anteriores à reorganização de pastas e imports. Essa identificação permite distinguir a fonte executada de versões posteriores do repositório.')
for record in repro['verificacao_fontes']:
    p = paragraph(record['membro'], 'Fonte', keep=True)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p = paragraph('SHA256: ' + record['sha256'], 'Fonte')
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT

# Number headings explicitly so their text is preserved in Word and PDF navigation.
chapter, subsection = '', 0
for p in doc.paragraphs:
    if p.style.name == 'Heading 1':
        match = re.match(r'^(\d+)\s', p.text)
        appendix = re.match(r'^APÊNDICE ([ABC])', p.text)
        chapter = match[1] if match else appendix[1] if appendix else ''
        subsection = 0
    elif p.style.name == 'Heading 2' and chapter:
        subsection += 1
        p.text = f'{chapter}.{subsection} ' + re.sub(r'^(?:\d+|[ABC])\.\d+\s+', '', p.text)

# A source SVG is edited, retaining the existing code-native diagram and its layout.
architecture_rid = P[186]._p.xpath('.//a:blip/@r:embed')[0]
doc.part.related_parts[architecture_rid]._blob = (HERE / 'figuras/arquiteturas_corrigidas.png').read_bytes()
P[186]._p.xpath('.//wp:docPr')[0].set('descr', 'Estruturas implementadas de LSTM, Transformer e Informer, com destilação entre os encoders do Informer.')

assert original_cells == [[c.text for row in table.rows for c in row.cells] for table in doc.tables[:15]]
assert len(doc.tables) == 17
assert len(doc.inline_shapes) == 13
assert not any('TimesNet' in p.text or 'DilatedRNN' in p.text for p in doc.paragraphs if p.style.name != 'Bibliografia')
assert not any('APÊNDICE D' in p.text for p in doc.paragraphs if p.style.name not in ('toc 1', 'toc 2'))
doc.core_properties.title = 'Previsão multirresolução de irradiância global horizontal em localidades associadas à fabricação de veículos elétricos'
doc.core_properties.author = 'Gustavo de Melo Nascimento'
doc.core_properties.last_modified_by = 'Gustavo de Melo Nascimento'
doc.core_properties.modified = datetime.now(timezone.utc)
working = HERE / 'authoring_working.docx'
doc.save(working)
with ZipFile(working) as z:
    authored = {n: z.read(n) for n in z.namelist()}

# Keep the institutional template's opaque parts byte-identical.
parts = dict(original)
editable = {'word/document.xml', 'word/_rels/document.xml.rels', '[Content_Types].xml', 'docProps/core.xml'}
for name in editable:
    parts[name] = authored[name]
for name, data in authored.items():
    if name.startswith('word/media/'):
        parts[name] = data
# Drop only the old orphaned external-model image when python-docx removed it.
for name in list(parts):
    if name.startswith('word/media/') and name not in authored:
        del parts[name]
with ZipFile(OUTPUT, 'w') as z:
    for name, data in parts.items():
        z.writestr(name, data)
with ZipFile(OUTPUT) as z:
    final_root = E.fromstring(z.read('word/document.xml'))
    assert original_equations == [''.join(e.xpath('.//m:t/text()', namespaces=NS)) for e in final_root.findall('.//m:oMath', NS)]
    for name in original:
        if name.startswith('word/header') or name.startswith('word/_rels/header') or name in {'word/styles.xml', 'word/numbering.xml', 'word/theme/theme1.xml'}:
            assert z.read(name) == original[name], name
audit = {
    'source': str(SOURCE), 'source_sha256': sha(SOURCE.read_bytes()), 'output': str(OUTPUT),
    'output_sha256': sha(OUTPUT.read_bytes()), 'original_result_tables_preserved': 15,
    'total_tables': 17, 'figures': 13, 'native_equations_preserved': 7,
    'references': 17, 'three_models_only': True,
    'removed': 'Former reference-study Figure 13 and Appendix D',
    'added': ['Canonical training-loss Figure 13', 'Architecture and parameter Tables 16–17', 'Related work references 15–17', 'Recorded environment and source identities'],
    'paragraph_changes': changes,
    'changed_parts': [name for name in original if name in parts and original[name] != parts[name]],
    'new_parts': sorted(set(parts) - set(original)), 'removed_parts': sorted(set(original) - set(parts)),
}
(HERE / 'auditoria_edicao.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: audit[k] for k in ('output', 'original_result_tables_preserved', 'total_tables', 'figures', 'references')}, ensure_ascii=False))
