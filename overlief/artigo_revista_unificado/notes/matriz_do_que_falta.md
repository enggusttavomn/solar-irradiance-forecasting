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

## Experimentos executados para comparação justa

| Experimento | Estado | Evidência |
|---|---|---|
| DilatedRNN horário | Concluído | Extensão 336 h → 72 h, semente oficial 42, alinhada um a um ao artefato TimesNet |
| TimesNet mensal | Concluído | Tarefas 12 → 1 e 12 → 6 meses, com cinco sementes |
| TimesNet diário | Concluído | Tarefa 365 → 30 dias, com horizontes congelados antes do teste |
| DilatedRNN diário | Concluído | Mesmas amostras, origens e regras da tarefa TimesNet diária |
| TimesNet e DilatedRNN multimensais | Concluído, exploratório | Saída direta de seis meses; sete origens de teste por local |

Os artefatos completos estão em
`../../../resultados/avaliacao_multirresolucao/`; as consolidações e os dados
de contexto estão em `../../../resultados/artigo_revista_unificado/`.

## Conteúdo concluído

- revisão bibliográfica organizada por alvo, informação e horizonte;
- definição operacional conjunta de resolução e horizonte;
- classificação Köppen--Geiger documentada para as dez localidades;
- mapa mundial com ampliações para localidades próximas;
- contexto meteorológico independente do NASA POWER, usado apenas pós-hoc;
- casos de maior ganho e maior déficit escolhidos por regra global prévia;
- cinco sementes nas tarefas diária e mensais;
- justificativa explícita para a única semente do protocolo horário;
- hiperparâmetros, contrato temporal, versões e hashes no anexo;
- tabelas macro, resultados por local, variabilidade e comparação pareada;
- limitações estatísticas, meteorológicas e de validade externa.

## Pendências externas ao conteúdo executado

- substituir a descrição dos dois manuscritos-base por citações formais apenas
  quando houver metadados públicos de publicação ou submissão autorizados;
- regenerar `main.pdf` e compilar `main_ieee.tex` em Overleaf ou em uma máquina
  com distribuição TeX, pois o ambiente local atual não possui compilador;
- preencher, no momento da submissão, os campos editoriais dependentes do
  periódico escolhido (declaração de dados/código, financiamento, CRediT e
  conflitos de interesse) sem inferir informações dos autores.

## Restrições de integridade

- Não comparar numericamente erros horários e mensais como se fossem a mesma tarefa.
- Não chamar a previsão mensal de um passo de “vários meses à frente”.
- Não afirmar chuva apenas porque a GHI observada foi baixa.
- Não selecionar apenas fábricas ou métricas favoráveis ao método proposto.
- Não preencher resultados ausentes por interpolação, estimativa ou texto hipotético.
