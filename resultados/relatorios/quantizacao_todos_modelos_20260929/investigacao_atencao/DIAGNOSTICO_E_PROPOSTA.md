# Diagnóstico dos controles de Transformer e Informer

Os quatro trabalhos terminaram o treinamento do controle sem quantização e pararam na conferência contra os controles antigos. Não houve erro de memória, dado ausente ou falha de treinamento nos logs examinados. A mensagem de auditoria pendente decorre de diferenças numéricas entre retreinamentos no **mesmo dispositivo CUDA**: `novo_controle_por_dispositivo=false` nos quatro casos. A política de migração CPU→CUDA permanece inaplicável.

## Evidências verificadas

- **36 checkpoints reproduzidos com diferença máxima zero**: 12 controles novos de seleção, 12 originais de seleção e 12 originais de refit. A tolerância de 1e-6 W/m² foi preservada.
- Cada inferência foi repetida sem restaurar RNG. As saídas permaneceram idênticas e o RNG global CUDA permaneceu inalterado. Os alvos foram substituídos por NaN durante o replay.
- O Informer usa gerador local com semente 0 na avaliação. Sua amostragem de avaliação não explica as diferenças entre os arquivos antigos e novos.
- Janelas, valores brutos, alvos, identidades, origens, normalização min-max e matrizes normalizadas foram comparados entre os executores antigo e novo nas fases de seleção/refit: igualdade exata.
- Configuração, lotes, sementes, taxa de aprendizado, regularização, paciência, máximo de épocas e épocas selecionadas são iguais. Estados iniciais dos executores também são idênticos.
- As fontes de arquitetura e executor GPU coincidem com os hashes originais. A única diferença em `experimento_multirresolucao.py` é o caminho textual do wrapper; reverter somente essa cadeia em memória reproduz exatamente o hash original. Nenhuma fonte foi editada.

## Onde a variabilidade aparece

Com os mesmos pesos, lote e RNG restaurado, o backend atual (`warn_only=True`) produziu saídas idênticas, mas gradientes ligeiramente diferentes entre repetições. O próprio PyTorch avisou sobre o algoritmo de backward de atenção não determinístico. Isso demonstra uma fonte de variabilidade durante o treinamento, enquanto a avaliação dos checkpoints é reproduzível.

As trajetórias antigas e novas começam com perdas muito próximas e terminam nas mesmas épocas selecionadas. No Informer, decisões discretas de top-k podem amplificar pequenas diferenças; isso é uma explicação plausível, não uma prova isolada de que esse componente explica toda a divergência pontual.

Os números abaixo são **MAEs de validação de 2023 de controles sem quantização**, no horizonte completo. Não são efeitos de quantização nem resultados novos do teste de 2024.

| Caso | Modelo | MAE antigo | MAE novo | Diferença |
|---|---|---:|---:|---:|
| Diário, 30 dias | Transformer | 44,469381 | 44,467647 | -0,001734 |
| Diário, 30 dias | Informer | 45,244231 | 45,242915 | -0,001316 |
| Horário, 72 horas | Transformer | 54,444250 | 54,435365 | -0,008885 |
| Horário, 72 horas | Informer | 131,067300 | 131,088022 | +0,020721 |

A maior diferença pontual bruta do Informer horário, 279,1758 W/m², não corresponde a uma mudança dessa magnitude no MAE agregado. Ainda assim, a reprodução exata do retreinamento antigo falhou e não foi aprovada por este diagnóstico.

## Proposta mínima, ainda não implementada

Nos quatro pares, três repetições do mesmo lote com `torch.use_deterministic_algorithms(True, warn_only=False)` tiveram **saídas e gradientes bitexatos** usando o backend automático. SDPA MATH estrito também passou. Portanto, a primeira candidata é tornar o determinismo estrito após cada chamada de `fixar_semente`, preservando a escolha automática de backend. Não há evidência de que seja necessário forçar MATH.

Antes de qualquer execução completa, validar essa candidata em duas pequenas execuções idênticas de treinamento, com múltiplos lotes e atualizações, verificando pesos, curvas e previsões. A sonda atual contém somente forward/backward, sem `optimizer.step`; ela não comprova sozinha a reprodução de toda a trajetória.

Se esse piloto passar, usar um adaptador versionado restrito aos quatro pares, mantendo arquitetura, dados, épocas, sementes, hiperparâmetros, min-max e quantização. Preservar os 12 checkpoints atuais e seus relatórios como diagnóstico; gerar novamente o controle e as três variantes sob a mesma configuração estrita. O motor ca56d204… e a política de seis migrações não precisam ser alterados. Os demais pares já concluídos permanecem utilizáveis.

Nenhum aceite, treinamento completo adicional ou alteração dos motores foi realizado por estes scripts.

## Artefatos

- `indice.json`: hashes dos quatro relatórios completos por par.
- `resumo_replays.json`: replay, repetição da avaliação, configuração, épocas e MAE.
- `sonda_determinismo_estrito.json`: três repetições por backend/par, sem atualização de pesos.
- `diferenca_fonte_multirresolucao.json`: demonstração do hash após reversão textual do caminho do wrapper, somente em memória.
- `metricas/`: comparação dos controles, sem emissão de aceite.
- Scripts `scripts/investigar_controles_atencao.py` e `scripts/sondar_determinismo_atencao.py`.
