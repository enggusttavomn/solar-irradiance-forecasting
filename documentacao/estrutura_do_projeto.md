# Onde encontrar e salvar cada coisa

O projeto mantém os nomes em português e separa o código reutilizável, os
comandos, os dados e os produtos da pesquisa. Comece pelo
[README principal](../README.md) para instalar o ambiente e pelo
[catálogo de comandos](../scripts/COMANDOS.md) para escolher uma operação.

## Mapa das pastas

```text
TCC/
|-- codigo_fonte/              lógica reutilizável da pesquisa
|   |-- coleta/                API e cadastro das localidades
|   |-- preparacao/            limpeza, validação e agregação
|   |-- modelos/               interfaces dos modelos por família
|   |-- experimento/           métricas e avaliação temporal
|   `-- visualizacao/          figuras dos experimentos
|-- scripts/                   comandos e automações
|   |-- coleta/                coleta e preparação do histórico
|   |-- treinamento/           experimentos, otimização e quantização
|   |-- auditoria/             verificação dos experimentos
|   |-- relatorios/            geração de figuras e relatórios
|   |-- operacao/              acompanhamento dos treinamentos
|   `-- apresentacoes/         geração e inspeção de slides
|-- executaveis/               implementações históricas dos comandos
|-- testes/                    testes científicos e novos testes
|-- tests/                     testes com caminhos históricos preservados
|-- dados/                     dados brutos, externos e processados
|-- resultados/                previsões, modelos, métricas e manifestos
|-- relatorios/                auditorias, revisões e painéis
|-- artigos/                   manuscritos, figuras e templates LaTeX
|-- documentacao/              guias, referências e entregas
|-- output/                    exportações e prévias locais
`-- tmp/                       trabalho temporário e estado operacional local
```

Os testes operacionais que podem ser transferidos sem invalidar contratos
ficam em `testes/operacao/`. Os arquivos mantidos em `tests/` continuam
incluídos na descoberta padrão do pytest.

## Como escolher o destino de um arquivo

| Arquivo novo | Destino | Critério |
|---|---|---|
| Função ou classe reutilizável | `codigo_fonte/`, na camada correspondente | pode ser importada e testada sem iniciar uma execução completa |
| Comando de linha de comando | `scripts/<área>/` | trata argumentos e chama a lógica reutilizável |
| Teste de software | `testes/`; operação local em `testes/operacao/` | usa dados sintéticos ou diretórios temporários quando possível |
| Insumo original | `dados/brutos/` ou `dados/externos/` | registra origem e condições de coleta |
| Base preparada | `dados/processados/` | identifica os insumos e o gerador |
| Resultado de experimento | `resultados/<execução>/` | acompanha configuração, sementes e proveniência |
| Revisão ou auditoria | `relatorios/<assunto>_<AAAAMMDD>/` | interpreta ou verifica uma execução identificada |
| Manuscrito e suas figuras | `artigos/<publicação>/` | mantém os ativos da publicação juntos |
| Guia de uso ou decisão de projeto | `documentacao/` | tem título claro e links para código e evidências |
| Prévia ou exportação local | `output/` | pode ser regenerada; não integra o versionamento padrão |
| Arquivo temporário | `tmp/` | não é fonte de resultados publicáveis |

Use nomes em `snake_case` para novos módulos Python. Evite arquivos genéricos
como `novo.py`, `final2.py` ou `teste_final.py`: o nome deve explicar a
responsabilidade. Prefira uma pasta por execução a sobrescrever resultados
anteriores. Mantenha os arquivos de configuração das ferramentas na raiz,
incluindo `pyproject.toml` e os `requirements*.txt`.

## Comandos organizados e implementações preservadas

Execute os novos pontos de entrada como módulos, a partir da raiz:

```bash
python -m scripts.treinamento.rodar_quantizacao_todos_modelos --help
python -m scripts.auditoria.auditar_quantizacao_todos_modelos --help
python -m scripts.operacao.painel_progresso_quantizacao --help
```

Esses módulos encaminham a execução para os comandos existentes e preservam
seus argumentos, destinos e códigos de saída. A lógica tem uma única
implementação. Os arquivos antigos em `scripts/`, `executaveis/` e na raiz
continuam nos mesmos caminhos porque contratos e auditorias registram seus
nomes e hashes SHA-256.

O mesmo vale para módulos científicos em `codigo_fonte/`, guias antigos e
testes referenciados por manifestos. Os índices antigos nessas pastas fazem
parte de snapshots de integridade; este guia e o catálogo descrevem a
navegação atual. Novos módulos devem seguir as camadas existentes, evitando
ampliar a lista de implementações históricas na raiz das pastas.

Uma futura transferência de código auditado deve ter um plano de migração
que preserve as fontes da execução original e registre a nova versão.
Modificar um snapshot antigo para fazê-lo corresponder a uma reorganização
apaga a evidência de qual código produziu o resultado.

## Rotina de desenvolvimento

1. Consulte este mapa antes de criar um arquivo.
2. Coloque a lógica em `codigo_fonte/` e a interface em `scripts/<área>/`.
3. Execute `python -m pytest -q` na raiz; o comando inclui ambas as pastas
   de testes e usa o modo de importação `importlib` para nomes repetidos.
4. Confira `git diff` e os arquivos novos antes de versionar.
5. Registre a execução e suas fontes antes de usar resultados em um artigo.

`output/`, `tmp/`, caches e ambientes virtuais ficam locais. Alguns arquivos
temporários existentes são usados por rotinas de retomada; remova-os apenas
quando essas dependências tiverem sido encerradas ou substituídas.
