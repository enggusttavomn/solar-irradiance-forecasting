# Arquivos processados por localidade

Para a avaliacao mensal corrigida, use exclusivamente os dez arquivos com o
sufixo:

```text
*_features_mensal_v2.csv
```

Eles sao recriados por `treinar_todas_localidades.py --frequencia mensal` e
contem 12 defasagens mensais consecutivas, medias moveis de 3/6/12 meses,
calendario circular do mes-alvo e alvo continuo normalizado por min--max. As
colunas com `quantizado` permanecem apenas para auditoria e nao sao usadas como
alvo nem como atributo dos modelos publicados.

Os arquivos `*_features_mensal.csv` sem `_v2` pertencem ao pipeline anterior:
usam poucas defasagens e transformacoes discretizadas. Foram preservados para
rastreabilidade, mas nao podem ser usados para reproduzir, interpretar ou
atualizar o TCC e os artigos atuais.

Os arquivos diarios `*_features.csv` tambem sao artefatos de outro protocolo e
nao passaram pela mesma auditoria integrada do experimento mensal.
