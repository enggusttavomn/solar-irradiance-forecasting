"""Shared paths and validation helpers for the student's narrated final video."""
from pathlib import Path
import hashlib,json,subprocess,time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/montagem_final_v10'
TMP=ROOT/'tmp/montagem_final_v10'
FFMPEG=ROOT/'.tools/video-python/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
BASE=ROOT/'documentacao/relatorio_final_ea019/video/completo_v9/Video_TCC_GHI_Revisado_sem_legendas_v9.mp4'
MAIN_AUDIO=Path('C:/Users/gusta/OneDrive/Documents/Sound Recordings/Recording.m4a')
END_AUDIO=Path('C:/Users/gusta/OneDrive/Documents/Sound Recordings/Recording (2).m4a')
PATCH=OUT/'patches/matriz_historica_corrigida_6s_v10.mp4'
INTRO=OUT/'intro_1080p30_colorido_fundo_preto_v10_capa_v5.mp4'
FACTORY=OUT/'encerramento/fabrica_encerramento_limpa_v10.png'
FONTS=Path('C:/Windows/Fonts')
FPS=30

def read(path,default=None):
    for i in range(25):
        try:return json.loads(Path(path).read_text(encoding='utf-8-sig'))
        except FileNotFoundError:return default
        except (PermissionError,json.JSONDecodeError):
            if i==24:raise
            time.sleep(.08)

def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    for i in range(25):
        try:
            tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            tmp.replace(path);return
        except PermissionError:
            if i==24:raise
            time.sleep(.1)

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def run(args):
    p=subprocess.run([str(x)for x in args],cwd=ROOT,capture_output=True,text=True,
        encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if p.returncode:raise RuntimeError(p.stderr[-6500:])
    return p

def progress(stage,**data):
    write(OUT/'progresso_montagem_v10.json',{'stage':stage,'updated_unix':time.time(),**data})

def media_info(path,decode=False):
    import re
    p=subprocess.run([str(FFMPEG),'-hide_banner','-i',str(path)],capture_output=True,text=True,
        encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    info={'path':str(Path(path).relative_to(ROOT)),'bytes':Path(path).stat().st_size,'sha256':sha(path),
        'has_audio':'Audio:'in p.stderr,'ffmpeg_header':p.stderr}
    if decode:
        p=run([FFMPEG,'-v','error','-nostats','-progress','pipe:1','-i',path,'-f','null','-'])
        info['full_decode_errors']=p.stderr.strip()
        frames=re.findall(r'^frame=(\d+)',p.stdout,re.M)
        info['decoded_frames']=int(frames[-1]) if frames else None
        if info['full_decode_errors']:raise ValueError(info['full_decode_errors'])
    return info
