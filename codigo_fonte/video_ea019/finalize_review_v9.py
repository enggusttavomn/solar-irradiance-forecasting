"""Record manual sampled review after technical checks, without altering media."""
import argparse,subprocess,sys
from datetime import datetime,timezone
from pipeline_v9 import *
from compose_v9 import progress
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sampled-review-complete',action='store_true',required=True)
    parser.parse_args()
    audit=read(OUT/'audit_delivery_v9.json');pixel=read(OUT/'verificacao_resultados_preservados_v9.json')
    if not audit['technical_ok'] or not pixel['approved_v8_results_preserved_pixel_exact']:
        raise ValueError('Technical or preservation audit has not passed')
    p=OUT/'verificacao_video_v9.json';r=read(p)
    for entry in r['files']+[r['mobile_preview']]:
        if sha(ROOT/entry['path'])!=entry['sha256']:raise ValueError('Reviewed media changed')
    r.update(status='complete',sampled_visual_review_passed=True,
             completed_utc=datetime.now(timezone.utc).isoformat(),
             final_realtime_playback_reviewed=False,
             results_v8_preserved_pixel_exact=True)
    r['manual_visual_review']={'automatically_approved':False,
        'scope':'Sampled final exported frames, contact sheets and mobile stills; not full real-time playback.',
        'contact_sheets':r['contact_sheets'],'material_findings_remaining':[]}
    review=read(OUT/'revisao_visual_final_v9.json')
    if review.get('material_findings_remaining'):raise ValueError('Unresolved manual visual findings')
    r['manual_visual_review'].update(report=str((OUT/'revisao_visual_final_v9.json').relative_to(ROOT)),
        sampled_frames_reviewed=review['sampled_frames_reviewed'],mobile_samples_reviewed=review['mobile_samples_reviewed'])
    r['mobile_preview']['sampled_visual_review_passed']=True
    root_launcher=ROOT/'ASSISTIR_VIDEO_TCC.cmd';backup=ROOT/'ASSISTIR_VIDEO_TCC_ANTES_V9.cmd'
    if root_launcher.exists() and not backup.exists():backup.write_bytes(root_launcher.read_bytes())
    root_launcher.write_bytes((ROOT/'ASSISTIR_VIDEO_REVISADO_V9.cmd').read_bytes())
    r['default_launcher']=str(root_launcher.relative_to(ROOT))
    write_json(p,r)
    result=subprocess.run([sys.executable,str(ROOT/'codigo_fonte/video_ea019/audit_delivery_v9.py')],
                          cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    progress('complete',duration_seconds=560,total_with_personal_intro=580,
             files=r['files'],mobile_preview=r['mobile_preview'],manual_sampled_review_passed=True)
    print('V9_COMPLETE_VERIFIED_AND_REVIEWED',flush=True)
if __name__=='__main__':main()
