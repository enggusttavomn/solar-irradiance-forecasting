# Contexto para auxiliar a elaboração do relatório final do TCC

Preparado em 29/10/2026 para acompanhar os arquivos do projeto. Este documento transfere contexto; não substitui as fontes científicas nem registra novos experimentos.

## Identificação e objetivo

- Aluno: Gustavo de Melo Nascimento; RA 239679.
- Instituição: Universidade Estadual de Campinas, Faculdade de Engenharia Elétrica e de Computação; Engenharia Elétrica, curso 41.
- Disciplina: EA019, segundo semestre de 2026.
- Orientador: Gustavo Fraidenraich. Coorientador: Thales Wulfert Cabral.
- Repositório: https://github.com/enggusttavomn/solar-irradiance-forecasting
- Commit do repositório consultado antes de preparar este pacote: `6c465a6161899f458fde9a062efeb7117c4ef5de`. O repositório pode receber mudanças posteriores; esta entrega é um retrato datado.
- Tema do relatório: previsão multirresolução de irradiância global horizontal em localidades associadas à fabricação de veículos elétricos; comparação de Transformer, Informer e LSTM sob quantização das entradas.
- Necessidade do aluno: receber auxílio em português para compreender, revisar e concluir um relatório de TCC completo, com fundamentação, metodologia reproduzível, resultados, gráficos, tabelas, discussão, limitações e referências.

## Documento que deve ser continuado

O documento atual é `01_relatorio_e_modelo/Relatorio_Final_GHI_Transformer_Informer_LSTM_Revisado.docx`, acompanhado do PDF com o mesmo nome. O PDF atual tem 36 páginas, 13 figuras, 15 tabelas e três apêndices. A revisão consolidou experimentos previamente executados; não realizou novos treinamentos.

Preserve os resultados e a identidade deste trabalho. Antes de editar, leia a versão revisada e explique o que será corrigido e por quê. Diferencie uma correção editorial de uma mudança metodológica que exigiria nova análise ou experimento.

Não use inventários antigos de 37 páginas ou notas antigas de campos em branco para substituir o estado atual do relatório. A compactação de 28/10/2026 preservou o conteúdo científico e mudou a paginação de 37 para 36 páginas. As informações de aluno, RA e orientadores já estão preenchidas na versão revisada.

## Arquivos do pacote e ordem de leitura

1. Este contexto e `Instrucoes_Projeto_GPT_TCC.txt`.
2. Relatório revisado em PDF, para leitura, e DOCX, para edição.
3. Modelo institucional da EA019 em DOCX e sua conversão em PDF. Este foi o modelo de apresentação efetivamente usado.
4. `02_resultados/quantizacao_ghi_modelos_para_disciplina_legivel.pdf`: síntese dos resultados dos três modelos do relatório.
5. `02_resultados/metricas_teste_modelos_disciplina.csv`, `classificacoes_modelos_disciplina.csv` e `manifesto_resultados_disciplina.json`: valores, classificações e escolhas de validação rastreáveis.
6. `03_base_tecnica/`: artigo de Cabral e colaboradores, artigo multirresolução TimesNet/DilatedRNN do projeto e manuscrito mensal DilatedRNN. São trabalhos com escopos próprios; seus resultados não substituem os deste relatório.
7. `04_exemplos_de_escrita/artigo1.pdf` e `artigo2.pdf`: exemplos disponíveis de apresentação de artigos. Tratam, respectivamente, de diagnóstico de transformadores elétricos e reconhecimento de cargas. Não tratam de previsão de GHI; não há comprovação suficiente de que tenham orientado diretamente a redação final.
8. `05_auditorias/`: auditoria numérica, contratos de execução, manifesto da revisão final e verificação bibliográfica. São apoio para conferir as fontes, não substitutos dos artigos originais.
9. `MANIFESTO_PACOTE.json`: lista de arquivos, origens e hashes SHA256 das cópias. Não contém uma conclusão científica adicional.

Se houver divergência, confira o recorte de modelo, regime temporal, variante e horizonte antes de comparar números. Para valores e escolhas, priorize os CSVs e os artefatos científicos congelados; para apresentação, o modelo institucional; para texto atual, o relatório revisado; para teoria, as fontes primárias verificadas. Explicite conflitos que não puder resolver.

## Dados e escopo científico

São estimativas modeladas da NSRDB para dez localidades associadas a instalações industriais: BYD Camaçari, Tesla Nevada, Tesla Texas, Hyundai Georgia, Rivian Normal, Tesla Fremont, Lucid Casa Grande, GM Factory Zero, Ford Rouge EV Center e BMW San Luis Potosí. Há uma localidade no Brasil, oito nos Estados Unidos e uma no México.

A variável prevista é GHI em W/m². As coordenadas selecionam células da base; não representam sensores instalados nas fábricas. O estudo não prevê diretamente produção fotovoltaica, carga industrial, retorno financeiro ou economia de energia.

As redes recebem somente o histórico de GHI e a identificação aprendida da localidade. Não recebem temperatura, nebulosidade, previsões meteorológicas ou imagens como entradas do experimento principal. O contexto climático do mapa é descritivo.

As redes compartilham parâmetros entre localidades, mas isso não demonstra generalização para localidades inéditas. O experimento é retrospectivo.

## Quatro tarefas

| Tarefa | Histórico de entrada | Horizonte de saída | Origens de teste de 2024 por localidade |
|---|---|---|---:|
| Horária | 336 horas | 72 horas | 363 |
| Diária | 365 dias | 30 dias | 337 |
| Mensal de um passo | 12 meses | Um mês | 12 |
| Mensal de seis passos | 12 meses | Seis meses | 7 |

A tarefa de seis meses é exploratória. São redes e tarefas distintas: o primeiro passo da tarefa de seis meses não equivale ao experimento mensal de um passo.

Os resultados principais são cumulativos: um resultado até 72 horas reúne os passos de 1 a 72; não é somente o erro na hora 72. Na tarefa horária, leads exatos de 24/48/72 horas podem coincidir com a noite; erros nulos nesses instantes não demonstram previsão diurna perfeita.

## Partições temporais que não devem ser confundidas

| Regime | Treinamento inicial | Validação | Refit antes do teste | Teste |
|---|---|---|---|---|
| Atual | Jan/2019 a dez/2022 | Jan a dez/2023 | Jan/2019 a dez/2023 | Jan a dez/2024 |
| Histórico longo | Jan/1998 a mar/2018 | Abr/2018 a mar/2019 | Jan/1998 a mar/2019 | Abr/2019 a dez/2022 |
| Histórico curto pareado | Abr/2014 a mar/2018 | Abr/2018 a mar/2019 | Abr/2014 a mar/2019 | Abr/2019 a dez/2022 |

A comparação do tamanho do histórico utiliza os dois últimos regimes, com validação e teste idênticos. Não compare diretamente os erros do teste de 2024 com os erros do teste histórico para atribuir diferenças à duração do treinamento.

## Normalização, quantização, seleção e treinamento

As escalas min–max são ajustadas somente com dados admissíveis anteriores ao corte correspondente. São comparadas quatro condições: controle contínuo, Q64, Q128 e Q256.

Nas variantes quantizadas, aplica-se à entrada normalizada a operação `rint(clip(u, 0, 1) * (N - 1)) / (N - 1)`, com N em 64, 128 ou 256. Apenas a amplitude do histórico de GHI é quantizada. O identificador da localidade não passa pelo quantizador. Os valores são reconstruídos em float32; pesos, alvos e saída regressiva permanecem contínuos.

O controle contínuo não recebe clipping. Assim, a comparação mistura arredondamento e saturação: falta um controle independente com apenas clipping. Não atribua todos os efeitos exclusivamente à discretização.

Épocas são escolhidas na validação, separadamente por variante e semente. A condição de entrada é escolhida pelo macro-MAE de validação do horizonte completo. Essa escolha é congelada antes do teste e mantida nos checkpoints menores. Não substitua essa condição pelo nível que posteriormente apresentou o menor erro de teste.

O refit reinicia o treinamento na mesma semente e utiliza os dados anteriores ao teste, com a quantidade de épocas já escolhida. Na tarefa horária existe somente a semente 42. Nas tarefas diária e mensais combinam-se as previsões de cinco sementes: 11, 23, 42, 67 e 89. Essa média de previsões não equivale à média dos MAEs individuais.

O relatório documenta Adam, taxa de aprendizagem 0,001 e weight decay 0,00001. Horário/diário: até 30 épocas, paciência 5, lote 128, GPU. Mensais: até 300 épocas, paciência 30, lote 32, CPU. Confirme os detalhes nos contratos; configurações comuns não garantem igualdade de custo ou capacidade entre arquiteturas.

Após a combinação das previsões, aplica-se piso zero. No horário também se anulam previsões noturnas pela geometria solar. Isso é pós-processamento, não entrada meteorológica.

## Métricas e principais resultados

MAE, MSE, RMSE, nRMSE e R² são calculados por localidade e depois agregados por média macro, com pesos iguais. O MAE é a métrica principal. O nRMSE é normalizado pela média da GHI de referência avaliada; o CSV guarda razão, enquanto tabelas percentuais multiplicam por cem. Macro-RMSE não precisa ser igual à raiz do macro-MSE.

| Teste de 2024, horizonte completo | Melhor configuração entre os três modelos | Macro-MAE em W/m² |
|---|---|---:|
| Horário até 72 h | Transformer, controle contínuo | 53,2061 |
| Diário até 30 dias | Transformer, Q256 | 43,8869 |
| Mensal de um passo | Informer, Q128 | 12,7266 |
| Mensal de seis passos | Informer, Q128 | 13,6679 |

As vantagens agregadas de Transformer sobre LSTM nas tarefas horária e diária completas são pequenas, cerca de 0,32 e 0,30 W/m². Não representam demonstração de significância estatística. No diário, a LSTM lidera até 1, 3, 7 e 14 dias; Transformer lidera no horizonte completo de 30 dias. A liderança também varia entre localidades.

A condição de entrada escolhida na validação melhora o teste em cinco das 12 combinações de modelo e tarefa, piora em quatro e mantém o controle contínuo em três. Não existe benefício universal da quantização.

Nos controles sem quantização da comparação histórica pareada, o histórico longo melhora 11 de 12 combinações. A exceção é a LSTM horária, com aumento de MAE de 14,68%. Esses números pertencem ao teste histórico, não a 2024.

## Mapa das figuras e tabelas

- Figuras 1–2 e Tabela 1: localidades, mapa e perfis da GHI nas três resoluções. O perfil NSRDB não é uma medição em fábrica.
- Figuras 3–5 e Tabelas 2–3: janelas, partições e fluxo experimental.
- Figura 6 e Tabela 4: quantização e clipping. O desenho com oito níveis é ilustrativo; os experimentos usam 64/128/256.
- Figura 7 e Tabela 5: implementações das redes e parâmetros de treinamento.
- Figuras 8–9 e Tabela 6: desempenho agregado e heterogeneidade local.
- Figura 10 e Tabela 7: sensibilidade à quantização e escolha congelada na validação.
- Figura 11 e Tabelas 9–12: métricas cumulativas por horizonte.
- Figura 12 e Tabela 8: históricos longo e curto pareados.
- Figura 13: curvas TimesNet/DilatedRNN de um estudo anterior, usadas como contexto complementar. Não são curvas do experimento principal Transformer/Informer/LSTM.
- Tabelas 13–15: todas as condições de entrada nos três regimes.
- Apêndice C: proveniência, artefatos e reprodução da consolidação. Registra 432 linhas de teste e 432 de validação, 36 classificações completas e 48 comparações históricas.

## Base de apresentação e exemplos de escrita

O modelo institucional original é `Modelo Relatório Final - EA019.EA006.docx`, fornecido pelo aluno. O pacote inclui cópias com nome simplificado. Ele orientou A4, cabeçalho institucional e logos, Times New Roman 12 no corpo, apresentação e seções. Preserve essa referência de apresentação, sem inserir textos instrucionais do modelo no relatório.

O artigo de Cabral, Fraidenraich e Capretz tem o título “Can large language models predict solar irradiance in the long term?”. É fundamento e contexto: utiliza GPT-Neo e protocolo diferente, portanto seus números não são resultados deste aluno nem uma comparação direta com o recorte do TCC.

Os manuscritos TimesNet/DilatedRNN e mensal DilatedRNN são trabalhos do próprio projeto, com comparadores e janelas próprios. A presença deles no pacote não amplia automaticamente o conjunto principal de três modelos do relatório.

Os dois artigos SBrT disponibilizados como exemplos de escrita tratam de outros problemas. Não use seus resultados como evidência de previsão solar nem confunda transformadores elétricos com a arquitetura Transformer.

## Pontos a revisar e limites das conclusões

- Conferir e preencher o link do vídeo, ainda em branco, se ele for exigido na entrega.
- Rever a expressão “continuidade do TCC” na conclusão, caso este documento seja a versão definitiva do próprio TCC.
- Reforçar a justificativa do recorte e, quando houver dados comparáveis, discutir persistência, sazonalidade e climatologia. Não inventar resultados de referências simples ausentes deste protocolo.
- Discutir estabilidade e incerteza; não inferir significância a partir de diferenças pequenas de médias. O horário usa uma semente e o mensal de seis passos somente sete origens por localidade.
- Considerar que janelas sobrepostas repetem alvos; pares origem/passo não são observações independentes.
- Manter explícita a falta do controle somente clipping.
- Não afirmar ganho de memória, velocidade, compressão de pesos ou eficiência computacional: essas grandezas não foram medidas.
- Não converter automaticamente erro de irradiância em ganho energético, econômico ou operacional.
- Não tratar observações críticas de pareceres internos sobre artigos externos como erros conclusivamente demonstrados; confira o artigo original e explicite hipóteses e dúvidas.
- A bibliografia deve ser verificada em fontes primárias quando receber novas citações. Não inventar DOI, autores, títulos, páginas ou resultados.

## Como o assistente deve trabalhar

1. Começar identificando os arquivos que conseguiu ler. Informar se não consegue acessar o repositório ou algum anexo; não alegar acesso sem evidência.
2. Ler o relatório revisado e apresentar um diagnóstico curto de cobertura, coerência e pontos pendentes.
3. Ajudar o aluno a compreender e defender cada escolha, gráfico e tabela, com explicações claras e exemplos quando úteis.
4. Propor revisões por seção, em português acadêmico natural, sem ampliar conclusões além das evidências.
5. Para afirmações numéricas, indicar arquivo e tabela/linha, regime, tarefa, modelo, variante e horizonte relevantes.
6. Preservar números em precisão integral nos dados; arredondar somente na apresentação. Não alterar dados para combinar com uma frase.
7. Separar resultados atuais, históricos e de artigos anteriores. Explicitar incerteza e informações ausentes.
8. Trabalhar sobre a versão revisada, preservando o original. Ao editar, conferir sumário, referências cruzadas, equações, fontes, unidades e legibilidade das figuras e tabelas.
9. Não executar treinamentos, substituir fontes científicas, publicar ou enviar materiais sem uma solicitação correspondente do aluno.

## Localização do código e dos dados no repositório

- `codigo_fonte/experimentos/experimento_quantizacao_concorrentes.py`: execução, regimes, variantes, seleção e refit.
- `codigo_fonte/modelos/modelos_baselines_adicionais.py`: implementações relevantes de Transformer e Informer.
- `codigo_fonte/experimentos/experimento_baselines_adicionais.py`: configuração e execução dos concorrentes.
- `codigo_fonte/experimentos/quantizacao_timesnet.py`: normalização e quantização utilizadas pelo executor.
- `codigo_fonte/experimentos/experimento_multirresolucao.py`: tarefas e componentes da avaliação multirresolução.
- `resultados/relatorios/pdfs_resumidos_legiveis_20261027/disciplina/`: métricas, classificações e manifesto do resumo quantitativo.
- `resultados/relatorios/quantizacao_todos_modelos_20260929/`: auditorias dos três regimes e pareamento histórico.
- `documentacao/relatorio_final_ea019/`: relatório e este material de contexto.

Não suponha que todo arquivo existente em uma cópia local esteja disponível no GitHub. Há arquivos ignorados, como PDFs gerados em `resultados/pdf/`, e artefatos científicos locais. O pacote fornece uma cópia dos documentos selecionados; se uma verificação depender de previsões individuais ou de outros arquivos ausentes, solicite especificamente esses dados em vez de presumir seu conteúdo.

