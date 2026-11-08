"""Revise the retained TCC while preserving scientific tables and native maths."""
from pathlib import Path
from zipfile import ZipFile
from copy import deepcopy
from lxml import etree as E
import hashlib
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC_Corrigido.docx'
OUTPUT = SOURCE.with_name('Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC_Revisado.docx')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W, 'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
q = lambda name: '{' + W + '}' + name
sha = lambda b: hashlib.sha256(b).hexdigest()
plain = lambda p: ''.join(p.xpath('.//w:t/text()', namespaces=NS))

inventory = json.loads((HERE / 'inventario_fonte.json').read_text(encoding='utf-8'))
assert sha(SOURCE.read_bytes()) == inventory['sha256'], 'The retained source changed.'
with ZipFile(SOURCE) as z:
    infos = z.infolist()
    original = {i.filename: z.read(i.filename) for i in infos}
root = E.fromstring(original['word/document.xml'])
body = root.find('w:body', NS)
ps = root.xpath('//w:body//w:p', namespaces=NS)
assert len(ps) == 1349
table_text = lambda r: [[plain(c) for c in t.findall('.//w:tc', NS)] for t in r.findall('.//w:tbl', NS)]
math_text = lambda r: [''.join(e.xpath('.//m:t/text()', namespaces=NS)) for e in r.findall('.//m:oMath', NS)]
before_tables, before_math = table_text(root), math_text(root)
assert len(before_tables) == 17 and len(before_math) == 7

edits = {}
origins = {}
for filename in ['revisao_fluidez.json', 'revisao_cientifica.json', 'revisao_citacoes.json']:
    proposals = json.loads((HERE / filename).read_text(encoding='utf-8'))['replacements']
    if isinstance(proposals, list):
        proposals = {p['id']: p['text'] for p in proposals}
    for key, value in proposals.items():
        edits[int(key)] = value
        origins[int(key)] = filename

# Integrate reviews and explicitly remove references to redundant representations.
edits.update({
    80: 'A quantização permite investigar quanta resolução de amplitude é necessária para a previsão. Ao substituir amplitudes por um conjunto finito de níveis, introduz uma distorção de representação [6]. Neste estudo, avalia-se a sensibilidade das previsões a essa transformação, sem emular um sensor específico. Jacob et al. [7] tratam de uma aplicação distinta, com quantização de pesos e ativações para inferência em aritmética inteira. A implementação e os ganhos computacionais dessa abordagem exigem uma avaliação própria.',
    191: 'A Tabela 2 distingue o contexto observado C, o horizonte de saída H e a cobertura efetiva do teste. O histórico horário corresponde a duas semanas; os contextos diário e mensal abrangem aproximadamente um ciclo anual. As redes produzem o vetor futuro diretamente. Na tarefa mensal de seis passos, as avaliações cumulativas de um, três e seis meses utilizam a mesma rede. A tarefa mensal de um passo utiliza uma rede treinada separadamente.',
    194: 'O protocolo divide os dados em quatro etapas cronológicas. No treino inicial, a rede aprende com a primeira parte do histórico; a validação orienta a escolha do número de épocas e da condição de entrada. Em seguida, o novo ajuste anterior ao teste, denominado refit, reinicia o treinamento com todo o histórico anterior ao teste, incluindo a validação. O teste avalia as escolhas já fixadas. A Tabela 3 apresenta as datas dos regimes atual, histórico longo e histórico curto pareado, e a Figura 5 reúne o fluxo experimental.',
    220: 'As janelas respeitam os limites da Tabela 3: é necessário dispor do contexto C antes da primeira origem, e todo o horizonte H deve caber na partição avaliada. No regime atual, 2019 fornece o histórico necessário às primeiras janelas diárias e mensais com alvos em 2020. Durante o teste deslizante, observações já disponíveis podem integrar a entrada de uma previsão posterior, enquanto pesos, escalas e condição de entrada permanecem fixos.',
    260: 'Para cada modelo, tarefa, condição de entrada e semente, treina-se uma rede global com as dez localidades. Os três modelos minimizam MSE na escala normalizada, e cada execução seleciona seu número de épocas pela perda de validação. Depois, escolhe-se a condição de entrada pelo menor macro-MAE em W/m² da previsão combinada na validação, no horizonte completo. Em empate, a prioridade é controle, 64, 128 e 256 níveis. Essa escolha permanece fixa nos horizontes menores e no teste. O fluxo está na Figura 5; as Seções 4.2 a 4.4 descrevem as redes, e as Tabelas 16 e 17 do Apêndice C detalham suas configurações e quantidades de parâmetros.',
    294: 'Nas tarefas diária e mensais, combinam-se por média aritmética as previsões das cinco sementes da Tabela 5, após reconversão para W/m² e antes do pós-processamento. No horário utiliza-se a semente 42. Avalia-se o erro da previsão combinada, que difere da média dos erros individuais.',
    295: 'O pós-processamento aplica piso zero a todas as previsões. No horário, anula também os valores com elevação solar não positiva no centro do intervalo, calculada com pvlib [11]. Não há teto comum. A média entre sementes precede o piso, pois inverter essa ordem pode alterar os resultados.',
    297: 'As métricas são calculadas após a inversão da escala e o pós-processamento. Seja eᵢ = yᵢ − ŷᵢ, com referência yᵢ, previsão ŷᵢ e n pares de origem e passo em uma localidade. As Equações 3 a 6 definem o erro absoluto médio (MAE), o erro quadrático médio (MSE), sua raiz quadrada (RMSE), o RMSE normalizado (nRMSE) e o coeficiente de determinação (R²). O MAE expressa a magnitude média do erro em W/m² e constitui o critério principal; MSE e RMSE dão maior influência a desvios grandes [8,9].',
    302: 'O nRMSE divide o RMSE pela média da referência; os CSVs registram a razão, multiplicada por cem nas tabelas percentuais. O R² compara o erro quadrático com a variação da referência em torno de sua média. Pode ser negativo e fica indefinido quando o denominador é numericamente nulo. Valores indefinidos não são substituídos por zero.',
    303: 'Para uma métrica M, a Equação 7 calcula a média macro entre L localidades com valores finitos, atribuindo o mesmo peso a cada uma. Todas as dez contribuem aos resultados cumulativos principais. Como a raiz quadrada é não linear, o macro-RMSE difere, em geral, da raiz do macro-MSE.',
    305: 'A avaliação cumulativa reúne os passos de um até H de todas as origens válidas. Previsões emitidas em origens diferentes para o mesmo instante-alvo são preservadas, com o peso temporal decorrente das janelas. A sobreposição impede tratar o total de previsões como observações independentes.',
    306: 'Na tarefa horária, as emissões à meia-noite fazem os passos exatos de 24, 48 e 72 horas coincidirem com intervalos noturnos. Utilizam-se, por isso, métricas cumulativas, que incluem dia e noite. Períodos com referência e previsão nulas reduzem o MAE em relação ao recorte apenas diurno; o nRMSE também depende da média da referência e não necessariamente diminui. Comparações entre estudos exigem o mesmo recorte de horas avaliadas [9].',
    440: 'A Tabela 6 reúne as métricas das configurações selecionadas na validação de 2023 e avaliadas no teste de 2024. A comparação utiliza a semente 42 na tarefa horária e a média das previsões de cinco sementes nas demais tarefas, conforme a Seção 3.6.',
    559: 'Os históricos longo e curto são comparados nos mesmos alvos e datas de validação e teste, conforme a Tabela 3. Na tarefa horária, ambos utilizam as 1.368 origens válidas por localidade após a exclusão da janela incompleta descrita na metodologia. O pareamento evita que a mudança do período de avaliação se confunda com a ampliação do histórico.',
    560: 'A Tabela 8 mostra que, nos controles contínuos, o histórico longo apresentou menor MAE em 11 das 12 combinações de modelo e tarefa. No Informer horário, o erro passou de 136,21 para 60,90 W/m², redução de 55,29%. A exceção foi a LSTM horária, cujo MAE aumentou de 53,72 para 61,61 W/m², ou 14,68%. Incorporar anos anteriores esteve, assim, associado à melhora na maioria das configurações, sem garanti-la.',
    646: 'A comparação se restringe às três implementações avaliadas e não estabelece uma classificação geral dos métodos de previsão solar [9]. Como o protocolo não inclui persistência ou climatologia, também não quantifica o ganho em relação a essas referências simples. A eficiência computacional exigiria outra avaliação: as entradas discretizadas permanecem em float32 e os pesos não são quantizados, sem implementação ou medição de redução de memória e tempo de execução.',
    651: 'Quanto à duração do histórico, os controles contínuos apresentaram redução de MAE em onze das doze combinações pareadas. A exceção da LSTM horária mostra que incluir anos anteriores não garante melhora. Como essa ampliação modifica a quantidade de janelas, os anos representados e os extremos da normalização, o resultado não isola um mecanismo causal único. As trajetórias de treinamento também variaram entre os históricos.',
})
remove_ids = {161,162,163,195,196,197,437,438,439,629,630,631,311,653}
changes = []

def set_text(p, new):
    old = plain(p)
    if old == new:
        return
    assert not p.xpath('.//w:drawing | .//m:oMath', namespaces=NS)
    rpr = p.find('w:r/w:rPr', NS)
    rpr = deepcopy(rpr) if rpr is not None else None
    for child in list(p):
        if child.tag not in {q('pPr'),q('bookmarkStart'),q('bookmarkEnd')}:
            p.remove(child)
    run = E.Element(q('r'))
    if rpr is not None:
        run.append(rpr)
    text = E.SubElement(run, q('t'))
    text.text = new
    if new[:1].isspace() or new[-1:].isspace():
        text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    ends = p.findall('w:bookmarkEnd', NS)
    if ends:
        p.insert(p.index(ends[0]), run)
    else:
        p.append(run)

for i, new in sorted(edits.items()):
    if i in remove_ids:
        continue
    p = ps[i]
    assert not p.xpath('ancestor::w:tbl', namespaces=NS), 'Unexpected table edit.'
    old = plain(p)
    set_text(p, new)
    if old != new:
        changes.append({'id':i,'old':old,'new':new,'review':origins.get(i,'integracao')})

for i in sorted(remove_ids):
    p = ps[i]
    changes.append({'id':i,'removed':True,'old':plain(p),'drawing':bool(p.findall('.//w:drawing',NS))})
    p.getparent().remove(p)

# Renumber retained figures; source-figure references in captions 105/225 remain external.
figure_map = {1:1,2:2,5:3,6:4,7:5,9:6,10:7,11:8,13:9}
for p in root.xpath('//w:body//w:p', namespaces=NS):
    old = plain(p)
    if p is ps[105] or p is ps[225]:
        continue
    def renumber_figure(match):
        n = int(match.group(1))
        assert n in figure_map, 'A reference to a removed figure remains: ' + old
        return 'Figura ' + str(figure_map[n])
    new = re.sub(r'Figura (\d+)\b', renumber_figure, old)
    if old != new:
        set_text(p,new)

# Resolve numeric citations by first appearance, preserving [0,1] as a mathematical range.
ref_nodes = {int(re.match(r'^\[(\d+)\]',plain(p)).group(1)):p for p in ps[655:672]}
assert set(ref_nodes) == set(range(1,18))
citation_re = re.compile(r'\[(\d+(?:\s*[,–-]\s*\d+)*)\]')
def parse_group(raw):
    values=[]
    for part in raw.split(','):
        edges=re.split('[–-]',part.strip())
        if len(edges)==1:
            values.append(int(edges[0]))
        elif len(edges)==2:
            values.extend(range(int(edges[0]),int(edges[1])+1))
        else:
            return []
    return values if values and all(1<=v<=17 for v in values) else []

ordered=[]
for p in root.xpath('//w:body//w:p',namespaces=NS):
    if p in ref_nodes.values():
        continue
    for m in citation_re.finditer(plain(p)):
        for n in parse_group(m.group(1)):
            if n not in ordered:
                ordered.append(n)
assert set(ordered)==set(range(1,18)), ordered
citation_map={old:new for new,old in enumerate(ordered,1)}
def format_group(numbers):
    numbers=sorted(set(numbers))
    chunks=[]
    start=previous=numbers[0]
    def append(a,b):
        chunks.extend([str(a)] if a==b else ([str(a),str(b)] if b==a+1 else [str(a)+'–'+str(b)]))
    for n in numbers[1:]:
        if n==previous+1:
            previous=n
        else:
            append(start,previous)
            start=previous=n
    append(start,previous)
    return '['+','.join(chunks)+']'
for p in root.xpath('//w:body//w:p',namespaces=NS):
    if p in ref_nodes.values():
        continue
    old=plain(p)
    def renumber_citation(m):
        parsed=parse_group(m.group(1))
        return format_group([citation_map[n] for n in parsed]) if parsed else m.group(0)
    new=citation_re.sub(renumber_citation,old)
    # Normalize adjacent groups without changing mathematical text.
    new=re.sub(r'\[(\d+)\], \[(\d+)\]',lambda m:format_group([int(m[1]),int(m[2])]),new)
    if new!=old:
        set_text(p,new)
for old,node in ref_nodes.items():
    set_text(node,re.sub(r'^\[\d+\]', '['+str(citation_map[old])+']',plain(node)))
ref_parent=ps[654].getparent()
insert_at=ref_parent.index(ps[654])+1
for node in ref_nodes.values():
    ref_parent.remove(node)
for offset,old in enumerate(ordered):
    ref_parent.insert(insert_at+offset,ref_nodes[old])

assert table_text(root)==before_tables
assert math_text(root)==before_math
assert len(root.findall('.//w:drawing',NS))==9
captions=[plain(p) for p in root.xpath('//w:body//w:p',namespaces=NS) if re.match(r'^Figura \d+ —',plain(p))]
assert [int(re.match(r'Figura (\d+)',s)[1]) for s in captions]==list(range(1,10))
assert '[0,1]' in ''.join(plain(p) for p in root.xpath('//w:body//w:p',namespaces=NS))

updated=dict(original)
updated['word/document.xml']=E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
with ZipFile(OUTPUT,'w') as z:
    for info in infos:
        z.writestr(info,updated[info.filename])
assert sha(SOURCE.read_bytes())==inventory['sha256']
audit={'source_sha256':inventory['sha256'],'output':str(OUTPUT),'changed_paragraphs':len([c for c in changes if not c.get('removed')]),'removed_paragraphs':len(remove_ids),'removed_original_figures':[3,4,8,12],'retained_figures':9,'preserved_tables':17,'preserved_native_equations':7,'citation_mapping_old_to_new':citation_map,'changed_package_parts':['word/document.xml'],'changes':changes}
(HERE/'alteracoes_editoriais.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in audit.items() if k!='changes'},ensure_ascii=False))
