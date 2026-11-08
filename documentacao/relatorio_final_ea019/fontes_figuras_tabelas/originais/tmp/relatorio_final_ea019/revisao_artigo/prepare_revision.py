from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
TMP=HERE.parent
source=(TMP/'build_report.py').read_text(encoding='utf-8')

def change(old,new):
    global source
    assert source.count(old)==1,(old[:90],source.count(old))
    source=source.replace(old,new)

change("Relatorio_Final_GHI_Transformer_Informer_LSTM.docx'","Relatorio_Final_GHI_Transformer_Informer_LSTM_Revisado.docx'")
change("def fig(name,title,note=''):","def fig(name,title,note='',source='elaboração própria',width=16.7):")
change("z.add_run().add_picture(str(TMP/'figuras'/f'{name}.png'),width=Cm(16.7))", "pic=z.add_run().add_picture(str(TMP/'revisao_artigo/figuras'/f'{name}.png'),width=Cm(width))\n    pic._inline.docPr.set('descr',title)")
change("p('Fonte: elaboração própria.'+(' '+note if note else ''),'Fonte')","p('Fonte: '+source+'.'+(' '+note if note else ''),'Fonte')")
change("working=TMP/'authoring_working.docx'","working=TMP/'revisao_artigo/authoring_working.docx'")
change("(TMP/'authoring_audit.json')","(TMP/'revisao_artigo/authoring_audit.json')")

# Preserve the original tables and their numbers while enriching the visual explanation.
anchor="table('Localidades e coordenadas de referência'"
pos=source.index(anchor)
source=source[:pos]+"""fig('11_mapa','Distribuição geográfica e contexto climático das dez localidades',
    'Mapa reproduzido da Figura 1 do artigo [14]. Os números 1 a 10 seguem a ordem da Tabela 1. Os painéis ampliam os Estados Unidos e a região de Detroit. Cores e códigos climáticos têm função descritiva e não são entradas dos modelos.',
    source='Nascimento, Cabral e Fraidenraich [14]')
page()
"""+source[pos:]

change("h('Tarefas e janelas temporais',2)","""h('Resoluções temporais da GHI',2,new=True)
p('A mesma grandeza física apresenta estruturas diferentes conforme a agregação temporal. Os perfis a seguir mostram a série de referência de BYD Camaçari em intervalos fixos do calendário de 2024. A curva horária evidencia ciclos diurnos; as médias diárias e mensais sintetizam os intervalos correspondentes. As três escalas conservam a unidade W/m². A comparação visual caracteriza os dados e não representa previsões dos modelos.')
fig('10_perfis_dados','Perfis reais da GHI nas resoluções horária diária e mensal',
    'Séries NSRDB de BYD Camaçari. Semana de 1 a 7 de janeiro, médias diárias de janeiro e médias mensais de 2024. Horária e diária provêm de consultas independentes; a mensal é calculada das diárias. Escalas verticais próprias por painel.')
h('Tarefas e janelas temporais',2)
fig('08_janelas','Contextos observados e horizontes de saída nas quatro tarefas',
    'Diagrama esquemático, sem escala de duração. C representa o comprimento do histórico e H o número de valores futuros. As tarefas mensais de um e seis passos utilizam redes treinadas separadamente.')""")
change("h('Separação cronológica e comparação pareada',2)","""h('Separação cronológica e comparação pareada',2)
fig('09_particoes','Partições temporais e comparabilidade entre os regimes',
    'Blocos sem escala proporcional de duração. O refit inclui somente dados anteriores ao teste. Histórico longo e curto pareado compartilham validação e teste; o regime atual avalia outro período.')""")
change("fig('01_fluxo','Fluxo causal de preparação seleção e avaliação','Apenas X passa pelo quantizador. O alvo permanece contínuo e o teste não escolhe épocas ou nível de entrada.')",
"""fig('01_fluxo','Fluxo experimental em etapas de dados seleção e avaliação',
    'Organização em faixas adaptada da Figura 2 do artigo [14] para o recorte com quantização e três modelos. A validação fixa as escolhas; o teste avalia a configuração congelada. Na tarefa horária há uma semente; nas demais, média de cinco sementes.',
    source='elaboração própria, com organização visual adaptada de Nascimento, Cabral e Fraidenraich [14]')""")
change("fig('04_mae_atual','Comparação do MAE dos modelos no regime atual','Teste de 2024 e nível escolhido na validação. As escalas verticais são próprias de cada tarefa.')",
"""fig('04_mae_atual','Classificação dos modelos por tarefa no teste de 2024',
    'Horizonte cumulativo completo e nível escolhido na validação. Menor MAE indica menor erro. Escalas horizontais próprias por painel; cores identificam o mesmo modelo ao longo do relatório.')""")
change("        h('Escolha por validação e efeito no teste',2)","""        h('Heterogeneidade entre localidades',2,new=True)
        p('A média macro atribui o mesmo peso às dez localidades, mas pode ocultar mudanças de liderança. A matriz apresenta os MAEs de cada local com a mesma condição de entrada utilizada na classificação agregada. Cada painel corresponde a uma tarefa e ao seu horizonte cumulativo completo.')
        fig('12_localidades','Desempenho por localidade nas quatro tarefas',
            'Métricas locais de teste com seleção fixa pela validação. Escala de cor própria por painel. Contorno e negrito indicam o menor MAE local com a precisão integral dos dados; valores arredondados podem parecer empatados. A comparação é descritiva e não indica significância estatística.',width=16.1)
        paras('''O Transformer apresenta o menor MAE em sete localidades na tarefa horária e seis na diária. A LSTM lidera nas três e quatro localidades restantes, respectivamente. Nas tarefas mensais de um e seis passos, o Informer lidera em cinco localidades, a LSTM em três e o Transformer em duas. Logo, o primeiro lugar na média macro não equivale a liderança em todos os locais.

Os resultados mensais também mostram situações distintas para os pontos de Detroit: a LSTM apresenta o menor MAE em GM Factory Zero e Ford Rouge EV Center nas duas tarefas mensais. Esses resultados descrevem a heterogeneidade observada; não identificam sua causa climática nem demonstram generalização para localidades não usadas no ajuste.''')
        h('Escolha por validação e efeito no teste',2)""")
change("    for tx in block['paragraphs']:p(tx)","    for tx in (block['paragraphs'][:3] if i==0 else block['paragraphs']):p(tx)")
change("fig('06_historico','Variação do erro com ampliação do histórico sob teste pareado','Comparação descritiva do controle sem quantização, mantendo validação e teste históricos comuns.')",
"""fig('06_historico','MAE com histórico curto e longo sob teste pareado',
            'Cada segmento conecta os MAEs do mesmo modelo no controle sem quantização. Validação e teste são comuns aos dois históricos. Δ = 100 × (MAE longo / MAE curto − 1); valores negativos indicam redução do erro. Escalas próprias por tarefa.')""")
change('Estrela indica escolha na validação quando a variante escolhida é quantizada.','Estrela identifica a condição escolhida na validação; contorno destaca escolhas quantizadas.')
change("[13] DIAGNE, M.; DAVID, M.; LAURET, P.; BOLAND, J.; SCHMUTZ, N. Review of solar irradiance forecasting methods and a proposition for small-scale insular grids. Renewable and Sustainable Energy Reviews, v. 27, p. 65–76, 2013. DOI: 10.1016/j.rser.2013.06.042.'",
"""[13] DIAGNE, M.; DAVID, M.; LAURET, P.; BOLAND, J.; SCHMUTZ, N. Review of solar irradiance forecasting methods and a proposition for small-scale insular grids. Renewable and Sustainable Energy Reviews, v. 27, p. 65–76, 2013. DOI: 10.1016/j.rser.2013.06.042.',
'[14] NASCIMENTO, G. de M.; CABRAL, T. W.; FRAIDENRAICH, G. Multi-Resolution Global Horizontal Irradiance Forecasting at Electric-Vehicle Manufacturing Locations: TimesNet and Dilated Recurrent Networks. Manuscrito do projeto encaminhado aos orientadores em 7 set. 2026, 19 p. Arquivo: Artigo_Gustavo_Nascimento.pdf.'""")
change("O manifesto da disciplina registra dez seções do resumo de resultados.","""A matriz de desempenho por localidade utiliza os arquivos metricas_por_localidade_teste.csv das doze combinações atuais de modelo e tarefa, na variante escolhida na validação. A média dos dez MAEs locais foi conferida contra o macro-MAE auditado em cada combinação. Os perfis de GHI usam os dados brutos de BYD Camaçari em 2024: dados/brutos/localidades_ev/byd_camacari.csv e dados/brutos/localidades_ev_horario/nsrdb_ghi_horaria_2024.csv.gz. O mapa é reproduzido do artigo [14]; os demais gráficos de resultados foram reconstruídos com dados deste recorte.

O manifesto da disciplina registra dez seções do resumo de resultados.""")

# Remove two repeated explanations that would otherwise create residual pages.
start=source.index("p('Material do próprio projeto consultado:")
end=source.index('\n',start)
source=source[:start]+source[end:]
start=source.index('O manifesto da disciplina registra dez seções do resumo de resultados.')
end=source.index("''')",start)
source=source[:start]+source[end:]

out=TMP/'build_report_revisado.py'
out.write_text(source,encoding='utf-8')
for name in ['04_mae_atual','05_quantizacao','06_historico','07_horizontes']:
    for ext in ['png','svg']:
        shutil.copy2(HERE/'figuras_comparativas'/f'{name}.{ext}',HERE/'figuras'/f'{name}.{ext}')
shutil.copy2(HERE/'11_mae_localidades.png',HERE/'figuras/12_localidades.png')
(HERE/'artifact_revision.md').write_text('''# Revisão visual a partir do artigo

Documento de base: documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM.docx.
Saída distinta: Relatorio_Final_GHI_Transformer_Informer_LSTM_Revisado.docx. A versão anterior permanece intacta.
Preservar o contrato de geometria, fontes, cabeçalhos, logotipos, campos em branco, equações e tabelas registrado em ../artifact.md. O builder deriva do mesmo modelo retido. Comparar as 15 tabelas integralmente com a entrega anterior.
O pedido atual autoriza ampliar o conteúdo visual usando o artigo do envio de 7 de setembro. Introduzir mapa original com atribuição, perfis reais da GHI, janelas de entrada/saída, partições cronológicas e desempenho local. Redesenhar os sete diagramas/gráficos existentes para coerência em Arial nas figuras e cores constantes dos modelos. Títulos e corpo do Word permanecem no sistema acadêmico original.
O PDF de referência corresponde por hash a artigos/revista_unificado/main.pdf, mas suas fontes LaTeX atuais incluem revisões posteriores. Não transferir curvas, rankings ou números de TimesNet/DilatedRNN para o estudo de três modelos.
Séries ponto a ponto de previsões atuais estão ausentes; não criar curvas artificiais. A análise por localidade usa métricas reais auditadas e escolhas da validação. Perfis de entrada são identificados como séries de referência NSRDB.
Runtime confirmado pelo runtime.json: C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime. Python e Node em dependencies. Não há LibreOffice bundled; usar o wrapper existente render_docx_word.py para conversão Word COM oculta e o render_docx.py empacotado para páginas PNG. Atualizar campos com update_docx_fields.ps1 e guardas do pacote. Inspecionar todas as páginas finais.
''',encoding='utf-8')
print(out)
