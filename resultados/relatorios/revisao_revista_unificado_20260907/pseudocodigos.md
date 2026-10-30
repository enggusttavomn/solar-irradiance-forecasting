> Registro da auditoria anterior. Para o escopo atual dos pseudocódigos e a remoção das inclusões de XGBoost, consulte [ajuste de foco](ajuste_de_foco.md).

# Revisão dos pseudocódigos — 2026-09-07

Escopo: os três algoritmos de `artigos/revista_unificado/sections/`, o wrapper `04_algorithms.tex` e os três blocos de `appendices/supplementary_algorithms.tex`, conferidos contra a implementação efetivamente usada no experimento unificado.

## Correções e esclarecimentos aplicados

- **TimesNet:** amplitude definida como média dos módulos da rFFT pelos canais de uma única amostra; seleção limitada aos índices positivos, período inteiro e extensão para preenchimento com zeros explícitos; agregação usa os mesmos valores espectrais selecionados. Os dois bancos Inception calculam médias das saídas das convoluções 1×1 e 3×3, com GELU entre bancos. Indicadas as dimensões da entrada e da projeção temporal. Evidência: `codigo_fonte/timesnet_horario.py:42`, `:115`, `:143`, `:192`, `:264`, `:389`, `:475`; configurações ativas em `codigo_fonte/experimento_multirresolucao.py:180` e `codigo_fonte/experimento_horario_timesnet.py:125`.
- **DilatedRNN:** explicitados entrada C×1, estados C×16, indexação temporal iniciando em zero, último estado C−1 e concatenação 16+8=24. Dilatações (1,2,4), pesos compartilhados dentro da camada e estados iniciais zero já estavam corretos. Evidência: `codigo_fonte/dilated_rnn_direta.py:29`, `:69`, `:74`, `:163`, `:192`.
- **Protocolo principal:** incluídas retenção das previsões de validação antes de descartar cada modelo selecionador, inversão com a escala adequada a cada corte e aplicação do piso separadamente às sementes e ao ensemble. O XGBoost recebe dois ajustes independentes com orçamento fixo. Evidência: `codigo_fonte/experimento_multirresolucao.py:1237`, `:1384`, `:1861`.
- **Suplemento:** unificada a notação `(r,C,H)`; explicitado o ramo horário que importa as previsões oficiais e acrescenta somente DilatedRNN/42; detalhadas as entradas e árvores de saída vetorial do XGBoost; explicitado que o ensemble é média de previsões brutas já em W/m², antes do piso; máscara solar calculada no centro do intervalo e aplicada somente aos novos resultados. Evidência: `codigo_fonte/experimento_multirresolucao.py:464`, `:543`, `:888`, `:914`, `:2175`, `:2455`.

## Verificações sem necessidade de alteração

As equações do background correspondem ao código: amplitude por amostra/canal, exclusão da componente DC, floor(T/f), softmax sobre amplitudes, resíduo do TimesBlock e recorrência h[t−d]. O treinamento usa Adam, MSE normalizado, restaura o checkpoint com menor perda de validação e reinicializa com a mesma semente para exatamente E* épocas; o wrapper inclui cada pseudocódigo uma vez. A implementação compacta possui diferenças deliberadas da TimesNet original, cuja explicitação na metodologia está sob responsabilidade do revisor principal.

## Validação

Verificação estrutural passou nos cinco arquivos: chaves, ambientes LaTeX e blocos If/For balanceados; seis rótulos de algoritmo sem duplicação. `git diff --check` passou para os arquivos do escopo. Compilação e inspeção da paginação ficam com o revisor principal. O trabalho alterou quatro arquivos TeX e este relatório; não exigiu executar novamente os experimentos.
