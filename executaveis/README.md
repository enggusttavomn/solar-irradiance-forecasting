# Executáveis de linha de comando

Esta pasta reúne os scripts que executam etapas longas do estudo: coleta de
dados, treinamento, avaliação e geração de artefatos para os manuscritos.
Todos são chamados a partir da raiz do repositório.

| Objetivo | Comando |
|---|---|
| Avaliação multirresolução | `python executaveis/executar_avaliacao_multirresolucao.py --help` |
| Avaliação horária da TimesNet | `python executaveis/executar_avaliacao_horaria_timesnet.py --help` |
| Retomada da avaliação horária | `python executaveis/retomar_avaliacao_horaria_timesnet.py --help` |
| Artefatos do artigo unificado | `python executaveis/gerar_artefatos_artigo_unificado.py --help` |
| Atualização do artigo IEEE | `python executaveis/atualizar_artigo_ieee_timesnet.py --help` |
| Preenchimento dos artigos canônicos | `python executaveis/preencher_artigos_canonicos.py --help` |
| Coleta horária da NSRDB | `python executaveis/coletar_dados_horarios_nsrdb.py --help` |
| Contexto meteorológico | `python executaveis/coletar_contexto_meteorologico.py --help` |
| Contexto geográfico | `python executaveis/gerar_contexto_geografico.py --help` |
| Treinamento de série única | `python executaveis/treinamento_principal.py --help` |
| Experimentos legados de redes avançadas | `python executaveis/experimentos_redes_avancadas.py --help` |

Cada script insere a raiz do repositório em `sys.path` antes de importar
`codigo_fonte`, de modo que funciona tanto executado diretamente quanto
importado pela suíte de testes.

## Por que quatro executáveis continuam na raiz

`treinar_todas_localidades.py`, `reavaliar_modelos_salvos.py`,
`executar_avaliacao_mensal_canonica.py` e `gerar_figuras_avaliacao_canonica.py`
permanecem na raiz do repositório. Os manifestos de execução em
`resultados/avaliacao_mensal_corrigida/` e `resultados/avaliacao_mensal_canonica/`
registram o caminho e o `sha256` desses arquivos como entradas que produziram
resultados publicáveis, e `testes/test_resultados_mensais_publicaveis.py`
confere essa correspondência. Movê-los ou editá-los quebraria o vínculo entre
o código atual e os números já divulgados.

Para desenvolvimento novo, prefira as interfaces de `codigo_fonte/` e os
atalhos de `scripts/`.
