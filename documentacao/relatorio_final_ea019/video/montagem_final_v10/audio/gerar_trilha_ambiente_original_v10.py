"""Original, sample-free ambient accompaniment for the scientific video.

Creates a stereo 48 kHz PCM16 stem. No voice, drum loop, external recording or
music-service/API asset is used. All pitched material is synthesized here.
"""
from pathlib import Path
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('MKL_NUM_THREADS','1')
import sys,math,json,wave,hashlib,subprocess
from datetime import datetime,timezone

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'codigo_fonte/video_ea019').is_dir())
sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
import numpy as np
from scipy.signal import butter,sosfilt,resample_poly

OUT=Path(__file__).resolve().parent
WAV=OUT/'trilha_ambiente_original_v10.wav'
SYNTH_RATE=24000
OUTPUT_RATE=48000
DURATION=620
SEED=20261104
N=SYNTH_RATE*DURATION
rng=np.random.default_rng(SEED)
music=np.zeros((N,2),np.float32)
chord_events=[];piano_events=[]

VOICINGS={
 'Dmaj9': [[50,57,61,64,66],[50,54,57,61,64]],
 'Bm7': [[47,54,57,62,66],[47,54,59,62,69]],
 'Gmaj9': [[43,50,54,57,59],[43,54,57,59,62]],
 'Aadd9': [[45,52,57,59,61],[45,52,59,61,64]],
}
PITCH_CLASSES={
 'Dmaj9':[62,64,66,69,73], 'Bm7':[59,62,66,69,74],
 'Gmaj9':[59,62,66,69,74], 'Aadd9':[61,64,69,71,76]
}

def frequency(midi):return 440*2**((midi-69)/12)
def pan_gains(pan):
    angle=(pan+1)*math.pi/4
    return math.cos(angle),math.sin(angle)
def smoothstep(x):
    x=np.clip(x,0,1);return x*x*(3-2*x)
def add_signal(start,signal,pan,amount):
    first=round(start*SYNTH_RATE)
    if first>=N:return
    offset=max(0,-first);first=max(0,first)
    count=min(len(signal)-offset,N-first)
    if count<=0:return
    left,right=pan_gains(pan)
    music[first:first+count,0]+=signal[offset:offset+count]*(amount*left)
    music[first:first+count,1]+=signal[offset:offset+count]*(amount*right)

def pad(start,duration,notes,cycle):
    release=5.0
    t=np.arange(round((duration+release)*SYNTH_RATE),dtype=np.float64)/SYNTH_RATE
    envelope=smoothstep(t/4.0)*(1-smoothstep((t-duration)/release))
    envelope*=.96+.04*np.sin(2*np.pi*t/17.3+cycle*.6)
    for i,note in enumerate(notes):
        f=frequency(note)
        base=np.zeros(len(t),np.float32)
        # Detuned string-like voices, with smoothly diminishing overtones.
        for cents,weight in [(-3.4,.26),(0,.48),(3.1,.26)]:
            actual=f*2**(cents/1200)
            phase=2*np.pi*actual*t+(.31*i+.19*cycle)
            tone=np.sin(phase)+.24*np.sin(2*phase+.12)+.085*np.sin(3*phase+.31)+.025*np.sin(4*phase+.7)
            base+=(tone*weight).astype(np.float32)
        base*=envelope.astype(np.float32)
        add_signal(start,base,[-.60,-.32,0,.32,.60][i],.038 if i else .030)
    # A restrained low foundation, not a rhythm or kick.
    f=frequency(notes[0]-12)
    bass=(np.sin(2*np.pi*f*t)+.10*np.sin(4*np.pi*f*t+.2))*envelope
    add_signal(start,bass.astype(np.float32),0,.014)

def piano(start,midi,velocity,pan):
    length=7.6
    t=np.arange(round(length*SYNTH_RATE),dtype=np.float64)/SYNTH_RATE
    f=frequency(midi)
    sig=np.zeros(len(t),np.float64)
    # Soft struck-string spectrum: inharmonicity and shorter upper-partial decay.
    for k,gain,decay in [(1,1,2.7),(2,.40,1.95),(3,.19,1.4),(4,.095,1.0),(5,.045,.78),(7,.014,.5)]:
        fk=f*k*math.sqrt(1+.00016*k*k)
        sig+=gain*np.sin(2*np.pi*fk*t+.17*k)*np.exp(-t/decay)
    sig+=(.10*np.sin(2*np.pi*f*1.0008*t+.03))*np.exp(-t/3.1)
    attack=smoothstep(t/.025)
    release=1-smoothstep((t-(length-.85))/.85)
    sig*=attack*release
    add_signal(start,sig.astype(np.float32),pan,velocity)

schedule=['Dmaj9','Bm7','Gmaj9','Aadd9']
durations=[28,28,32,24,32,24,28,28]
start=0.;index=0
while start<DURATION:
    duration=durations[index%len(durations)]
    chord=schedule[index%4]
    if start>=584:
        chord='Dmaj9';duration=DURATION-start
    notes=VOICINGS[chord][(index//4)%2]
    chord_events.append({'start':start,'duration':duration,'chord':chord,'midi_notes':notes})
    pad(start,duration,notes,index)
    # Sparse, newly generated broken-chord gestures with breathing space.
    offsets=[5.7,10.9,17.2,22.8] if index%3 else [7.0,13.4,20.6]
    palette=PITCH_CLASSES[chord]
    pattern=[0,2,1,3] if index%2 else [1,0,3,2]
    for j,offset in enumerate(offsets):
        if offset>=duration-2.5:continue
        actual_start=start+offset+float(rng.uniform(-.35,.35))
        note=palette[(pattern[j]+index//4)%len(palette)]
        # Upper octave sparingly, avoiding repeated high-pitched signal-like tones.
        if index%5==4 and j==len(offsets)-1:note-=12
        velocity=float(rng.uniform(.028,.042))
        pan=float(rng.uniform(-.22,.22))
        piano(actual_start,note,velocity,pan)
        piano_events.append({'start':round(actual_start,3),'midi':note,'velocity':round(velocity,5),'pan':round(pan,3)})
    start+=duration;index+=1

# Gentle analogue-like warmth and a soft upper spectrum.
music=np.tanh(music*.95).astype(np.float32)/.95
music=sosfilt(butter(2,30,'highpass',fs=SYNTH_RATE,output='sos'),music,axis=0).astype(np.float32)
music=sosfilt(butter(2,4600,'lowpass',fs=SYNTH_RATE,output='sos'),music,axis=0).astype(np.float32)

# Short stereo ambience built from original signal, not an external impulse.
wet=np.zeros_like(music)
delays=[(.049,.12),(.071,.11),(.113,.10),(.173,.085),(.241,.075),(.337,.065),
        (.431,.053),(.593,.043),(.769,.032),(1.01,.022),(1.29,.014),(1.63,.008)]
for i,(seconds,gain) in enumerate(delays):
    d=round(seconds*SYNTH_RATE)
    for channel in range(2):
        source=(1-channel) if i%2 else channel
        wet[d:,channel]+=gain*music[:-d,source]
wet=sosfilt(butter(2,2100,'lowpass',fs=SYNTH_RATE,output='sos'),wet,axis=0).astype(np.float32)
music=music*.89+wet*.29
del wet
music=resample_poly(music,2,1,axis=0,window=('kaiser',8.0)).astype(np.float32)
assert len(music)==OUTPUT_RATE*DURATION

fade_in=round(6*OUTPUT_RATE);fade_out=round(12*OUTPUT_RATE)
music[:fade_in]*=smoothstep(np.arange(fade_in,dtype=np.float64)/fade_in).astype(np.float32)[:,None]
music[-fade_out:]*=smoothstep(np.arange(fade_out,0,-1,dtype=np.float64)/fade_out).astype(np.float32)[:,None]
raw_peak=float(np.max(np.abs(music)))
target_peak=10**(-8/20)
music*=target_peak/raw_peak

peak=0.;squares=np.zeros(2,np.float64);sum_channels=np.zeros(2,np.float64)
cross=0.;max_step=0.;window_stats=[];previous=None
with wave.open(str(WAV),'wb') as w:
    w.setnchannels(2);w.setsampwidth(2);w.setframerate(OUTPUT_RATE)
    for first in range(0,len(music),OUTPUT_RATE):
        chunk=music[first:first+OUTPUT_RATE]
        # TPDF quantization dither only; no recorded noise or sampled sound.
        dither=(rng.random(chunk.shape,dtype=np.float32)-rng.random(chunk.shape,dtype=np.float32))/65536
        pcm=np.clip(np.rint((chunk+dither)*32767),-32768,32767).astype('<i2')
        if first==0:pcm[:32]=0
        if first+len(chunk)==len(music):pcm[-32:]=0
        w.writeframes(pcm.tobytes())
        normalized=pcm.astype(np.float64)/32768
        peak=max(peak,float(np.max(np.abs(normalized))))
        squares+=(normalized*normalized).sum(axis=0)
        sum_channels+=normalized.sum(axis=0)
        cross+=float((normalized[:,0]*normalized[:,1]).sum())
        if previous is not None:max_step=max(max_step,float(np.max(np.abs(normalized[0]-previous))))
        max_step=max(max_step,float(np.max(np.abs(np.diff(normalized,axis=0)))))
        previous=normalized[-1]
        if first//OUTPUT_RATE%10==0:
            rms=float(np.sqrt((normalized*normalized).mean()))
            window_stats.append({'second':first//OUTPUT_RATE,'rms_dbfs':20*math.log10(max(rms,1e-12))})

with wave.open(str(WAV),'rb') as w:
    info={'channels':w.getnchannels(),'sample_width_bytes':w.getsampwidth(),
          'sample_rate':w.getframerate(),'frames':w.getnframes(),'duration_seconds':w.getnframes()/w.getframerate()}
assert info=={'channels':2,'sample_width_bytes':2,'sample_rate':48000,'frames':29760000,'duration_seconds':620.0}
rms=np.sqrt(squares/len(music))
means=sum_channels/len(music)
correlation=(cross/len(music)-means[0]*means[1])/math.sqrt((squares[0]/len(music)-means[0]**2)*(squares[1]/len(music)-means[1]**2))
peak_db=20*math.log10(peak)
assert peak_db<=-6
assert np.all(np.isfinite(music))
report={'created_utc':datetime.now(timezone.utc).isoformat(),'path':str(WAV.relative_to(ROOT)),
 'sha256':hashlib.sha256(WAV.read_bytes()).hexdigest(),'bytes':WAV.stat().st_size,
 'format':'PCM signed16-bit little-endian WAV stereo','technical':info,
 'sample_peak_dbfs':peak_db,'rms_dbfs_per_channel':[20*math.log10(float(x)) for x in rms],
 'dc_per_channel':means.tolist(),'stereo_correlation':float(correlation),'maximum_sample_step':max_step,
 'clipping_samples':0,'fade_in_seconds':6,'fade_out_seconds':12,'synthesis_rate':SYNTH_RATE,
 'seed':SEED,'style':'Warm quiet documentary ambience: slow harmonic pads and sparse soft struck-string piano; no drums or vocals.',
 'original_synthesis':True,'external_audio_or_samples_used':False,'music_service_or_api_used':False,
 'recorded_voice_used':False,'dynamics_mixed_to_voice':False,'human_listening_claimed':False,
 'harmony':chord_events,'piano_notes':piano_events,'one_second_rms_samples':window_stats,
 'reverb':'Original stereo multitap ambience, final tap1.63s, damped2100Hz',
 'master_note':'This620-second stem has headroom. Trim to final montage and apply a new end fade at that cut; root will duck under speech.',
 'reproduction_script':Path(__file__).name}
(OUT/'trilha_ambiente_original_v10.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'ready':True,**info,'sample_peak_dbfs':peak_db,'rms_dbfs_per_channel':report['rms_dbfs_per_channel'],
                  'chord_events':len(chord_events),'piano_notes':len(piano_events),'sha256':report['sha256']}),flush=True)

ffmpeg=ROOT/'.tools/video-python/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
preview=OUT/'amostra_trilha_original_20s_v10.m4a'
command=[str(ffmpeg),'-v','error','-y','-ss','20','-i',str(WAV),'-t','20','-c:a','aac','-b:a','192k',
         '-ar','48000','-ac','2','-map_metadata','-1','-movflags','+faststart',str(preview)]
result=subprocess.run(command,capture_output=True,text=True)
if result.returncode:raise RuntimeError(result.stderr)
print('V10_ORIGINAL_MUSIC_STEM_READY',flush=True)
