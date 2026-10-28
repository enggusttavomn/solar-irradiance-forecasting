# Artigos e materiais de publicação

Os manuscritos e seus ativos estão consolidados neste diretório. Cada artigo
mantém suas próprias figuras e arquivos de compilação para evitar dependências
implícitas entre submissões.

| Conteúdo | Entrada principal | Estado |
|---|---|---|
| Artigo de revista unificado | [`revista_unificado/main.tex`](revista_unificado/main.tex) | manuscrito principal |
| Artigo IEEE | [`ieee/artigo.tex`](ieee/artigo.tex) | estudo horário de TimesNet |
| Artigo BTSym'26 | [`btsym26/main.tex`](btsym26/main.tex) | estudo mensal de DilatedRNN |
| Manuscrito MCSM | [`mcsm/artigo_ghi_iii_mcsm.tex`](mcsm/artigo_ghi_iii_mcsm.tex) | material histórico |
| Templates parametrizados | [`templates/`](templates/) | fontes internas dos geradores |

O fluxo automatizado com o Overleaf publica somente
`artigos/revista_unificado/` e somente quando alterações chegam à branch
`main`. Os demais manuscritos permanecem independentes.

Arquivos em `templates/` contêm marcadores e não são manuscritos prontos para
submissão. Resultados e números devem ser regenerados a partir das pastas
canônicas em `resultados/`, nunca copiados manualmente de execuções legadas.
