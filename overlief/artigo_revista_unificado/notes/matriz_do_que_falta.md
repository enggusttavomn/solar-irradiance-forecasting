# Matriz de conteúdo e experimentos

## Escopo definitivo

- Incluído: artigo IEEE/TimesNet.
- Incluído: artigo BTSym/DilatedRNN.
- Excluído: artigo MCSM e aproximação DeepNPTS.
- Referência estrutural: `../article_thales.pdf`.

## Evidência já disponível

| Resolução | Modelo | Entrada | Saída | Período | Situação |
|---|---|---:|---:|---|---|
| Horária | TimesNet | 336 h | 72 h direta; prefixos 24/48 h | 2019--2024 | Completo |
| Mensal | DilatedRNN | 12 meses | 1 mês | 2019--2024 | Completo |

## Experimentos necessários para comparação justa

| Prioridade | Experimento | Regra |
|---:|---|---|
| 1 | DilatedRNN horário | Mesmas origens, entrada, saída, partições e pós-processamento do TimesNet horário |
| 2 | TimesNet mensal | Mesmo contexto, origens, partições, sementes e alvo do DilatedRNN mensal |
| 3 | TimesNet diário | Horizonte diário definido antes de consultar o teste |
| 4 | DilatedRNN diário | Exatamente as mesmas amostras do TimesNet diário |
| 5 | TimesNet e DilatedRNN multimensais | Somente se “longo prazo” for definido como vários meses à frente |

## Conteúdo ainda necessário

- revisão bibliográfica robusta e verificada;
- definição operacional de curto, médio e longo prazo;
- classificação climática documentada das dez localidades;
- mapa mundial das fábricas;
- variável ou fonte independente para confirmar chuva/nebulosidade;
- tabelas de melhor e pior desempenho baseadas em regra prévia;
- múltiplas sementes no protocolo horário ou justificativa explícita;
- referências citáveis dos dois trabalhos anteriores para caracterizar a extensão;
- hiperparâmetros completos e ambiente de execução no anexo.

## Restrições de integridade

- Não comparar numericamente erros horários e mensais como se fossem a mesma tarefa.
- Não chamar a previsão mensal de um passo de “vários meses à frente”.
- Não afirmar chuva apenas porque a GHI observada foi baixa.
- Não selecionar apenas fábricas ou métricas favoráveis ao método proposto.
- Não preencher resultados ausentes por interpolação, estimativa ou texto hipotético.

