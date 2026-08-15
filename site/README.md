# Site de visualizacao do projeto

O site foi separado em quatro paginas para permitir evolucao independente:

| Pagina | Conteudo |
|---|---|
| `index.html` | HOME: pergunta, fluxo e escopo geral |
| `data.html` | DATA: API, auditoria, divisao temporal e preparacao |
| `modelos.html` | ML MODELS: os dez metodos e seus arquivos |
| `resultados.html` | RESULTADOS: tabelas, ranking, incerteza e figuras |

Todas compartilham `assets/estilo.css` e a mesma barra horizontal de navegacao.

Para atualizar o site depois de uma mudanca nos CSVs canônicos:

```bash
python site/gerar_site.py
```

O comando usa o caminho do arquivo porque `site` tambem e o nome de um modulo
da biblioteca padrao do Python.

Para visualizar localmente a partir da raiz do repositorio:

```bash
python -m http.server 8000
```

Depois abra `http://localhost:8000/site/` ou a URL encaminhada pelo Codespaces.

O HTML nao consulta a internet. Os dados sao incorporados no momento da
geracao e as figuras sao carregadas da pasta de resultados canonicos.
