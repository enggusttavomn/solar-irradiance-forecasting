# Passagem para continuação no Codex/VS Code

## Estado publicado

- Repositório: `enggusttavomn/TCC`
- Branch de trabalho: `codex/finalizacao-artigo-unificado`
- Commit científico consolidado antes desta passagem: `86fc38ec7b55962662bc9038e0a8003908779eab`
- A branch `main` foi preservada para recuperação; continue pela branch acima.

## O que está concluído

As quatro avaliações multirresolução foram concluídas e validadas:

| Tarefa | Estado |
|---|---|
| Mensal, horizonte 1 | concluída |
| Mensal, horizonte 6 | concluída |
| Horária, extensão 72 h | concluída |
| Diária, horizonte 30 dias | concluída e `resultado_publicavel: true` |

A tarefa diária contém as 10 localidades, cinco sementes (`11, 23, 42, 67, 89`) e os 20 pares modelo/semente. As épocas escolhidas foram:

- TimesNet: semente 11 já existente; sementes 23/42/67/89 = 4/3/4/4 épocas.
- DilatedRNN: sementes 11/23/42/67/89 = 24/30/29/24/23 épocas.

Também estão versionados:

- caches e modelos finais;
- métricas macro e por localidade;
- comparações pareadas e variabilidade entre sementes;
- protocolos, auditorias, escalas, hiperparâmetros e manifestos;
- coordenador de retomada paralela;
- correções de portabilidade de caminhos e manifestos.

Os dois arquivos grandes de previsões diárias foram armazenados em fragmentos rastreados pelo Git. O módulo `codigo_fonte/artefatos_fragmentados.py` os recompõe automaticamente e valida o SHA-256; isso evita o limite de tamanho sem perda de dados.

## O que ainda falta

A parte científica/experimental está concluída. A finalização editorial ainda precisa ser feita:

1. Executar novamente a suíte completa de testes após as últimas alterações. Os testes direcionados de fragmentação, portabilidade e sintaxe LaTeX passaram; a suíte completa anterior passou com 186 testes e 6 ignorados, mas não foi repetida depois do último conjunto de commits.
2. Gerar os artefatos finais do artigo unificado com `gerar_artefatos_artigo_unificado.py`.
3. Atualizar:
   - `overlief/artigo_revista_unificado/main.tex`;
   - `overlief/artigo_revista_unificado/main_ieee.tex`;
   - `overlief/artigo_revista_unificado/sections/07_results_and_discussion.tex`;
   - `overlief/artigo_revista_unificado/sections/09_conclusion.tex`.
4. Substituir todos os `\DraftNote` e resumos provisórios pelos números gerados.
5. Copiar/integrar tabelas e figuras geradas nas pastas `tables` e `figures` do artigo.
6. Compilar e revisar visualmente as versões Elsevier e IEEE.
7. Fazer o commit final e, somente após revisão, decidir se a branch será mesclada na `main`.

## Retomada no Windows/PowerShell

```powershell
cd "C:\Users\gm.nascimento\Documents\Meus Projetos\TCC"
git fetch origin
git switch codex/finalizacao-artigo-unificado
git pull origin codex/finalizacao-artigo-unificado
```

Se a branch ainda não existir localmente:

```powershell
git switch --track -c codex/finalizacao-artigo-unificado origin/codex/finalizacao-artigo-unificado
```

Depois, peça ao Codex do VS Code para ler primeiro este arquivo e continuar apenas a finalização editorial, sem repetir os treinamentos já concluídos.
