"""Build the 415-second V4 cut, its narration and contiguous Portuguese SRT."""
from __future__ import annotations

import json
from pathlib import Path
import re
import textwrap

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "documentacao/relatorio_final_ea019/video"
OUTPUT = BASE / "completo_v4"
SOURCE = BASE / "trecho_animado_v2/plano_trecho_animado_v2.json"

TIMINGS = {2:(0,35),3:(35,20),4:(55,40),5:(95,35),6:(130,40),
           7:(170,75),8:(245,35),9:(280,30),10:(310,60),
           11:(370,20),12:(390,15),13:(405,10)}

NETWORK_PHASES = [
    {"id":"LSTM","start_local":0,"end_local":24,
     "narration":"Cada ponto desta sequência representa um valor passado de GHI. Na LSTM, os dados entram em ordem. A rede mantém uma memória e usa portas aprendidas para controlar o que esquece, o que acrescenta e o que transmite. Assim, a memória é atualizada a cada passo e ajuda a formar a previsão."},
    {"id":"Transformer","start_local":24,"end_local":50,
     "narration":"No Transformer, cada posição é representada junto com sua ordem temporal. A atenção compara representações da sequência e calcula pesos. Esses pesos orientam a combinação dos valores, permitindo reunir informações de posições diferentes. As conexões e intensidades aqui são didáticas: não exibem pesos medidos neste estudo."},
    {"id":"Informer","start_local":50,"end_local":75,
     "narration":"O Informer seleciona algumas posições de consulta para um cálculo de atenção mais detalhado. Em outra etapa, reduz o comprimento das representações entre camadas do codificador. A atenção cruzada continua completa. Nos três modelos, usamos histórico de GHI e identificação da localidade para produzir diretamente um vetor de valores futuros. Comparamos precisão; velocidade e memória não foram medidas."},
]


def clock(seconds):
    minutes, sec = divmod(int(seconds),60)
    return f"{minutes}:{sec:02d}"


def stamp(seconds):
    milliseconds=round(seconds*1000)
    hours,milliseconds=divmod(milliseconds,3600000)
    minutes,milliseconds=divmod(milliseconds,60000)
    sec,milliseconds=divmod(milliseconds,1000)
    return f"{hours:02d}:{minutes:02d}:{sec:02d},{milliseconds:03d}"


def caption_blocks(text):
    """Wrap complete words; at most two 42-character lines per cue."""
    lines=textwrap.wrap(text,width=42,break_long_words=False,break_on_hyphens=False)
    blocks=["\n".join(lines[i:i+2]) for i in range(0,len(lines),2)]
    # Avoid an isolated final word becoming a sub-second subtitle. Rebalance
    # the last pair without changing a single spoken word.
    if len(blocks)>1 and len(blocks[-1].replace("\n"," "))<30:
        words=(blocks[-2]+" "+blocks[-1]).split()
        candidates=[]
        for cut in range(1,len(words)):
            left=" ".join(words[:cut]); right=" ".join(words[cut:])
            ll=textwrap.wrap(left,width=42,break_long_words=False,break_on_hyphens=False)
            rr=textwrap.wrap(right,width=42,break_long_words=False,break_on_hyphens=False)
            if len(ll)<=2 and len(rr)<=2:
                candidates.append((abs(len(left)-len(right)),"\n".join(ll),"\n".join(rr)))
        if candidates:
            _,left,right=min(candidates)
            blocks[-2:]=[left,right]
    assert all(len(b.splitlines())<=2 and max(map(len,b.splitlines()))<=42 for b in blocks)
    assert " ".join(" ".join(blocks).split())==" ".join(text.split())
    return blocks


def timed_cues(text,start,end,chapter,phase=None):
    blocks=caption_blocks(text)
    weights=[len(re.sub(r"\s+"," ",b))+(8 if b.endswith((".",";",":")) else 0) for b in blocks]
    total=sum(weights)
    cues=[]
    elapsed=0
    for block,weight in zip(blocks,weights):
        a=round(start+(end-start)*elapsed/total,3)
        elapsed+=weight
        b=round(start+(end-start)*elapsed/total,3)
        cue={"start":a,"end":b,"duration":round(b-a,3),"text":block,"chapter":chapter}
        if phase:
            cue["phase"]=phase
        cues.append(cue)
    assert cues[0]["start"]==start and cues[-1]["end"]==end
    return cues


def label(chapter,a,b,text,x,y,size=40,color="F3F5F7",align=7,available=1700):
    start=TIMINGS[chapter][0]
    return {"start":start+a,"end":start+b,"start_local":a,"end_local":b,
            "text":text,"x":x,"y":y,"size":size,"color":color,
            "align":align,"available":available}


def short_labels(chapter):
    """Only labels needed to read the otherwise native 3D explanation."""
    if chapter==2:
        return [
            label(2,0,4,"GHI",1500,240,54,"E9B95F",available=300),
            label(2,4,9,"Horizontal",500,240,40,align=8),
            label(2,4,9,"1 m²",1500,240,48,"E9B95F",available=300),
            label(2,9,12,"W/m²",1500,240,54,"E9B95F",available=300),
            label(2,12,17,"Direta",500,240,40,"E9B95F",8),
            label(2,12,17,"Difusa",1500,240,40,"E9B95F",8),
            label(2,17,24,"Geometria solar",400,240,38,align=8),
            label(2,17,24,"Atmosfera",1500,240,38,align=8),
            label(2,24,35,"Histórico",450,260,38,align=8),
            label(2,24,35,"Presente",1050,260,36,"A9B2BE",8),
            label(2,24,35,"Futuro",1550,260,38,"A9B2BE",8),
        ]
    if chapter==3:
        return [label(3,0,5,"Prever GHI",960,240,46,align=8),
                label(3,5,12,"LSTM",350,240,40,"F28779",8),
                label(3,5,12,"Transformer",960,240,40,"58CADA",8),
                label(3,5,12,"Informer",1570,240,40,"AA91E8",8),
                label(3,12,15,"Escala temporal",960,730,38,align=8),
                label(3,15,17.5,"Representação da entrada",960,730,38,align=8),
                label(3,17.5,20,"Histórico de treinamento",960,730,38,align=8)]
    if chapter==4:
        return [label(4,0,6,"NSRDB",1500,240,48,available=300),
                label(4,6,12,"1 Brasil",1320,280,38,available=450),
                label(4,6,12,"8 Estados Unidos",1320,360,38,available=450),
                label(4,6,12,"1 México",1320,440,38,available=450),
                label(4,12,19,"Célula NSRDB",1450,240,40,align=8),
                label(4,19,27,"Histórico de GHI",680,60,38,align=8),
                label(4,19,27,"ID da localidade",680,520,34,align=8),
                label(4,27,34,"Entradas: GHI + ID",960,240,42,align=8),
                label(4,34,40,"Parâmetros compartilhados",960,730,40,align=8)]
    if chapter==5:
        return [label(5,0,5,"Histórico",430,240,40,align=8),
                label(5,0,5,"Previsão",1450,240,40,"E9B95F",8),
                label(5,5,11,"Horária · 336 h → 72 h",960,730,44,align=8),
                label(5,11,16,"Diária · 365 d → 30 d",960,730,44,align=8),
                label(5,16,21,"Mensal · 12 meses → 1 mês",960,730,44,align=8),
                label(5,21,26,"Mensal · 12 meses → 6 meses",960,730,44,align=8),
                label(5,21,26,"Exploratória",1650,240,32,"AA91E8",8),
                label(5,26,35,"Redes distintas: 1 e 6 saídas",960,730,40,align=8)]
    if chapter==6:
        return [label(6,0,7,"Treino · 2019–2022",960,200,38,align=8),
                label(6,7,13,"Validação · 2023",960,200,38,align=8),
                label(6,13,19,"Teste · 2024",960,200,38,align=8),
                label(6,19,24,"Seleção pela validação",960,730,40,align=8),
                label(6,24,29,"Novo ajuste · 2019–2023",960,730,40,align=8),
                label(6,29,34,"Teste retrospectivo · 2024",960,730,40,align=8),
                label(6,34,40,"Houve exposição anterior ao teste",960,730,38,align=8)]
    # Chapters 7–13 use their own billboard labels in the 3D renderer.
    return []


def build_plan():
    source=json.loads(SOURCE.read_text(encoding="utf-8-sig"))
    chapters=[]
    cues=[]
    for original in source["scenes"]:
        cid=original["id"]
        if cid==1:
            continue
        start,duration=TIMINGS[cid]
        narration=original["narration"]
        notes=list(original.get("notes",[]))
        if cid==7:
            narration=" ".join(p["narration"] for p in NETWORK_PHASES)
            notes += ["As portas, conexões, pesos de atenção e intensidades mostrados são didáticos, sem extração dos pesos das execuções avaliadas.",
                      "LSTM 0–24 s; Transformer 24–50 s; Informer 50–75 s. A redução do encoder é mostrada numa etapa distinta da seleção de consultas."]
        chapter={"id":cid,"start":start,"end":start+duration,"duration":duration,
                 "title":original["title"],"narration":narration,
                 "label_events":short_labels(cid),"notes":notes}
        if cid==7:
            chapter["phases"]=[dict(p,start=start+p["start_local"],end=start+p["end_local"]) for p in NETWORK_PHASES]
            for p in chapter["phases"]:
                cues.extend(timed_cues(p["narration"],p["start"],p["end"],cid,p["id"]))
        else:
            cues.extend(timed_cues(narration,start,start+duration,cid))
        chapters.append(chapter)
    for index,cue in enumerate(cues,1):
        cue["id"]=index
    assert [c["id"] for c in chapters]==list(range(2,14))
    assert all(a["end"]==b["start"] for a,b in zip(chapters,chapters[1:]))
    assert sum(c["duration"] for c in chapters)==415
    assert cues[0]["start"]==0 and cues[-1]["end"]==415
    assert all(a["end"]==b["start"] for a,b in zip(cues,cues[1:]))
    for c in chapters:
        chapter_cues=[q for q in cues if q["chapter"]==c["id"]]
        assert " ".join(" ".join(q["text"] for q in chapter_cues).split())==" ".join(c["narration"].split())
    return {"version":"v4","title":"Previsão de irradiância solar — animação completa",
            "duration":415,"fps":30,"frame_count":12450,
            "resolution":[1920,1080],"source_plan":str(SOURCE),
            "scope":"Parte animada completa, sem cartões institucionais ou filmagens do aluno. Narração do aluno a inserir posteriormente.",
            "design":{"background":"07090D","surfaces":"171C22","white":"F3F5F7","muted":"A9B2BE","gold":"E9B95F","LSTM":"F28779","Transformer":"58CADA","Informer":"AA91E8","axes":"626D7A",
                      "fixed_headers":False,"institutional_cards":False,"source_footers":False,"grid":False,
                      "native_3d_labels_chapters":[7,8,9,10,11,12,13],"ass_label_chapters":[2,3,4,5,6],
                      "caption_font":"Segoe UI","caption_size":44,"caption_max_lines":2,"caption_max_characters_per_line":42,"caption_anchor":[960,985]},
            "chapters":chapters,"cues":cues}


def write_outputs(output=OUTPUT):
    plan=build_plan()
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    json_path=output/"plano_video_v4.json"
    json_path.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding="utf-8")
    speech=["FALAS — VÍDEO ANIMADO DO TCC — V4","Duração: 6min55s. Ler somente os parágrafos de fala.",
            "A narração está organizada pelos 12 capítulos da animação; sem cartões institucionais ou filmagens.",""]
    for c in plan["chapters"]:
        speech += [f"CAPÍTULO {c['id']:02d} | {clock(c['start'])}–{clock(c['end'])} | {c['title']}",c["narration"],""]
    (output/"Falas_para_narrar_video_v4.txt").write_text("\n".join(speech),encoding="utf-8-sig")
    srt=[]
    for cue in plan["cues"]:
        srt.append(f"{cue['id']}\n{stamp(cue['start'])} --> {stamp(cue['end'])}\n{cue['text']}\n")
    (output/"Legendas_video_v4.srt").write_text("\n".join(srt),encoding="utf-8-sig")
    return {"plan":str(json_path),"duration":415,"chapters":len(plan["chapters"]),"cues":len(plan["cues"]),
            "network_words":len(plan["chapters"][5]["narration"].split()),
            "shortest_cue":min(c["duration"] for c in plan["cues"])}


if __name__=="__main__":
    print(json.dumps(write_outputs(),ensure_ascii=True,indent=2))
