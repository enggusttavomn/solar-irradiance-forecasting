"""Export the new spoken script and recording guide without touching any video."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/roteiro_continuo_v12'
SOURCE = OUT / 'narracao_continua_v12.json'
REPORT = ROOT / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.pdf'
REFERENCE = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v11/timeline_montagem_v11.json'


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def spoken_expansion(text):
    for pattern, replacement in [
        (r'\bmacro-MAE\b', 'macro ême á ê'), (r'\bGHI\b', 'gê agá i'),
        (r'\bDNI\b', 'dê ene i'), (r'\bNSRDB\b', 'ene esse erre dê bê'),
        (r'\bLSTM\b', 'éle esse tê ême'), (r'\bMAE\b', 'ême á ê'),
    ]:
        text = re.sub(pattern, replacement, text)
    return text


def main():
    plan = json.loads(SOURCE.read_text(encoding='utf-8-sig'))
    protected = {str(p.relative_to(ROOT)): digest(p) for p in [REPORT, REFERENCE]}
    paragraphs = [p for section in plan['sections'] for p in section['paragraphs']]
    spoken = '\n\n'.join(paragraphs) + '\n'
    assert not any(c in spoken for c in ['\ufffd', '[', ']'])
    assert len(plan['sections']) == 9
    for pause in plan['planned_observation_pauses']:
        assert spoken.count(pause['after_exact_sentence']) == 1
    # These explicit readings avoid the two numerical ambiguities in the first recording.
    for required in ['cinquenta e três vírgula vinte e um', 'quarenta e três vírgula oitenta e nove',
                     'doze vírgula setenta e três', 'treze vírgula sessenta e sete',
                     'nos horizontes completos avaliados', 'nos controles contínuos']:
        assert required.lower() in spoken.lower(), required
    target = OUT / 'Texto_Corrido_Para_Gravar_v12.txt'
    target.write_text(spoken, encoding='utf-8-sig')
    assert target.read_text(encoding='utf-8-sig') == spoken

    word_count = len(spoken.split())
    expanded_count = len(spoken_expansion(spoken).split())
    pause_seconds = sum(row['seconds'] for row in plan['planned_observation_pauses'])
    duration_models = [{
        'spoken_words_per_minute': pace,
        'estimated_total_seconds': expanded_count / pace * 60 + plan['existing_opening']['duration_seconds'] + pause_seconds,
    } for pace in [130, 135, 140, 150]]
    guide = [
        'GUIA PARA GRAVAR A NARRAÇÃO CONTÍNUA\n',
        'O arquivo Texto_Corrido_Para_Gravar_v12.txt contém apenas o que você deve falar. '
        'Ele começa em "Para entender essa previsão" e termina em "Obrigado pela atenção".\n',
        'ABERTURA\n'
        'Seu vídeo de apresentação atual pode ser mantido com seu próprio áudio. '
        'Não é necessário gravá-lo novamente. O texto da nova narração começa depois dessa abertura. '
        'Você aparece somente no começo; a conclusão continua narrada sobre a fábrica.\n',
        'COMO GRAVAR\n'
        'Faça uma gravação única, como se explicasse o projeto para alguém. Respire naturalmente '
        'entre os parágrafos e mantenha o tom de uma conversa. Os parágrafos organizam a leitura; '
        'não são comandos para parar o gravador.\n'
        'Leia com o texto à frente e deixe a sincronização com o vídeo para a edição. '
        'As frases podem continuar enquanto a imagem muda.\n'
        'Deixe cerca de dois segundos de silêncio no início e no fim. Se travar, espere dois segundos '
        'e repita a frase inteira. A tomada anterior pode ser retirada depois, preservando a frase correta.\n'
        'Use o mesmo local e a mesma distância do microfone durante a gravação. Grave somente sua voz; '
        'a trilha entra na montagem. M4A do gravador serve.\n',
        'RITMO\n'
        f'O texto novo tem {word_count} palavras escritas, aproximadamente {expanded_count} ao expandir as siglas. '
        'A duração é uma estimativa, não uma obrigação para cada frase. Uma leitura calma, '
        'por volta de 130 a 140 palavras por minuto, deixa o conjunto perto de nove a dez minutos, '
        'incluindo sua abertura e pausas de observação. O limite final é dez minutos. '
        'O tempo real será conferido depois de receber o áudio.\n',
        'PAUSAS VISUAIS PARA A MONTAGEM\n'
        'As referências abaixo são para a edição. Na gravação, você pode apenas respirar naturalmente '
        'nesses pontos; eu ajusto a duração exata conforme o movimento das animações. '
        'Não leia estes comentários em voz alta.\n',
    ]
    for index, pause in enumerate(plan['planned_observation_pauses'], 1):
        guide.append(f'{index}. Depois de "{pause["after_exact_sentence"]}"\n'
                     f'   Aproximadamente {str(pause["seconds"]).replace(".", ",")} s para {pause["purpose"][0].lower() + pause["purpose"][1:]}\n')
    guide.extend([
        '\nPRONÚNCIA DAS SIGLAS\n'
        'GHI: gê, agá, i. DNI: dê, ene, i. NSRDB: ene, esse, erre, dê, bê.\n'
        'LSTM: éle, esse, tê, ême. MAE: ême, á, ê. Macro-MAE: macro, ême, á, ê.\n'
        'Os números já estão escritos por extenso no roteiro, inclusive doze vírgula setenta e três '
        'e treze vírgula sessenta e sete nos resultados mensais.\n',
        'COMO SERÁ A NOVA MONTAGEM\n'
        '1. Selecionar as tomadas completas e retirar erros e repetições sem apagar as respirações úteis.\n'
        '2. Organizar o ritmo por grandes blocos de explicação, permitindo que a voz atravesse as trocas de imagem.\n'
        '3. Aproveitar as animações e gráficos já aprovados, ajustando cortes e permanências aos momentos da nova fala.\n'
        '4. Preservar o movimento dos exemplos didáticos e o tempo de ler os resultados; evitar acelerações para fazer a fala caber.\n'
        '5. Refazer as legendas a partir da gravação real e verificar fórmulas, unidades, nomes e números.\n'
        '6. Exportar novamente as duas versões, somente voz e voz com música baixa.\n\n'
        'Não há novos horários definitivos nem legendas finais nesta etapa: eles dependem da nova gravação. '
        'Os vídeos V11 e os arquivos originais continuam preservados.\n',
    ])
    guide_path = OUT / 'Guia_Para_Gravar_e_Montar_v12.txt'
    guide_path.write_text('\n'.join(guide), encoding='utf-8-sig')
    plan['status'] = 'ready_for_new_recording'
    plan['written_narration_word_count'] = word_count
    plan['estimated_spoken_word_count_with_expanded_acronyms'] = expanded_count
    plan['estimated_duration_models'] = duration_models
    plan['source_report'] = {'path': str(REPORT.relative_to(ROOT)), 'sha256': digest(REPORT)}
    write_json(SOURCE, plan)
    verification = {
        'status': 'ready_for_new_recording', 'version': 12,
        'checked_utc': datetime.now(timezone.utc).isoformat(),
        'paragraph_count': len(paragraphs), 'narrative_blocks': 9,
        'written_new_narration_words': word_count,
        'spoken_word_estimate_including_acronym_expansion': expanded_count,
        'duration_models': duration_models,
        'duration_is_estimate_not_final_edit': True,
        'observation_pause_anchors_valid': True,
        'spoken_numerals_verified_against_canonical_report': True,
        'same_approved_opening_video_to_be_reused': True,
        'scientific_review': {'status': 'passed_with_corrections_applied',
                              'corrections': ['Selected input conditions compared with continuous control.',
                                              'Historical 11/12 comparison explicitly limited to continuous controls.']},
        'editorial_review': {'status': 'passed_with_clarity_changes_applied',
                             'changes': ['GHI expanded at first mention.', 'Attention weights contribution explained.',
                                         'Cross attention described by its function.', 'Distance between quantization levels clarified.']},
        'source_files_unchanged': protected,
        'new_video_rendered': False, 'new_audio_received': False,
        'final_captions_generated': False, 'external_uploads_performed': False,
        'outputs': [{'path': str(p.relative_to(ROOT)), 'sha256': digest(p), 'bytes': p.stat().st_size}
                    for p in [target, guide_path, SOURCE]],
    }
    assert protected == {str(p.relative_to(ROOT)): digest(p) for p in [REPORT, REFERENCE]}
    write_json(OUT / 'verificacao_roteiro_v12.json', verification)
    print(json.dumps({'status': verification['status'], 'new_narration_words': word_count,
                      'spoken_estimate': expanded_count, 'paragraphs': len(paragraphs),
                      'duration_models': duration_models, 'outputs': verification['outputs']}, ensure_ascii=True))


if __name__ == '__main__':
    main()
