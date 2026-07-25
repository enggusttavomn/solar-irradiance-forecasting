# Modelos do protocolo mensal

Esta pasta e a entrada recomendada para estudar os dez metodos comparados no
artigo. Cada metodo possui um arquivo com o mesmo nome usado no texto.

```text
modelos/
├── referencias_simples/
│   ├── persistencia.py
│   ├── sazonal_ingenuo.py
│   └── climatologia.py
├── tabulares/
│   ├── xgboost.py
│   └── mlp.py
├── recorrentes/
│   ├── rnn.py
│   ├── lstm.py
│   └── dilated_rnn.py
└── probabilisticos/
    ├── deepar.py
    └── deepnpts.py
```

Os arquivos desta estrutura expoem funcoes com nomes simples, como
`construir`, `treinar` e `prever`. Eles delegam aos motores cientificos usados
na execucao canonica. Esses motores antigos nao foram apagados nem alterados,
pois seus caminhos e hashes estao registrados em
`resultados/avaliacao_mensal_canonica/manifesto_execucao.json`.
