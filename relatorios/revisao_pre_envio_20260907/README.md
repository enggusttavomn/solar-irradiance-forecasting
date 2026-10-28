# Revisão para envio aos orientadores — 07/09/2026

O artigo principal e o material suplementar estão adequados para circulação ao professor e ao coorientador. A revisão não equivale a uma aprovação institucional ou editorial.

## Correções e conferências

- Plano EA019: data final corrigida de 09/11 para 02/11/2026; etapas de análise e redação/vídeo antecipadas para terminar em 01/11. Removidos os asteriscos sem nota em “DESCRIÇÃO”. Mantida a data real de elaboração, 07/09/2026. Preservadas as alterações que estavam abertas no Word e cópias anteriores em `.codex_pre_envio_20260907/backup/plano/`.
- Texto científico: explicitado o período 1980–2016 da classificação Köppen–Geiger e a definição de confiança como concordância entre os 12 mapas usados por Beck et al. A descrição atual da TimesNet distingue a reversão da padronização da janela da posterior conversão para unidades físicas.
- Documentação: README da raiz e índice de resultados agora identificam `avaliacao_multirresolucao_corrigida_v2/` como fonte atual local e deixam explícito que o pacote integral de previsões não está no snapshot público.
- Versão IEEE: corrigido o transbordamento vertical dos elementos de resultados, ajustando somente os espaçamentos próprios desse formato.
- PDFs principal, suplementar e IEEE recompilados a partir das fontes atuais. Cópias nativas verificadas por SHA-256 contra a saída do compilador.

## Validação

- 129 valores e vencedores conferidos independentemente nas tabelas atuais contra os CSVs corrigidos: nenhuma divergência.
- A auditoria numérica anterior registra 276 verificações aprovadas; esse total não representa uma nova execução integral nesta revisão.
- 44 testes existentes passaram: exportação Overleaf, comparação focal e geração de artefatos do artigo.
- 52 registros bibliográficos; 49 chaves citadas no principal/IEEE e 11 no suplemento. Nenhuma chave ausente, rótulo duplicado ou referência cruzada indefinida.
- PDFs: principal 19 páginas; suplemento 9; IEEE 18. Nenhum transbordamento horizontal/vertical, caractere de substituição ou marcador de referência indefinida na auditoria final.
- Revisão visual das 19 páginas do principal, das 9 do suplemento e das páginas 12–13 do IEEE, que continham os elementos ajustados.
- Permanecem avisos de espaçamento não preenchido e substituição de fontes do Tectonic na versão IEEE; não impedem leitura nem compilação.
- Nenhum modelo foi treinado e nenhum resultado numérico foi alterado.

## Pendência administrativa

A página oficial da FEEC para EA019 no segundo semestre de 2026 informa entrega do plano até **31/08/2026** e do relatório final com vídeo até **02/11/2026**. Como o plano está datado de 07/09/2026, eventual prorrogação ou regularização precisa ser confirmada com os professores ou a secretaria. Não se alterou a data para simular uma entrega anterior. Isso é distinto de enviar os arquivos aos orientadores para revisão.

Fontes consultadas em 07/09/2026:

- [Calendário oficial FEEC — TCC](https://site.fee.unicamp.br/cg/tcc-trabalho-de-conclusao-de-curso).
- [Beck et al. (2018), classificação Köppen–Geiger e definição de confiança](https://www.nature.com/articles/sdata2018214).

Evidências técnicas desta execução: `.codex_pre_envio_20260907/validacao_documentos.json` e `manifesto_fontes_congeladas.json`.
## Verificação final do plano e condição de compartilhamento

O plano corrigido foi exportado pelo próprio Word, mantendo o DOCX salvo e aberto no caminho original. O PDF da raiz e o da pasta de envio estão atualizados: duas páginas, entrega em 02/11/2026, ausência da data antiga e referências completas. As duas páginas foram inspecionadas com PDFium; fonte, tabelas e texto estão legíveis, sem cortes. A distorção encontrada na primeira renderização era específica do renderizador PDF.js utilizado na revisão.

A exportação normal do Word mantém proteção corporativa **NASCA DRM** tanto no DOCX quanto no PDF do plano. O cabeçalho protegido foi confirmado na leitura nativa do Windows. A leitura pelo Word e por processos autorizados nesta máquina não comprova que os professores conseguirão abrir esses arquivos externamente. Para o plano, é necessário um procedimento autorizado de compartilhamento que permita acesso aos destinatários. Nenhuma proteção foi removida ou alterada.

O artigo e o suplemento da pasta de envio são PDFs comuns, com cabeçalho `%PDF` e cópias idênticas às saídas do compilador. O envio das mensagens e dos arquivos aos professores não foi realizado.

## Versão de entrega

Novas edições de formatação do suplemento chegaram durante a revisão e foram incorporadas. O pacote final corresponde às 38 fontes preservadas em `.codex_pre_envio_20260907/fontes_entrega/`, incluindo o suplemento em uma coluna, recompilado e novamente conferido em suas nove páginas. Conteúdo, métricas e bibliografia foram preservados. Alterações posteriores nas fontes de trabalho não alteram este pacote de PDFs revisados. O manifesto das fontes congeladas registra a versão de entrega.
