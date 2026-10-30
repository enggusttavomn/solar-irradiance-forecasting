# Revisão técnica da revista unificada — 07/09/2026

A revisão abrangeu o artigo principal, o suplemento, a visualização IEEE e os arquivos auxiliares de `artigos/revista_unificado`. Os pseudocódigos foram confrontados com a implementação dos experimentos; as citações foram verificadas em fontes primárias e metadados editoriais; os resultados foram recalculados a partir das previsões salvas.

## Correções aplicadas

- **Foco dos algoritmos:** Os pseudocódigos principal e suplementares, o diagrama e a metodologia agora se concentram em TimesNet e DilatedRNN. Foram retirados os ramos de XGBoost/LSTM dos algoritmos, o detalhamento de árvores e as duas referências de XGBoost acrescentadas na revisão anterior. Os demais modelos permanecem identificados no benchmark e na documentação dos resultados.
- **Bibliografia:** corrigidas autorias em seis registros; normalizadas as iniciais de Ahmed et al. para os nomes efetivamente confirmados; TimesNet identificado como publicação de conferência; completado o título do relatório IRENA; substituído o link quebrado da Ford por uma divulgação oficial acessível.
- **Pseudocódigos:** explicitados amplitudes e índices da rFFT, dimensões das redes, dilatações, previsões de validação, reinicialização, escalas por corte, importação do arquivo horário e ordem entre média das sementes e piso zero. As fórmulas centrais de TimesNet e DilatedRNN conferem com o código.
- **Atribuição e métricas:** esclarecida a adaptação compacta de TimesNet; corrigida a atribuição bibliográfica das explicações de nRMSE e R²; descrito o caso de soma de quadrados numericamente nula conforme a implementação.
- **Literatura:** corrigidos os dados meteorológicos previstos de Huang, a avaliação qualitativa de GHI de Chow, a meteorologia usada por Zhao, a variável mês em Ozoegwu e o suporte diurno de Cheng. Para Zhao, preservou-se o título bibliográfico, usando “solar radiation” na descrição porque os trechos disponíveis não estabelecem sua unidade de modo inequívoco.
- **Tabela residual:** corrigidos 29 valores de TimesNet em `tables/terminal_location_comparison.tex`, que não é incluída nos documentos principais. Conferidos os 40 grupos de local/tarefa e seus vencedores.
- **Visualização IEEE:** ajustado o espaçamento entre figuras e tabelas na seção de resultados para eliminar transbordamento vertical.

## Validação realizada

- 52 referências originais auditadas; os 38 DOIs originais resolveram metadados editoriais. A base final contém 52 registros, dos quais 49 são citados.
- 725.700 linhas de previsões, 10.440 linhas de métricas locais e 1.044 linhas macro verificadas; **276 verificações numéricas aprovadas, zero falhas**. A maior divergência numérica foi aproximadamente 3,55 × 10⁻¹⁴, abaixo da tolerância de 10⁻⁸.
- Confirmados vencedores, percentuais, unidades, sementes, horizontes cumulativos/exatos, casos meteorológicos e três perfis de sete dias.
- Confirmadas as 12 contagens de parâmetros das redes, por instanciação sem treinamento.
- **44 testes existentes aprovados:** exportação Overleaf, comparação focal, TimesNet e DilatedRNN direta.
- Os resultados numéricos apresentados no artigo e no suplemento conferem com os artefatos canônicos.

## Evidências

- [Bibliografia: inventário completo e fontes](bibliografia.md).
- [Pseudocódigos: correspondência com a implementação](pseudocodigos.md).
- [Literatura: sustentação dos dez estudos examinados](literatura.md). As cinco correções recomendadas nesse relatório foram aplicadas.
- [Resultados: auditoria independente](resultados.md).
- [Metadados editoriais consultados](metadados_bibliograficos.json).
- [Manifesto dos fontes revisados](manifesto_fontes_revisadas.json).
- [Auditoria numérica detalhada](../../resultados/artigo_revista_unificado/auditoria_resultados_20260907/auditoria_numerica.json).
- [Verificação final de LaTeX/PDF](validacao_documentos.json).
- [Verificação das dependências no Overleaf](overleaf_verificado.json).

## Limites da verificação

A conferência bibliográfica distingue metadados, trechos primários acessíveis e leitura de texto integral. Alguns artigos e relatórios bloquearam o download integral; não se afirma leitura integral de todas as referências nem reprodução dos experimentos publicados por terceiros. O inventário registra as fontes e os limites de acesso. As previsões do próprio estudo foram auditadas sem treinar novamente os modelos.

A compilação pode registrar avisos de ambiente: substituição de fontes na visualização IEEE com Tectonic e ausência de paginação de ICLR na referência TimesNet. Não foi inventada paginação para eliminar o aviso bibliográfico.

## Estado final dos documentos

- Artigo principal: 19 paginas; suplemento: 9; visualizacao IEEE: 19.
- Nenhuma citacao indefinida, referencia cruzada ausente, chave duplicada, caractere substituido no texto ou transbordamento vertical/horizontal nos PDFs finais.
- A confirmação de sincronização desta mudança de foco está no arquivo overleaf_verificado.json.
- [PDF principal revisado](../../artigos/revista_unificado/main.pdf), [suplemento revisado](../../artigos/revista_unificado/supplementary_material.pdf), [visualizacao IEEE](../../artigos/revista_unificado/main_ieee.pdf).
