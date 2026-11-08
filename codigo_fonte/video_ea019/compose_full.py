"""Unir os 13 capítulos renderizados e compor o vídeo completo de 6min55s.

Só executar quando todos os renders 3D dos capítulos estiverem concluídos.
Legendas continuam usando tempos de referência até a gravação real da voz.
"""
import argparse
import json
from pathlib import Path

from compose_pilot import DEFAULT_FFMPEG, command, probe_and_decode
from overlays import DEFAULT_PLAN, DEFAULT_SRT, write_full_ass

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/trecho_animado_v2/producao'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=OUT)
    parser.add_argument('--ffmpeg',type=Path,default=DEFAULT_FFMPEG)
    args=parser.parse_args()
    directory=args.output_dir.resolve()
    ffmpeg=args.ffmpeg.resolve()
    manifest=json.loads((directory/'manifesto_producao_3d.json').read_text(encoding='utf-8'))
    chapters=sorted(manifest['chapters'],key=lambda row:row['id'])
    assert len(chapters)==13 and sum(c['duration_seconds'] for c in chapters)==415
    concat=[]
    for chapter in chapters:
        path=Path(chapter['raw_mp4']).resolve()
        assert path.is_relative_to(directory)
        assert path.is_file() and path.stat().st_size>10000,f"Ainda falta renderizar a cena {chapter['id']:02d}: {path}"
        # A completed MP4 must report the exact planned duration and decode.
        probe_and_decode(ffmpeg,path,chapter['duration_seconds'],chapter['frame_count'])
        escaped=path.as_posix().replace("'","'\\''")
        concat.append("file '"+escaped+"'")
    listing=directory/'capitulos_para_unir.txt'
    listing.write_text('\n'.join(concat)+'\n',encoding='utf-8')
    raw=directory/'video_ghi_6min55s_3d_base.mp4'
    command([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',listing,
             '-map','0:v:0','-an','-c:v','copy','-movflags','+faststart',raw])
    checks=[]
    for captions,suffix in [(True,'com_legendas'),(False,'sem_legendas')]:
        ass=directory/f'video_completo_{suffix}.ass'
        write_full_ass(DEFAULT_PLAN,DEFAULT_SRT,ass,include_captions=captions)
        target=directory/f'video_ghi_6min55s_{suffix}_v1.mp4'
        command([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',raw,
                 '-vf','ass='+ass.relative_to(ROOT).as_posix(),'-an','-c:v','libx264',
                 '-preset','medium','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart','-threads','6',target])
        checks.append(probe_and_decode(ffmpeg,target,415,12450))
        print('FULL_VIDEO_COMPOSED '+json.dumps(checks[-1],ensure_ascii=True),flush=True)
    report={'duration_seconds':415,'files':checks,'status':'render completo e decodificação integral concluídos',
            'audio':'sem narração gravada','subtitle_timing':'referência do roteiro; sincronizar com a voz real'}
    (directory/'verificacao_video_completo_v1.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
