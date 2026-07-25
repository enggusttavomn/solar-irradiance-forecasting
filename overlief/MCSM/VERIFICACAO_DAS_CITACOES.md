# Verificação das citações do artigo MCSM

Este arquivo permite conferir o que cada referência realmente sustenta no
`artigo_mcsm.tex`. A verificação foi feita em **20 de julho de 2026**, usando
preferencialmente a página da revista, o texto dos próprios autores ou a
documentação oficial.

## Resultado geral da conferência

- Todas as onze referências citadas no texto **existem**. Não foi encontrada
  referência inventada.
- O uso de **Antonanzas et al. (2016), Voyant et al. (2017), Sengupta et al.
  (2018), Voyant et al. (2022), Salinas et al. (2020), Rangapuram et al.
  (2023), NLR (2026) e Gneiting e Raftery (2007)** é compatível com as ideias
  atribuídas a elas, observadas as ressalvas descritas abaixo.
- Há **dois pontos que merecem correção no `.tex`** antes da versão final:
  **Alexandrov et al. (2020)** não comprova sozinho que o DeepNPTS faz parte do
  GluonTS, pois o artigo é anterior ao DeepNPTS; e **Hyndman e Koehler (2006)**
  não fundamenta diretamente todo o trecho que inclui R² e nRMSE.
- A referência de **Duffie e Beckman (2013)** é bibliograficamente válida e é
  adequada para os fundamentos de radiação solar, mas o livro não é de acesso
  aberto. Para máxima auditabilidade, convém indicar capítulo ou página.

Legenda: **✅ direto** = a fonte sustenta a afirmação; **⚠️ parcial** = a fonte
sustenta apenas parte da frase ou precisa ser acompanhada por outra fonte.

## 1. Alexandrov et al. (2020) — GluonTS

**Onde aparece no artigo:** no objetivo, para afirmar que a implementação
oficial do DeepNPTS está disponível no GluonTS.

**Fontes para leitura:**

- [Página do artigo no JMLR](https://www.jmlr.org/papers/v21/19-820.html)
- [PDF aberto no JMLR](https://www.jmlr.org/papers/volume21/19-820/19-820.pdf)
- [Repositório oficial do GluonTS](https://github.com/awslabs/gluonts)
- [Documentação oficial do DeepNPTS no GluonTS](https://ts.gluon.ai/v0.11.x/api/gluonts/gluonts.torch.model.deep_npts.html)
- [Versão 0.16.2 do GluonTS](https://github.com/awslabs/gluonts/releases/tag/v0.16.2)

**O que a fonte comprova:** o artigo de Alexandrov apresenta o GluonTS como
uma biblioteca para modelagem e previsão de séries temporais e informa que ela
contém implementações de referência. A documentação do GluonTS mostra
explicitamente o `DeepNPTSEstimator`, a variante discreta e os embeddings de
variáveis categóricas.

**Avaliação: ⚠️ parcial.** Alexandrov et al. (2020) comprova o GluonTS, mas não
pode comprovar sozinho a presença do DeepNPTS, divulgado em 2023. Para a frase
atual, o correto é usar em conjunto **Rangapuram et al. (2023)** e a
documentação ou o código oficial do GluonTS.

## 2. Antonanzas et al. (2016) — importância e horizonte da previsão solar

**Onde aparece no artigo:** primeiro parágrafo da introdução.

**Fontes para leitura:**

- [Página oficial e resumo na Solar Energy](https://doi.org/10.1016/j.solener.2016.06.069)

**O que a fonte comprova:** a variabilidade solar cria dificuldades para a
gestão da rede; previsões ajudam a reduzir incertezas; e os estudos variam em
horizonte temporal, extensão espacial, entradas e métricas.

**Avaliação: ✅ direto.** Há apenas uma diferença de escopo: o artigo de
Antonanzas revisa principalmente previsão de **potência fotovoltaica**, embora
também explique a previsão indireta por irradiância. Por isso, seu uso em
conjunto com Voyant et al. (2017), que trata diretamente de irradiância, está
adequado.

## 3. Duffie e Beckman (2013) — definição física de GHI

**Onde aparece no artigo:** definição de Irradiância Global Horizontal.

**Fontes para leitura:**

- [Página oficial do livro na Wiley](https://onlinelibrary.wiley.com/doi/book/10.1002/9781118671603)
- [Sumário e material oficial da quarta edição](https://bcs.wiley.com/he-bcs/Books?action=contents&bcsId=8204&itemId=0470873663)

**O que a fonte comprova:** o livro apresenta os fundamentos da radiação solar
em superfícies e a decomposição da radiação incidente. A relação usada no
artigo — GHI formada pela radiação difusa horizontal mais a projeção horizontal
da componente direta — é a definição física padrão.

**Avaliação: ⚠️ válida, mas difícil de auditar pelo link.** O livro é uma fonte
adequada, porém seu conteúdo integral depende de acesso institucional ou
compra. Antes da submissão, é recomendável indicar o capítulo ou a página exata
consultada, em vez de deixar apenas o livro inteiro como referência.

## 4. Gneiting e Raftery (2007) — CRPS, cobertura e largura

**Onde aparece no artigo:** avaliação probabilística de DeepNPTS e DeepAR.

**Fontes para leitura:**

- [PDF aberto hospedado pela University of Washington](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf)
- [DOI do artigo na JASA](https://doi.org/10.1198/016214506000001437)

**O que a fonte comprova:** apresenta o CRPS para avaliar distribuições
preditivas e discute que intervalos devem considerar simultaneamente
**cobertura** e **largura/concentração**. Também fornece a forma do CRPS para
uma distribuição representada por amostras, equivalente à fórmula usada no
artigo quando se adota a convenção de erro em que valores menores são melhores.

**Avaliação: ✅ direto para os conceitos e para o CRPS.** Os nomes PICP e MPIW
não são o foco do artigo de 2007, mas os conceitos de cobertura e largura que
eles medem são explicitamente discutidos. Portanto, a conclusão de que uma boa
cobertura não compensa intervalos excessivamente largos está fundamentada.

## 5. Hyndman e Koehler (2006) — métricas pontuais

**Onde aparece no artigo:** explicação de MAE, MSE, RMSE, R² e nRMSE.

**Fontes para leitura:**

- [Página do artigo mantida pelo autor](https://robjhyndman.com/publications/another-look-at-measures-of-forecast-accuracy/)
- [PDF aberto mantido pelo autor](https://robjhyndman.com/papers/mase.pdf)
- [DOI na International Journal of Forecasting](https://doi.org/10.1016/j.ijforecast.2006.03.001)

**O que a fonte comprova:** define e discute MAE, MSE e RMSE, inclusive o fato
de o RMSE voltar à mesma escala dos dados e de erros quadráticos darem maior
peso a erros grandes. O texto também discute medidas dependentes da escala,
percentuais e escaladas.

**Avaliação: ⚠️ parcial.** A fonte não trata diretamente do R² como métrica de
previsão e não define exatamente o nRMSE utilizado neste estudo. A citação é
adequada para MAE, MSE e RMSE, mas não deve parecer que fundamenta sozinha toda
a frase. Para máxima precisão, o `.tex` deve separar esses conceitos ou incluir
uma fonte específica para R² e para a normalização adotada.

## 6. National Laboratory of the Rockies (2026) — produto de dados

**Onde aparece no artigo:** descrição do produto GOES Aggregated PSM v4 da
NSRDB.

**Fontes para leitura:**

- [Documentação oficial da NSRDB](https://developer.nlr.gov/docs/solar/nsrdb/)
- [Documentação oficial da API GOES Aggregated PSM v4](https://developer.nlr.gov/docs/solar/nsrdb/nsrdb-GOES-aggregated-v4-0-0-download/)

**O que a fonte comprova:** o produto usa o Physical Solar Model v4, cobre o
período a partir de 1998 com os satélites GOES leste e oeste, possui resolução
espacial de 4 km e disponibiliza intervalos de 30 ou 60 minutos na API.

**Avaliação: ✅ direto.** Esta é a referência correta para identificar o
produto e os parâmetros da consulta. O nome NLR e o domínio
`developer.nlr.gov` são atuais; o domínio antigo do NREL foi desativado em
2026.

## 7. Rangapuram et al. (2023) — DeepNPTS

**Onde aparece no artigo:** descrição do DeepNPTS como modelo global e não
paramétrico, cuja variante discreta atribui probabilidades aos valores do
contexto.

**Fontes para leitura:**

- [Página do trabalho no arXiv](https://arxiv.org/abs/2312.14657)
- [PDF aberto do trabalho](https://arxiv.org/pdf/2312.14657)

**O que a fonte comprova:** o método não impõe uma forma paramétrica à
distribuição preditiva, gera previsões por amostragem da distribuição empírica
e possui uma versão global que aprende a estratégia de amostragem usando
várias séries relacionadas.

**Avaliação: ✅ direto.** Para os detalhes exatos da variante implementada no
experimento — rede discreta, posições do contexto e parâmetros da API — o
artigo deve ser lido junto com a documentação oficial do GluonTS indicada na
seção 1.

## 8. Salinas et al. (2020) — DeepAR

**Onde aparece no artigo:** descrição do DeepAR como uma rede recorrente
autorregressiva probabilística treinada globalmente.

**Fontes para leitura:**

- [Página e versão aberta no arXiv](https://arxiv.org/abs/1704.04110)
- [Artigo publicado na International Journal of Forecasting](https://doi.org/10.1016/j.ijforecast.2019.07.001)

**O que a fonte comprova:** o DeepAR produz previsões probabilísticas por meio
de uma rede recorrente autorregressiva treinada sobre várias séries temporais
relacionadas.

**Avaliação: ✅ direto.** A descrição no artigo MCSM é compatível com a fonte.

## 9. Sengupta et al. (2018) — natureza dos dados da NSRDB

**Onde aparece no artigo:** introdução, método e limitações, para explicar que
a NSRDB fornece uma referência modelada e não uma medição feita nas fábricas.

**Fontes para leitura:**

- [Registro e texto no repositório oficial do Departamento de Energia dos EUA](https://www.osti.gov/pages/biblio/1490905)
- [DOI do artigo](https://doi.org/10.1016/j.rser.2018.03.003)

**O que a fonte comprova:** descreve a NSRDB moderna e a obtenção de irradiância
a partir de imagens de satélite, propriedades de nuvens, dados meteorológicos e
modelos físicos.

**Avaliação: ✅ direto, com uma nuance.** Os valores usados neste projeto são
estimativas derivadas de satélite e modelos, e não leituras de um piranômetro
instalado em cada fábrica. Medições de solo podem ser utilizadas para validar a
base; isso não transforma os pontos extraídos da NSRDB em medições locais de
solo. A redação atual preserva essa diferença.

## 10. Voyant et al. (2017) — previsão de irradiância e comparabilidade

**Onde aparece no artigo:** importância da previsão, efeito de horizonte e
dados disponíveis e dificuldade de comparar modelos.

**Fontes para leitura:**

- [Página oficial e resumo na Renewable Energy](https://www.sciencedirect.com/science/article/pii/S0960148116311648)
- [DOI do artigo](https://doi.org/10.1016/j.renene.2016.12.095)

**O que a fonte comprova:** revisa métodos de aprendizado de máquina para
previsão de irradiância e afirma que a comparação de desempenho é dificultada
pelas diferenças de base de dados, passo temporal, horizonte, configuração e
métricas.

**Avaliação: ✅ direto.** É uma fonte apropriada para a afirmação feita na
introdução e trata diretamente de irradiância solar.

## 11. Voyant et al. (2022) — referências simples e benchmark

**Onde aparece no artigo:** justificativa para comparar modelos aprendidos com
referências sazonais simples.

**Fontes para leitura:**

- [Página e texto aberto no arXiv](https://arxiv.org/abs/2203.14959)
- [PDF aberto](https://arxiv.org/pdf/2203.14959)
- [DOI do artigo publicado](https://doi.org/10.1016/j.renene.2022.04.065)

**O que a fonte comprova:** modelos avançados devem ser comparados com métodos
de referência ingênuos; a referência adequada depende de características como
sazonalidade e do horizonte de previsão; e o benchmark deve ser justo.

**Avaliação: ✅ direto para o uso de referências simples; ⚠️ parcial para a
frase inteira.** A obrigação de usar exatamente o mesmo corte temporal para
todos os modelos é uma decisão correta do protocolo deste estudo, mas não é a
afirmação central dessa referência. A citação sustenta a comparação justa e a
escolha de referências, não cada detalhe operacional do corte temporal.

## Afirmações do artigo que não vêm de referências externas

Os itens abaixo não podem ser confirmados lendo os onze artigos, pois são
resultados ou decisões deste projeto. Eles devem ser auditados nos arquivos
locais:

- **Correção dos embeddings do DeepNPTS:**
  [`../../codigo_fonte/redes_deepnpts_registradas.py`](../../codigo_fonte/redes_deepnpts_registradas.py),
  [`../../codigo_fonte/modelos_globais_gluonts.py`](../../codigo_fonte/modelos_globais_gluonts.py)
  e
  [`../../testes/test_modelos_gluonts.py`](../../testes/test_modelos_gluonts.py).
  O teste relevante confirma que os embeddings entram no `state_dict` e são
  restaurados. Essa é evidência de software do projeto, não uma conclusão do
  artigo de Rangapuram.
- **Versões, sementes, hiperparâmetros, quantização e ambiente:**
  [`../../resultados/avaliacao_mensal_canonica/manifesto_execucao.json`](../../resultados/avaliacao_mensal_canonica/manifesto_execucao.json).
- **MAE, RMSE, R², nRMSE e ordenação dos modelos:**
  [`../../resultados/avaliacao_mensal_canonica/metricas_medias_modelos.csv`](../../resultados/avaliacao_mensal_canonica/metricas_medias_modelos.csv).
- **CRPS, cobertura e largura dos intervalos:**
  [`../../resultados/avaliacao_mensal_canonica/metricas_probabilisticas_medias.csv`](../../resultados/avaliacao_mensal_canonica/metricas_probabilisticas_medias.csv).
- **Resultados por localidade:**
  [`../../resultados/avaliacao_mensal_canonica/metricas_por_localidade.csv`](../../resultados/avaliacao_mensal_canonica/metricas_por_localidade.csv)
  e
  [`../../resultados/avaliacao_mensal_canonica/metricas_probabilisticas_por_localidade.csv`](../../resultados/avaliacao_mensal_canonica/metricas_probabilisticas_por_localidade.csv).
- **Origem e metadados dos arquivos da NSRDB:**
  [`../../dados/brutos/localidades_ev/manifesto_nsrdb.csv`](../../dados/brutos/localidades_ev/manifesto_nsrdb.csv)
  e
  [`../../dados/brutos/localidades_ev/README.md`](../../dados/brutos/localidades_ev/README.md).

## O que deve ser ajustado antes da submissão

1. Na frase sobre a “implementação oficial do DeepNPTS disponível no
   GluonTS”, citar também Rangapuram et al. (2023) e, se as regras do evento
   permitirem referência de software, incluir a documentação ou o repositório
   oficial da versão 0.16.2.
2. Separar a explicação de MAE/MSE/RMSE daquela de R²/nRMSE, evitando atribuir
   todas as definições a Hyndman e Koehler (2006).
3. Acrescentar capítulo ou página de Duffie e Beckman (2013) usada para a
   definição de GHI.

Esses três ajustes melhoram a precisão das citações; eles não alteram os
resultados numéricos do experimento.
