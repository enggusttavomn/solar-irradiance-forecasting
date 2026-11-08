"""Wait for the verified forty-second render, then prepare its review delivery."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/revisao_00_40_v6'
SCRIPTS=Path(__file__).resolve().parent


def main():
    print('V6_WAITING_FOR_COMPLETE_RENDER',flush=True)
    while True:
        progress=OUT/'progresso_intro_v6.json'
        if progress.is_file():
            state=json.loads(progress.read_text(encoding='utf-8'))
            if state.get('stage')=='error':raise RuntimeError(state.get('error','Render failed'))
        verification=OUT/'verificacao_intro_v6.json'
        if verification.is_file():
            data=json.loads(verification.read_text(encoding='utf-8'))
            if data.get('status')=='complete' and data.get('duration_seconds')==40:break
        time.sleep(3)
    jobs=[('qa_intro_contact_v6.py',['--final']),('delivery_intro_v6.py',[]),('prepare_mobile_intro_v6.py',[])]
    for name,args in jobs:
        print('V6_FINALIZING '+name,flush=True)
        subprocess.run([sys.executable,'-u',str(SCRIPTS/name),*args],cwd=ROOT,check=True,
                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print('V6_DELIVERY_READY_FOR_FINAL_VISUAL_REVIEW',flush=True)


if __name__=='__main__':main()
