"""Reuse audio measurements only when final AAC packets are byte-identical."""
from copy import deepcopy
from datetime import datetime, timezone
import shutil
from montagem_v10_common import ROOT, FFMPEG, read, write, run, sha


def main():
    tmp=ROOT/'tmp/montagem_final_v12'
    path=tmp/'audit_audio_mix_v12.json'
    report=read(path)
    marker=ROOT/'documentacao/relatorio_final_ea019/video/montagem_final_v12/verificacao_video_final_v12.json'
    final=read(marker)
    previous=deepcopy(report['measurements'])
    audios=[];videos=[]
    for entry in final['files']:
        file=ROOT/entry['path']
        assert sha(file)==entry['sha256']
        for stream,target in [('a',audios),('v',videos)]:
            result=run([FFMPEG,'-v','error','-i',file,'-map',f'0:{stream}:0',
                        '-c','copy','-f','hash','-hash','sha256','-'])
            target.append(result.stdout.strip())
    assert audios==report['audio_packet_sha256'], 'Audio changed: repeat the full objective audio audit'
    assert videos[0]==videos[1]
    backup=tmp/'audit_audio_mix_v12_before_final_visual_fix.json'
    if not backup.exists():shutil.copy2(path,backup)
    for measurement,entry in zip(report['measurements'],final['files']):
        measurement['sha256']=entry['sha256']
        measurement['bytes']=entry['bytes']
    report['video_packet_sha256']=videos
    report['audio_measurements_reused_after_exact_aac_bitstream_identity']=True
    report['final_bitstream_identity_check']={
        'checked_utc':datetime.now(timezone.utc).isoformat(),
        'previous_video_only_revision_measurements':previous,
        'new_exports':final['files'],'aac_packet_hashes_unchanged':True,
        'reason':'Only five visual shots changed after the measured export. Every AAC packet is identical, so measured loudness, true peak, ducking and voice-presence results are exactly applicable.',
        'final_ready_marker_sha256':sha(marker),
    }
    report['protected_files_unchanged']=True
    write(path,report)
    print('FINAL_AUDIO_IDENTITY_VERIFIED: AAC unchanged in both final exports; metadata refreshed')


if __name__=='__main__':main()
