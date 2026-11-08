"""Audit a completed V4 delivery with stdlib and Pillow, without video decoding.

Run only after verificacao_video_v4.json reports status=complete. The existing
pipeline's full-decode result is checked and reported; FFmpeg and Blender are
never started. Technical integrity does not automatically approve the visuals.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import unquote, urlsplit

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_OUT=ROOT/"documentacao/relatorio_final_ea019/video/completo_v4"
EXPECTED_VIDEOS={"Video_TCC_GHI_6min55_com_legendas_v4.mp4",
                 "Video_TCC_GHI_6min55_sem_legendas_v4.mp4"}

try:
    from PIL import Image
except ModuleNotFoundError:
    sys.path.insert(0,str(ROOT/".venv/Lib/site-packages"))
    from PIL import Image

try:
    from .overlays import read_srt
except ImportError:
    from overlays import read_srt


def normalize(text):
    return " ".join(unicodedata.normalize("NFC",str(text)).split())


def number(value):
    result=Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Non-finite time or count")
    return result


def issue(errors,kind,**details):
    errors.append({"kind":kind,**details})


def read_json(path,errors):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError,UnicodeError,json.JSONDecodeError) as error:
        issue(errors,"missing_or_invalid_json",path=str(path),error=str(error))
        return None


def in_workspace(path):
    return path.resolve().is_relative_to(ROOT.resolve())


def declared_path(value,out):
    path=Path(str(value))
    if path.is_absolute():
        return path.resolve()
    root_path=(ROOT/path).resolve()
    return root_path if root_path.is_file() else (out/path).resolve()


def audit_videos(verification,out,errors):
    records=[]
    entries=verification.get("files",[])
    if not isinstance(entries,list) or len(entries)!=2:
        issue(errors,"unexpected_video_count",expected=2,actual=len(entries) if isinstance(entries,list) else None)
        entries=entries if isinstance(entries,list) else []
    names=[]
    for entry in entries:
        if not isinstance(entry,dict) or not entry.get("path"):
            issue(errors,"invalid_video_declaration",entry=entry)
            continue
        path=declared_path(entry["path"],out)
        names.append(path.name)
        record={"path":str(path),"exists":path.is_file(),"declared_bytes":entry.get("bytes"),
                "declared_sha256":entry.get("sha256"),"hash_matches":False,"size_matches":False,
                "full_decode_errors_from_pipeline":entry.get("full_decode_errors"),"video_decoded_again":False}
        if not in_workspace(path):
            issue(errors,"video_outside_workspace",path=str(path))
        elif not path.is_file():
            issue(errors,"missing_video",path=str(path))
        else:
            try:
                record["actual_bytes"]=path.stat().st_size
                record["size_matches"]=record["actual_bytes"]==entry.get("bytes") and record["actual_bytes"]>0
                if not record["size_matches"]:
                    issue(errors,"video_size_mismatch",path=str(path),actual=record["actual_bytes"],declared=entry.get("bytes"))
                digest=str(entry.get("sha256",""))
                if not re.fullmatch(r"[0-9a-fA-F]{64}",digest):
                    issue(errors,"missing_or_invalid_declared_hash",path=str(path))
                with path.open("rb") as stream:
                    record["actual_sha256"]=hashlib.file_digest(stream,"sha256").hexdigest()
                record["hash_matches"]=record["actual_sha256"]==digest.lower()
                if not record["hash_matches"]:
                    issue(errors,"video_hash_mismatch",path=str(path))
            except OSError as error:
                issue(errors,"unreadable_video",path=str(path),error=str(error))
        for key,expected in {"width":1920,"height":1080,"fps":30,"frame_count":12450,
                             "duration_seconds":415,"audio_tracks":0,"full_decode_errors":0}.items():
            if entry.get(key)!=expected:
                issue(errors,"unexpected_declared_video_metadata",path=str(path),field=key,expected=expected,actual=entry.get(key))
        records.append(record)
    if set(names)!=EXPECTED_VIDEOS or len(names)!=len(set(names)):
        issue(errors,"unexpected_video_names",expected=sorted(EXPECTED_VIDEOS),actual=names)
    return records


def audit_frames(verification,out,chapters,errors):
    samples=verification.get("sampled_frames",[])
    if not isinstance(samples,list) or len(samples)!=72:
        issue(errors,"unexpected_sample_count",expected=72,actual=len(samples) if isinstance(samples,list) else None)
        samples=samples if isinstance(samples,list) else []
    records=[];seen=set();coverage=Counter()
    for entry in samples:
        if not isinstance(entry,dict) or not entry.get("path"):
            issue(errors,"invalid_frame_declaration",entry=entry)
            continue
        path=declared_path(entry["path"],out)
        record={"path":str(path),"chapter":entry.get("chapter"),"exists":path.is_file(),
                "readable":False,"dimensions_match":False}
        key=str(path).casefold()
        if key in seen:
            issue(errors,"duplicate_sample_path",path=str(path))
        seen.add(key)
        cid=entry.get("chapter");coverage[cid]+=1
        chapter=chapters.get(cid)
        try:
            if chapter is None:
                raise ValueError("Unknown chapter")
            local=number(entry["local_second"]);global_time=number(entry["global_second"])
            if not (0<=local<number(chapter["duration"]) and number(chapter["start"])+local==global_time):
                raise ValueError("Sample time is outside its chapter or disagrees with global time")
        except (KeyError,ValueError,InvalidOperation,TypeError) as error:
            issue(errors,"invalid_sample_time",path=str(path),error=str(error))
        if not in_workspace(path):
            issue(errors,"frame_outside_workspace",path=str(path))
        elif not path.is_file():
            issue(errors,"missing_sample_frame",path=str(path))
        else:
            try:
                record["bytes"]=path.stat().st_size
                if not record["bytes"]:
                    raise ValueError("Empty image")
                with Image.open(path) as image:
                    record["format"]=image.format
                    image.verify()
                with Image.open(path) as image:
                    image.load()
                    record["dimensions"]=list(image.size)
                    record["readable"]=True
                    record["dimensions_match"]=image.size==(1920,1080)
                if record["format"]!="PNG" or path.suffix.lower()!=".png":
                    issue(errors,"sample_not_png",path=str(path),format=record["format"])
                if not record["dimensions_match"]:
                    issue(errors,"sample_wrong_dimensions",path=str(path),actual=record["dimensions"],expected=[1920,1080])
            except (OSError,ValueError,SyntaxError) as error:
                issue(errors,"unreadable_sample_frame",path=str(path),error=str(error))
        records.append(record)
    if set(coverage)!=set(range(2,14)):
        issue(errors,"incomplete_sample_chapter_coverage",actual=sorted(coverage,key=str),expected=list(range(2,14)))
    return {"expected":72,"inspected":len(records),"readable":sum(r["readable"] for r in records),
            "dimensions_match":sum(r["dimensions_match"] for r in records),
            "chapter_counts":dict(coverage),"frames":records}


def audit_plan(plan,out,errors):
    if not isinstance(plan,dict):
        return {},{"checked":False}
    chapters=plan.get("chapters",[]);cues=plan.get("cues",[])
    if len(chapters)!=12 or [c.get("id") for c in chapters]!=list(range(2,14)):
        issue(errors,"unexpected_plan_chapters",expected=list(range(2,14)),actual=[c.get("id") for c in chapters])
    by_id={c.get("id"):c for c in chapters}
    previous=Decimal(0)
    for c in chapters:
        try:
            start,end,duration=map(number,(c["start"],c["end"],c["duration"]))
            if start!=previous or end<=start or duration!=end-start:
                raise ValueError("Noncontiguous chapter or inconsistent duration")
            previous=end
        except (KeyError,ValueError,InvalidOperation,TypeError) as error:
            issue(errors,"invalid_chapter_bounds",chapter=c.get("id"),error=str(error))
    if previous!=415 or plan.get("duration")!=415:
        issue(errors,"unexpected_plan_duration",actual=plan.get("duration"),last_chapter_end=str(previous))
    if len(cues)!=75:
        issue(errors,"unexpected_cue_count",expected=75,actual=len(cues))
    previous=Decimal(0);chapter_text={cid:[] for cid in by_id}
    for index,cue in enumerate(cues,1):
        try:
            if cue["id"]!=index:
                raise ValueError("Unexpected cue sequence number")
            start,end=number(cue["start"]),number(cue["end"])
            if start!=previous or end<=start:
                raise ValueError("Cue is empty, overlapping, or leaves a gap")
            previous=end
            chapter=by_id[cue["chapter"]]
            if start<number(chapter["start"]) or end>number(chapter["end"]):
                raise ValueError("Cue crosses its chapter boundary")
            lines=cue["text"].splitlines()
            if not 1<=len(lines)<=2 or any(not line or len(line)>42 for line in lines):
                raise ValueError("Cue exceeds two 42-character lines or contains an empty line")
            chapter_text[cue["chapter"]].append(cue["text"])
        except (KeyError,ValueError,InvalidOperation,TypeError) as error:
            issue(errors,"invalid_caption_cue",cue=index,error=str(error))
    if previous!=415:
        issue(errors,"unexpected_last_cue_end",actual=str(previous),expected=415)
    for cid,c in by_id.items():
        if normalize(" ".join(chapter_text[cid]))!=normalize(c.get("narration","")):
            issue(errors,"cue_narration_mismatch",chapter=cid)
    try:
        srt=read_srt(out/"Legendas_video_v4.srt")
        if len(srt)!=len(cues):
            raise ValueError("SRT and plan have different cue counts")
        for source,exported in zip(cues,srt):
            if (number(source["start"])!=number(exported.start) or number(source["end"])!=number(exported.end)
                    or source["text"]!=exported.text):
                raise ValueError(f"SRT differs from plan at cue {source['id']}")
    except (OSError,ValueError,UnicodeError) as error:
        issue(errors,"srt_mismatch_or_invalid",error=str(error))
    try:
        speech=(out/"Falas_para_narrar_video_v4.txt").read_text(encoding="utf-8-sig")
        blocks=re.findall(r"CAPÍTULO (\d+) \| [^\n]+\n([^\n]+)",speech)
        if len(blocks)!=12 or [int(cid) for cid,_ in blocks]!=list(range(2,14)):
            raise ValueError("Narration TXT chapter order or count differs from plan")
        if any(normalize(text)!=normalize(by_id[int(cid)]["narration"]) for cid,text in blocks):
            raise ValueError("Narration TXT differs from plan")
    except (OSError,ValueError,UnicodeError) as error:
        issue(errors,"narration_txt_mismatch_or_invalid",error=str(error))
    return by_id,{"checked":True,"chapters":len(chapters),"cues":len(cues),
                  "first_cue_start":cues[0].get("start") if cues else None,
                  "last_cue_end":cues[-1].get("end") if cues else None,
                  "cue_text_sha256":hashlib.sha256(json.dumps(cues,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()}


class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.references=[]

    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key in ("href","src","poster") and value:
                self.references.append({"tag":tag,"attribute":key,"url":value})


def audit_links(path,errors):
    parser=Links();records=[];seen=set()
    try:
        parser.feed(path.read_text(encoding="utf-8-sig"))
    except (OSError,UnicodeError) as error:
        issue(errors,"missing_or_unreadable_player",path=str(path),error=str(error))
        return records
    for reference in parser.references:
        url=reference["url"];parts=urlsplit(url)
        if parts.scheme or parts.netloc or not parts.path or parts.path.startswith("/"):
            continue
        target=(path.parent/unquote(parts.path)).resolve()
        if str(target) in seen:
            continue
        seen.add(str(target))
        inside=in_workspace(target)
        exists=inside and target.is_file()
        size=target.stat().st_size if exists else 0
        records.append({**reference,"resolved":str(target),"within_workspace":inside,
                        "exists":exists,"bytes":size})
        if not inside:
            issue(errors,"player_link_outside_workspace",url=url,target=str(target))
        elif not exists or not size:
            issue(errors,"missing_or_empty_relative_link",url=url,target=str(target))
    if not records:
        issue(errors,"no_relative_player_links_checked",path=str(path))
    return records


def run(out=DEFAULT_OUT):
    out=Path(out).resolve()
    if not in_workspace(out):
        raise ValueError("Delivery directory must remain inside the project workspace")
    errors=[]
    verification=read_json(out/"verificacao_video_v4.json",errors)
    completed=isinstance(verification,dict) and verification.get("status")=="complete"
    videos=[];frames={"inspected":0};plan_summary={"checked":False};links=[]
    if not completed:
        issue(errors,"pipeline_not_complete",actual=verification.get("status") if isinstance(verification,dict) else None)
    else:
        for key,expected in {"duration_seconds":415,"frame_count":12450,"fps":30,"resolution":[1920,1080],
                             "chapters":12,"audio_tracks":0,"full_decode_errors":0}.items():
            if verification.get(key)!=expected:
                issue(errors,"unexpected_pipeline_metadata",field=key,expected=expected,actual=verification.get(key))
        plan=read_json(out/"plano_video_v4.json",errors)
        chapters,plan_summary=audit_plan(plan,out,errors)
        videos=audit_videos(verification,out,errors)
        frames=audit_frames(verification,out,chapters,errors)
        links=audit_links(out/"assistir_video_v4.html",errors)
    report={"version":4,"generated_utc":datetime.now(timezone.utc).isoformat(),
            "tool":"verify_delivery_v4.py","pipeline_status":verification.get("status") if isinstance(verification,dict) else None,
            "source_verification":str(out/"verificacao_video_v4.json"),
            "technical_ok":not errors,"error_count":len(errors),"errors":errors,
            "error_counts":dict(Counter(error["kind"] for error in errors)),
            "videos":videos,"sampled_frames":frames,"plan_and_captions":plan_summary,"relative_links":links,
            "full_decode_errors_reported_by_pipeline":verification.get("full_decode_errors") if isinstance(verification,dict) else None,
            "video_decoding_performed":False,"external_processes_started":False,
            "visual_review":{"automatically_approved":False,"performed_by_this_verifier":False,
                             "pipeline_sampled_visual_review_passed":verification.get("sampled_visual_review_passed") if isinstance(verification,dict) else None}}
    path=out/"verificacao_entrega_v4.json"
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return path,report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=DEFAULT_OUT)
    args=parser.parse_args()
    path,report=run(args.output_dir)
    print(json.dumps({"report":str(path),"technical_ok":report["technical_ok"],
                      "error_count":report["error_count"],"error_counts":report["error_counts"],
                      "videos_checked":len(report["videos"]),"frames_checked":report["sampled_frames"]["inspected"],
                      "visual_review_automatically_approved":False},ensure_ascii=True,indent=2),flush=True)
    return 0 if report["technical_ok"] else 2


if __name__=="__main__":
    raise SystemExit(main())
