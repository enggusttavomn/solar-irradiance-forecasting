"""Local recurrent video matting, preserving original RGB and the visible chair."""
from pathlib import Path
import sys, json, subprocess, hashlib, time, argparse, math, re

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
import numpy as np
import onnxruntime as ort
from PIL import Image,ImageDraw,ImageFilter,ImageOps

SOURCE=Path('C:/Users/gusta/Pictures/Camera Roll/WIN_20261104_20_01_05_Pro.mp4')
BASE=ROOT/'documentacao/relatorio_final_ea019/video/abertura_apresentacao_v1/capa_apresentacao_fundo_v1.png'
MODEL=ROOT/'.tools/video-matting/rvm_mobilenetv3_fp32.onnx'
FF=ROOT/'.tools/video-python/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
OUT=ROOT/'documentacao/relatorio_final_ea019/video/montagem_final_v10'
TMP=ROOT/'tmp/montagem_final_v10/intro'
OUT.mkdir(parents=True,exist_ok=True);TMP.mkdir(parents=True,exist_ok=True)
IW,IH=960,540
FPS=30
ROI=(220,90,800,540)
DX,DY,DW,DH=1300,600,560,480
GRAY=False
VARIANT=''
SAMPLE_TIME=4

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd):
    r=subprocess.run([str(x)for x in cmd],cwd=ROOT,capture_output=True)
    if r.returncode:raise RuntimeError(r.stderr.decode('utf-8',errors='replace'))
    return r
def write(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def session():
    so=ort.SessionOptions();so.intra_op_num_threads=4;so.inter_op_num_threads=1
    so.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    return ort.InferenceSession(str(MODEL),sess_options=so,providers=['CPUExecutionProvider'])

def chair_mask():
    im=Image.new('L',(IW,IH),0);d=ImageDraw.Draw(im)
    # Add only the visible backrest/wings, not the backpack to the left.
    right=[(604,190),(620,199),(628,251),(669,317),(706,342),(739,375),(757,402),(765,429),(758,449),(747,470),(735,463),(702,434),(650,406),(610,383),(572,360),(577,250)]
    left=[(407,314),(392,326),(373,345),(352,363),(336,380),(320,402),(311,430),(312,456),(325,479),(359,459),(398,410),(422,374)]
    d.polygon(right,fill=255);d.polygon(left,fill=255)
    return np.asarray(im.filter(ImageFilter.GaussianBlur(.8)),dtype=np.float32)/255

def composite(rgb,alpha,base,processed=False):
    a=alpha if processed else np.maximum(np.clip((alpha-.025)/.975,0,1),CHAIR)
    # Original source colors, not RVM foreground predictions or generated imagery.
    sx,sy=rgb.shape[1]/IW,rgb.shape[0]/IH
    rgb_roi=(round(ROI[0]*sx),round(ROI[1]*sy),round(ROI[2]*sx),round(ROI[3]*sy))
    im=Image.fromarray(rgb,'RGB').crop(rgb_roi)
    if GRAY:im=ImageOps.grayscale(im).convert('RGB')
    am=Image.fromarray(np.uint8(np.clip(a,0,1)*255),'L').crop(ROI)
    rw,rh=im.size;s=min(DW/rw,DH/rh);nw,nh=round(rw*s),round(rh*s)
    im=im.resize((nw,nh),Image.Resampling.LANCZOS)
    am=am.resize((nw,nh),Image.Resampling.LANCZOS)
    dest=base.copy();x=DX+(DW-nw)//2;y=1080-nh
    dest.paste(im,(x,y),am)
    return dest,am,a

CHAIR=chair_mask()
BASEIM=Image.open(BASE).convert('RGB')
if BASEIM.size!=(1920,1080):raise ValueError('Incorrect cover resolution')
if np.asarray(BASEIM)[200:880,96:1154].std()<12:raise ValueError('Cover typography missing')

def infer(sess,rgb,states):
    src=np.ascontiguousarray(rgb.transpose(2,0,1)[None].astype(np.float32)/255)
    feeds={'src':src,'downsample_ratio':np.array([.5],np.float32),**{f'r{i+1}i':x for i,x in enumerate(states)}}
    outputs=sess.run(None,feeds)
    return outputs[1][0,0],outputs[2:]

def preview(cached=False):
    sample_label=f'{SAMPLE_TIME:g}'.replace('.','_')
    frame=TMP/(f'original_{sample_label}s_fullhd.png' if cached else f'original_{sample_label}s_960.png')
    cmd=[FF,'-v','error','-y','-ss',str(SAMPLE_TIME),'-threads','2','-i',SOURCE,'-frames:v','1']
    if not cached:cmd+=['-vf','scale=960:540']
    cmd+=['-threads','2','-update','1',frame];run(cmd)
    rgb=np.asarray(Image.open(frame).convert('RGB'))
    if cached:
        cacheframe=TMP/f'matte_cache_{sample_label}s{VARIANT}.png'
        run([FF,'-v','error','-y','-ss',str(SAMPLE_TIME),'-threads','2','-i',OUT/'intro_matte_960x540_v10.mkv',
             '-frames:v','1','-threads','2','-update','1',cacheframe])
        a=np.asarray(Image.open(cacheframe).convert('L'),dtype=np.float32)/255
    else:
        sess=session();states=[np.zeros((1,1,1,1),np.float32)for _ in range(4)]
        for _ in range(5):a,states=infer(sess,rgb,states)
    out,am,a=composite(rgb,a,BASEIM,processed=cached)
    path=TMP/f'preview_real_{sample_label}s_v10{VARIANT}.png'
    out.save(path);Image.fromarray(np.uint8(a*255),'L').save(TMP/f'matte_real_{sample_label}s_v10{VARIANT}.png')
    original=np.asarray(BASEIM);comp=np.asarray(out)
    assert np.array_equal(original[:,:min(DX,1250)],comp[:,:min(DX,1250)]),'Presenter changed the title area'
    print('PREVIEW_READY '+str(path),flush=True)

def render(cached=False):
    before=sha(SOURCE);sess=None if cached else session();states=[np.zeros((1,1,1,1),np.float32)for _ in range(4)]
    raw=OUT/f'intro_1080p30_sem_audio_v10{VARIANT}.mp4';alpha_path=OUT/'intro_matte_960x540_v10.mkv'
    dec_filter='fps=30' if cached else 'fps=30,scale=960:540'
    rw,rh=(1920,1080) if cached else (IW,IH)
    dec=subprocess.Popen([str(FF),'-v','error','-threads','2','-i',str(SOURCE),'-an','-vf',dec_filter,
        '-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=(TMP/'decode.log').open('wb'))
    enc=subprocess.Popen([str(FF),'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','pipe:0',
        '-an','-map_metadata','-1','-c:v','libx264','-preset','medium','-crf','18','-threads','2','-pix_fmt','yuv420p',
        '-video_track_timescale','15360','-movflags','+faststart',str(raw)],stdin=subprocess.PIPE,stderr=(TMP/'encode.log').open('wb'))
    matdec=None;mae=None
    if cached:
        matdec=subprocess.Popen([str(FF),'-v','error','-threads','2','-i',str(alpha_path),'-an','-f','rawvideo','-pix_fmt','gray','pipe:1'],
            stdout=subprocess.PIPE,stderr=(TMP/'matte_decode.log').open('wb'))
    else:
        mae=subprocess.Popen([str(FF),'-v','error','-y','-f','rawvideo','-pix_fmt','gray','-s','960x540','-r','30','-i','pipe:0',
            '-an','-map_metadata','-1','-c:v','ffv1','-level','3','-threads','2',str(alpha_path)],stdin=subprocess.PIPE,stderr=(TMP/'matte_encode.log').open('wb'))
    count=0;started=time.time();qa=[];nbytes=rw*rh*3
    try:
        while True:
            data=dec.stdout.read(nbytes)
            if not data:break
            if len(data)!=nbytes:raise ValueError('Short RGB frame')
            rgb=np.frombuffer(data,np.uint8).reshape(rh,rw,3)
            if cached:
                m=matdec.stdout.read(IW*IH)
                if len(m)!=IW*IH:raise ValueError('Cached matte frame mismatch')
                a=np.frombuffer(m,np.uint8).reshape(IH,IW).astype(np.float32)/255
            else:a,states=infer(sess,rgb,states)
            out,am,a=composite(rgb,a,BASEIM,processed=cached)
            enc.stdin.write(np.asarray(out).tobytes())
            if mae:mae.stdin.write(np.uint8(a*255).tobytes())
            if count in [0,60,120,210,360,420]:
                p=TMP/f'qa_composicao_{count:04d}{VARIANT}.png';out.save(p);qa.append(str(p.relative_to(ROOT)))
                assert np.array_equal(np.asarray(BASEIM)[:,:min(DX,1250)],np.asarray(out)[:,:min(DX,1250)]),'Altered cover text'
            count+=1
            if count%30==0:print(f'INTRO_MATTE {count} frames {time.time()-started:.1f}s',flush=True)
    finally:
        enc.stdin.close();dec.stdout.close()
        if mae:mae.stdin.close()
        if matdec:matdec.stdout.close()
    codes=[dec.wait(),enc.wait()]+([mae.wait()]if mae else[])+([matdec.wait()]if matdec else[])
    if any(codes):raise RuntimeError('FFmpeg stream failed '+str(codes))
    duration=count/FPS
    final=OUT/f'intro_1080p30_com_audio_v10{VARIANT}.mp4'
    run([FF,'-v','error','-y','-i',raw,'-i',SOURCE,'-map','0:v:0','-map','1:a:0',
         '-map_metadata','-1','-c:v','copy','-af',f'aresample=48000:async=1:first_pts=0,apad=whole_dur={duration}',
         '-c:a','aac','-b:a','192k','-t',str(duration),'-movflags','+faststart',final])
    decoded=run([FF,'-v','error','-nostats','-progress','pipe:1','-threads','2','-i',final,'-f','null','-'])
    final_frames=[int(x)for x in re.findall(rb'^frame=(\d+)$',decoded.stdout,re.M)]
    if final_frames[-1]!=count or decoded.stderr.strip():raise ValueError('Final intro decode failed')
    if sha(SOURCE)!=before:raise ValueError('Original video changed')
    record={'version':10,'status':'provisional_encoded_pending_cover_approval','cover_user_approval_pending':True,'path':str(final.relative_to(ROOT)),
        'sha256':sha(final),'source_path':str(SOURCE),'source_sha256':before,'source_original_unmodified':True,
        'background_path':str(BASE.relative_to(ROOT)),'background_sha256':sha(BASE),
        'duration_seconds':duration,'fps':30,'frame_count':count,'resolution':[1920,1080],
        'audio':'original recording, 48kHz AAC stereo, tail aligned to exact video duration within one frame',
        'method':'RVM recurrent alpha plus feathered fixed chair polygons; original footage with requested grayscale transform' if GRAY else 'RVM recurrent alpha plus feathered fixed chair polygons; original RGB preserved',
        'model_url':'https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx',
        'model_license':'GPL-3.0','model_sha256':sha(MODEL),'provider':'CPUExecutionProvider','onnxruntime_version':ort.__version__,
        'intra_op_threads':4,'input_resolution':[960,540],'downsample_ratio':.5,'recurrent_states_recycled':True,
        'roi':ROI,'presenter_region':[DX,DY,DW,DH],'matte_lossless_path':str(alpha_path.relative_to(ROOT)),
        'matte_cache_reused':cached,'monochrome_opening':GRAY,'variant':VARIANT,
        'rgb_decode_resolution':[rw,rh],
        'qa_frames':qa,'full_decode_errors':0,'full_decode_frame_count':final_frames[-1],
        'cover_pixels_outside_overlay_verified_identical_before_encoding':True,
        'generative_images_used_in_video':False,'elapsed_seconds':round(time.time()-started,2)}
    write(OUT/f'intro_manifesto_v10{VARIANT}.json',record)
    print('INTRO_V10_ENCODED '+str(final),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--preview',action='store_true');p.add_argument('--render',action='store_true')
    p.add_argument('--cached',action='store_true');p.add_argument('--grayscale',action='store_true');p.add_argument('--base',type=Path)
    p.add_argument('--placement',nargs=4,type=int);p.add_argument('--variant',default='');p.add_argument('--sample-time',type=float,default=4);a=p.parse_args()
    GRAY=a.grayscale;VARIANT=('_'+a.variant)if a.variant else '';SAMPLE_TIME=a.sample_time
    if a.base:BASE=a.base.resolve();BASEIM=Image.open(BASE).convert('RGB')
    if a.placement:DX,DY,DW,DH=a.placement
    if a.preview:preview(cached=a.cached)
    elif a.render:render(cached=a.cached)
    else:p.error('Specify --preview or --render')
