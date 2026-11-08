"""Prepare the V5 documents and build a local player after verified rendering.

Only new V5 output is written. Existing V5 plans are preserved on normal runs,
so late annotation adjustments are not replaced while the film is rendering.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

try:
    from .player_v4 import STYLE
except ImportError:
    from player_v4 import STYLE

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"documentacao/relatorio_final_ea019/video/completo_v4"
OUTPUT=ROOT/"documentacao/relatorio_final_ea019/video/completo_v5"
VIDEO_WITH="Video_TCC_GHI_6min55_com_legendas_v5.mp4"
VIDEO_WITHOUT="Video_TCC_GHI_6min55_sem_legendas_v5.mp4"
PLAN="plano_video_v5.json"
REPORT="verificacao_video_v5.json"


def clock(seconds):
    return f"{int(seconds)//60}:{int(seconds)%60:02d}"


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")


def prepare(output=OUTPUT,refresh=False):
    output=Path(output).resolve()
    if not output.is_relative_to(ROOT.resolve()):
        raise ValueError("V5 output must stay inside the project workspace")
    output.mkdir(parents=True,exist_ok=True)
    source_plan=json.loads((SOURCE/"plano_video_v4.json").read_text(encoding="utf-8-sig"))
    target=output/PLAN
    if refresh or not target.is_file():
        plan=json.loads(json.dumps(source_plan,ensure_ascii=False))
        plan["version"]="v5"
        plan["derived_from_plan"]=str(SOURCE/"plano_video_v4.json")
        plan["appearance_revision"]={
            "requested_direction":"Materiais e iluminação mais naturais, cores mais vivas e fundo preto.",
            "content_and_timing_source":"v4", "factory_geometry_revision":True,
            "camera_footage_included":False,
        }
        for chapter in plan['chapters']:
            if chapter['id']==2:
                for event in chapter['label_events']:
                    if 4 <= event.get('start_local',event['start']) < 12 and event.get('end_local',event['end']) <= 12:
                        event['color']='263945'
                        event['size']=max(42,event['size'])
        target.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    plan=json.loads(target.read_text(encoding="utf-8-sig"))
    # Check the scientific content and timings before copying supporting files.
    assert plan["duration"]==415 and len(plan["chapters"])==12
    assert [c["id"] for c in plan["chapters"]]==list(range(2,14))
    assert canonical(plan["cues"])==canonical(source_plan["cues"]),"V5 caption text/timing changed"
    assert [(c["id"],c["start"],c["end"],c["narration"]) for c in plan["chapters"]]==[
        (c["id"],c["start"],c["end"],c["narration"]) for c in source_plan["chapters"]],"V5 narration/timing changed"
    for old,new in [("Falas_para_narrar_video_v4.txt","Falas_para_narrar_video_v5.txt"),
                    ("Legendas_video_v4.srt","Legendas_video_v5.srt")]:
        destination=output/new
        if refresh or not destination.is_file():
            if old.endswith(".srt"):
                destination.write_bytes((SOURCE/old).read_bytes())
            else:
                speech=(SOURCE/old).read_text(encoding="utf-8-sig")
                speech=speech.replace("— V4","— V5",1)
                destination.write_text(speech,encoding="utf-8-sig")
    return plan,{
        "plan":str(target),"chapters":len(plan["chapters"]),"duration_seconds":415,
        "cues":len(plan["cues"]),"cue_sha256":hashlib.sha256(canonical(plan["cues"])).hexdigest(),
        "same_cues_as_v4":True,"same_narration_and_timing_as_v4":True,
        "srt_byte_identical_to_v4":(output/"Legendas_video_v5.srt").read_bytes()==(SOURCE/"Legendas_video_v4.srt").read_bytes(),
    }


def verified_ready(output):
    """Reject stale version reports, partial MP4s and foreign output paths."""
    report_path=output/REPORT
    try:
        report=json.loads(report_path.read_text(encoding="utf-8-sig"))
        if (str(report.get("version")).lower().lstrip("v")!="5" or report.get("status")!="complete"
            or report.get("duration_seconds")!=415 or report.get("frame_count")!=12450
            or report.get("full_decode_errors")!=0):
            return False
        entries=report["files"]
        if len(entries)!=2:
            return False
        found=set()
        for entry in entries:
            declared=Path(entry["path"])
            path=declared.resolve() if declared.is_absolute() else (ROOT/declared).resolve()
            if path.parent!=output.resolve() or path.name not in (VIDEO_WITH,VIDEO_WITHOUT):
                return False
            if not path.is_file() or path.stat().st_size<=0 or path.stat().st_size!=entry["bytes"]:
                return False
            if entry.get("full_decode_errors")!=0:
                return False
            found.add(path.name)
        return found=={VIDEO_WITH,VIDEO_WITHOUT}
    except (OSError,UnicodeError,json.JSONDecodeError,KeyError,TypeError,ValueError):
        return False


def qa_index(output):
    folder=output/"verificacao_final"
    folder.mkdir(exist_ok=True)
    images=sorted(folder.glob("*.png"))
    cards=[]
    for image in images:
        name=html.escape(image.name,quote=True)
        cards.append(f'<figure><a href="{name}"><img src="{name}" alt="{name}" loading="lazy"></a><figcaption>{name}</figcaption></figure>')
    content="\n".join(cards) or '<p class="intro">Os quadros extraídos do MP4 final aparecerão aqui após a renderização e a verificação.</p>'
    target=folder/"indice_qa_v5.html"
    target.write_text('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Quadros de verificação V5</title><style>'+STYLE+'</style></head><body><main><a href="../assistir_video_v5.html">Voltar ao vídeo</a><h1>Quadros de verificação</h1><p class="intro">'+str(len(images))+' imagens disponíveis.</p><div class="qa-grid">'+content+'</div></main></body></html>',encoding="utf-8")
    return target,len(images)


def write_player(output=OUTPUT):
    output=Path(output).resolve()
    plan=json.loads((output/PLAN).read_text(encoding="utf-8-sig"))
    chapters=plan["chapters"]
    ready=verified_ready(output)
    index,image_count=qa_index(output)
    buttons=[]
    for chapter in chapters:
        buttons.append(f'<button class="chapter" type="button" data-time="{chapter["start"]}" data-id="{chapter["id"]}"><span>{clock(chapter["start"])}</span>{html.escape(chapter["title"])}</button>')
    phases=[("LSTM",170),("Transformer",194),("Informer",220)]
    phase_buttons="".join(f'<button type="button" data-seek="{second}">{name} · {clock(second)}</button>' for name,second in phases)
    data=[{k:c[k] for k in ("id","start","end","title","narration")} for c in chapters]
    if ready:
        media=f'''<video id="player" controls preload="metadata" playsinline src="{VIDEO_WITH}"></video>
<div class="controls"><button type="button" data-version="com" aria-pressed="true">Com legendas</button><button type="button" data-version="sem" aria-pressed="false">Sem legendas</button><label>Velocidade <select id="speed"><option value="0.75">0,75×</option><option value="1" selected>1×</option><option value="1.25">1,25×</option></select></label></div>
<p class="state" id="state">Com legendas embutidas. A versão sem legendas preserva os nomes, unidades e valores das animações.</p>'''
        downloads=f'<a href="{VIDEO_WITH}" download>Baixar MP4 com legendas</a><a href="{VIDEO_WITHOUT}" download>Baixar MP4 sem legendas</a>'
        state_tag="Vídeo renderizado e verificado"
        intro="A versão completa com materiais e iluminação mais naturais, cores vivas e fundo preto. Está sem áudio para receber sua narração; suas filmagens de abertura e encerramento entram depois."
    else:
        media='''<section class="production" role="status"><strong>V5 em produção</strong><p>A nova versão está sendo preparada. O player e os downloads serão habilitados após a conclusão e a verificação dos dois MP4s.</p></section><p class="state" id="state">Você já pode consultar as falas e o roteiro por capítulo.</p>'''
        downloads=""
        state_tag="Em produção"
        intro="Esta revisão mantém o conteúdo e os tempos da V4 e trabalha os materiais, a iluminação, as cores e a fábrica para deixar o 3D mais natural."
    links='<a href="../../Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.pdf">Relatório final</a> · <a href="'+PLAN+'">Planejamento</a> · <a href="verificacao_final/indice_qa_v5.html">Quadros de verificação</a>'
    if ready:
        links+=' · <a href="'+REPORT+'">Verificação do vídeo</a>'
        if (output/"verificacao_entrega_v5.json").is_file():
            links+=' · <a href="verificacao_entrega_v5.json">Verificação da entrega</a>'
    document='''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vídeo TCC · 6min55s · V5</title><style>'''+STYLE+'''
.production{padding:36px;margin:24px 0;background:#11161c;border:1px solid #303943;border-radius:9px}.production strong{font-size:25px;color:#E9B95F}.production p{color:#A9B2BE;max-width:840px}
</style></head><body><main><header><div class="eyebrow">Gustavo de Melo Nascimento · UNICAMP / FEEC</div><h1>Previsão de irradiância solar.</h1><p class="intro">'''+intro+'''</p><div class="tags"><span>'''+state_tag+'''</span><span>6min55s</span><span>1920 × 1080</span><span>30 fps</span><span>12 capítulos</span><span>Sem áudio</span></div></header>
'''+media+'''
<div class="downloads">'''+downloads+'''<a href="Legendas_video_v5.srt" download>Legendas SRT</a><a href="Falas_para_narrar_video_v5.txt">Falas para narrar</a></div>
<section class="script" aria-label="Roteiro do capítulo atual"><small>Fala para narrar o capítulo atual</small><h2 id="scene-title"></h2><p id="speech"></p></section>
<h2>'''+("Ir para um capítulo" if ready else "Consultar um capítulo")+'''</h2><nav class="chapters" aria-label="Capítulos do vídeo">'''+"".join(buttons)+'''</nav>
<p class="note">Na explicação das redes:</p><div class="phase-links">'''+phase_buttons+'''</div>
<p class="note">As legendas seguem as falas planejadas. A sincronização final poderá acompanhar o ritmo da sua gravação.</p><footer>'''+links+'''</footer></main><script>
const chapters='''+json.dumps(data,ensure_ascii=False).replace("</","<\\/")+''';
const ready='''+json.dumps(ready)+''';
const versions={com:'''+json.dumps(VIDEO_WITH)+''',sem:'''+json.dumps(VIDEO_WITHOUT)+'''};
const player=document.getElementById('player');
const title=document.getElementById('scene-title');
const speech=document.getElementById('speech');
const state=document.getElementById('state');
let selectedTime=0;
function updateScene(){const t=player?(player.currentTime||0):selectedTime;const chapter=chapters.find(c=>t>=c.start&&t<c.end)||chapters[chapters.length-1];title.textContent=chapter.title;speech.textContent=chapter.narration;document.querySelectorAll('.chapter').forEach(b=>b.classList.toggle('active',Number(b.dataset.id)===chapter.id));}
function seekTo(t){selectedTime=t;if(!player){updateScene();return;}if(player.readyState>0){player.currentTime=t;updateScene();}else{player.addEventListener('loadedmetadata',()=>{player.currentTime=t;updateScene();},{once:true});player.load();}}
document.querySelectorAll('.chapter').forEach(button=>button.addEventListener('click',()=>seekTo(Number(button.dataset.time))));
document.querySelectorAll('[data-seek]').forEach(button=>button.addEventListener('click',()=>seekTo(Number(button.dataset.seek))));
if(player){player.addEventListener('timeupdate',updateScene);player.addEventListener('loadedmetadata',updateScene);document.getElementById('speed').addEventListener('change',event=>{player.playbackRate=Number(event.target.value);});document.querySelectorAll('[data-version]').forEach(button=>button.addEventListener('click',()=>{const t=player.currentTime||0;const playing=!player.paused;const rate=player.playbackRate;const version=button.dataset.version;player.pause();document.querySelectorAll('[data-version]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));player.addEventListener('loadedmetadata',()=>{player.currentTime=Math.min(t,player.duration||415);player.playbackRate=rate;if(playing)player.play().catch(()=>{});},{once:true});player.src=versions[version];player.load();state.textContent=version==='com'?'Com legendas embutidas.':'Sem legendas de fala; nomes, unidades e valores preservados.';}));}
updateScene();
</script></body></html>'''
    target=output/"assistir_video_v5.html"
    target.write_text(document,encoding="utf-8")
    (output/"Abrir_video_v5.cmd").write_text('@echo off\nstart "" "%~dp0assistir_video_v5.html"\n',encoding="ascii")
    _readme(output,ready)
    return {"player":str(target),"render_ready":ready,"qa_index":str(index),"qa_images":image_count,
            "duration_seconds":415,"chapter_count":12,"network_starts":{"LSTM":170,"Transformer":194,"Informer":220}}


def _readme(output,ready):
    state="Renderização completa e verificada." if ready else "V5 em produção. Os MP4s ainda não foram declarados prontos pelo montador."
    text=f'''VÍDEO DO TCC — V5

{state}

Abrir Abrir_video_v5.cmd ou assistir_video_v5.html no navegador.
O player só habilita os vídeos depois da verificação final dos dois arquivos.

ARQUIVOS
{VIDEO_WITH}
{VIDEO_WITHOUT}
Falas_para_narrar_video_v5.txt
Legendas_video_v5.srt
plano_video_v5.json

Duração de referência: 6min55s. Full HD, 30 fps, 12.450 quadros. Sem áudio.
LSTM: 2:50; Transformer: 3:14; Informer: 3:40.
Os 12 capítulos e as 75 legendas preservam os tempos e as falas da V4.
Suas gravações de abertura, encerramento e narração entram depois.

DIREÇÃO DESTA REVISÃO
Materiais e iluminação mais naturais, cores mais vivas, fábrica reconstruída
e fundo preto. A dinâmica e o conteúdo científico seguem a V4. A fábrica,
o Sol, as curvas de explicação e os estados internos das redes são recursos
visuais didáticos; não são medições ou ativações extraídas dos experimentos.
Os resultados numéricos permanecem os do relatório final.

VERIFICAÇÃO
verificacao_video_v5.json é produzido pelo montador após exportar e decodificar
ambos os MP4s completos. verificacao_entrega_v5.json confere arquivos, hashes,
tempos, legendas, amostras e links; não aprova o visual automaticamente.
Os quadros extraídos do MP4 final ficam em verificacao_final/.
O relatório e os vídeos V4 foram preservados.
'''
    (output/"LEIA-ME_VIDEO_V5.txt").write_text(text,encoding="utf-8-sig")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=OUTPUT)
    parser.add_argument("--refresh-plan",action="store_true",help="Explicitly recopy the V4 plan and narration into V5.")
    args=parser.parse_args()
    _,prepared=prepare(args.output_dir,refresh=args.refresh_plan)
    player=write_player(args.output_dir)
    print(json.dumps({"preparation":prepared,"player":player},ensure_ascii=True,indent=2),flush=True)


if __name__=="__main__":
    main()
