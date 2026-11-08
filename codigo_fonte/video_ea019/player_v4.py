"""Build the local V4 player and an index of existing final QA images."""
from __future__ import annotations

import html
import json
from pathlib import Path

try:
    from .plan_v4 import OUTPUT, clock
except ImportError:
    from plan_v4 import OUTPUT, clock

VIDEO_WITH="Video_TCC_GHI_6min55_com_legendas_v4.mp4"
VIDEO_WITHOUT="Video_TCC_GHI_6min55_sem_legendas_v4.mp4"

STYLE="""
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#07090D;color:#F3F5F7;font:16px/1.65 'Segoe UI',Arial,sans-serif}main{max-width:1220px;margin:auto;padding:40px 26px 64px}h1{font-size:clamp(32px,4.5vw,50px);line-height:1.2;letter-spacing:-1px;margin:10px 0 14px}.eyebrow{color:#A9B2BE;font-size:12px;letter-spacing:2px;text-transform:uppercase}.intro{color:#A9B2BE;max-width:960px}.tags,.controls,.downloads{display:flex;gap:9px;flex-wrap:wrap;margin:18px 0}.tags span{font-size:13px;border:1px solid #303943;border-radius:30px;padding:5px 12px}video{display:block;width:100%;aspect-ratio:16/9;background:#07090D;border:1px solid #303943;border-radius:9px;margin-top:24px}button,.downloads a,select{font:inherit;background:#171C22;border:1px solid #303943;border-radius:7px;padding:9px 13px;color:#F3F5F7;text-decoration:none;cursor:pointer}button[aria-pressed=true],.chapter.active{border-color:#58CADA;color:#58CADA;background:#10252b}.state{font-size:14px;color:#A9B2BE}.script{border-left:3px solid #E9B95F;background:#11161c;padding:23px 26px;margin-top:26px;border-radius:0 8px 8px 0}.script small{color:#A9B2BE}.script h2{font-size:22px;margin:8px 0 12px;line-height:1.3}.script p{font-size:18px;line-height:1.9;margin:0}h2{font-size:25px;margin-top:35px}.chapters{display:grid;grid-template-columns:1fr 1fr;gap:9px}.chapter{display:flex;align-items:center;text-align:left;gap:14px;padding:13px 15px}.chapter span{color:#A9B2BE;font-variant-numeric:tabular-nums;min-width:40px}.phase-links{display:flex;gap:9px;flex-wrap:wrap;margin-top:12px}.note{font-size:14px;color:#A9B2BE}a{color:#58CADA;text-underline-offset:4px}footer{border-top:1px solid #303943;margin-top:34px;padding-top:20px;color:#A9B2BE;font-size:14px}.qa-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.qa-grid img{display:block;width:100%;height:auto}.qa-grid figure{margin:0}.qa-grid figcaption{color:#A9B2BE;word-break:break-word}@media(max-width:760px){main{padding:25px 15px 45px}.chapters,.qa-grid{grid-template-columns:1fr}.script{padding:20px}.script p{font-size:17px}}
"""


def qa_index(folder):
    folder.mkdir(parents=True,exist_ok=True)
    images=sorted(folder.glob("*.png"))
    cards=[]
    for image in images:
        name=html.escape(image.name,quote=True)
        cards.append(f'<figure><a href="{name}"><img src="{name}" alt="{name}" loading="lazy"></a><figcaption>{name}</figcaption></figure>')
    content="\n".join(cards) or '<p class="intro">As imagens de verificação aparecerão aqui após a geração dos quadros finais. Execute novamente o montador desta página para atualizar o índice.</p>'
    target=folder/"indice_qa_v4.html"
    target.write_text('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Quadros de verificação V4</title><style>'+STYLE+'</style></head><body><main><a href="../assistir_video_v4.html">Voltar ao vídeo</a><h1>Quadros de verificação</h1><p class="intro">'+str(len(images))+' imagens disponíveis. Clique para abrir no tamanho original.</p><div class="qa-grid">'+content+'</div></main></body></html>',encoding="utf-8")
    return target,len(images)


def write_player(output=OUTPUT):
    output=Path(output)
    plan=json.loads((output/"plano_video_v4.json").read_text(encoding="utf-8"))
    chapters=plan["chapters"]
    assert len(chapters)==12 and chapters[0]["start"]==0 and chapters[-1]["end"]==415
    index,image_count=qa_index(output/"verificacao_final")
    buttons=[]
    for chapter in chapters:
        buttons.append(f'<button class="chapter" type="button" data-time="{chapter["start"]}" data-id="{chapter["id"]}"><span>{clock(chapter["start"])}</span>{html.escape(chapter["title"])}</button>')
    data=[{k:c[k] for k in ("id","start","end","title","narration")} for c in chapters]
    phases=chapters[5]["phases"]
    phase_buttons="".join(f'<button type="button" data-seek="{p["start"]}">{html.escape(p["id"])} · {clock(p["start"])}</button>' for p in phases)
    technical=output/"verificacao_video_completo_v4.json"
    technical_link=' · <a href="verificacao_video_completo_v4.json">Verificação técnica</a>' if technical.is_file() else ''
    document='''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vídeo TCC · 6min55s · V4</title><style>'''+STYLE+'''</style></head><body><main>
<header><div class="eyebrow">Gustavo de Melo Nascimento · UNICAMP / FEEC</div><h1>Previsão de irradiância solar.</h1><p class="intro">A parte animada completa, com a fábrica, os dados, as redes e os resultados. As redes recebem uma explicação mais detalhada. Esta montagem está sem áudio para receber sua narração; suas filmagens de abertura e encerramento podem entrar depois.</p><div class="tags"><span>6min55s</span><span>1920 × 1080</span><span>30 fps</span><span>12 capítulos</span><span>Sem áudio</span></div></header>
<video id="player" controls preload="metadata" playsinline src="'''+VIDEO_WITH+'''"></video>
<div class="controls"><button type="button" data-version="com" aria-pressed="true">Com legendas</button><button type="button" data-version="sem" aria-pressed="false">Sem legendas</button><label>Velocidade <select id="speed"><option value="0.75">0,75×</option><option value="1" selected>1×</option><option value="1.25">1,25×</option></select></label></div>
<p class="state" id="state">Com legendas embutidas. A versão sem legendas conserva os nomes, as unidades e os valores dentro das animações.</p>
<div class="downloads"><a href="'''+VIDEO_WITH+'''" download>Baixar MP4 com legendas</a><a href="'''+VIDEO_WITHOUT+'''" download>Baixar MP4 sem legendas</a><a href="Legendas_video_v4.srt" download>Legendas SRT</a><a href="Falas_para_narrar_video_v4.txt">Falas para narrar</a></div>
<section class="script" aria-label="Roteiro do capítulo atual"><small>Fala para narrar o capítulo atual</small><h2 id="scene-title"></h2><p id="speech"></p></section>
<h2>Ir para um capítulo</h2><nav class="chapters" aria-label="Capítulos do vídeo">'''+"".join(buttons)+'''</nav>
<p class="note">Na explicação das redes:</p><div class="phase-links">'''+phase_buttons+'''</div>
<p class="note">As legendas seguem as falas planejadas. A sincronização final poderá acompanhar o ritmo da sua gravação.</p>
<footer><a href="../../Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.pdf">Relatório final</a> · <a href="plano_video_v4.json">Planejamento</a> · <a href="verificacao_final/indice_qa_v4.html">Quadros de verificação</a>'''+technical_link+'''</footer>
</main><script>
const chapters='''+json.dumps(data,ensure_ascii=False).replace("</","<\\/")+''';
const versions={com:'''+json.dumps(VIDEO_WITH)+''',sem:'''+json.dumps(VIDEO_WITHOUT)+'''};
const player=document.getElementById('player');
const title=document.getElementById('scene-title');
const speech=document.getElementById('speech');
const state=document.getElementById('state');
function updateScene(){const t=player.currentTime||0;const chapter=chapters.find(c=>t>=c.start&&t<c.end)||chapters[chapters.length-1];title.textContent=chapter.title;speech.textContent=chapter.narration;document.querySelectorAll('.chapter').forEach(b=>b.classList.toggle('active',Number(b.dataset.id)===chapter.id));}
function seekTo(t){if(player.readyState>0){player.currentTime=t;updateScene();}else{player.addEventListener('loadedmetadata',()=>{player.currentTime=t;updateScene();},{once:true});player.load();}}
player.addEventListener('timeupdate',updateScene);player.addEventListener('loadedmetadata',updateScene);updateScene();
document.querySelectorAll('.chapter').forEach(button=>button.addEventListener('click',()=>seekTo(Number(button.dataset.time))));
document.querySelectorAll('[data-seek]').forEach(button=>button.addEventListener('click',()=>seekTo(Number(button.dataset.seek))));
document.getElementById('speed').addEventListener('change',event=>{player.playbackRate=Number(event.target.value);});
document.querySelectorAll('[data-version]').forEach(button=>button.addEventListener('click',()=>{const t=player.currentTime||0;const playing=!player.paused;const rate=player.playbackRate;const version=button.dataset.version;player.pause();document.querySelectorAll('[data-version]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));player.addEventListener('loadedmetadata',()=>{player.currentTime=Math.min(t,player.duration||415);player.playbackRate=rate;if(playing)player.play().catch(()=>{});},{once:true});player.src=versions[version];player.load();state.textContent=version==='com'?'Com legendas embutidas.':'Sem legendas de fala; os nomes, as unidades e os valores das animações permanecem.';}));
</script></body></html>'''
    target=output/"assistir_video_v4.html"
    target.write_text(document,encoding="utf-8")
    return {"player":str(target),"qa_index":str(index),"qa_images":image_count,
            "duration_seconds":415,"chapter_count":12,"first_chapter":2,
            "video_with_captions":VIDEO_WITH,"video_without_captions":VIDEO_WITHOUT}


if __name__=="__main__":
    print(json.dumps(write_player(),ensure_ascii=True,indent=2))
