# Código-fonte

O código está organizado pelo fluxo científico. Execute os pontos de entrada a
partir da raiz do repositório para que caminhos relativos e manifestos sejam
resolvidos de forma consistente.

## Camadas principais

| Caminho | Responsabilidade |
|---|---|
| `coleta/` | cliente da NSRDB e cadastro das dez localidades |
| `preparacao/` | validação, limpeza, agregação e construção da base mensal |
| `modelos/` | interface pública dos modelos mensais por família |
| `experimento/` | métricas, avaliação temporal e reprodutibilidade mensal |
| `visualizacao/` | geração das figuras do fluxo mensal |

## Avaliação multirresolução

Os módulos abaixo implementam o estudo mais recente:

- `experimento_multirresolucao.py`: orquestra tarefas horárias, diárias e
  mensais com contratos e retomada;
- `experimento_horario_timesnet.py`: avaliação horária oficial;
- `timesnet_horario.py`: arquitetura TimesNet e componentes temporais;
- `dilated_rnn_direta.py`: previsão direta com recorrência dilatada;
- `contexto_geografico.py` e `contexto_meteorologico.py`: contexto independente
  das localidades;
- `artefatos_artigo_unificado.py`: tabelas, figuras e manifestos do manuscrito.

## Busca de hiperparâmetros mensais da TimesNet

A busca é separada da avaliação canônica e grava sempre em pasta nova:

- `treinamento_timesnet_otimizacao.py`: treina um candidato com perda MSE, MAE
  ou Huber e escolhe a época pelo MAE físico em W/m² da validação;
- `otimizacao_timesnet_mensal.py`: percorre os candidatos, congela a seleção em
  2023 sem usar os alvos de 2024 na sele??o e, sob `--avaliar-teste`, refaz apenas
  o vencedor.

Os resultados canônicos em `resultados/` não são alterados: a execução recusa
qualquer saída dentro das pastas oficiais.

Os executáveis da raiz são pontos de entrada e implementações históricas cujos
caminhos constam em manifestos já produzidos. Não os mova sem atualizar o
contrato de reprodutibilidade e os testes correspondentes.

Para uma visão por modelo, consulte [`modelos/README.md`](modelos/README.md).
