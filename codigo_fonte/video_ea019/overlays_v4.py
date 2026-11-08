"""V4: short explanatory labels and narration captions over dynamic 3D.

There are no fixed chapter headers, institutional cards, source footers,
result-chart drawings, or opaque background masks in this overlay.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

try:
    from .overlays import Cue
    from .overlays_v3 import OverlayV3, STYLES as BASE_STYLES
    from .plan_v4 import OUTPUT, write_outputs
except ImportError:
    from overlays import Cue
    from overlays_v3 import OverlayV3, STYLES as BASE_STYLES
    from plan_v4 import OUTPUT, write_outputs

PLAN=OUTPUT/"plano_video_v4.json"
STYLES=BASE_STYLES.replace("EA019 - 63-shot animated cut v3","EA019 - dynamic 3D animated cut v4")


class OverlayV4(OverlayV3):
    def header(self,*args,**kwargs):
        raise ValueError("V4 does not use fixed headers")

    def source(self,*args,**kwargs):
        raise ValueError("V4 does not use source footers")

    def rect(self,*args,**kwargs):
        raise ValueError("V4 ASS must not obscure native 3D with drawings or masks")

    def write(self,path):
        path=Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(STYLES+"\n".join(self.events)+"\n",encoding="utf-8-sig")
        issues=[]
        for event in self.checks:
            x0,y0,x1,y1=event["bbox_approx"]
            if x0<80 or x1>1840 or y0<25 or y1>1010:
                issues.append({"type":"outside_safe_area","event":event})
            if event["role"]!="caption" and y1>840:
                issues.append({"type":"enters_caption_band","event":event})
        labels=[c for c in self.checks if c["role"]!="caption"]
        overlaps=[]
        for i,a in enumerate(labels):
            for b in labels[i+1:]:
                if a["start"]>=b["end"] or b["start"]>=a["end"]:
                    continue
                aa,bb=a["bbox_approx"],b["bbox_approx"]
                if min(aa[2],bb[2])-max(aa[0],bb[0])>3 and min(aa[3],bb[3])-max(aa[1],bb[1])>3:
                    overlaps.append({"chapter":a["shot"],"text_a":a["text"],"text_b":b["text"]})
        return {"path":str(path.resolve()),"version":"v4","duration_seconds":415,
                "chapter_count":12,"event_count":len(self.events),
                "caption_count":sum(c["role"]=="caption" for c in self.checks),
                "label_count":len(labels),"canvas":[1920,1080],"font":"Segoe UI",
                "caption_anchor":[960,985],"fixed_headers":False,"source_footers":False,
                "opaque_masks":False,"result_chart_drawings":False,
                "native_3d_label_chapters":[7,8,9,10,11,12,13],
                "event_count_by_chapter":dict(Counter(c["shot"] for c in self.checks)),
                "layout_issues":issues,"potential_text_overlaps":overlaps,
                "events":self.checks,"source_plan":str(PLAN.resolve())}


def write_v4_ass(path,include_captions=True):
    if not PLAN.is_file():
        write_outputs()
    plan=json.loads(PLAN.read_text(encoding="utf-8"))
    assert plan["duration"]==415
    assert [c["id"] for c in plan["chapters"]]==list(range(2,14))
    o=OverlayV4(plan)
    for chapter in plan["chapters"]:
        cid=chapter["id"]
        o.shot=f"chapter_{cid:02d}"
        for event in chapter["label_events"]:
            if cid>=7:
                raise ValueError("Chapters 7–13 have native 3D labels; duplicate ASS labels are prohibited")
            o.text(event["start"],event["end"],event["text"],x=event["x"],y=event["y"],
                   size=event["size"],color=event["color"],align=event["align"],
                   available=event["available"],minimum=30,fade=140,role="label")
    if include_captions:
        for cue in plan["cues"]:
            o.shot=f"chapter_{cue['chapter']:02d}"
            o.caption(Cue(cue["start"],cue["end"],cue["text"]))
    return o.write(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--no-captions",action="store_true")
    parser.add_argument("--report",type=Path)
    args=parser.parse_args()
    report=write_v4_ass(args.output,include_captions=not args.no_captions)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="events"},ensure_ascii=True,indent=2))


if __name__=="__main__":
    main()
