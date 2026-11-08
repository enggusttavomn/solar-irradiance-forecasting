"""Consolidate V12 reviews and expose the continuous narrated cut locally."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time

from montagem_v10_common import ROOT, read, write, sha

OUT=ROOT/'documentacao/relatorio_final_ea019/video/montagem_final_v12'
TMP=ROOT/'tmp/montagem_final_v12'


def main():
    verification=read(OUT/'verificacao_video_final_v12.json')
    voice=read(OUT/'voz_e_legendas_continuas_v12.json')
    timeline=read(OUT/'timeline_montagem_v12.json')
    edit=read(TMP/'audit_edicao_continua_v12.json')
    mix=read(TMP/'audit_audio_mix_v12.json')
    visual=read(OUT/'verificacao_amostral_continua_v12.json')
    general=read(TMP/'qa_geral_final_v12.json')
    temporal=read(TMP/'qa_temporal_visual_v12.json')
    holds=read(TMP/'qa_hold_endpoints_v12.json')
    root_review=read(TMP/'qa_root_general_final_v12.json')
    assert general['status']=='pass' and not general['flags']
    assert temporal['status']=='passed_final_temporal_sample_review'
    assert not temporal['material_issues'] and not temporal['required_changes']
    assert temporal['all21material_hold_endpoints_passed']
    assert holds['status']=='passed_all_21_material_hold_endpoint_audits'
    assert not holds['pending_material_action_fixes']
    assert root_review['sampled_visual_review_passed']
    assert general['manifest_video_sha256']==temporal['video_sha256']==verification['files'][0]['sha256']
    assert root_review['source_video_sha256']==verification['files'][0]['sha256']
    assert edit['status']=='pass' and not edit['material_conflicts']
    assert mix['status']=='pass' and not mix['errors'] and not mix['material_flags']
    assert visual['manual_general_review_passed'] and visual['manual_sequence_review_passed']
    assert visual['all_sampled_native_frames_correspond']
    assert not visual['source_frame_comparison_failures']
    assert timeline['frames']==voice['frames']==14718 and timeline['duration']==490.6
    for entry in verification['files']:
        path=ROOT/entry['path']
        assert path.is_file() and sha(path)==entry['sha256']
        assert entry['decoded_frames']==14718 and not entry['full_decode_errors']
    review=OUT/'revisao';review.mkdir(exist_ok=True)
    records=[]
    for source in [TMP/'audit_edicao_continua_v12.json',TMP/'audit_audio_mix_v12.json',
                   TMP/'audio/retakes_review_v12.json',TMP/'observation_pause_boundaries_audit.json',
                   TMP/'visual_schedule_v12.json', TMP/'qa_geral_final_v12.json',
                   TMP/'qa_temporal_visual_v12.json', TMP/'qa_hold_endpoints_v12.json',
                   TMP/'qa_root_general_final_v12.json']:
        target=review/source.name;shutil.copy2(source,target)
        records.append({'path':str(target.relative_to(ROOT)),'sha256':sha(target)})
    source=Path('C:/Users/gusta/OneDrive/Documents/Sound Recordings/GRAVACAO.m4a')
    assert sha(source)=='64afb2c901412c499cdaa0e2c8438075beb30309f9fbb05e36145e271bae5d3e'
    result={
        'version':12,'status':'complete','completed_utc':datetime.now(timezone.utc).isoformat(),
        'duration_seconds':490.6,'fps':30,'frames':14718,'resolution':[1920,1080],
        'original_recording_seconds':579.648,'original_recording_preserved':True,
        'new_continuous_voice_used':True,'approved_personal_intro_preserved':True,
        'voice_time_stretch_used':False,'speech_synthesis_used':False,
        'noise_reduction':'Conservative70Hz highpass and6dB FFT denoise;25ms filter latency compensated.',
        'voice_normalization':'Whole narration at -16LUFS, not independent per-sentence gain.',
        'visual_motion':'Selected animation actions play at native1x; redundant shots and settled tails are shortened. Key construction completeness and21 held endpoints were reviewed.',
        'voice_and_captions_cross_visual_cuts':True,
        'retakes_removed':2,'incorrect_numeric_clause_removed':'Spoken13.77 six-month reading only.',
        'correct_six_month_value_on_chart':'13,67 W/m²',
        'caption_policy':'Verified transcript/orthography; no synthetic replacement of the missing numerical reading.',
        'full_decode_passed_both_exports':True,
        'general_samples_reviewed':visual['general_samples'],
        'temporal_samples_reviewed':visual['temporal_samples'],
        'held_scene_endpoints_reviewed':21,
        'sampled_visual_and_temporal_review_passed':True,
        'objective_audio_review_passed':True,'encoder':'Intel Quick Sync h264_qsv',
        'audio_listening_performed':False,'full_realtime_playback_reviewed':False,
        'review_scope':'Objective source/audio checks and static/sequential visual samples, not human listening or full realtime playback.',
        'files':verification['files'],'reports':records,'external_uploads_performed':False,
    }
    write(OUT/'revisao_final_continua_v12.json',result)
    verification.update({'status':'complete','sampled_visual_review_passed':True,
                         'sampled_temporal_review_passed':True,'objective_audio_review_passed':True,
                         'review_report':str((OUT/'revisao_final_continua_v12.json').relative_to(ROOT))})
    write(OUT/'verificacao_video_final_v12.json',verification)
    (OUT/'LEIA_ME_VIDEO_FINAL_CONTINUO_V12.txt').write_text(
        'VÍDEO FINAL COM NARRAÇÃO CONTÍNUA V12\n\n'
        'Duração: 8min10,6s, incluindo sua apresentação inicial e conclusão sobre a fábrica.\n'
        'Full HD 1920×1080, 30 quadros/s. Codificação Intel Quick Sync.\n\n'
        'ARQUIVOS FINAIS\n'
        'Video_TCC_Final_Continuo_Somente_Voz_v12.mp4\n'
        'Video_TCC_Final_Continuo_Com_Trilha_v12.mp4\n'
        'Abra assistir_video_final_continuo_v12.html para alternar o áudio e navegar pelos assuntos.\n'
        'As legendas estão na imagem e também em Legendas_Finais_v12.srt.\n\n'
        'EDIÇÃO\n'
        'Nova gravação GRAVACAO.m4a. Retiradas as tentativas abortadas na quantização e no resultado horário; tomadas completas posteriores mantidas.\n'
        'Intervalos longos de gravação encurtados; respirações e pausas úteis preservadas.\n'
        'Limpeza suave do ruído e normalização da faixa de voz inteira.\n'
        'As falas e legendas continuam através das trocas de imagem. As pausas de observação são pontuais.\n'
        'Os movimentos selecionados permanecem em velocidade original; cenas redundantes e permanências finais foram encurtadas.\n'
        'A leitura equivocada de 13,77 no resultado de seis meses foi retirada.\n'
        'O gráfico conserva o valor correto, 13,67 W/m², sem fabricar uma nova fala.\n'
        'Mantidos capa aprovada, apresentador e cadeira coloridos, fundo preto e correção da exceção da LSTM.\n\n'
        'CONFERÊNCIA\n'
        'Decodificação integral dos dois MP4; conferência de fontes PCM, cortes, níveis, legendas e amostras sequenciais.\n'
        'Escopo de revisão: verificações objetivas e amostras visuais. Não houve escuta humana nem playback integral em tempo real.\n'
        'Os arquivos originais e versões anteriores foram preservados. Nenhum upload externo foi feito.\n',encoding='utf-8')
    new_launcher=ROOT/'ASSISTIR_VIDEO_FINAL_CONTINUO_V12.cmd'
    if new_launcher.exists():
        default=ROOT/'ASSISTIR_VIDEO_TCC.cmd'
        backup=ROOT/'ASSISTIR_VIDEO_TCC_ANTES_V12.cmd'
        if default.exists() and not backup.exists():shutil.copy2(default,backup)
        shutil.copy2(new_launcher,default)
    write(OUT/'progresso_montagem_v12.json',{'stage':'complete','updated_unix':time.time(),
          'duration_seconds':490.6,'exports':2,'encoder':'h264_qsv'})
    print('V12_CONTINUOUS_DELIVERY_COMPLETE: 490.6 seconds,2 final exports')


if __name__=='__main__':
    main()
