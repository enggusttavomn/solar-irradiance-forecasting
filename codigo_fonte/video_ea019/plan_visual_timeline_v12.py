"""Frame-exact native-speed picture edit under the continuous V12 voice master.

The sound and captions are independent global layers. Shots may change before
or after a paragraph boundary; their lengths are not dictated by voice snippets.
Only completed plateaus/repeated explanatory views are shortened. No audio is
written here and no source clip is accelerated.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v12'
TMP = ROOT / 'tmp/montagem_final_v12'
VOICE_PLAN = OUT / 'voz_e_legendas_continuas_v12.json'
TARGET = TMP / 'visual_schedule_v12.json'
BASE = ROOT / 'documentacao/relatorio_final_ea019/video/completo_v9/Video_TCC_GHI_Revisado_sem_legendas_v9.mp4'
INTRO = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v10/intro_1080p30_colorido_fundo_preto_v10_capa_v5.mp4'
PATCH = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v10/patches/matriz_historica_corrigida_6s_v10.mp4'
FACTORY = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v10/encerramento/fabrica_encerramento_limpa_v10.png'
FPS = 30


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def rel(path):
    return path.relative_to(ROOT).as_posix()


def frame(value):
    return round(value * FPS)


def main():
    voice = json.loads(VOICE_PLAN.read_text(encoding='utf-8-sig'))
    assert voice['frames'] == 14718 and abs(voice['duration'] - 490.6) < 1e-6
    assert not voice['voice_time_stretch_used'] and not voice['speech_synthesis_used']
    paragraphs = {p['index']: p for p in voice['paragraphs']}
    ending_start = paragraphs[26]['edited_start'] - .5
    assert 467.9 < ending_start < 468.1
    # (id, output start, output end, source start, source end, reason)
    # Output boundaries are frame-quantized once, so adjacent picture items
    # remain contiguous while the original recording continues underneath.
    shots = [
        ('sun_factory',14.133333333333333,20.0,0,5,'Establish natural Sun/factory while irradiance is introduced; short completed-state retention.'),
        ('unit_area',20.0,34.333333333333336,5,10.7,'Keep the completed1m² receiving area and its label before the native camera flyout starts10.7; meaningful voiced hold on the visible unit construction.'),
        ('dni_normal_plane',34.333333333333336,41.63333333333333,10.7,18,'Preserve the complete native camera flyout and tilted-plane/90degree construction; plane11.8 and marker12.5 keep their existing output anchors.'),
        ('horizontal_projection',41.63333333333333,49.8,18,24.9,'Native zenith/cosine/diffuse sequence, then retain its completed visible geometry before the24.95camera/day-night transition. Source endpoint24.9avoids freezing the next scene first frame.'),
        ('day_night',49.8,54.8,25,30,'Complete original day/night sequence at1x.'),
        ('cloud_variation',54.8,57.8,30,33,'Keep cloud-induced curve change; omit last settled duplicate second.'),
        ('dashed_future',57.8,60.1,38,40.3,'Use the actual dashed-future construction with the forecasting sentence; skip duplicate history reprise34–38.'),
        ('photovoltaic_application',60.1,62.4,42,44.3,'PV appears with its potential application; shorten settled tail.'),
        ('energy_planning_bridge',62.4,73.18333333333334,47,52,'Complete energy-planning objects, then retain factory while the continuous sentence introduces learning from the past.'),
        ('three_models',73.18333333333334,77.18333333333334,52,56,'Three-model introduction aligned to Comparei três; no audio break.'),
        ('lstm_native',77.18333333333334,92.7,56,71,'Complete ordered packets, gates, memory and final state at native speed; half-second finished-state retention.'),
        ('transformer_native',92.7,111.7,71,87,'Complete position/query/key/weight/value sequence and readable finished context; preserve temporal-order discussion.'),
        ('informer_queries_intro',111.7,115.7,87,91,'Native initial selected-query explanation.'),
        ('informer_sparse_queries',115.7,118.7,91,94,'Show one complete selected-query example; remove an additional repeated/settled final second.'),
        ('informer_encoder_reduction',118.7,124.5,95,98.6,'Native reduction finishes97.61; hold its completed state before encoder lift begins98.65, never in the middle of the lift.'),
        ('informer_cross_attention',124.5,128.9,98.6,103,'Preserve the complete encoder lift98.65–99.15and all cross-attention query updates at native1x; last update finishes101.95.'),
        ('same_input_three_models',128.9,139.2,103,112,'All three receive the same history/locality and produce direct future vectors; retain finished comparison during the data bridge.'),
        ('americas_counts',139.2,149.3,112,115.23333333333333,'Keep all10factory symbols and country counts visible while Brasil/EUA/México are enumerated; omit unspoken Detroit zoom reprise.'),
        ('nsrdb_satellite_atmosphere',149.3,155.3,122,128,'NSRDB logo, satellite and atmosphere native flow; physical-model label appears with its spoken phrase.'),
        ('nsrdb_model_to_cell',155.3,162.5,128,135.2,'Native model→cell construction and first complete output flows; omit only repeated settled final1.8s.'),
        ('history_curve_reveal',162.5,164.5,137,139,'Full1.7s time-curve reveal plus selected points; then omit the unchanged early curve plateau.'),
        ('curve_to_histogram_bin',164.5,175.4,142.8,150,'Preserve continuous selected-reading migration into the bin; retain the completed400–450bucket while that range is read.'),
        ('histogram_fraction',175.4,179.2,150,153.8,'881/18496and4.8% appear with the spoken percentage; denominator remains readable.'),
        ('all_ten_distributions',179.2,191.2,157,169,'Complete native1.2s-per-locality sweep through all10sites. Omit the duplicate final overview and allow the next introductory clause to Jcut over the last sites.'),
        ('input_actual_history',191.2,195.7,172,176.5,'Native six-reading growth and1.8s chronological curve reveal; omit redundant order-label plateau178–184.'),
        ('camacari_representation',195.7,199.0,184,187.3,'Show complete named Camaçari learned representation; omit redundant Nevada repeat.'),
        ('two_input_routes',199.0,202.5,192,195.5,'Complete separate history/locality paths and future-vector construction; omit completed long tail.'),
        ('shared_ten_localities',202.5,205.5,200,203,'All10named factory symbols and initial city-to-shared-model paths are visible; no need to repeat all identical flows.'),
        ('task_hourly',205.5,210.0,210,214.5,'Native history and dashed72hforecast form before três dias; remove only settled task tail.'),
        ('task_daily',210.0,213.8,218,221.8,'Native year-history and30-day output reveal complete by+2.11s, followed by a reading window.'),
        ('task_monthly_one',213.8,217.2,226,229.4,'Native12month history and one-output construction; keep settled output for about1s.'),
        ('task_monthly_six',217.2,221.5,231,235.3,'Native six-output sequence finishes around+2.92s; last points remain readable.'),
        ('separate_monthly_networks',221.5,225.2,236,239.7,'Distinct one- and six-output networks; trim duplicate comparison tail and omit old four-task overview206–210.'),
        ('initial_training_years',225.2,232.2,242,249,'Native training2019–2022span and labels.'),
        ('validation_test_years',232.2,236.7,249,253.5,'Validation2023/test2024visible; omit settled final1.5s.'),
        ('validation_selection',236.7,244.5,255,262.8,'Keep configuration selection/normalization routes and labels; omit stable final1.2s.'),
        ('refit_restart',244.5,253.0,264,272.5,'Keep restart/refit action and2024test; omit settled final2.5s.'),
        ('retrospective_limit',253.0,258.7,275,280.7,'Previously examined2024and limited independence remain clear; omit repeated static tail.'),
        ('quantization_introduction',258.7,269.1,290,298,'Full selected-reading construction, held under the continuous preprocessing introduction.'),
        ('normalize_437',269.1,274.1,298,303,'Native437→0.437normalization packet completes; omit settled formula tail.'),
        ('q64_grid',274.1,280.6,305,311.5,'Native nearest-level movement and all arithmetic;444.44remains visible through the complete spoken444.'),
        ('q128_grid',280.6,285.1,313,317.5,'Native nearest-level movement;433.07visible before and during its spoken number, followed by reading time.'),
        ('q256_grid',285.1,289.3,321,325.2,'Native nearest-level movement;435.29visible throughout the spoken435.'),
        ('quantized_comparison',289.3,295.0,327,331.8,'Compare all three reconstructions at the same time; completed comparison retained briefly.'),
        ('clip_then_round',295.0,300.5,341,346.5,'Native clipping then rounding, in the order of the new narration; remove only rounded-state tail.'),
        ('input_only_quantization',300.5,305.3,334,338.8,'Native input-GHI quantizer, locality bypass and continuous network/outputs finish337.1, followed by1.7scompleted reading. Shorten only the remaining plateau.'),
        ('freeze_validation_choice',305.3,311.0,348,353.7,'Preserve the entire native validation-choice→test transfer, which finishes353.2, and retain its completed endpoint for0.5s before MAE.'),
        ('mae_vertical_distances',311.0,320.0,354,363,'Full vertical-distance construction and zoom preparation at native speed.'),
        ('mae_600_650_50',320.0,328.96666666666664,363,369,'Native close-up construction; completed50difference held through its complete spoken numeral.'),
        ('mae_sum_and_28',328.96666666666664,336.96666666666664,372,380,'Native extracted errors, mean formula at+3s,28result at+6s and2sresult reading. Next scene also starts with MAE28.'),
        ('mae_converges_zero',336.96666666666664,350.2,382,394,'Preserve both native approaches, including full zero at+9s; retain zero during the interpretation sentence.'),
        ('macro_equal_localities',350.2,359.0,396,404.8,'All native locality contributions complete by+6.62s, with2.18scompleted equal-weight view.'),
        ('cumulative_72_steps',359.0,371.9,408.3,418.3,'Trim only0.3sinitial stationary baseline. Keep full7.2sscan, night label,72hresult and reading window; settled end retained for the results bridge.'),
        ('hourly_results',371.9,378.9,427,434,'Native hourly bars settle after1.8s; all correct values remain readable.'),
        ('hourly_small_difference',378.9,381.7,436,438.8,'Native small-difference bracket and retained hourly values; omit long unchanged plateau.'),
        ('daily_results',381.7,387.7,444,450,'Native daily bar transition;43.89remains visible throughout the spoken number.'),
        ('daily_small_difference',387.7,391.8,452,455,'Native small-difference bracket, with short final retention while differences are described.'),
        ('monthly_one_results',391.8,399.0,460,467.2,'Native one-month bars and12.73readout stay through em um mês; omit selection-detail duplicate.'),
        ('monthly_six_results',399.0,403.2,474,478.2,'Native six-month bars and correct13.67readout, held2.4safter settling. There is deliberately no spoken13.77or synthetic replacement.'),
        ('compare_within_task',403.2,409.3,420,425.5,'Comparison rule accompanies scales/targets and the next linking sentence; retain completed overview.'),
        ('daily_horizon_leaders',409.3,417.2,500,506.4,'Native1/3/7/14/30day winner construction, held through the spoken30days.'),
        ('monthly_locality_leaders',417.2,427.6,493,500,'Start on the last daily map state, then preserve both distinct3smonthly leader maps and retain the final one. Omit redundant hourly/daily-map reprise already covered by earlier plots.'),
        ('quantization_reprise',427.6,430.6,327,330,'Brief native return to the three-level comparison supports the new analysis bridge.'),
        ('quantization_outcomes',430.6,444.4,508,514,'Native5improvements/4worsenings/3controls chart, retained while the continuous voice explains its exact counts.'),
        ('historical_setup',444.4,448.4,514,518,'Separate historical continuous-control comparison; omit only setup tail.'),
        ('historical_matrix_patch',448.4,454.4,0,6,'Full repaired matrix with visible LSTM-hourly exception; use patch source, never the overlapped original.'),
        ('historical_confounders',454.4,457.8,526,529.4,'Years/normalization confounders visible with their spoken names; trim stable final0.6s.'),
        ('precision_not_cost',457.8,461.6,284,287.8,'Precision/cost caveat moved from methodology to its newly spoken location.'),
        ('six_month_exploratory',461.6,ending_start,536,541.8,'Exploratory task/origin context accompanies the final limitations; omit redundant seed/unseen-site silent slides not spoken in the new paragraph.'),
    ]

    items = [{'id':'intro','kind':'intro','source_path':rel(INTRO),'video_start':0.,'video_end':424/FPS,
              'start_frame':0,'end_frame':424,'frames':424,'duration':424/FPS,
              'native_playback_speed':1.,'tail_hold_frames':0,'reason':'Approved colored presenter/chair on black background; original opening audio belongs to the global master.'}]
    for ident, start, end, source_start, source_end, reason in shots:
        first, last = frame(start), frame(end)
        source_first, source_last = frame(source_start), frame(source_end)
        frames, native = last-first, source_last-source_first
        rounding_trim = 0
        if native > frames and native-frames <= 1:
            source_last = source_first+frames; rounding_trim = native-frames; native = frames
        assert frames >= native > 0, (ident, frames, native)
        assert first == items[-1]['end_frame'], (ident, first, items[-1]['end_frame'])
        path = PATCH if ident == 'historical_matrix_patch' else BASE
        items.append({'id':ident,'kind':'body','source_path':rel(path),
                      'video_start':source_first/FPS,'video_end':source_last/FPS,
                      'start_frame':first,'end_frame':last,'frames':frames,'duration':frames/FPS,
                      'start':first/FPS,'end':last/FPS,'native_source_frames':native,
                      'native_playback_speed':1.,'tail_hold_frames':frames-native,
                      'subframe_rounding_tail_trim_frames':rounding_trim,'reason':reason})
    first = items[-1]['end_frame']
    assert first == frame(ending_start)
    frames = voice['frames']-first
    items.append({'id':'ending','kind':'ending','source_path':rel(FACTORY),
                  'video_start':0.,'video_end':frames/FPS,'start_frame':first,
                  'end_frame':voice['frames'],'frames':frames,'duration':frames/FPS,
                  'start':first/FPS,'end':voice['duration'],'native_playback_speed':1.,
                  'tail_hold_frames':0,'reason':'Clean approved factory, subtle pan and global headers already synchronized by ROOT; presenter only in intro.'})
    assert items[-1]['end_frame'] == voice['frames']
    assert all(a['end_frame']==b['start_frame'] for a,b in zip(items,items[1:]))
    assert sum(item['frames'] for item in items)==voice['frames']
    assert all(Path(ROOT/item['source_path']).exists() for item in items)
    assert all(not (item['kind']=='body' and item['source_path']==rel(BASE) and item['video_end']>547) for item in items)

    by_id={item['id']:item for item in items}
    def event(ident, source_second):
        item=by_id[ident]
        return item['start_frame']/FPS + source_second-item['video_start']
    def word_time(paragraph, canonical_token, occurrence=0):
        hits=[w for w in paragraphs[paragraph]['words'] if w['canonical_token']==canonical_token]
        return hits[occurrence]['edited_start']
    checks=[
      {'name':'DNI tilted plane','item':'dni_normal_plane','visible_at':event('dni_normal_plane',11.8),'speech_at':word_time(1,'de'),'type':'geometric_construction'},
      {'name':'Zenith/cosine projection','item':'horizontal_projection','visible_at':event('horizontal_projection',18.),'speech_at':word_time(1,'cosseno'),'type':'geometric_construction'},
      {'name':'Histogram4.8percent','item':'histogram_fraction','visible_at':event('histogram_fraction',150.5),'speech_at':176.18333333333334,'type':'number_readout'},
      {'name':'Q64444.44','item':'q64_grid','visible_at':event('q64_grid',306.6),'speech_at':278.91333333333336,'speech_end':280.3933333333333,'type':'held_number_readout'},
      {'name':'Q128433.07','item':'q128_grid','visible_at':event('q128_grid',314.6),'speech_at':283.21333333333337,'speech_end':284.47333333333336,'type':'held_number_readout'},
      {'name':'Q256435.29','item':'q256_grid','visible_at':event('q256_grid',322.6),'speech_at':287.58333333333337,'speech_end':288.80333333333334,'type':'held_number_readout'},
      {'name':'MAE28','item':'mae_sum_and_28','visible_at':event('mae_sum_and_28',378.),'speech_at':335.6933333333333,'speech_end':336.2733333333333,'type':'held_number_readout','minimum_visible_seconds':2.0},
      {'name':'MAEzero','item':'mae_converges_zero','visible_at':event('mae_converges_zero',391.),'speech_at':346.04333333333335,'speech_end':346.36333333333334,'type':'held_number_readout'},
      {'name':'72-hour complete scan','item':'cumulative_72_steps','visible_at':event('cumulative_72_steps',416.),'speech_at':366.4633333333333,'speech_end':366.9033333333333,'type':'numeric_completion','allowed_lag_seconds':.30},
      {'name':'Monthlyone12.73','item':'monthly_one_results','visible_at':event('monthly_one_results',461.8),'speech_at':396.0833333333333,'speech_end':398.1433333333333,'type':'held_number_readout'},
      {'name':'Monthlysix13.67visualonly','item':'monthly_six_results','visible_at':event('monthly_six_results',475.8),'speech_at':None,'type':'visual_only_correct_reference_value','minimum_visible_seconds':2.0},
      {'name':'LSTMhourlyexception','item':'historical_matrix_patch','visible_at':event('historical_matrix_patch',3.6),'speech_at':452.3183333333333,'speech_end':453.35833333333335,'type':'held_readout'},
    ]
    for check in checks:
        item=by_id[check['item']]
        check['visible_until']=item['end_frame']/FPS
        check['visible_reading_seconds']=check['visible_until']-check['visible_at']
        check['review_status']='planned_requires_actual_export_sequence_QA'
        if check.get('speech_at') is not None:
            check['appearance_minus_speech_seconds']=check['visible_at']-check['speech_at']
        if check.get('speech_end') is not None:
            check['speech_contained_in_shot']=item['start_frame']/FPS<=check['speech_at'] and check['visible_until']>=check['speech_end']-.05
        if check.get('minimum_visible_seconds'):
            assert check['visible_reading_seconds']>=check['minimum_visible_seconds']-.04,check
    assert all(check.get('speech_contained_in_shot',True) for check in checks), checks
    source_paths={item['source_path'] for item in items}
    chapter_names={'ghi':'GHI e aplicações','modelos':'Funcionamento das redes','dados':'Localidades e dados',
                   'entradas':'Entradas e tarefas','protocolo':'Protocolo experimental','quantizacao':'Quantização',
                   'mae':'Entendendo o MAE','resultados':'Resultados','conclusao':'Interpretação e conclusão'}
    chapters=[{'id':'intro','title':'Apresentação','start':0.,'start_frame':0}]
    seen=set()
    for paragraph in voice['paragraphs']:
        section=paragraph['section_id']
        if section not in seen:
            seen.add(section)
            chapters.append({'id':section,'title':chapter_names[section],'start':paragraph['edited_start'],
                             'start_frame':frame(paragraph['edited_start'])})
    chapters.append({'id':'factory_conclusion','title':'Conclusão sobre a fábrica','start':first/FPS,'start_frame':first})
    schedule={
        'version':12,'status':'frame_exact_visual_schedule_ready_for_encoding',
        'generated_utc':datetime.now(timezone.utc).isoformat(),
        'frames':voice['frames'],'fps':FPS,'duration':voice['duration'],
        'voice_plan_path':rel(VOICE_PLAN),'voice_plan_sha256':sha(VOICE_PLAN),
        'audio_path':voice['audio_path'],'audio_sha256':voice.get('voice_sha256'),
        'source_hashes':{path:sha(ROOT/path) for path in source_paths},
        'visual_items':items,'chapters':chapters,'anchorsreview':checks,
        'all_frames_contiguous':True,'all_native_animation_speed_1x':True,
        'accelerated_shots':0,'audio_or_captions_modified':False,
        'body_source_native_seconds':sum(item['native_source_frames']/FPS for item in items if item['kind']=='body'),
        'completed_state_hold_seconds':sum(item['tail_hold_frames']/FPS for item in items if item['kind']=='body'),
        'picture_policy':'One continuous voice master spans independently edited native-speed shots. Shorten completed duplicate plateaus, preserve active construction and numeric reading states; no88phase audio padding.',
        'cut_rationale':[{'id':item['id'],'reason':item['reason']} for item in items],
        'source_reorders':['Clipping341–348 precedes scope334–341.','Dailyhorizons500–508 precede monthly locality maps493–500.',
                           'Comparison rule420–427 occurs after monthlyplots.','Precision/cost284–290 moves to the concluding limitations.'],
        'excluded_legacy_content':['Old weak conclusion547–560.','Old overlapped matrix520–526, replaced by isolated repaired patch.',
                                   'Duplicate history reprise34–38 and settled curve tails.','Redundant Nevada embedding, task overview, and unspoken seed/unseen-locality slides.'],
        'next_required_check':'ROOT must inspect sequential actual-export frames around plane/cosine, quantization,28/0/72, monthlyplots and matrix repair. This plan is not a claim of full realtime viewing.'
    }
    TMP.mkdir(parents=True,exist_ok=True)
    TARGET.write_text(json.dumps(schedule,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':schedule['status'],'frames':voice['frames'],'duration':voice['duration'],
                      'visual_items':len(items),'native_body_seconds':schedule['body_source_native_seconds'],
                      'completed_holds_seconds':schedule['completed_state_hold_seconds'],
                      'ending_start':first/FPS,'accelerated_shots':0,'path':rel(TARGET)},ensure_ascii=True))


if __name__=='__main__':
    main()
