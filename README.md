# Previsão multirresolução de irradiância solar (GHI)

[![CI](https://github.com/enggusttavomn/solar-irradiance-forecasting/actions/workflows/testes.yml/badge.svg)](https://github.com/enggusttavomn/solar-irradiance-forecasting/actions/workflows/testes.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Status: pesquisa acadêmica](https://img.shields.io/badge/status-pesquisa%20acad%C3%AAmica-5B5BD6)](#escopo-e-limitações)

Repositório de pesquisa para previsão de Irradiância Global Horizontal (GHI)
em dez localidades associadas a fábricas de veículos elétricos. O projeto
compara modelos de aprendizado de máquina e redes neurais em resoluções
horária, diária e mensal, com protocolo temporal reproduzível e artefatos de
auditoria.

**Repositório oficial:** <https://github.com/enggusttavomn/solar-irradiance-forecasting><br>
**Visibilidade:** público · **branch padrão:** `main`

> Os dados da NSRDB são estimativas modeladas, não medições realizadas nas
> fábricas. Os resultados são retrospectivos e não constituem uma previsão
> solar operacional.

## Visão geral

O estudo avalia quatro tarefas alinhadas por origem temporal:

| Resolução | Horizonte | Papel no estudo |
|---|---:|---|
| Horária | até 72 h | extensão com uma semente (`42`) |
| Diária | até 30 dias | avaliação principal com cinco sementes |
| Mensal | 1 mês | avaliação principal com cinco sementes |
| Mensal | até 6 meses | análise exploratória com cinco sementes |

Os modelos comparados incluem TimesNet, DilatedRNN, LSTM, XGBoost,
persistência, sazonal ingênuo e climatologia. O protocolo usa divisões
temporais, ajuste sem acesso aos alvos de teste e métricas calculadas por
localidade antes da agregação macro.

Os resultados apresentados, as ressalvas estatísticas e a proveniência estão no
[manuscrito unificado](artigos/revista_unificado/README.md). A fonte atual é o
arquivo local `resultados/avaliacao_multirresolucao_corrigida_v2/`, descrito no
[índice de resultados](resultados/README.md). O pacote completo de previsões
não integra o snapshot público; um clone do repositório, por si só, não permite
recalcular as métricas do artigo a partir das previsões individuais. Não copie
números de diretórios históricos para artigos ou apresentações.

## Comece por aqui

| Objetivo | Caminho |
|---|---|
| Entender o desenho do estudo | [`artigos/revista_unificado/`](artigos/revista_unificado/) |
| Explorar código por etapa | [`codigo_fonte/`](codigo_fonte/) |
| Consultar dados e proveniência | [`dados/`](dados/) |
| Conferir resultados oficiais | [`resultados/`](resultados/) |
| Executar comandos usuais | [`scripts/COMANDOS.md`](scripts/COMANDOS.md) |
| Rodar as avaliações completas | [`executaveis/`](executaveis/) |
| Acompanhar treinamentos | [`relatorios/painel_treinamentos.html`](relatorios/painel_treinamentos.html) |
| Consultar auditorias e revisões | [`relatorios/README.md`](relatorios/README.md) |
| Ler a documentação complementar | [`documentacao/`](documentacao/) |
| Escolher a pasta de um arquivo novo | [`documentacao/estrutura_do_projeto.md`](documentacao/estrutura_do_projeto.md) |

## Estrutura do repositório

```text
.
├── artigos/              manuscritos, figuras e templates LaTeX
├── codigo_fonte/         coleta, preparação, modelos e experimentos
├── dados/                dados brutos, externos e processados
├── documentacao/         guias, plano de trabalho, envios e referências
├── executaveis/          scripts de linha de comando das avaliações
├── output/               saídas temporárias locais e prévias
├── relatorios/           painéis, auditorias e revisões datadas
├── resultados/           resultados canônicos, manifestos e legados
├── scripts/              automações e comandos agrupados por finalidade
│   ├── apresentacoes/    geração e revisão de apresentações
│   ├── auditoria/        verificações dos experimentos
│   ├── coleta/           obtenção e preparação de insumos
│   ├── operacao/         acompanhamento local dos treinamentos
│   ├── relatorios/       geração de figuras e relatórios
│   └── treinamento/      execução de buscas e treinamentos
├── testes/               testes científicos e de operação
│   └── operacao/         testes operacionais sem caminhos históricos fixos
├── tests/                testes preservados por contratos de auditoria
└── tmp/                  trabalho temporário e estado operacional local
```

Na raiz ficam os arquivos que as ferramentas leem por convenção
(`README.md`, `pyproject.toml`, `CITATION.cff`, os `requirements*.txt` e os
arquivos de configuração ocultos), o atalho Windows
`Abrir painel de progresso.cmd` e quatro executáveis:
`treinar_todas_localidades.py`, `reavaliar_modelos_salvos.py`,
`executar_avaliacao_mensal_canonica.py` e `gerar_figuras_avaliacao_canonica.py`.
Esses quatro permanecem onde estão porque os manifestos de
`resultados/avaliacao_mensal_corrigida/` e
`resultados/avaliacao_mensal_canonica/` registram seu caminho e seu `sha256`
como entradas dos resultados publicáveis; `testes/test_resultados_mensais_publicaveis.py`
confere essa correspondência a cada execução da suíte.

Os demais executáveis de linha de comando estão em
[`executaveis/`](executaveis/). Os comandos do [catálogo](scripts/COMANDOS.md)
oferecem uma navegação por finalidade e encaminham para as implementações
existentes, preservadas nos caminhos registrados pelos manifestos.

Para arquivos novos, use `codigo_fonte/` para lógica reutilizável e a subpasta
adequada de `scripts/` para comandos e automações. Coloque evidências de experimentos em
`resultados/`, auditorias e resumos em `relatorios/`, orientações em
`documentacao/` e saídas descartáveis em `output/`. Os caminhos científicos
existentes devem ser preservados: renomear um arquivo pode invalidar
manifestos, hashes e retomadas. Consulte o
[guia da estrutura](documentacao/estrutura_do_projeto.md) antes de reorganizar
artefatos existentes.

## Instalação

O ambiente de referência usa **CPython 3.12**. A instalação completa inclui
bibliotecas pesadas de aprendizado profundo e foi validada para CPU.

```bash
git clone https://github.com/enggusttavomn/solar-irradiance-forecasting.git
cd solar-irradiance-forecasting
python -m venv .venv
```

Ative o ambiente:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Instale as dependências e valide o checkout:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
```

Para executar somente a suíte usada na integração contínua, pode-se instalar o
conjunto menor:

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q
```

## Uso

Consulte a ajuda antes de iniciar avaliações longas:

```bash
python executaveis/executar_avaliacao_multirresolucao.py --help
python executar_avaliacao_mensal_canonica.py --help
python executaveis/gerar_artefatos_artigo_unificado.py --help
```

Os comandos agrupados devem ser chamados como módulos, a partir da raiz:

```bash
python -m scripts.treinamento.rodar_quantizacao_todos_modelos --help
python -m scripts.auditoria.auditar_quantizacao_todos_modelos --help
python -m scripts.operacao.painel_progresso_quantizacao --help
```

Para consultar o painel HTML disponível no checkout, abra
[`relatorios/painel_treinamentos.html`](relatorios/painel_treinamentos.html).
No Windows, o atalho `Abrir painel de progresso.cmd` inicia o painel local de
progresso; ele usa o ambiente Python local configurado em
`scripts/abrir_painel_progresso.ps1`. Consulte
[`relatorios/README.md`](relatorios/README.md) para distinguir os painéis e as
evidências de cada execução.

### Coleta opcional de dados

O repositório contém dados e artefatos de diferentes etapas do estudo, mas o
pacote completo da avaliação atual do artigo unificado permanece local.
Reproduzir suas métricas a partir das previsões individuais requer acesso ao
arquivo `resultados/avaliacao_multirresolucao_corrigida_v2/` identificado no
suplemento. Uma nova coleta não substitui o arquivo original, pois revisões
dos produtos podem alterar os dados.

Para uma nova coleta, copie `.env.example` para `.env`, configure
`NREL_API_KEY` e `NREL_EMAIL` e mantenha o arquivo `.env` somente na máquina
local.

## Reprodutibilidade e governança dos resultados

- `resultados/avaliacao_multirresolucao_corrigida_v2/` é a fonte atual local
  das quatro tarefas do artigo unificado; o pacote completo não está versionado.
- `resultados/avaliacao_multirresolucao/` preserva a avaliação multirresolução
  anterior e não fornece os números do manuscrito atual.
- `resultados/avaliacao_mensal_canonica/` preserva a avaliação mensal
  canônica anterior e seus manifestos.
- Outros diretórios de correção, legado, `smoke` ou `validacao` servem para
  rastreabilidade e não são fonte automática de conclusões. A fonte atual deve
  ser identificada explicitamente no manuscrito e no índice de resultados.
- Configurações, sementes, hashes SHA-256 e status de execução acompanham os
  artefatos científicos relevantes.
- O modo `smoke` verifica apenas o fluxo de software; ele não produz evidência
  científica publicável.

## Qualidade de software

A suíte automatizada cobre preparação dos dados, baselines, modelos, métricas,
reprodutibilidade, geração de figuras, integridade dos manuscritos e contratos
da estrutura pública. O comando padrão descobre `testes/` e `tests/`, incluindo
os testes operacionais. Pull requests executam a CI em Python 3.12.

Antes de contribuir, leia [`CONTRIBUTING.md`](.github/CONTRIBUTING.md). Falhas de
segurança devem seguir [`SECURITY.md`](.github/SECURITY.md).

## Escopo e limitações

- As dez localidades não formam uma amostra aleatória de todos os climas.
- A NSRDB fornece irradiância modelada; não há sensores de solo nas fábricas.
- O repositório não contém dados de carga, produção industrial ou geração
  fotovoltaica das empresas citadas.
- Horizontes sobrepostos reduzem a independência entre observações; as
  comparações devem ser interpretadas com essa ressalva.
- A extensão horária usa uma única semente e não estima variabilidade entre
  inicializações.
- Resultados históricos descrevem o recorte avaliado e não estabelecem
  superioridade universal de uma arquitetura.

## Citação

Use os metadados de [`CITATION.cff`](CITATION.cff). O GitHub também oferece a
opção **Cite this repository** na página do projeto.

## Licenciamento

Este repositório ainda não declara uma licença de reutilização. A visibilidade
pública permite consulta e colaboração pelo GitHub, mas não concede
automaticamente permissão para redistribuir código, dados ou manuscritos.
Consulte os autores antes de reutilizar o material até que um arquivo
`LICENSE` seja definido.
