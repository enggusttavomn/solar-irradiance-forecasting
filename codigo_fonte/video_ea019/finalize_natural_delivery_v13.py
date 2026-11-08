"""Publish verified local V13 artifacts; no cloud upload or report mutation."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from montagem_v10_common import ROOT, read, write, sha

OUT = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v13'
TMP = ROOT / 'tmp/montagem_final_v13'


def main():
    audio = read(TMP/'qa_audio_original_v13.json')
    visual = read(TMP/'qa_visual_transicoes_v13.json')
    verification = read(OUT/'verificacao_video_final_v13.json')
    assert audio['status'] == 'pass' and not audio['conflicts']
    for audited_path, expected_hash in audio['files_sha256'].items():
        assert sha(Path(audited_path)) == expected_hash, audited_path
    assert visual['status'].startswith('passed_')
    assert not visual['material_issues'] and not visual['required_changes']
    picture = ROOT/visual['video_picture_path']
    assert sha(picture) == visual['video_picture_sha256']
    for record in verification['files']:
        path = ROOT/record['path']
        assert sha(path) == record['sha256'] and path.stat().st_size == record['bytes']
        assert record['decoded_frames'] == 14667 and not record['full_decode_errors']
    evidence = {
        'audio_qa':str((TMP/'qa_audio_original_v13.json').relative_to(ROOT)),
        'audio_qa_sha256':sha(TMP/'qa_audio_original_v13.json'),
        'visual_qa':str((TMP/'qa_visual_transicoes_v13.json').relative_to(ROOT)),
        'visual_qa_sha256':sha(TMP/'qa_visual_transicoes_v13.json'),
        'root_visual_review':'Full-size GHI annotation preview, transition sheets01/08, and6final closing stills inspected.',
        'audio_source_identity_verified':True,
        'audio_listening_performed':False,
        'full_realtime_playback_reviewed':False,
        'external_uploads_performed':False,
        'report_modified':False,
        'publication_deferred_by_user':True,
    }
    verification.update(status='complete',completed_utc=datetime.now(timezone.utc).isoformat(),
                        audio_review_passed=True,sampled_visual_review_passed=True,
                        final_retaken_ending_verified=True,qa=evidence)
    write(OUT/'verificacao_video_final_v13.json',verification)
    write(OUT/'revisao_final_v13.json',{
        'version':13,'status':'complete','duration':488.9,'frames':14667,
        'resolution':[1920,1080],'fps':30,'voice_original_without_timbre_filters':True,
        'voice_constant_gain_db':-1,'ending_repeated_attempt_removed':True,
        'transition_count':30,'body_timing_preserved':True,'subtitle_count':112,
        'two_final_versions':verification['files'],'qa':evidence,
    })
    launcher=ROOT/'ASSISTIR_VIDEO_TCC.cmd'
    backup=ROOT/'ASSISTIR_VIDEO_TCC_ANTES_V13.cmd'
    if launcher.exists() and not backup.exists():
        shutil.copy2(launcher,backup)
    launcher.write_text('@echo off\nstart "" "%~dp0documentacao\\relatorio_final_ea019\\video\\montagem_final_v13\\assistir_video_voz_natural_v13.html"\n',encoding='ascii')
    pending=read(TMP/'publicacao_adiada.json')
    pending['current_delivery_status']='V13_complete_for_user_review'
    pending['final_video_files']=[{'path':r['path'],'sha256':r['sha256']} for r in verification['files']]
    pending['duration_seconds']=488.9
    write(TMP/'publicacao_adiada.json',pending)
    print('V13_COMPLETE: two verified FullHD MP4s; player/launcher updated; YouTube and report unchanged.')


if __name__=='__main__':
    main()
