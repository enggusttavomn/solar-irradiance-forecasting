# Otimiza??o mensal da TimesNet

A busca est? implementada em `codigo_fonte/otimizacao_timesnet_mensal.py`, com
entrada em `scripts/otimizar_timesnet_mensal.py`. Ela mant?m os resultados do
artigo em `resultados/avaliacao_multirresolucao_corrigida_v2/` e gera os novos
experimentos em outra pasta.

## O que foi implementado

- Sele??o da ?poca pelo macro-MAE em W/m? da valida??o de 2023, ap?s invers?o
  da escala e aplica??o do piso zero. Cada localidade tem o mesmo peso.
- Busca de perdas MSE, MAE e Huber (delta 0,1 na escala normalizada), taxas
  0,001/0,0003, dimens?es 8/16 e um/dois blocos. O limite de ?pocas permanece
  300, com paci?ncia de 30; nenhuma melhora ? pressuposta.
- Janelas de 12/24/36 meses, com contagens expl?citas de exemplos. No hist?rico
  dispon?vel (2019?2024), a janela de 36 meses ? descartada pelo m?nimo de
  18 origens de ajuste por localidade. A janela de 24 admite 24 origens para
  um passo e 19 para seis passos; as de 12 admitem 36 e 31.
- Candidatos que aprendem o desvio do GHI em rela??o ? climatologia mensal.
  A climatologia usa apenas observa??es anteriores ao corte de cada fase;
  ela ? subtra?da das entradas/alvos e somada ? previs?o antes do piso zero.
  Isso ? uma variante do pipeline, n?o a TimesNet original nem uma garantia
  de superar a climatologia.
- Escolha do candidato pelo erro do ensemble das cinco sementes
  11, 23, 42, 67 e 89. A m?dia dos erros individuais ? registrada ? parte.
- Escolha congelada antes do refit: somente o vencedor ? reinicializado e
  treinado at? 2023 pelas ?pocas escolhidas para cada semente. A avalia??o
  retrospectiva em 2024 exige `--avaliar-teste`.
- Contratos com hashes de c?digo e insumos, cache por candidato/semente,
  hist?rico de treino, escalas e previs?es; retomada recusa contrato diferente.
- Checkpoints novos incluem escalas, identidades e climatologia congelada.
  `prever_checkpoint` reproduz a infer?ncia sem consultar os CSVs de treino.
  Checkpoints hist?ricos sem esses campos precisam dos insumos originais.

A normaliza??o min?max continua ativa e n?o h? quantiza??o. A padroniza??o
interna de cada janela na arquitetura tamb?m foi mantida.

## Resultados j? registrados e auditados

Execu??o completa: `resultados/busca_timesnet_mensal_v2_20260920/`.
Valores de macro-MAE no teste de 2024, em W/m?:

| Configura??o | 1 m?s | At? 6 meses, cumulativo |
|---|---:|---:|
| TimesNet can?nica | 13,8915 | 14,4582 |
| TimesNet otimizada, alvo de desvio da climatologia | 13,2363 | 13,1671 |
| Climatologia | 12,5747 | 13,0272 |

A redu??o observada do MAE ? de aproximadamente 4,72% e 8,93%. Os candidatos
selecionados foram `anomalia_mae_lr_0003` para um m?s e
`anomalia_mae_dim16` para seis meses, ambos com contexto de 12 meses. O
primeiro usa dimens?o 8 e taxa 0,0003; o segundo dimens?o 16 e taxa 0,001.
Ambos usam um bloco e perda MAE. Cada coluna ? uma tarefa diferente.

A climatologia ainda vence a rede otimizada na valida??o e no teste. Os dois
MAEs da TimesNet ainda s?o maiores que 13. A sele??o escolhe o melhor
candidato TimesNet da grade; ela n?o escolhe automaticamente entre a rede e
as refer?ncias simples. Para uso aplicado, a climatologia permanece uma
refer?ncia indispens?vel.

A busca inicial sem os candidatos de anomalia est? preservada em
`resultados/busca_timesnet_mensal_20260920/`. Ela registrou MAE 13,8561 e
14,1975. As duas buscas s?o desenvolvimento explorat?rio; 2024 j? havia sido
observado quando a otimiza??o foi proposta. O resultado requer confirma??o
em um per?odo futuro independente. N?o ? evid?ncia de superioridade sobre o
artigo do Lu?s, que tem outros locais e hist?rico, nem previs?o de 60 meses.

## Executar

Na raiz do projeto, com as depend?ncias cient?ficas instaladas:

```powershell
# Verificar o fluxo completo em uma pasta tempor?ria (sem valor cient?fico).
python -m scripts.otimizar_timesnet_mensal --pasta-saida tmp/timesnet_smoke --smoke --avaliar-teste

# Busca completa: primeiro apenas a valida??o.
python -m scripts.otimizar_timesnet_mensal --pasta-saida resultados/timesnet_nova_busca

# Mesma configura??o e mesma pasta: refit e teste s? do candidato congelado.
python -m scripts.otimizar_timesnet_mensal --pasta-saida resultados/timesnet_nova_busca --avaliar-teste
```

O ambiente local dispon?vel nesta revis?o ?
`.venv-baselines-gpu-20260912/Scripts/python.exe`; substitua `python` por esse
caminho se ele n?o estiver no PATH. O treinamento desta rotina usa CPU e uma
thread, mesmo quando o PyTorch instalado oferece CUDA.

Use `--candidatos`, `--sementes`, `--max-epocas`, `--paciencia` e
`--minimo-origens` para definir uma nova busca. Trocar configura??o, c?digo
ou dados exige outra pasta; n?o altere hashes de contratos para for?ar retomada.
O arquivo `resumo.csv` resume as tarefas da ?ltima chamada; para consolidar
ambas, execute-as juntas (padr?o). Os resultados e status por tarefa s?o
preservados mesmo ao executar uma delas separadamente.
Uma pasta com lock ativo n?o pode ser reutilizada simultaneamente. Ap?s uma
interrup??o for?ada, confirme que o processo terminou antes de remover o lock
identificado na mensagem de erro.

Para uma compara??o de contexto com as mesmas origens de treino, forne?a
`--inicio-ajuste 2021-01-31` e compare candidatos de 12 e 24 meses. Na grade
padr?o cada candidato usa todas as suas origens admiss?veis: a compara??o
combina o efeito do contexto com o n?mero de exemplos, e n?o isola apenas o
comprimento da janela.

## Ampliar o hist?rico

`--pasta-csv` aceita uma pasta com os dez CSVs di?rios do cadastro, com colunas
`data`, `ghi` e identidades correspondentes, uma grade di?ria cont?nua e comum.
Para manter as origens de treino a partir de janeiro de 2020, a janela de
24 meses precisa de dados desde janeiro de 2018; a de 36, desde janeiro de
2017. Para aumentar tamb?m as origens de ajuste, indique um
`--inicio-ajuste` anterior, sempre no ?ltimo dia do m?s e com contexto
completo. Valida??o e teste continuam em 2023 e 2024.

Nenhuma nova coleta foi feita nesta implementa??o. Os arquivos dispon?veis
continuam cobrindo 2019?2024. O mensal de seis passos possui apenas sete
origens de teste por localidade e alvos sobrepostos; a melhora descritiva n?o
constitui um teste de signific?ncia nem comprova generaliza??o para outros anos.

## Artefatos para revis?o

- `ranking_validacao.csv`: candidatos eleg?veis e MAE do ensemble.
- `candidatos_descartados.json`: configura??es sem hist?rico suficiente.
- `selecao_por_semente.csv` e `selecao_congelada.json`: ?pocas e vencedor.
- `previsoes_teste.csv`, `metricas_macro.csv` e `metricas_por_localidade.csv`:
  somente ap?s a avalia??o do vencedor, com refer?ncias simples.
- `preprocessamento_refit.json` e `modelos/`: transforma??es e pesos de novas
  execu??es; n?o est?o presentes nos checkpoints hist?ricos legados.
- `contrato_execucao.json`, `status_execucao.json` e `manifesto_artefatos.json`:
  proced?ncia, situa??o e integridade.

Os manuscritos e as tabelas oficiais n?o foram promovidos automaticamente
para os resultados da busca. A variante com climatologia deve ser descrita
explicitamente antes de qualquer incorpora??o cient?fica.

## Verifica??o da implementa??o em 22/09/2026

Passaram 109 testes dos m?dulos de otimiza??o, treino, checkpoints, locks,
TimesNet e protocolo multirresolu??o. A execu??o curta com dados reais das
duas tarefas concluiu sele??o, refit e gera??o de artefatos em
`tmp/timesnet_smoke_20260922/`; seus n?meros n?o s?o resultados cient?ficos.

A [auditoria independente](../relatorios/otimizacao_timesnet_20260922/auditoria.md)
recalcula os MAEs da busca completa e recarrega seus dez modelos, sem retreino.
O script de verifica??o ? `scripts/auditar_busca_timesnet_mensal.py`.

Os contratos hist?ricos foram preservados. As corre??es posteriores no
orquestrador alteram seu hash, por isso as buscas antigas n?o devem ser
retomadas com o c?digo novo na mesma pasta. Isso n?o invalida as previs?es
hist?ricas conferidas contra seus manifestos e reproduzidas pela recarga.
