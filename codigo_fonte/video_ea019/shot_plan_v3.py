"""Read the provided XLSX storyboard without modifying it or requiring Excel."""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

WORKSPACE = Path(__file__).resolve().parents[2]
SOURCE = Path(r"C:\Users\gusta\.codex\.chatgpt-projects\g-p-6ae3fa423da08191a5eeb790c9051300\outputs\planejamento_video_tcc_20261101\Planejamento_completo_video_TCC.xlsx")
OUTPUT = WORKSPACE / "documentacao/relatorio_final_ea019/video/completo_v3/plano_73_extraido.json"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_workbook(path=SOURCE):
    """Return the cached typed cell values in each sheet, using stdlib XML."""
    sheets = {}
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(t.itertext()) for t in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", NS)]
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {r.attrib["Id"]: r.attrib["Target"].lstrip("/") for r in rels}
        for sheet in ET.fromstring(archive.read("xl/workbook.xml")).findall("s:sheets/s:sheet", NS):
            target = targets[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            if not target.startswith("xl/"):
                target = "xl/" + target
            rows = []
            for row in ET.fromstring(archive.read(target)).findall("s:sheetData/s:row", NS):
                result = []
                for cell in row.findall("s:c", NS):
                    letters = re.match(r"[A-Z]+", cell.attrib["r"]).group()
                    index = 0
                    for ch in letters:
                        index = index * 26 + ord(ch) - 64
                    while len(result) < index:
                        result.append(None)
                    value = cell.find("s:v", NS)
                    value = value.text if value is not None else None
                    kind = cell.attrib.get("t")
                    if kind == "s":
                        value = strings[int(value)] if value is not None else None
                    elif kind == "inlineStr":
                        inline = cell.find("s:is", NS)
                        value = "".join(inline.itertext()) if inline is not None else None
                    elif value is not None and kind not in ("str", "e"):
                        value = float(value)
                        if value.is_integer():
                            value = int(value)
                    result[index - 1] = value
                rows.append(result)
            sheets[sheet.attrib["name"]] = rows
    return sheets


def tc(seconds):
    minutes, sec = divmod(round(seconds), 60)
    return f"{minutes:02d}:{sec:02d}"


def extract(workbook):
    fps, clip_first, clip_end = 30, 750, 13200
    shots, phases = [], {}
    for r in workbook["Quadros"][4:]:
        if not r or not isinstance(r[0], (float, int)):
            continue
        frame, shot, phase = r[0], r[5], r[8]
        parts = phases.setdefault(shot, [])
        if parts and parts[-1]["phase"] == phase and parts[-1]["action"] == r[9]:
            parts[-1]["last_frame_full"] = frame
        else:
            parts.append({"phase": phase, "action": r[9], "first_frame_full": frame, "last_frame_full": frame})
    for rownum, r in enumerate(workbook["Planos"][4:], 5):
        if not r or not re.fullmatch(r"P\d+", str(r[0])):
            continue
        first, last = int(r[4]), int(r[5])
        shot = {
            "id": r[0], "source_row": rownum,
            "start_s_full": first / fps, "end_s_full": (last + 1) / fps,
            "duration_s": (last + 1 - first) / fps,
            "first_frame_full": first, "last_frame_full": last,
            "chapter": r[6], "composition": r[7], "camera_action": r[8],
            "on_screen_text": r[9], "colors_materials": r[10],
            "speech_excerpt": r[11], "phases_transition": r[12],
            "scientific_precision": r[13], "source_status": r[14],
            "frame_phases": phases.get(r[0], []),
        }
        shots.append(shot)
    middle = []
    for shot in shots:
        if shot["first_frame_full"] >= clip_first and shot["last_frame_full"] < clip_end:
            local = dict(shot)
            local["start_s"] = (shot["first_frame_full"] - clip_first) / fps
            local["end_s"] = (shot["last_frame_full"] + 1 - clip_first) / fps
            local["start_timecode"] = tc(local["start_s"])
            local["end_timecode"] = tc(local["end_s"])
            local["first_frame"] = shot["first_frame_full"] - clip_first
            local["last_frame"] = shot["last_frame_full"] - clip_first
            local["frame_phases"] = [dict(p, first_frame=p["first_frame_full"]-clip_first, last_frame=p["last_frame_full"]-clip_first) for p in shot["frame_phases"]]
            middle.append(local)
    overview = []
    for row in workbook["Visao geral"][4:]:
        if len(row) < 12 or not isinstance(row[6], (float, int)):
            continue
        overview.append({
            "id": row[0], "start_s_full": row[6]/fps,
            "end_s_full": (row[7]+1)/fps, "duration_s": row[5],
            "start_s": round(row[3]*86400, 9) if row[3] is not None else None,
            "end_s": round(row[4]*86400, 9) if row[4] is not None else None,
            "first_frame_full": row[6], "last_frame_full": row[7],
            "composition": row[9], "colors": row[10], "status": row[11],
        })
    design = [{"group": r[0], "element": r[1], "specification": r[2], "hex": r[3], "application": r[4]} for r in workbook["Design"][4:] if len(r)>=5 and r[0]]
    voice, results, captions, coordinates, sources = [], [], [], [], []
    section = "voice"
    for r in workbook["Falas e dados"][4:]:
        r = r + [None] * (6-len(r))
        if str(r[0]).startswith("Resultados preservados"):
            section = "results"
        elif str(r[0]).startswith("90 blocos"):
            section = "captions"
        elif str(r[0]).startswith("Fontes locais"):
            section = "sources"
        elif str(r[0]).startswith("Localidades e coordenadas"):
            section = "coordinates"
        elif section == "voice" and isinstance(r[1], (float,int)):
            voice.append({"chapter":r[0],"start_s_full":round(r[1]*86400,9),"end_s_full":round(r[2]*86400,9),"subject":r[3],"speech":r[4],"source_status":r[5]})
        elif section == "results" and isinstance(r[3], (float,int)):
            results.append({"task":r[0],"model":r[1],"input":r[2],"macro_mae_w_m2":r[3],"interpretation":r[4],"note":r[5]})
        elif section == "captions" and isinstance(r[0], (float,int)):
            captions.append({"id":r[0],"start_s_full":round(r[1]*86400,9),"end_s_full":round(r[2]*86400,9),"start_s":round(r[3]*86400,9),"end_s":round(r[2]*86400-25,9),"text":r[4],"status":r[5]})
        elif section == "sources" and r[4]:
            sources.append({"label":r[0],"path":r[4]})
        elif section == "coordinates" and isinstance(r[2], (float,int)):
            coordinates.append({"locality":r[0],"country":r[1],"latitude":r[2],"longitude":r[3],"source":r[4],"use":r[5]})
    assert len(shots) == 73, len(shots)
    assert middle[0]["first_frame"] == 0 and middle[-1]["last_frame"] == 12449
    assert all(a["last_frame"]+1 == b["first_frame"] for a,b in zip(middle,middle[1:]))
    assert sum(s["last_frame"]+1-s["first_frame"] for s in middle) == 12450
    assert len(captions) == 90 and len(results) == 12 and len(coordinates) == 10
    return {
        "source_xlsx": str(SOURCE), "extraction": "Read-only stdlib ZIP/XML extraction of cached values. Original workbook preserved.",
        "timing": {"fps":fps,"full_duration_s":480,"render_start_s_full":25,"render_end_s_full_exclusive":440,"render_duration_s":415,"frame_count":12450,"time_end_exclusive":True,"frame_last_inclusive":True},
        "validation": {"original_shots":len(shots),"middle_shots":len(middle),"continuous_middle":True,"original_frame_records":len(workbook["Quadros"])-4,"subtitle_blocks":len(captions)},
        "overview":overview,"design":design,"all_73_shots":shots,"middle_shots":middle,
        "speech":voice,"results_rounded_report":results,"subtitles":captions,"coordinates":coordinates,"source_files":sources,
    }


if __name__ == "__main__":
    data = extract(read_workbook())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data["validation"], ensure_ascii=True))
    print(str(OUTPUT))
    for s in data["middle_shots"]:
        print(s["id"], s["start_timecode"], s["end_timecode"], s["chapter"].splitlines()[0])
