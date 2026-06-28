# TCC - Previsão Diária de GHI com Machine Learning

Pipeline completo para prever a **Irradiância Global Horizontal (GHI) média do
dia seguinte** em dez localidades associadas a fábricas de veículos elétricos.

O projeto usa dados oficiais do **NLR/NSRDB**, transforma a série histórica em
features temporais e compara dois modelos de regressão:

- XGBoost;
- rede neural MLP.

Além do código de treinamento, o repositório contém dados auditáveis, testes,
notebooks explicativos, resultados, gráficos e relatórios HTML.

## Visão rápida

```text
Dados horários NLR/NSRDB
        ↓
Média diária de GHI
        ↓
Validação e limpeza
        ↓
Quantização em 128 níveis
        ↓
Normalização para [0, 1]
        ↓
Lags + médias móveis
        ↓
Previsão do dia seguinte
        ↓
Treino cronológico de XGBoost e MLP
        ↓
Métricas, previsões, modelos e gráficos
```

| Item | Configuração atual |
|---|---|
| Problema | regressão de série temporal |
| Variável prevista | GHI médio diário do próximo dia |
| Horizonte | 1 dia à frente |
| Fonte | NLR/NSRDB, GOES Aggregated PSM v4 |
| Período | 1º de janeiro de 2019 a 31 de dezembro de 2024 |
| Localidades | 10 |
| Dados brutos | 2.192 dias por localidade |
| Base de modelagem | 2.162 exemplos por localidade |
| Features | 4 lags e 3 médias móveis |
| Divisão | 80% treino e 20% teste, sem embaralhamento |
| Modelos | XGBoost e MLP |
| Métricas | MAE, MSE, RMSE, R², nRMSE e COV horário |

## Sumário

- [Objetivo e escopo](#objetivo-e-escopo)
- [Como executar rapidamente](#como-executar-rapidamente)
- [Dados e localidades](#dados-e-localidades)
- [Como as médias funcionam](#como-as-médias-funcionam)
- [Pipeline técnico](#pipeline-técnico)
- [Features e alvo](#features-e-alvo)
- [Treino, modelos e avaliação](#treino-modelos-e-avaliação)
- [Resultados atuais](#resultados-atuais)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Arquivos gerados](#arquivos-gerados)
- [Testes e relatórios](#testes-e-relatórios)
- [Limitações](#limitações)
- [Problemas comuns](#problemas-comuns)

## Objetivo e escopo

O objetivo é estimar o GHI do dia `t+1` usando somente informações disponíveis
até o dia `t`.

```text
Entradas: histórico diário até hoje
Saída:    GHI de amanhã
```

O projeto prevê **irradiância solar**, não:

- produção elétrica de uma fábrica;
- consumo de energia;
- geração de um sistema fotovoltaico;
- condições meteorológicas completas.

Para converter irradiância em geração fotovoltaica seriam necessários dados
adicionais, como área e eficiência dos módulos, inclinação, temperatura e
perdas do sistema.

As fábricas são usadas como pontos geográficos de análise. O trabalho não
afirma que elas causam alterações na irradiância.

## Como executar rapidamente

### 1. Preparar o ambiente

Pré-requisitos:

- Python 3.10 ou superior;
- `pip`;
- ambiente virtual recomendado.

Linux ou macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Validar os CSVs oficiais

```bash
python treinar_todas_localidades.py --validar-dados
```

Essa validação verifica origem, cobertura, unidade, coordenadas e hashes
SHA-256 antes do treinamento.

### 3. Treinar as dez localidades

```bash
python treinar_todas_localidades.py
```

### 4. Consultar os resultados

Os principais arquivos são:

```text
resultados/todas_localidades/metricas_geral.csv
resultados/todas_localidades/resumo_localidades.csv
relatorios/02_resultados_todas_localidades.html
```

### Treinar somente uma localidade

```bash
python treinamento_principal.py \
  --data-path dados/brutos/localidades_ev/byd_camacari.csv
```

Sem gerar gráficos:

```bash
python treinamento_principal.py \
  --data-path dados/brutos/localidades_ev/byd_camacari.csv \
  --sem-graficos
```

Sem `--data-path`, o script procura automaticamente um CSV, Excel ou Parquet
nas pastas de dados:

```bash
python treinamento_principal.py
```

Para evitar ambiguidades, recomenda-se informar explicitamente o arquivo.

## Dados e localidades

### Fonte dos dados

Os dados são coletados pelo `pvlib` a partir do:

```text
NLR/NSRDB
Produto: GOES Aggregated PSM v4
Variável: GHI
Intervalo solicitado: 60 minutos
Unidade retornada: W/m²
```

O recorte oficial é 2019–2024. O projeto não completa anos indisponíveis com
dados sintéticos.

### Localidades

| # | Localidade | País |
|---:|---|---|
| 1 | BYD Camaçari | Brasil |
| 2 | Tesla Gigafactory Nevada | EUA |
| 3 | Tesla Gigafactory Texas | EUA |
| 4 | Hyundai Metaplant Georgia | EUA |
| 5 | Rivian Normal | EUA |
| 6 | Tesla Fremont Factory | EUA |
| 7 | Lucid AMP 1 Casa Grande | EUA |
| 8 | GM Factory Zero | EUA |
| 9 | Ford Rouge Electric Vehicle Center | EUA |
| 10 | BMW San Luis Potosí | México |

Cada localidade possui:

- um CSV bruto próprio;
- uma base processada própria;
- um XGBoost próprio;
- uma MLP própria;
- métricas, previsões e gráficos próprios.

Os dados das localidades não são misturados em um treinamento global.

### Cobertura

Cada CSV oficial possui uma linha para todos os dias entre 2019 e 2024:

```text
2019: 365 dias
2020: 366 dias
2021: 365 dias
2022: 365 dias
2023: 365 dias
2024: 366 dias
Total: 2.192 dias
```

### Proveniência e integridade

Os CSVs registram:

- localidade, país, endereço, latitude e longitude;
- fontes usadas para validar a fábrica e suas coordenadas;
- elemento OpenStreetMap;
- produto, versão e endpoint da API;
- intervalo, agregação e unidade;
- coordenadas e identificação do ponto da grade NSRDB;
- fuso, elevação e data de coleta.

O arquivo `dados/brutos/localidades_ev/manifesto_nsrdb.csv` guarda o hash
SHA-256 de cada CSV.

O validador rejeita, entre outros casos:

- metadados obrigatórios ausentes;
- fonte diferente de `NLR/NSRDB`;
- datas inválidas, duplicadas ou incompletas;
- GHI fora da faixa diária esperada de 0 a 500 W/m²;
- coordenadas incompatíveis com o cadastro;
- ponto NSRDB a mais de 5 km da fábrica;
- arquivo diferente do registrado no manifesto;
- indícios de dados sintéticos.

### Recoletar os dados

Crie um arquivo `.env` na raiz:

```env
NREL_API_KEY=sua_chave
NREL_EMAIL=seu_email
```

Depois execute:

```bash
python treinar_todas_localidades.py \
  --somente-download \
  --forcar-download
```

O `.env` contém credenciais e não deve ser versionado ou compartilhado.

## Como as médias funcionam

Existem três conceitos diferentes no projeto.

### Média diária

A API fornece uma observação de GHI a cada 60 minutos. O projeto calcula:

```text
GHI diário = média das observações horárias daquele dia
```

Essa operação gera a série usada pelos modelos.

A unidade continua sendo `W/m²`, pois é uma média de potência por área. Ela
não representa energia diária acumulada em `Wh/m²` ou `kWh/m²/dia`.

### Média mensal

O notebook de coleta agrupa os valores diários de cada mês:

```python
mensal = dados_diarios.resample("ME").mean()
```

A média mensal é usada **somente para visualização exploratória**. Ela não
entra no treinamento.

### Média móvel

As médias móveis são features dos modelos:

```text
média móvel de 3 dias
média móvel de 7 dias
média móvel de 30 dias
```

Para uma linha referente a 30 de janeiro:

```text
média 3d  = média de 28, 29 e 30 de janeiro
média 7d  = média dos últimos 7 dias até 30 de janeiro
média 30d = média dos últimos 30 dias até 30 de janeiro
```

No dia seguinte, a janela avança uma posição. Uma janela de 30 dias não é o
mesmo que um mês civil e pode atravessar a virada do mês.

| Média | Origem | Uso |
|---|---|---|
| diária | observações horárias | série principal |
| mensal | valores diários do mês | gráficos exploratórios |
| móvel | últimos 3, 7 ou 30 dias | feature dos modelos |

## Pipeline técnico

### 1. Entrada

O pipeline aceita CSV, Excel ou Parquet com:

- uma coluna de data;
- uma coluna numérica de GHI.

Nomes de data reconhecidos:

```text
data, date, datetime, timestamp, time, ds
```

Nomes de GHI reconhecidos incluem:

```text
ghi
global_horizontal_irradiance
irradiancia_global_horizontal
```

Também são aceitos nomes que contenham `ghi`.

### 2. Limpeza e padronização

A função `limpar_serie_ghi`:

1. detecta as colunas;
2. converte datas e valores numéricos;
3. remove registros inválidos ou ausentes;
4. remove GHI negativo;
5. ordena cronologicamente;
6. remove datas duplicadas;
7. agrega para frequência diária usando média.

Mesmo quando o CSV já é diário, essa etapa garante um contrato único para o
restante do pipeline.

### 3. Quantização

O GHI contínuo é convertido para 128 níveis inteiros:

```text
0, 1, 2, ..., 127
```

Conceitualmente:

```text
q = arredondar((x - mínimo) / (máximo - mínimo) × 127)
```

A quantização reduz pequenas variações, mas também perde parte da precisão
original. Ela é uma escolha metodológica, não uma exigência dos modelos.

### 4. Normalização

Os níveis quantizados são normalizados para `[0, 1]`:

```text
ghi_normalizado = ghi_quantizado / 127
```

Isso é especialmente importante para o treinamento da MLP.

Os limites da quantização são ajustados somente no trecho de treinamento. O
teste é transformado com os mesmos parâmetros, evitando que estatísticas
futuras definam a escala do passado.

### 5. Criação das features

São criadas quatro defasagens e três médias móveis sobre o GHI quantizado e
normalizado.

### 6. Criação do alvo

Para a linha do dia `t`:

```text
data_alvo = t+1
ghi_alvo  = GHI normalizado de t+1
```

Também são preservados o alvo quantizado e o valor original para auditoria.

### 7. Remoção de linhas incompletas

A janela de 30 dias precisa de histórico completo, e a última data não possui
um dia seguinte dentro da base:

```text
Base diária original:             2.192 linhas
Perda pela janela inicial de 30d:    29 linhas
Perda pela ausência do alvo t+1:      1 linha
Base final:                       2.162 linhas
```

## Features e alvo

### Entradas dos modelos

| Feature | Significado em relação ao alvo do dia `t+1` |
|---|---|
| `ghi_t-1` | GHI do dia `t` |
| `ghi_t-2` | GHI do dia `t-1` |
| `ghi_t-3` | GHI do dia `t-2` |
| `ghi_t-7` | GHI do dia `t-6` |
| `ghi_media_movel_3d` | média de `t-2` até `t` |
| `ghi_media_movel_7d` | média de `t-6` até `t` |
| `ghi_media_movel_30d` | média de `t-29` até `t` |

O nome `ghi_t-1` é contado em relação ao **alvo**. Como a linha do dia `t`
prevê `t+1`, `ghi_t-1` contém o próprio valor observado no dia `t`.

### Exemplo de alinhamento

Para uma linha em 3 de janeiro:

```text
ghi_t-1   = GHI de 03/01
ghi_t-2   = GHI de 02/01
ghi_t-3   = GHI de 01/01
média 3d  = média de 01/01 a 03/01
alvo      = GHI de 04/01
```

As features usam somente informações disponíveis até a data da linha. O alvo
fica no futuro imediato.

### Prevenção de vazamento temporal

O projeto evita vazamento porque:

- as janelas terminam no dia `t`;
- o alvo está em `t+1`;
- a escala é ajustada no treinamento;
- a divisão preserva a ordem cronológica;
- existe teste automatizado para o alinhamento.

## Treino, modelos e avaliação

### Divisão temporal

Os 2.162 exemplos são divididos sem embaralhamento:

```text
Treino: 1.729 exemplos
Teste:    433 exemplos
```

Período dos alvos:

```text
Treino: 31/01/2019 a 25/10/2023
Teste:  26/10/2023 a 31/12/2024
```

Essa estratégia simula o uso real: aprender com o passado e avaliar em dados
posteriores.

### XGBoost

Configuração:

```python
XGBRegressor(
    n_estimators=300,
    max_depth=3,
    learning_rate=0.05,
    subsample=0.9,
    colsample_bytree=0.9,
    objective="reg:squarederror",
    random_state=42,
    n_jobs=-1,
)
```

É adequado a dados tabulares e captura relações não lineares por meio de um
conjunto sequencial de árvores.

### MLP

Arquitetura:

```text
7 entradas → 64 neurônios → 32 neurônios → 1 saída
```

Configuração principal:

```python
MLPRegressor(
    hidden_layer_sizes=(64, 32),
    activation="relu",
    solver="adam",
    max_iter=1000,
    learning_rate_init=0.001,
    random_state=42,
)
```

As previsões dos dois modelos são limitadas ao intervalo `[0, 1]`.

### Métricas

| Métrica | Interpretação | Melhor valor |
|---|---|---|
| MAE | média do erro absoluto | menor |
| MSE | média do erro ao quadrado | menor |
| RMSE | raiz do MSE, penaliza erros grandes | menor |
| R² | proporção da variação explicada | maior |
| nRMSE | RMSE dividido pela média do GHI real | menor |
| COV horário | `sigma / média` do GHI horário | contextual |

As métricas são salvas em duas escalas. A versão normalizada preserva a leitura
interna do modelo, enquanto a versão `wm2` calcula os erros depois de converter
real e previsto para a escala física aproximada em `W/m²`.

A desnormalização depende da faixa de treinamento da localidade:

```text
GHI em W/m² ≈ GHI normalizado × (máximo_treino - mínimo_treino) + mínimo_treino
nRMSE = RMSE_wm2 / média(GHI real em W/m²)
COV horário = sigma(GHI horário) / média(GHI horário)
```

O arquivo `resultados/todas_localidades/estatisticas_horarias.csv` registra
média, sigma e COV dos dados horários quando a localidade foi coletada com essa
granularidade. CSVs antigos que já estão agregados por dia ficam marcados como
`indisponivel_csv_diario`, pois não é possível reconstruir a variabilidade
horária a partir da média diária.

### Gráficos

Para cada localidade são gerados:

- série temporal do teste com real, XGBoost e MLP;
- real versus previsto de cada modelo;
- dispersão real versus previsto de cada modelo;
- versões normalizadas e versões desnormalizadas em `W/m²`.

No gráfico de dispersão, previsões melhores ficam mais próximas da diagonal.

## Resultados atuais

Resultados presentes em `resultados/todas_localidades/resumo_localidades.csv`:

| Localidade | Melhor modelo por R² | Melhor R² |
|---|---|---:|
| BYD Camaçari | MLP | 0,3892 |
| Tesla Gigafactory Nevada | XGBoost | 0,8596 |
| Tesla Gigafactory Texas | MLP | 0,5716 |
| Hyundai Metaplant Georgia | MLP | 0,5188 |
| Rivian Normal | MLP | 0,6401 |
| Tesla Fremont Factory | XGBoost | 0,8701 |
| Lucid AMP 1 Casa Grande | MLP | 0,8161 |
| GM Factory Zero | MLP | 0,6362 |
| Ford Rouge Electric Vehicle Center | XGBoost | 0,6515 |
| BMW San Luis Potosí | MLP | 0,5895 |

Síntese:

```text
MLP foi melhor em 6 localidades.
XGBoost foi melhor em 4 localidades.
```

Médias entre as dez localidades:

| Modelo | MAE médio normalizado | RMSE médio normalizado | RMSE médio W/m² | nRMSE médio W/m² | R² médio W/m² |
|---|---:|---:|---:|---:|---:|
| XGBoost | 0,1068 | 0,1410 | 50,77 | 27,41% | 0,6396 |
| MLP | 0,1052 | 0,1390 | 50,08 | 27,05% | 0,6529 |

Não existe um vencedor universal. A previsibilidade varia entre localidades,
e resultados menores indicam dificuldade para representar as mudanças diárias
usando somente o histórico do próprio GHI.

## Estrutura do repositório

```text
.
|-- README.md
|-- requirements.txt
|-- pytest.ini
|-- treinamento_principal.py
|-- treinar_todas_localidades.py
|-- codigo_fonte/
|   |-- configuracao.py
|   |-- utilitarios.py
|   |-- preprocessamento.py
|   |-- features.py
|   |-- modelos.py
|   |-- avaliacao.py
|   |-- graficos.py
|   +-- localidades_ev.py
|-- dados/
|   |-- brutos/localidades_ev/
|   +-- processados/localidades_ev/
|-- cadernos_jupyter/
|   |-- 00_coleta_dados_localidades.ipynb
|   |-- 01_explicacao_teorica_pipeline.ipynb
|   +-- 02_resultados_todas_localidades.ipynb
|-- relatorios/
|-- resultados/
|-- testes/
+-- tools/
```

### Scripts principais

#### `treinamento_principal.py`

Executa o pipeline para uma série:

- carrega e prepara os dados;
- divide treino e teste;
- treina XGBoost e MLP;
- salva modelos, métricas, previsões e gráficos.

#### `treinar_todas_localidades.py`

Executa o fluxo completo das dez localidades:

- valida ou coleta os CSVs;
- prepara uma base por local;
- treina os dois modelos;
- gera resultados individuais e comparativos;
- atualiza o manifesto de integridade.

Opções:

```text
--validar-dados    valida os arquivos sem treinar
--somente-download coleta e valida sem treinar
--forcar-download  ignora os CSVs existentes e coleta novamente
```

### Módulos

| Módulo | Responsabilidade |
|---|---|
| `configuracao.py` | caminhos e criação das pastas |
| `utilitarios.py` | localização automática de arquivos |
| `preprocessamento.py` | coleta, limpeza, quantização e normalização |
| `features.py` | lags, médias móveis, alvo e divisão temporal |
| `modelos.py` | treinamento e salvamento dos modelos |
| `avaliacao.py` | métricas e arquivos de previsão |
| `graficos.py` | gráficos temporais e de dispersão |
| `localidades_ev.py` | cadastro auditável das localidades |

### Notebooks

| Notebook | Conteúdo |
|---|---|
| `00_coleta_dados_localidades.ipynb` | coleta, validação e exploração dos dados |
| `01_explicacao_teorica_pipeline.ipynb` | guia completo para entender e apresentar o projeto |
| `02_resultados_todas_localidades.ipynb` | análise comparativa dos resultados |

Os notebooks documentam e apresentam. A lógica reutilizável permanece nos
módulos Python, o que facilita testes e execução fora do Jupyter.

## Arquivos gerados

### Dados processados

```text
dados/processados/localidades_ev/*_features.csv
```

Colunas principais:

```text
data
ghi
ghi_quantizado
ghi_normalizado
ghi_t-1
ghi_t-2
ghi_t-3
ghi_t-7
ghi_media_movel_3d
ghi_media_movel_7d
ghi_media_movel_30d
data_alvo
ghi_alvo
ghi_alvo_quantizado
ghi_alvo_original
```

### Modelos

```text
resultados/modelos/localidades/xgboost_<localidade>.joblib
resultados/modelos/localidades/mlp_<localidade>.joblib
```

### Métricas e previsões

```text
resultados/todas_localidades/metricas_geral.csv
resultados/todas_localidades/resumo_localidades.csv
resultados/todas_localidades/previsoes/<localidade>/
```

### Figuras

```text
resultados/todas_localidades/figuras/<localidade>/
```

### Execução de uma única série

```text
resultados/metricas/
resultados/modelos/xgboost_ghi.joblib
resultados/modelos/mlp_ghi.joblib
resultados/figuras/
```

## Testes e relatórios

### Executar os testes

```bash
pytest -q
```

Os testes verificam:

- quantização;
- normalização;
- criação das features;
- alinhamento entre features e alvo;
- rejeição de dados sintéticos;
- validação de metadados, unidade e distância da grade.

### Abrir os notebooks

```bash
jupyter notebook
```

### Exportar para HTML

```bash
jupyter nbconvert --to html \
  cadernos_jupyter/01_explicacao_teorica_pipeline.ipynb \
  --output-dir relatorios

jupyter nbconvert --to html \
  cadernos_jupyter/02_resultados_todas_localidades.ipynb \
  --output-dir relatorios
```

Relatórios disponíveis:

```text
relatorios/01_explicacao_teorica_pipeline.html
relatorios/02_resultados_todas_localidades.html
```

## Limitações

O projeto atual:

- usa somente o histórico do GHI;
- prevê apenas um dia à frente;
- usa uma única divisão temporal 80/20;
- utiliza hiperparâmetros fixos;
- não compara formalmente com um baseline de persistência;
- não inclui variáveis meteorológicas;
- não inclui features sazonais explícitas;
- quantiza o sinal e, portanto, perde resolução;
- treina modelos independentes por localidade.

Melhorias naturais:

- baseline `previsão = GHI de hoje`;
- validação temporal *walk-forward*;
- temperatura, nuvens, umidade e precipitação;
- mês, dia do ano e codificação seno/cosseno;
- comparação entre GHI contínuo e quantizado;
- otimização de hiperparâmetros dentro do treino;
- recoleta dos CSVs para preencher COV horário nas bases antigas;
- armazenamento dos transformadores junto aos modelos.

## Problemas comuns

### `python` não é reconhecido

Confirme a instalação e o PATH:

```bash
python --version
python -m pip --version
```

Em alguns sistemas o comando é `python3`.

### Dependência não instalada

```bash
pip install -r requirements.txt
```

Se `cartopy` falhar, o pipeline de treinamento pode funcionar sem os mapas,
mas o notebook de resultados pode perder visualizações geográficas.

### Arquivo de dados não encontrado

Informe explicitamente:

```bash
python treinamento_principal.py --data-path caminho/do/arquivo.csv
```

Para o fluxo oficial, os arquivos ficam em:

```text
dados/brutos/localidades_ev/
```

### CSV oficial rejeitado

Verifique o motivo:

```bash
python treinar_todas_localidades.py --validar-dados
```

Se houver credenciais configuradas, faça uma nova coleta:

```bash
python treinar_todas_localidades.py \
  --somente-download \
  --forcar-download
```

### Credenciais ausentes

Configure no `.env`:

```env
NREL_API_KEY=sua_chave
NREL_EMAIL=seu_email
```

### Relatório HTML desatualizado

Exporte novamente o notebook correspondente com `jupyter nbconvert`.

### Resultados diferentes após alterações

Os modelos usam `random_state=42`, mas versões diferentes das bibliotecas ou
mudanças nos dados podem alterar os resultados. Registre o ambiente e valide
novamente os CSVs antes de comparar execuções.

## Documentação recomendada

Para uma explicação detalhada e preparada para apresentação:

```text
cadernos_jupyter/01_explicacao_teorica_pipeline.ipynb
relatorios/01_explicacao_teorica_pipeline.html
```

Para analisar tabelas e gráficos das dez localidades:

```text
cadernos_jupyter/02_resultados_todas_localidades.ipynb
relatorios/02_resultados_todas_localidades.html
```

Em uma frase:

> O projeto transforma dados horários oficiais em uma série diária auditável,
> cria informações históricas sem acessar o futuro e compara XGBoost e MLP na
> previsão do GHI médio do dia seguinte.
