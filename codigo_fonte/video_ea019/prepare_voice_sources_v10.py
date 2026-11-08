"""Decode entire recordings to one zero-based PCM timeline before any cuts."""
import sys,json,wave,re
from pathlib import Path
from montagem_v10_common import *
sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
import numpy as np

DEST=TMP/'voice_pcm'
DEST.mkdir(parents=True,exist_ok=True)

def wav_info(path):
    with wave.open(str(path),'rb') as w:
        rate=w.getframerate();channels=w.getnchannels();samples=w.getnframes()
        pcm=np.frombuffer(w.readframes(samples),dtype='<i2').astype(np.float32)/32768
    return {'sample_rate':rate,'channels':channels,'samples':samples,'duration':samples/rate,
        'peak_dbfs':float(20*np.log10(max(np.max(np.abs(pcm)),1e-12))),
        'rms_dbfs':float(20*np.log10(max(np.sqrt(np.mean(pcm*pcm)),1e-12)))}

def prepare(name,source):
    raw=DEST/(name+'_raw_48k.wav');normalized=DEST/(name+'_normalizado_48k.wav')
    rec=DEST/(name+'_manifest.json');key=sha(source)
    old=read(rec,{})
    if old.get('source_sha256')==key and normalized.exists()and sha(normalized)==old.get('normalized_sha256'):
        return old
    progress('preparing_recorded_voice',source=name)
    run([FFMPEG,'-v','error','-y','-threads','2','-i',source,'-map','0:a:0','-vn',
        '-af','asetpts=PTS-STARTPTS','-ac','1','-ar','48000','-c:a','pcm_s16le','-map_metadata','-1',raw])
    # Conservative speech cleanup. Keep the natural rhythm, pitch and syllables.
    before='highpass=f=70'
    first=run([FFMPEG,'-hide_banner','-y','-i',raw,'-af',before+',loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json',
        '-f','null','-'])
    match=re.findall(r'\{\s*"input_i".*?\}',first.stderr,re.S)
    if not match:raise ValueError('Missing loudness analysis')
    stats=json.loads(match[-1])
    norm=('loudnorm=I=-16:TP=-1.5:LRA=11:measured_I='+stats['input_i']+
        ':measured_TP='+stats['input_tp']+':measured_LRA='+stats['input_lra']+
        ':measured_thresh='+stats['input_thresh']+':offset='+stats['target_offset']+
        ':linear=true:print_format=json')
    second=run([FFMPEG,'-v','info','-y','-i',raw,'-af',before+','+norm,
        '-ac','1','-ar','48000','-c:a','pcm_s16le','-map_metadata','-1',normalized])
    after_json=re.findall(r'\{\s*"input_i".*?\}',second.stderr,re.S)
    raw_info=wav_info(raw);info=wav_info(normalized)
    if abs(info['duration']-raw_info['duration'])>.01:raise ValueError('Normalization changed timing')
    result={'source':str(source),'source_sha256':key,'timebase':'First decoded PCM sample = 0; no seeking on compressed source',
        'raw_path':str(raw.relative_to(ROOT)),'raw_sha256':sha(raw),'raw_info':raw_info,
        'normalized_path':str(normalized.relative_to(ROOT)),'normalized_sha256':sha(normalized),'normalized_info':info,
        'filters':before+','+norm,'loudness_before':stats,'loudness_after':json.loads(after_json[-1]) if after_json else None,
        'source_modified':False,'voice_synthesis_used':False,'speech_time_stretch_used':False}
    write(rec,result);print('VOICE_READY '+name,flush=True);return result

if __name__=='__main__':
    all_sources={name:prepare(name,path) for name,path in [('principal',MAIN_AUDIO),('encerramento',END_AUDIO),('apresentacao',INTRO)]}
    write(OUT/'fontes_voz_v10.json',all_sources)
    print('ALL_VOICE_SOURCES_READY',flush=True)
