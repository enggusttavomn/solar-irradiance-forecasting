# Vídeo do relatório EA019

## Versão 5 — materiais e cores naturais

Saída: `documentacao/relatorio_final_ea019/video/completo_v5/`.
O player local é `assistir_video_v5.html`. O conteúdo, os 415 segundos e as
75 legendas são preservados da V4. A fábrica foi reconstruída em escala
plausível, com cobertura de zinco, fachadas claras, vidro azul, docas,
veículos e vegetação. A referência horizontal continua tendo exatamente 1 m².
O Sol usa uma luz direcional e um marcador claro; a nuvem tem malha orgânica.

`natural_style_v5.py` separa superfícies, traços, marcadores e textos. A fábrica
usa EEVEE com materiais Principled e iluminação solar; os diagramas usam
Workbench fosco com cores mais cheias e sem brilho cromado. Câmeras, movimentos
e dados experimentais dos diagramas permanecem os da V4.

```powershell
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/delivery_v5.py'
& '.tools/blender/blender-4.5.14-windows-x64/blender.exe' --background --factory-startup -t 6 --python-exit-code 1 --python 'codigo_fonte/video_ea019/director_v5.py' -- --qa
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/qa_v5.py'
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/render_complete_v5.py'
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/qa_v5.py' --final
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/delivery_v5.py'
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/verify_delivery_v5.py'
```

O render pode ser dividido por manifestos parciais com `--render-only` e
`--manifest`. Em trabalhos paralelos, usar `--progress-file` distinto para
cada processo. Somente iniciar a composição integral depois que todos os
renders parciais terminarem. O player habilita os MP4s após a verificação.

## Histórico — versão 4

A versão 4 ocupa `documentacao/relatorio_final_ea019/video/completo_v4/`.
O player é `assistir_video_v4.html`. São 415 s de animação, sem cartões
institucionais ou filmagens do aluno, com câmeras em perspectiva e rótulos 3D.
A explicação de cada rede tem a tela individualmente e totaliza 75 s.

- `plan_v4.py` e `overlays_v4.py`: falas, 75 legendas e rótulos curtos dos
  primeiros capítulos, sem cabeçalhos ou rodapés.
- `common_v4.py`: materiais, rótulos orientados à câmera e movimentos.
- `scenes_story_v4.py`: fábrica, dados, tarefas e protocolo.
- `scenes_networks_v4.py`: LSTM, Transformer e Informer em 14 subfases.
- `scenes_analysis_v4.py`: quantização, MAE, resultados, limites e síntese.
- `director_v4.py`: construção dos 12 capítulos e amostras de enquadramento.
- `render_complete_v4.py`: render, composição e decodificação dos MP4s inteiros.
- `qa_v4.py`: composição das prévias ou contatos das amostras do MP4 final.
- `player_v4.py`: player local e índice dos quadros de verificação.

```powershell
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/plan_v4.py'
& '.tools/blender/blender-4.5.14-windows-x64/blender.exe' --background --factory-startup -t 6 --python-exit-code 1 --python 'codigo_fonte/video_ea019/director_v4.py' -- --qa
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/qa_v4.py'
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/render_complete_v4.py'
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/qa_v4.py' --final
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/player_v4.py'
```

Preservar os projetos durante um render ativo. Para alterações posteriores,
reconstruir apenas os capítulos alterados antes de reiniciar o montador.
Capítulos prontos e mais novos que seus `.blend` são reutilizados.

## Histórico — versão 3

A versão 3 foi a produção anterior, com 6min55s, 63 planos e 13 capítulos. Os arquivos
de entrega ficam em `documentacao/relatorio_final_ea019/video/completo_v3/`.
O player local é `assistir_video_completo.html`; `Abrir_video_completo.cmd`
abre essa página no navegador padrão. Os MP4s têm versões com e sem legendas
de fala; ambas preservam títulos, rótulos, unidades e resultados.

Não inclui voz sintética, gravações do aluno ou música. A narração do roteiro
e as legendas SRT acompanham a entrega; os tempos devem ser ajustados à voz real.
Os trechos em câmera serão acrescentados pelo aluno.

## Produção da versão 3

- `shot_plan_v3.py`: extrai a planilha original sem alterá-la.
- `director_v3.py`: constrói os 13 projetos Blender e aplica os tempos dos planos.
- `scenes_factory_v3.py`: fábrica ilustrativa, referência horizontal de 1 m²,
  radiação direta/difusa e passagem para a série temporal.
- `render_style_v3.py`: Workbench 8AA, materiais foscos e fundo `#07090D`, sem grade.
- `overlays_v3.py`: textos e barras de base zero com valores do relatório.
- `render_complete_v3.py`: renderiza os 12.450 quadros, une os capítulos,
  compõe as duas versões, decodifica os MP4s completos e extrai 63 amostras.
- `build_delivery_v3.py`: página local, roteiro por capítulo e arquivos de apoio.
- `qa_delivery_v3.py`: contatos dos 63 quadros finais e verificação dos links.

Executar na raiz do projeto, no PowerShell:

```powershell
# Preparar projetos editáveis; --qa também gera amostras antes do render longo.
& '.tools/blender/blender-4.5.14-windows-x64/blender.exe' --background --factory-startup -t 6 --python-exit-code 1 --python 'codigo_fonte/video_ea019/director_v3.py' -- --qa
# Renderizar, compor e verificar. Capítulos concluídos mais novos que seus .blend são reutilizados.
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/render_complete_v3.py'
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/build_delivery_v3.py'
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/qa_delivery_v3.py'
```

O progresso fica em `completo_v3/progresso_render_v3.json`. A verificação final
exige 415 s, 1920×1080, 30 fps, H.264/yuv420p, 12.450 quadros e ausência de áudio.
O JSON `verificacao_video_completo_v3.json` só é escrito ao concluir ambos os
MP4s e as amostras. Contatos e estatísticas não substituem revisão visual.

## Histórico — piloto e versão 2

Os arquivos e comandos abaixo documentam as etapas anteriores. O piloto é uma
demonstração condensada de 30 segundos; a entrega atual usa `completo_v3/`.

## Arquivos

- `blender_pilot.py`: cena 3D e animação no Blender 4.5 LTS/EEVEE.
- `overlays.py`: títulos e legendas em ASS, separados da renderização 3D.
- `compose_pilot.py`: composição de MP4 com e sem legendas e verificação.
- `scenes_models.py`: elementos para as futuras cenas de arquiteturas e
  quantização; ainda precisam de revisão em render antes do vídeo completo.
- `scenes_map.py`: costa Natural Earth e coordenadas reais das dez localidades;
  históricos ilustrativos e os dois tipos de entrada.
- `scenes_explainer.py`: demais elementos didáticos, janelas e painéis.
- `blender_full.py`: prepara e renderiza os 13 capítulos separadamente.
- `compose_full.py`: une capítulos concluídos, aplica texto e verifica o vídeo
  completo. Não funciona como substituto dos renders ainda pendentes.

## Runtime local

O runtime portátil está isolado em `.tools`; não depende do Python quebrado da
`.venv` nem altera as dependências científicas do projeto.

- Blender: `.tools/blender/blender-4.5.14-windows-x64/blender.exe`.
- FFmpeg: `.tools/video-python/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe`.
- Python de composição: `.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe`.
- Fontes: Segoe UI e Segoe UI Bold do Windows, identificadas por DirectWrite.
- Download/checksum e testes: `tmp/video_runtime/runtime_manifest.json`.

## Reproduzir o piloto

Executar na raiz do projeto, no PowerShell:

```powershell
& '.tools/blender/blender-4.5.14-windows-x64/blender.exe' --background --factory-startup -t 6 --python-exit-code 1 --python 'codigo_fonte/video_ea019/blender_pilot.py' -- --output-dir 'documentacao/relatorio_final_ea019/video/piloto_v1' --samples 16 --stills 240 510 840 --render
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/compose_pilot.py'
```

A composição mantém os títulos na versão sem legendas. O render interno
`sem_textos.mp4` é somente a camada 3D, anterior à composição.

## Verificação

Cada MP4 final deve ter 1920×1080, H.264/yuv420p, 30 fps, 900 quadros e duração
de 30 s. A composição decodifica todos os quadros para detectar erros, registra
SHA256 e extrai amostras para revisão visual. A revisão visual também deve
conferir o movimento e a transição; metadados sozinhos não comprovam qualidade.

As legendas do piloto são demonstrações condensadas. As falas e os tempos do
vídeo completo permanecem em `documentacao/relatorio_final_ea019/video/trecho_animado_v2/`.

## Produção completa

Os capítulos preparados ficam em `trecho_animado_v2/producao/`. Preparar um
`.blend` confirma que o código constrói a cena; não equivale a renderizar ou
revisar seu movimento. Conferir quadros de cada capítulo antes do render longo.

```powershell
# Somente preparar os projetos, sem renderização:
& '.tools/blender/blender-4.5.14-windows-x64/blender.exe' --background --factory-startup -t 6 --python-exit-code 1 --python 'codigo_fonte/video_ea019/blender_full.py' --
# Para renderizar uma cena revisada, incluir --index e --render:
& '.tools/blender/blender-4.5.14-windows-x64/blender.exe' --background --factory-startup -t 6 --python-exit-code 1 --python 'codigo_fonte/video_ea019/blender_full.py' -- --index 7 --render
# Após concluir os treze capítulos:
& '.tools/python/cpython-3.12.16-windows-x86_64-none/python.exe' 'codigo_fonte/video_ea019/compose_full.py'
```

O mapa usa [Natural Earth, domínio público](https://www.naturalearthdata.com/about/terms-of-use/).
Os dois JSONs consumidos pela cena e sua proveniência ficam em `assets/`.
Os arquivos de download e o script de preparação inicial ficam em
`tmp/video_ea019_runtime/geodata/`. Os projetos `.blend` já preparados
contêm sua geometria.

Referências técnicas primárias: [Blender 4.5 LTS](https://www.blender.org/download/releases/4-5/),
[linha de comando](https://docs.blender.org/manual/en/4.5/advanced/command_line/index.html)
e [migração do EEVEE/compositor](https://developer.blender.org/docs/release_notes/4.2/eevee_migration/).
