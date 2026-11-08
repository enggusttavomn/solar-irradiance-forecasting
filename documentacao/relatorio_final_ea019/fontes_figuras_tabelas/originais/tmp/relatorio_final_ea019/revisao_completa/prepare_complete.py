from pathlib import Path
import json,shutil,hashlib

HERE=Path(__file__).resolve().parent
TMP=HERE.parent
ROOT=TMP.parents[1]
source=(TMP/'build_report_revisado.py').read_text(encoding='utf-8')
ED=json.loads((HERE/'revisao_editorial.json').read_text(encoding='utf-8'))
RES=json.loads((TMP/'texto_resultados.json').read_text(encoding='utf-8'))
def change(old,new,n=1):
    global source
    assert source.count(old)==n,(old[:85],source.count(old),n)
    source=source.replace(old,new)

# Preserve the currently reviewed files before replacing the requested revision.
for ext in ['docx','pdf']:
    f=ROOT/f'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_Revisado.{ext}'
    backup=HERE/f'antes_revisao_completa.{ext}'
    if not backup.exists():shutil.copy2(f,backup)

title='Previsão multirresolução de irradiância global horizontal\\nem localidades associadas à fabricação de veículos elétricos'
subtitle='Transformer Informer e LSTM sob quantização das entradas'
change('PREVISÃO DE IRRADIÂNCIA SOLAR\\nCOM TRANSFORMER INFORMER E LSTM',title,n=2)
change('Avaliação multirresolução e quantização das entradas',subtitle,n=2)
change("doc.core_properties.title='Previsão de irradiância solar com Transformer Informer e LSTM'","doc.core_properties.title='Previsão multirresolução de irradiância global horizontal em localidades associadas à fabricação de veículos elétricos'")
change("spacer(2.6)\np('GUSTAVO DE MELO NASCIMENTO','Frente')\nspacer(1.9)","spacer(2.0)\np('GUSTAVO DE MELO NASCIMENTO','Frente')\np('RA 239679','Frente')\nspacer(1.9)")
change("spacer(4.6)","spacer(4.4)")
change("page()\nspacer(3)\np('Previsão multirresolução", "page()\nspacer(1.5)\np('Previsão multirresolução")
change("for s in ['Aluno: Gustavo de Melo Nascimento','RA: __________________________________','Disciplina: ______________________________','Semestre: ______________________________','Orientador: _____________________________']:p(s,'Frente')",
"for s in ['Aluno: Gustavo de Melo Nascimento','RA: 239679','Curso: Engenharia Elétrica (41)','Disciplina: EA019','Semestre: 2º semestre de 2026','Professor orientador: Gustavo Fraidenraich','Coorientador: Thales Wulfert Cabral']:p(s,'Frente')")
change("spacer(2.1)\np('CAMPINAS'","spacer(1.0)\np('CAMPINAS'")
change("working=TMP/'revisao_artigo/authoring_working.docx'","working=TMP/'revisao_completa/authoring_working.docx'")
change("(TMP/'revisao_artigo/authoring_audit.json')","(TMP/'revisao_completa/authoring_audit.json')")


change("configure('Title',18,True,WD_ALIGN_PARAGRAPH.CENTER,0,14,0)","configure('Title',16.5,True,WD_ALIGN_PARAGRAPH.CENTER,0,10,0)\nstyles['Title'].paragraph_format.left_indent=Cm(1)\nstyles['Title'].paragraph_format.right_indent=Cm(1)\nstyles['Title'].paragraph_format.line_spacing=1.05")
change("configure('Subtitle',14,False,WD_ALIGN_PARAGRAPH.CENTER,0,14,0)","configure('Subtitle',13,False,WD_ALIGN_PARAGRAPH.CENTER,0,8,0)")
change("spacer(1.2)\nz=p('Relatório final", "spacer(.8)\nz=p('Relatório final")

# Link the existing figures to the reasoning without adding redundant sections.
replacements={
 'A Tabela 1 identifica os pontos e suas coordenadas.':'A Figura 1 situa as dez localidades nas Américas, e a Tabela 1 apresenta suas coordenadas.',
 'Os perfis a seguir mostram a série de referência de BYD Camaçari':'A Figura 2 mostra a série de referência de BYD Camaçari',
 'O contexto horário corresponde a duas semanas de observações':'Como sintetiza a Figura 3, o contexto horário corresponde a duas semanas de observações',
 'Os intervalos da Tabela 3 delimitam a informação admissível.':'A Figura 4 e a Tabela 3 delimitam a informação admissível em cada etapa.',
 'Os três modelos minimizam MSE na escala normalizada durante o treinamento.':'O fluxo da Figura 5 organiza as etapas de dados, seleção e avaliação. Os três modelos minimizam MSE na escala normalizada durante o treinamento.',
 'A função rint arredonda para o inteiro mais próximo e utiliza inteiro par em empates exatos.':'A Figura 6 ilustra a operação e sua saturação. A função rint arredonda para o inteiro mais próximo e utiliza inteiro par em empates exatos.',
 'A matriz apresenta os MAEs de cada local':'A Figura 9 apresenta os MAEs de cada local',
 'Os indicadores por horizonte são cumulativos:':'Os perfis da Figura 11 mostram indicadores cumulativos:',
 'Nos controles sem quantização, o histórico longo apresentou menor MAE':'A Figura 12 e a Tabela 8 mostram que, nos controles sem quantização, o histórico longo apresentou menor MAE',
 'A avaliação por localidade e em novos anos é necessária antes de ampliar as conclusões para outros cenários.':'A análise local realizada evidencia essa heterogeneidade. Sua extensão a outros anos e a erros condicionados à estação é necessária antes de ampliar as conclusões para novos cenários.',
 'Um nível com bom resultado na validação pode aumentar o erro no teste, especialmente diante de mudança na distribuição temporal.':'Uma condição escolhida na validação pode apresentar erro de teste maior que o controle. O experimento documenta essa diferença, mas não identifica isoladamente seu mecanismo.',
 'examinar perdas por localidade':'aprofundar o diagnóstico dos erros locais por estação do ano',
}
conclusion_old='No regime atual, o Transformer apresentou os menores MAEs cumulativos completos nas tarefas horária e diária, enquanto o Informer apresentou os menores nas duas tarefas mensais. A comparação entre essas tarefas exige cautela, pois elas diferem em agregação, contexto, horizonte e número de origens. Os resultados não sustentam uma superioridade universal de uma arquitetura.'
conclusion_new=next(x for x in ED['melhorias'] if x['id']=='conclusao_heterogeneidade')['substituir_paragrafo_243_por']
replacements[conclusion_old]=conclusion_new
condensed=next(x for x in ED['melhorias'] if x['id']=='reduzir_inventario_numerico')['substituir_paragrafos_198_199_por']
replacements[RES[0]['paragraphs'][1]]=condensed[0]
replacements[RES[0]['paragraphs'][2]]=condensed[1]
# The first paragraph of the quantization block is replaced by an argument tied to its evidence.
replacements[RES[1]['paragraphs'][0]]='A Figura 10 compara os três níveis de quantização com o controle do mesmo modelo e tarefa. Como as variantes quantizadas também incluem clipping, os contrastes refletem conjuntamente saturação e arredondamento das entradas. A Tabela 7 preserva a escolha realizada na validação, inclusive quando o controle foi selecionado.'
declarations='TEXT_REVISIONS='+repr(replacements)+'\n\n'
change("def p(txt='',style=None,align=None,bold=None):",declarations+"def p(txt='',style=None,align=None,bold=None):\n    for old,new in TEXT_REVISIONS.items():txt=txt.replace(old,new)")

# Coherent quantization section rather than two adjacent versions of the same heading.
change("    if i:h(block['heading'],2)","    if i and i!=1:h(block['heading'],2)")
change("h('Escolha por validação e efeito no teste',2)","h('Quantização e seleção da condição de entrada',2)")
change('Estrela indica escolha na validação quando a variante escolhida é quantizada.','Estrela identifica a condição escolhida na validação; contorno destaca escolhas quantizadas.')
change('Horizonte cumulativo completo e nível escolhido na validação. Menor MAE indica menor erro.','Macro-MAE no horizonte cumulativo completo, com nível escolhido na validação. Média dos MAEs das dez localidades com pesos iguais; menor valor indica menor erro.')
change('Variações calculadas em relação ao controle do mesmo modelo e tarefa.','Variações do macro-MAE calculadas em relação ao controle do mesmo modelo e tarefa.')
change('A condição de entrada permanece fixa pela escolha no horizonte completo da validação. O painel mensal de seis passos é exploratório.','Macro-MAE cumulativo, com pesos iguais entre localidades. A condição de entrada permanece fixa pela escolha no horizonte completo da validação. O painel mensal de seis passos é exploratório.')
change('Cada segmento conecta os MAEs do mesmo modelo no controle sem quantização.','Cada segmento conecta os macro-MAEs do mesmo modelo no controle sem quantização.')
change("note='Entrada é o nível escolhido na validação; Controle indica ausência de quantização.'","note='Métricas agregadas por média dos valores locais, com pesos iguais. Entrada é o nível escolhido na validação; Controle indica ausência de quantização.'")
change("    if 'Informer' in block['heading']:fig(","    if 'Informer' in block['heading']:\n        p('A Figura 7 sintetiza as estruturas implementadas e destaca quais operações são compartilhadas ou específicas de cada rede.')\n        fig(")

# Add the requested type of forecast curve using only the exact archived article trajectories.
shutil.copy2(HERE/'curvas/perfis_sete_dias_artigo_referencia.png',TMP/'revisao_artigo/figuras/13_perfis_referencia.png')
change("h('Discussão integrada e limitações',2)","""h('Perfis temporais do estudo de referência',2,new=True)
p('A Figura 13 apresenta três perfis horários do estudo de referência [14], com TimesNet e DilatedRNN. Esses casos permitem examinar picos e diferenças temporais que não aparecem na média de erro. Constituem uma análise complementar do artigo e não integram a avaliação de quantização de Transformer, Informer e LSTM.')
fig('13_perfis_referencia','GHI de referência e previsões em sete dias do estudo do artigo',
    'Curvas arquivadas do artigo [14], semente 42. Cada painel reúne os passos 1 a 24 de sete saídas de 72 horas emitidas em meias-noites locais consecutivas. O MAE considera os 168 pontos exibidos, incluindo a noite. A faixa cinza destaca o mesmo dia do artigo.',
    source='elaboração própria a partir de Nascimento, Cabral e Fraidenraich [14]',width=16.2)
p('Os perfis mostram subestimação de alguns picos e previsões excessivas em períodos de GHI baixa. A TimesNet tem menor MAE em GM e Hyundai; a DilatedRNN, no Texas. Essa ordenação se restringe às semanas selecionadas e não substitui a comparação anual nem demonstra causas meteorológicas.')
h('Discussão integrada e limitações',2)""")
change('Os apêndices apresentam as curvas em formato tabular e os MAEs das quatro condições nos três regimes.','Os apêndices apresentam os checkpoints em formato tabular e os MAEs das quatro condições nos três regimes.')
change('A separação dos regimes evita atribuir ao tamanho do histórico diferenças entre testes realizados em anos distintos.','A separação dos regimes evita atribuir ao tamanho do histórico diferenças entre testes realizados em anos distintos. Ao final, os perfis de sete dias do artigo [14] são apresentados como estudo de referência separado da comparação de quantização.')

# Keep source provenance concise enough to fit with the pre-existing numerical audit.
old='A matriz de desempenho por localidade utiliza os arquivos metricas_por_localidade_teste.csv das doze combinações atuais de modelo e tarefa, na variante escolhida na validação. A média dos dez MAEs locais foi conferida contra o macro-MAE auditado em cada combinação. Os perfis de GHI usam os dados brutos de BYD Camaçari em 2024: dados/brutos/localidades_ev/byd_camacari.csv e dados/brutos/localidades_ev_horario/nsrdb_ghi_horaria_2024.csv.gz. O mapa é reproduzido do artigo [14]; os demais gráficos de resultados foram reconstruídos com dados deste recorte.'
new='A matriz local usa metricas_por_localidade_teste.csv das doze combinações atuais; suas médias conferem com os macro-MAEs auditados. Os perfis de BYD Camaçari usam dados/brutos/localidades_ev/byd_camacari.csv e dados/brutos/localidades_ev_horario/nsrdb_ghi_horaria_2024.csv.gz. O mapa provém de [14]. As curvas de sete dias usam resultados/artigo_revista_unificado/revisao_20260907/perfis_sete_dias.csv e metricas_perfis_sete_dias.csv da mesma pasta: 504 alvos e seis MAEs conferidos, sem novos treinamentos. Esse estudo de referência permanece separado dos rankings de quantização.'
change(old,new)

(TMP/'build_report_completo.py').write_text(source,encoding='utf-8')
contract='''# Revisão completa solicitada pelo autor

Preservar o contrato de layout e o pacote de origem de ../artifact.md, com as exceções expressamente autorizadas nesta rodada: preencher identificação acadêmica, substituir título e subtítulo com base no artigo, integrar gráfico real de sete dias e rever a redação.
RA 239679, curso41, orientador Gustavo Fraidenraich e coorientador Thales Wulfert Cabral: plano legado legível de22/06/2026 em documentacao/materiais_de_referencia/Modelo-20Plano-20de-20Trabalho-2.pdf_0651.pdf,p1. DisciplinaEA019 e2ºsemestre2026: resultados/relatorios/revisao_pre_envio_20260907/README.md. O plano legado usaEA018; usar registro posterior para a disciplina atual. Não há professor responsável separado documentado; rotular Gustavo como professor orientador.
Manter a versão antiga em antes_revisao_completa.docx/pdf. Atualizar os arquivos Revisado no caminho já aberto pelo usuário. Não alterar o plano nem o relatório inicial sem Revisado.
Título contextualiza multirresolução, GHI e localidades industriais. Subtítulo explicita Transformer Informer e LSTM sob quantização das entradas. Manter estilosTitle eSubtitle, pretos, identidade institucional, A4 e corpoTNR12.
As treze figuras incluem curvas deTimesNet/DilatedRNN do estudo de referência, expressamente separadas dos resultados quantitativos dos três modelos. Ausentes trajetórias/checkpoints finais da quantização, não inventar curvas nem atribuir pilotos ao teste2024. As15tabelas e7equações ficam intactas. Melhorias editoriais incluem referências às figuras no corpo, conclusão com heterogeneidade local e organização coesa da quantização.
Runtime bundled Python/Node C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies. SemLibreOffice bundled; usar renderer canônico via wrapper WordCOM oculto existente, com atualização de campos e guardas de preservação do pacote. Revisar todas páginas e sumário.
'''
(HERE/'artifact.md').write_text(contract,encoding='utf-8')
(HERE/'changes.json').write_text(json.dumps({'title':title.replace('\\n',' '),'subtitle':subtitle.replace('\\n',' '),'identification':{'RA':'239679','curso':'41','disciplina':'EA019','semestre':'2º semestre de 2026','orientador':'Gustavo Fraidenraich','coorientador':'Thales Wulfert Cabral'},'expected_tables':15,'expected_figures':13,'expected_equations':7},ensure_ascii=False,indent=2),encoding='utf-8')
print('Preparado build_report_completo.py com identificação, título e treze figuras.')
