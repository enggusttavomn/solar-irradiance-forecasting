"""Compor títulos/legendas sobre o piloto 3D e verificar os dois MP4s.

Requer o runtime portátil em .tools e o render bruto concluído.
Não altera o relatório, suas métricas ou o roteiro completo.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from overlays import PILOT_CUES, write_pilot_ass

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_OUT=ROOT/'documentacao/relatorio_final_ea019/video/piloto_v1'
DEFAULT_FFMPEG=ROOT/'.tools/video-python/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'


def command(args):
    result=subprocess.run([str(a) for a in args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode:
        raise RuntimeError(result.stderr[-6000:])
    return result


def srt_time(seconds):
    ms=round(seconds*1000)
    return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'


def probe_and_decode(ffmpeg,path,expected_duration=30,expected_frames=900):
    probe=subprocess.run([str(ffmpeg),'-hide_banner','-i',str(path)],capture_output=True,text=True,encoding='utf-8',errors='replace')
    info=probe.stderr
    assert '1920x1080' in info, info
    assert '30 fps' in info, info
    assert 'Video: h264' in info, info
    assert 'Audio:' not in info, info
    expected_stamp=f'{int(expected_duration)//3600:02d}:{int(expected_duration)//60%60:02d}:{int(expected_duration)%60:02d}.00'
    assert 'Duration: '+expected_stamp in info,info
    decode=command([ffmpeg,'-hide_banner','-v','error','-nostats','-progress','pipe:1','-i',path,'-map','0:v:0','-f','null','-'])
    frames=[int(s) for s in re.findall(r'^frame=(\d+)$',decode.stdout,re.M)]
    assert frames and frames[-1]==expected_frames, decode.stdout[-3000:]
    assert not decode.stderr.strip(),decode.stderr
    with path.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':digest,
            'width':1920,'height':1080,'fps':30,'frame_count':expected_frames,'duration_seconds':expected_duration,
            'codec':'H.264','audio_tracks':0,'full_decode_errors':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=DEFAULT_OUT)
    parser.add_argument('--ffmpeg',type=Path,default=DEFAULT_FFMPEG)
    args=parser.parse_args()
    out=args.output_dir.resolve()
    ffmpeg=args.ffmpeg.resolve()
    raw=out/'piloto_ghi_v1_sem_textos.mp4'
    assert raw.is_file() and raw.stat().st_size>10000,'Aguardando o render bruto concluir.'
    files=[]
    for captions,name in [(True,'piloto_ghi_v1_com_legendas'),(False,'piloto_ghi_v1_sem_legendas')]:
        ass=out/(name+'.ass')
        write_pilot_ass(ass,include_captions=captions)
        ass_filter='ass='+ass.relative_to(ROOT).as_posix()
        target=out/(name+'.mp4')
        command([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',raw,'-vf',ass_filter,
                 '-an','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p',
                 '-movflags','+faststart','-threads','6',target])
        files.append(probe_and_decode(ffmpeg,target))
        print('COMPOSED '+json.dumps(files[-1],ensure_ascii=True),flush=True)
    srt='\n\n'.join(f'{i}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{c.text}' for i,c in enumerate(PILOT_CUES,1))+'\n'
    (out/'piloto_ghi_v1.srt').write_text(srt,encoding='utf-8-sig')
    qa=out/'verificacao_visual'
    qa.mkdir(exist_ok=True)
    final=out/'piloto_ghi_v1_com_legendas.mp4'
    stills=[]
    for second in [1,8,17,19.5,20.5,23,28,29.5]:
        target=qa/f"t_{str(second).replace('.','_')}s.png"
        command([ffmpeg,'-hide_banner','-loglevel','error','-y','-ss',str(second),'-i',final,'-frames:v','1','-update','1',target])
        stills.append(str(target.relative_to(ROOT)))
    report={'type':'piloto 3D condensado de 30 segundos','status':'MP4 renderizado e decodificado integralmente',
            'files':files,'visual_review_stills':stills,
            'narration':'sem áudio; texto condensado demonstrativo, diferente do roteiro completo de 6min55s',
            'full_415_second_video_rendered':False}
    (out/'verificacao_mp4_piloto_v1.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PILOT_VERIFY_OK',flush=True)


if __name__=='__main__':
    main()
