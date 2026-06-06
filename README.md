# TCC - Previsão Diária de GHI com Machine Learning

Este repositório contém um pipeline completo para previsão diária de **GHI** (*Global Horizontal Irradiance*, ou Irradiância Solar Global Horizontal) usando modelos de Machine Learning.

O projeto foi organizado para servir como base do Trabalho de Conclusão de Curso (TCC), com código-fonte modular, notebooks explicativos, dados de entrada, relatórios HTML e testes automatizados.

## Objetivo do Projeto

O objetivo é prever o valor diário de GHI do dia seguinte a partir de uma série temporal histórica. Para isso, o pipeline:

1. Lê dados brutos de GHI em CSV, Excel ou Parquet.
2. Limpa e padroniza a série temporal.
3. Agrega os dados para resolução diária, quando necessário.
4. Quantiza os valores de GHI em 128 níveis.
5. Normaliza os valores para o intervalo de 0 a 1.
6. Cria features temporais, como lags e médias móveis.
7. Divide a base em treino e teste respeitando a ordem cronológica.
8. Treina os modelos XGBoost e MLP.
9. Calcula métricas de avaliação.
10. Salva previsões, modelos treinados, gráficos e relatórios.

## Estrutura Geral

```text
.
|-- README.md
|-- requirements.txt
|-- .gitignore
|-- .env
|-- treinamento_principal.py
|-- treinar_todas_localidades.py
|-- codigo_fonte/
|   |-- __init__.py
|   |-- configuracao.py
|   |-- utilitarios.py
|   |-- preprocessamento.py
|   |-- features.py
|   |-- modelos.py
|   |-- avaliacao.py
|   +-- graficos.py
|-- dados/
|   |-- brutos/
|   |   +-- localidades_ev/
|   +-- processados/
|-- cadernos_jupyter/
|-- relatorios/
|-- testes/
+-- tools/
```

## Explicação dos Arquivos da Raiz

### `README.md`

Arquivo de documentação principal do projeto. Explica a finalidade do repositório, a estrutura de pastas, como instalar dependências, como executar scripts, como rodar testes e qual é o papel de cada arquivo.

### `requirements.txt`

Lista as bibliotecas Python necessárias para executar o projeto:

- `pandas`: manipulação de tabelas e séries temporais.
- `numpy`: cálculos numéricos.
- `pvlib`: coleta e tratamento de dados solares, incluindo integracao com NLR/NSRDB.
- `python-dotenv`: leitura das variáveis do arquivo `.env`.
- `openpyxl`: leitura de arquivos Excel.
- `pytest`: execução dos testes automatizados.
- `matplotlib`: geração de gráficos.
- `seaborn`: estilo visual complementar para gráficos.
- `scikit-learn`: modelo MLP e métricas auxiliares.
- `xgboost`: modelo XGBoost.
- `joblib`: salvamento dos modelos treinados.
- `jupyter`: abertura e execução dos notebooks.
- `nbconvert`: exportação dos notebooks para HTML.
- `pillow`: suporte a imagens em alguns gráficos dos notebooks.
- `cartopy`: geração de mapas nos notebooks.

### `.gitignore`

Define arquivos e pastas que não devem ser versionados, como:

- `.env`, por conter credenciais.
- `__pycache__/` e arquivos `.pyc`.
- ambientes virtuais como `venv/` e `.venv/`.
- caches do Jupyter e pytest.
- modelos treinados e resultados gerados automaticamente.

### `.env`

Arquivo local para credenciais da API NLR/NSRDB. Os nomes historicos das
variaveis (`NREL_API_KEY` e `NREL_EMAIL`) foram mantidos por compatibilidade.
O arquivo não deve ser enviado para repositórios públicos.

Formato esperado:

```env
NREL_API_KEY=sua_chave
NREL_EMAIL=seu_email
```

Para o treinamento das 10 localidades, os CSVs locais em
`dados/brutos/localidades_ev/` só são aceitos quando têm cobertura diária
completa, unidade `W/m2` e metadados compatíveis com a coleta NLR/NSRDB.
Arquivos sintéticos são rejeitados e precisam ser baixados novamente pela API.

O recorte oficial atual é 2019-2024. Em 6 de junho de 2026, o produto GOES
Aggregated PSM v4 ainda disponibiliza anos históricos somente até 2024; 2025
não é preenchido artificialmente.

### `treinamento_principal.py`

Script principal para executar o pipeline em uma única série de GHI.

Ele faz:

- criação das pastas padrão;
- carregamento de um arquivo informado por `--data-path` ou busca automática de um arquivo de dados;
- preparação da base de modelagem;
- divisão temporal treino/teste;
- treinamento de XGBoost e MLP;
- cálculo das métricas;
- salvamento dos modelos, previsões, métricas e gráficos.

Exemplo:

```bash
python treinamento_principal.py --data-path dados/brutos/localidades_ev/byd_camacari.csv
```

Esse comando exige que o CSV em `dados/brutos/localidades_ev/` tenha proveniência NLR/NSRDB validável. Se o arquivo for antigo/sintético, execute antes `python treinar_todas_localidades.py --somente-download --forcar-download`.

Também é possível executar sem informar arquivo:

```bash
python treinamento_principal.py
```

Nesse caso, o script procura automaticamente arquivos tabulares nas pastas de dados.

### `treinar_todas_localidades.py`

Script para treinar e avaliar os modelos nas 10 localidades de fábricas de veículos elétricos.

Ele usa a lista interna `LOCALIDADES`, que contém:

- nome da localidade;
- país;
- latitude;
- longitude.

Para cada localidade, o script:

- procura o CSV correspondente em `dados/brutos/localidades_ev/`;
- usa o cadastro auditavel de coordenadas e fontes em `codigo_fonte/localidades_ev.py`;
- valida se o CSV local foi coletado da API NLR/NSRDB;
- se o arquivo não existir ou falhar na validação, tenta coletar dados da API NLR/NSRDB;
- se a API falhar, interrompe a execução sem gerar dados sintéticos;
- prepara a série temporal;
- treina XGBoost e MLP;
- salva modelos por localidade;
- salva previsões;
- gera gráficos;
- cria tabelas comparativas finais.

O notebook `02_resultados_todas_localidades.ipynb` confere ainda os hashes
SHA-256 do manifesto, as fontes oficiais das fabricas, os elementos do
OpenStreetMap usados nas coordenadas e a distancia ate o ponto da grade NSRDB
antes de liberar os resultados de Machine Learning.

Exemplo:

```bash
python treinar_todas_localidades.py
```

Para validar apenas a origem dos CSVs locais:

```bash
python treinar_todas_localidades.py --validar-dados
```

Para baixar novamente todos os CSVs pela API, ignorando os arquivos locais:

```bash
python treinar_todas_localidades.py --somente-download --forcar-download
```

## Pasta `codigo_fonte/`

Contém os módulos Python reutilizados pelos scripts e notebooks. A ideia é deixar a lógica principal fora dos notebooks, de forma organizada e testável.

### `codigo_fonte/__init__.py`

Marca `codigo_fonte` como um pacote Python. Isso permite importar módulos com:

```python
from codigo_fonte.preprocessamento import preparar_serie_temporal
```

### `codigo_fonte/configuracao.py`

Centraliza os caminhos padrão do projeto.

Define constantes como:

- `PROJECT_ROOT`
- `PASTA_DADOS`
- `PASTA_DADOS_BRUTOS`
- `PASTA_DADOS_PROCESSADOS`
- `PASTA_RESULTADOS`
- `PASTA_FIGURAS`
- `PASTA_METRICAS`
- `PASTA_MODELOS`
- `PASTA_RELATORIOS`
- `PASTA_TESTES`
- `PASTA_TOOLS`

Também fornece:

- `criar_pastas()`: cria as pastas necessárias para execução do pipeline.
- `garantir_diretorios()`: alias mantido para compatibilidade com versões anteriores.

### `codigo_fonte/utilitarios.py`

Contém funções auxiliares de uso geral.

Função principal:

- `localizar_arquivo_dados()`: procura automaticamente arquivos `.csv`, `.xlsx`, `.xls` ou `.parquet` nas pastas de dados. A busca é recursiva, então também encontra arquivos dentro de `dados/brutos/localidades_ev/`.

### `codigo_fonte/preprocessamento.py`

Responsável por leitura, limpeza, coleta, quantização e normalização da série de GHI.

Principais componentes:

- `PreparationResult`: dataclass que guarda o resultado da preparação da série.
- `detectar_colunas(df)`: identifica automaticamente a coluna de data e a coluna de GHI.
- `limpar_serie_ghi(df)`: padroniza a base para as colunas `data` e `ghi`.
- `garantir_resolucao_diaria(df)`: agrega dados para frequência diária usando média.
- `encontrar_arquivo_ghi()`: procura um arquivo de GHI no projeto.
- `coletar_ghi_nrel(...)`: coleta dados da API NSRDB/NLR usando `pvlib`.
- `carregar_serie_ghi(data_path=None)`: carrega dados locais ou tenta usar a API.
- `quantizar_ghi(...)`: transforma valores contínuos de GHI em níveis discretos de 0 a 127.
- `normalizar_minmax(...)`: normaliza valores para o intervalo `[0, 1]`.
- `preparar_serie_temporal(...)`: executa o pré-processamento completo e cria a base final de modelagem.

### `codigo_fonte/features.py`

Cria as variáveis de entrada usadas pelos modelos.

Funções:

- `criar_features_temporais(...)`: cria lags, médias móveis e alvo do dia seguinte.
- `dividir_treino_teste_temporal(...)`: separa treino e teste mantendo a ordem temporal.

Features criadas:

- `ghi_t-1`
- `ghi_t-2`
- `ghi_t-3`
- `ghi_t-7`
- `ghi_media_movel_3d`
- `ghi_media_movel_7d`
- `ghi_media_movel_30d`
- `ghi_alvo`

### `codigo_fonte/modelos.py`

Contém as funções de treinamento e salvamento dos modelos.

Funções:

- `treinar_xgboost(X_train, y_train)`: treina um `XGBRegressor`.
- `treinar_mlp(X_train, y_train)`: treina um `MLPRegressor`.
- `salvar_modelo(model, output_path)`: salva o modelo treinado em `.joblib`.

Modelos usados:

- **XGBoost**: modelo baseado em árvores de decisão com gradient boosting.
- **MLP**: rede neural artificial do tipo *Multi-Layer Perceptron*.

### `codigo_fonte/avaliacao.py`

Calcula métricas e salva previsões.

Funções:

- `calcular_metricas(y_true, y_pred, modelo)`: calcula MAE, MSE, RMSE e R².
- `salvar_metricas(metricas, output_path)`: salva uma tabela CSV com as métricas.
- `salvar_previsoes(datas, y_true, predicoes, output_dir)`: salva CSVs de previsões por modelo e uma tabela comparativa.

Métricas:

- **MAE**: erro absoluto médio.
- **MSE**: erro quadrático médio.
- **RMSE**: raiz do erro quadrático médio.
- **R²**: coeficiente de determinação.

### `codigo_fonte/graficos.py`

Gera gráficos de avaliação dos modelos.

Funções:

- `gerar_grafico_temporal(...)`: compara valores reais e previstos ao longo do tempo.
- `gerar_grafico_real_vs_previsto(...)`: gera gráfico temporal para um modelo específico.
- `gerar_grafico_dispersao(...)`: gera dispersão entre real e previsto.
- `salvar_graficos(...)`: salva todos os gráficos obrigatórios.

## Pasta `dados/`

Armazena dados brutos e dados processados.

### `dados/brutos/localidades_ev/`

Contém os CSVs de entrada das localidades de fábricas de veículos elétricos.

Arquivos atuais:

- `byd_camacari.csv`
- `tesla_gigafactory_nevada.csv`
- `tesla_gigafactory_texas.csv`
- `hyundai_metaplant_georgia.csv`
- `rivian_normal.csv`
- `tesla_fremont_factory.csv`
- `lucid_amp_1_casa_grande.csv`
- `gm_factory_zero.csv`
- `ford_rouge_electric_vehicle_center.csv`
- `bmw_san_luis_potosi.csv`

Formato validado para as 10 localidades:

```csv
data,ghi,localidade,pais,lat,lon,ano,fonte_dados,produto_dados,versao_dados,endpoint_api,intervalo_minutos,agregacao,unidade_ghi,lat_grade_nsrdb,lon_grade_nsrdb
2019-01-01,304.98,BYD Camacari,Brasil,-12.6977,-38.324,2019,NLR/NSRDB,GOES Aggregated PSM v4,4.1.2,https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv,60,media_diaria,W/m2,-12.7,-38.32
```

Colunas:

- `data`: data da observação.
- `ghi`: valor diário de GHI.
- `localidade`: nome da fábrica/localidade definida no script.
- `pais`: país da localidade.
- `lat`: latitude.
- `lon`: longitude.
- `ano`: ano da observação.
- `fonte_dados`: origem dos dados. Para o pipeline das 10 localidades, deve ser `NLR/NSRDB`.
- `produto_dados`, `versao_dados` e `endpoint_api`: identificam o produto e a consulta.
- `intervalo_minutos`, `agregacao` e `unidade_ghi`: documentam como o GHI diario foi calculado.
- `lat_grade_nsrdb` e `lon_grade_nsrdb`: ponto da grade de satelite retornado pela API.

### `dados/processados/`

Guarda bases geradas após o pré-processamento.

Arquivo principal:

- `ghi_features.csv`

Esse arquivo contém a base final com features temporais, valores normalizados e alvo de previsão.

Principais colunas:

- `data`
- `ghi`
- `ghi_quantizado`
- `ghi_normalizado`
- `ghi_t-1`
- `ghi_t-2`
- `ghi_t-3`
- `ghi_t-7`
- `ghi_media_movel_3d`
- `ghi_media_movel_7d`
- `ghi_media_movel_30d`
- `data_alvo`
- `ghi_alvo`
- `ghi_alvo_quantizado`
- `ghi_alvo_original`

## Pasta `cadernos_jupyter/`

Contém os notebooks usados para explicação, análise e apresentação dos resultados.

### `01_explicacao_teorica_pipeline.ipynb`

Notebook didático. Explica teoricamente o pipeline:

- o que é GHI;
- como os dados são coletados;
- como funciona a limpeza;
- por que usar quantização;
- por que usar normalização;
- como são criadas as features temporais;
- por que a divisão treino/teste deve ser cronológica;
- como funcionam XGBoost e MLP;
- como interpretar as métricas.

### `02_resultados_todas_localidades.ipynb`

Notebook de análise dos resultados das 10 localidades.

Ele apresenta:

- leitura das métricas gerais;
- tabela resumo por localidade;
- comparação entre XGBoost e MLP;
- gráficos de R², RMSE e MAE;
- visualização por localidade;
- análise final dos modelos.

## Pasta `relatorios/`

Contém versões HTML exportadas dos notebooks.

Arquivos:

- `01_explicacao_teorica_pipeline.html`
- `02_resultados_todas_localidades.html`

Esses arquivos são úteis para abrir os resultados no navegador sem precisar executar o Jupyter.

Para gerar novamente:

```bash
jupyter nbconvert --to html cadernos_jupyter/01_explicacao_teorica_pipeline.ipynb --output-dir relatorios
jupyter nbconvert --to html cadernos_jupyter/02_resultados_todas_localidades.ipynb --output-dir relatorios
```

## Pasta `testes/`

Contém testes automatizados do projeto.

### `testes/test_preprocessamento.py`

Testa funções importantes do pré-processamento:

- se a quantização gera níveis esperados;
- se a normalização fica entre 0 e 1;
- se a preparação da série cria as features temporais corretamente;
- se a divisão treino/teste fica válida.

Para executar:

```bash
python -m pytest testes -q
```

## Pasta `tools/`

Guarda ferramentas auxiliares de manutenção do projeto.

### `tools/README.md`

Explica o objetivo da pasta `tools`.

### `tools/verificar_estrutura.ps1`

Script PowerShell que confere se os principais arquivos e pastas existem.

Uso no Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\verificar_estrutura.ps1
```

Se tudo estiver correto, a saída será:

```text
Estrutura principal OK.
```

## Pasta `resultados/`

Essa pasta é criada ou atualizada durante a execução dos scripts. Ela pode não existir em uma cópia inicial do projeto.

Estrutura esperada:

```text
resultados/
|-- figuras/
|-- metricas/
|-- modelos/
+-- todas_localidades/
    |-- figuras/
    |-- previsoes/
    |-- metricas_geral.csv
    +-- resumo_localidades.csv
```

Arquivos gerados:

- `resultados/metricas/metricas_modelos.csv`: métricas para uma execução única.
- `resultados/metricas/previsoes_modelos.csv`: previsões para uma execução única.
- `resultados/modelos/xgboost_ghi.joblib`: modelo XGBoost treinado.
- `resultados/modelos/mlp_ghi.joblib`: modelo MLP treinado.
- `resultados/figuras/*.png`: gráficos da execução única.
- `resultados/todas_localidades/metricas_geral.csv`: métricas de todos os modelos em todas as localidades.
- `resultados/todas_localidades/resumo_localidades.csv`: resumo comparativo por localidade.
- `resultados/todas_localidades/previsoes/`: previsões separadas por localidade.
- `resultados/todas_localidades/figuras/`: gráficos separados por localidade.

## Como Instalar

Pré-requisitos:

- Python 3.8 ou superior.
- `pip`.
- Ambiente virtual recomendado.

No Windows:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Se `cartopy` falhar na instalação, o pipeline principal ainda pode ser usado. O `cartopy` é necessário principalmente para mapas no notebook de resultados.

## Como Executar

### Executar uma localidade

```bash
python treinamento_principal.py --data-path dados/brutos/localidades_ev/byd_camacari.csv
```

Use esse caminho somente depois de validar ou baixar novamente os CSVs NLR/NSRDB.

### Executar com busca automática de dados

```bash
python treinamento_principal.py
```

### Executar todas as localidades

```bash
python treinar_todas_localidades.py
```

### Validar origem dos CSVs das localidades

```bash
python treinar_todas_localidades.py --validar-dados
```

### Baixar novamente os dados NLR/NSRDB

```bash
python treinar_todas_localidades.py --somente-download --forcar-download
```

### Executar sem gerar gráficos

```bash
python treinamento_principal.py --data-path dados/brutos/localidades_ev/byd_camacari.csv --sem-graficos
```

Também aqui, o CSV precisa passar na validação de proveniência NLR/NSRDB.

## Fluxo Técnico do Pipeline

### 1. Entrada

O pipeline recebe uma tabela com pelo menos:

- uma coluna de data;
- uma coluna numérica de GHI.

Nomes aceitos para data incluem:

- `data`
- `date`
- `datetime`
- `timestamp`
- `time`
- `ds`

Nomes aceitos para GHI incluem:

- `ghi`
- `global_horizontal_irradiance`
- `irradiancia_global_horizontal`
- nomes que contenham `ghi`.

### 2. Limpeza

O código:

- converte datas para `datetime`;
- converte GHI para número;
- remove datas inválidas;
- remove GHI ausente;
- remove GHI negativo;
- ordena a série temporal;
- remove duplicatas;
- agrega para frequência diária.

### 3. Quantização

Os valores contínuos de GHI são convertidos para 128 níveis:

```text
0, 1, 2, ..., 127
```

Essa etapa reduz ruído e transforma a série em uma escala discreta controlada.

### 4. Normalização

Depois da quantização, os valores são normalizados para:

```text
[0, 1]
```

Essa etapa é importante principalmente para o modelo MLP.

### 5. Features Temporais

O modelo usa valores anteriores para prever o próximo dia:

```text
ghi_t-1
ghi_t-2
ghi_t-3
ghi_t-7
```

Também usa médias móveis:

```text
ghi_media_movel_3d
ghi_media_movel_7d
ghi_media_movel_30d
```

### 6. Alvo

O alvo é o GHI normalizado do dia seguinte:

```text
ghi_alvo = GHI no dia t+1
```

### 7. Treino e Teste

A divisão é cronológica:

```text
80% inicial -> treino
20% final   -> teste
```

A série temporal não é embaralhada, porque isso causaria vazamento de informação do futuro.

### 8. Modelos

São treinados dois modelos:

- **XGBoost**, bom para dados tabulares e relações não-lineares.
- **MLP**, uma rede neural simples para regressão.

### 9. Avaliação

As previsões são comparadas com os valores reais usando:

- MAE;
- MSE;
- RMSE;
- R².

## Localidades Usadas

O script `treinar_todas_localidades.py` trabalha com 10 localidades:

| # | Localidade | País |
|---|------------|------|
| 1 | BYD Camacari | Brasil |
| 2 | Tesla Gigafactory Nevada | EUA |
| 3 | Tesla Gigafactory Texas | EUA |
| 4 | Hyundai Metaplant Georgia | EUA |
| 5 | Rivian Normal | EUA |
| 6 | Tesla Fremont Factory | EUA |
| 7 | Lucid AMP 1 Casa Grande | EUA |
| 8 | GM Factory Zero | EUA |
| 9 | Ford Rouge Electric Vehicle Center | EUA |
| 10 | BMW San Luis Potosi | México |

## Comandos Úteis

Verificar estrutura:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\verificar_estrutura.ps1
```

Rodar testes:

```bash
python -m pytest testes -q
```

Treinar uma localidade:

```bash
python treinamento_principal.py --data-path dados/brutos/localidades_ev/byd_camacari.csv
```

O CSV dessa pasta precisa ter `fonte_dados=NLR/NSRDB`.

Treinar todas as localidades:

```bash
python treinar_todas_localidades.py
```

Abrir Jupyter:

```bash
jupyter notebook
```

Exportar notebooks para HTML:

```bash
jupyter nbconvert --to html cadernos_jupyter/01_explicacao_teorica_pipeline.ipynb --output-dir relatorios
jupyter nbconvert --to html cadernos_jupyter/02_resultados_todas_localidades.ipynb --output-dir relatorios
```

## Observações Importantes

- O arquivo `.env` contém credenciais e não deve ser compartilhado publicamente.
- Os arquivos em `resultados/` são saídas geradas pelos scripts.
- Os notebooks em `cadernos_jupyter/` são usados para explicação e análise.
- Os relatórios HTML em `relatorios/` são versões exportadas dos notebooks e devem ser regenerados após uma nova coleta NLR/NSRDB.
- A pasta `dados/brutos/localidades_ev/` contém os dados de entrada usados no treinamento das 10 localidades; para esse fluxo, cada CSV deve passar em `python treinar_todas_localidades.py --validar-dados`.
- A pasta `dados/processados/` contém bases intermediárias/finais geradas pelo pré-processamento.

## Problemas Comuns

### `python` não é reconhecido

Instale o Python pelo site oficial ou ajuste o PATH do Windows.

Depois confirme:

```bash
python --version
pip --version
```

### `cartopy` falha ao instalar

O pipeline principal pode funcionar sem o mapa. O `cartopy` é mais importante para visualizações geográficas nos notebooks.

### Arquivo de dados não encontrado

Confira se os CSVs estão em:

```text
dados/brutos/localidades_ev/
```

Ou execute informando explicitamente o caminho:

```bash
python treinamento_principal.py --data-path caminho/do/arquivo.csv
```

### Relatório HTML está desatualizado

Exporte novamente o notebook:

```bash
jupyter nbconvert --to html cadernos_jupyter/02_resultados_todas_localidades.ipynb --output-dir relatorios
```

## Resumo Final

Este projeto está organizado em quatro partes principais:

- **Código-fonte** em `codigo_fonte/`, com a lógica do pipeline.
- **Dados** em `dados/`, com entradas brutas e bases processadas.
- **Análises e relatórios** em `cadernos_jupyter/` e `relatorios/`.
- **Execução e validação** por meio dos scripts da raiz, testes e ferramentas auxiliares.

Com isso, o projeto fica pronto para treinamento, avaliação, apresentação e manutenção.
