"""Player local e documentação de entrega da versão completa, sem servidor."""
from pathlib import Path
import html
import json
import shutil

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v3'
PLAN=ROOT/'documentacao/relatorio_final_ea019/video/trecho_animado_v2/plano_trecho_animado_v2.json'


def main():
    plan=json.loads(PLAN.read_text(encoding='utf-8'))
    shots=json.loads((OUT/'plano_73_extraido.json').read_text(encoding='utf-8'))
    phases=plan['scenes']
    buttons=[]
    for part in phases:
        sec=part['start_seconds']
        label=f'{sec//60}:{sec%60:02d}'
        buttons.append(f'<button class="chapter" type="button" data-time="{sec}" data-id="{part["id"]}"><span>{label}</span>{html.escape(part["title"])}</button>')
    payload=json.dumps(phases,ensure_ascii=False).replace('</','<\\/')
    css='''
    :root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#07090D;color:#F3F5F7;font:16px/1.65 'Segoe UI',Arial,sans-serif}main{max-width:1220px;margin:auto;padding:40px 26px 64px}h1{font-size:clamp(32px,4.5vw,50px);line-height:1.2;letter-spacing:-1px;margin:10px 0 14px}.eyebrow{color:#A9B2BE;font-size:12px;letter-spacing:2px;text-transform:uppercase}.intro{color:#A9B2BE;max-width:920px}.tags,.controls,.downloads{display:flex;gap:9px;flex-wrap:wrap;margin:18px 0}.tags span{font-size:13px;border:1px solid #303943;border-radius:30px;padding:5px 12px}video{display:block;width:100%;aspect-ratio:16/9;background:#07090D;border:1px solid #303943;border-radius:9px;margin-top:24px}button,.downloads a,select{font:inherit;background:#171C22;border:1px solid #303943;border-radius:7px;padding:9px 13px;color:#F3F5F7;text-decoration:none;cursor:pointer}button[aria-pressed=true],.chapter.active{border-color:#58CADA;color:#58CADA;background:#10252b}.state{font-size:14px;color:#A9B2BE}.script{border-left:3px solid #E9B95F;background:#11161c;padding:23px 26px;margin-top:26px;border-radius:0 8px 8px 0}.script small{color:#A9B2BE;text-transform:uppercase;letter-spacing:1px}.script h2{font-size:22px;margin:8px 0 12px;line-height:1.3}.script p{font-size:18px;line-height:1.9;margin:0}h2{font-size:25px;margin-top:35px}.chapters{display:grid;grid-template-columns:1fr 1fr;gap:9px}.chapter{display:flex;align-items:center;text-align:left;gap:14px;padding:13px 15px}.chapter span{color:#A9B2BE;font-variant-numeric:tabular-nums;min-width:40px}.note{font-size:14px;color:#A9B2BE}a{color:#58CADA;text-underline-offset:4px}footer{border-top:1px solid #303943;margin-top:34px;padding-top:20px;color:#A9B2BE;font-size:14px}@media(max-width:760px){main{padding:25px 15px 45px}.chapters{grid-template-columns:1fr}.script{padding:20px}.script p{font-size:17px}}
    '''
    page=f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vídeo completo EA019 · 6min55s</title><style>{css}</style></head><body><main>
    <header><div class="eyebrow">Gustavo de Melo Nascimento · UNICAMP / FEEC · EA019</div><h1>Previsão de irradiância solar.</h1><p class="intro">Vídeo completo da parte animada: apresentação do trabalho, fábrica, dados, três modelos e resultados. A versão atual está sem áudio para receber sua narração; suas filmagens de abertura e encerramento entram depois.</p><div class="tags"><span>6min55s</span><span>1920 × 1080</span><span>30 fps</span><span>63 planos</span><span>Sem áudio</span></div></header>
    <video id="player" controls preload="metadata" playsinline poster="verificacao_final/P08.png" src="Video_TCC_GHI_6min55_com_legendas_v3.mp4"></video>
    <div class="controls"><button type="button" data-version="com" aria-pressed="true">Com legendas</button><button type="button" data-version="sem" aria-pressed="false">Sem legendas</button><label>Velocidade <select id="speed"><option value="0.75">0,75×</option><option value="1" selected>1×</option><option value="1.25">1,25×</option></select></label></div>
    <p class="state" id="state">Com legendas embutidas. A versão sem legendas conserva títulos, rótulos e valores dos gráficos.</p>
    <div class="downloads"><a href="Video_TCC_GHI_6min55_com_legendas_v3.mp4" download>Baixar MP4 com legendas</a><a href="Video_TCC_GHI_6min55_sem_legendas_v3.mp4" download>Baixar MP4 sem legendas</a><a href="Legendas_video_completo_v3.srt" download>Legendas SRT</a><a href="Falas_para_narrar_video_completo_v3.txt">Falas para narrar</a></div>
    <section class="script" aria-label="Roteiro da cena atual"><small>Fala de referência do capítulo atual</small><h2 id="scene-title"></h2><p id="speech"></p></section>
    <h2>Ir para um capítulo</h2><nav class="chapters" aria-label="Capítulos do vídeo">{''.join(buttons)}</nav>
    <p class="note">Os tempos das legendas seguem o roteiro planejado. Ao gravar, podemos ajustar pausas, trechos do áudio e duração de cenas para fechar a sincronização.</p>
    <footer><p>A fábrica e as curvas didáticas são ilustrações. Os resultados vêm dos dados consolidados do relatório. GHI é potência solar por área horizontal, em W/m²; o vídeo não apresenta medições dentro das fábricas.</p><p><a href="../../Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.pdf">Relatório final</a> · <a href="Planejamento_completo_video_TCC.xlsx">Planilha dos 73 planos</a> · <a href="verificacao_video_completo_v3.json">Verificação técnica</a></p></footer>
    </main><script>
    const scenes={payload};
    const player=document.getElementById('player');
    const title=document.getElementById('scene-title');
    const speech=document.getElementById('speech');
    const state=document.getElementById('state');
    function updateScene(){{const t=player.currentTime||0;const part=scenes.find(s=>t>=s.start_seconds&&t<s.end_seconds)||scenes[scenes.length-1];title.textContent=part.title;speech.textContent=part.narration;document.querySelectorAll('.chapter').forEach(b=>b.classList.toggle('active',Number(b.dataset.id)===part.id));}}
    player.addEventListener('timeupdate',updateScene);player.addEventListener('loadedmetadata',updateScene);updateScene();
    document.querySelectorAll('.chapter').forEach(button=>button.addEventListener('click',()=>{{player.currentTime=Number(button.dataset.time);updateScene();}}));
    document.getElementById('speed').addEventListener('change',event=>{{player.playbackRate=Number(event.target.value);}});
    document.querySelectorAll('[data-version]').forEach(button=>button.addEventListener('click',()=>{{const t=player.currentTime||0;const playing=!player.paused;const rate=player.playbackRate;const version=button.dataset.version;document.querySelectorAll('[data-version]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));player.src=version==='com'?'Video_TCC_GHI_6min55_com_legendas_v3.mp4':'Video_TCC_GHI_6min55_sem_legendas_v3.mp4';player.addEventListener('loadedmetadata',()=>{{player.currentTime=Math.min(t,player.duration||415);player.playbackRate=rate;if(playing)player.play();}},{{once:true}});state.textContent=version==='com'?'Com legendas embutidas.':'Sem legendas de fala; títulos e rótulos preservados.';}}));
    </script></body></html>'''
    OUT.mkdir(exist_ok=True)
    (OUT/'assistir_video_completo.html').write_text(page,encoding='utf-8')
    (OUT/'Abrir_video_completo.cmd').write_text('@echo off\nstart "" "%~dp0assistir_video_completo.html"\n',encoding='ascii')
    (ROOT/'ASSISTIR_VIDEO_TCC.cmd').write_text('@echo off\nstart "" "%~dp0documentacao\\relatorio_final_ea019\\video\\completo_v3\\assistir_video_completo.html"\n',encoding='ascii')
    narration_path=OUT/'Falas_para_narrar_video_completo_v3.txt'
    if narration_path.is_file():
        narration=narration_path.read_text(encoding='utf-8-sig')
        narration=narration.replace('FALAS — TRECHO ANIMADO DO TCC — V2','FALAS — VÍDEO COMPLETO DO TRECHO ANIMADO — V3',1)
        narration_path.write_text(narration,encoding='utf-8-sig')
    source=Path(shots['source_xlsx'])
    if source.is_file():
        shutil.copy2(source,OUT/'Planejamento_completo_video_TCC.xlsx')
    readme='''VÍDEO COMPLETO DO TRECHO ANIMADO — EA019 — VERSÃO 3

Para assistir: abrir Abrir_video_completo.cmd ou assistir_video_completo.html.
Também é possível abrir diretamente Video_TCC_GHI_6min55_com_legendas_v3.mp4.

Escopo: 6min55s, 63 planos, 13 capítulos, 12.450 quadros em 1920×1080/30fps.
Não há voz sintética, música nem filmagens do aluno nesta versão. O arquivo
está preparado para receber a narração e, depois, a abertura/conclusão em câmera.

Com legendas: texto de fala incorporado ao MP4.
Sem legendas: preserva títulos, rótulos, unidades e dados dos gráficos.
SRT: Legendas_video_completo_v3.srt.
Falas: Falas_para_narrar_video_completo_v3.txt.

Mudanças desta versão: fundo #07090D sem grade decorativa; fábrica ilustrativa
fosca e telhado com referência de 1 m²; curvas e diagramas nos tempos da planilha;
resultados com barras frontais de base zero e valores reais; legendas discretas.

A planilha original foi preservada e uma cópia está nesta pasta. As cenas
editáveis ficam em cenas/. O código está em codigo_fonte/video_ea019/ na raiz
do projeto. Renderização 3D no Blender/Workbench 8AA; composição FFmpeg/libass.

O relatório e os resultados científicos não foram alterados. As curvas didáticas
são identificadas como ilustração. A GHI não equivale diretamente a geração
fotovoltaica, consumo industrial ou ganho financeiro.

O relatório técnico verificacao_video_completo_v3.json é gerado somente depois
que ambos os MP4s foram concluídos e decodificados integralmente.
'''
    (OUT/'LEIA-ME_VIDEO_COMPLETO.txt').write_text(readme,encoding='utf-8-sig')
    print(str(OUT/'assistir_video_completo.html'))


if __name__=='__main__':
    main()
