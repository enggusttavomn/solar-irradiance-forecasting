"""Consolidate completed V10 checks and point the local player to the final cut."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "documentacao/relatorio_final_ea019/video/montagem_final_v10"
TMP = ROOT / "tmp/montagem_final_v10"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def rel(path):
    return path.relative_to(ROOT).as_posix()


def main():
    verification = read(OUT / "verificacao_video_final_v10.json")
    samples = read(OUT / "amostras_exportacao_v10.json")
    early = read(TMP / "qa_intro_early_final.json")
    late = read(TMP / "qa_late_final.json")
    edits = read(TMP / "audit_edicao_independente_v10.json")
    music_path = TMP / "audit_audio_mix_v10.json"
    music = read(music_path)  # Finalize only after the separate mix audit is saved.

    assert music["status"] == "pass"
    assert not music["errors"] and not music["material_flags"]
    assert music["same_video_packets"] and music["audio_variants_different"]
    assert music["music_recovery_relative_to_speech_median_db"] > 6
    assert early["sampled_visual_review_passed"] is True
    assert not early["material_findings_remaining"]
    assert late["status"] == "passed_in_sampled_scope"
    assert not edits["material_conflicts"] and not edits["pcm_conflicts"]
    assert edits["all_items_pcm_interiors_exact"]
    assert edits["all_zero_padding_verified"]
    assert len(samples["stills"]) == 99
    for sample in samples["stills"]:
        assert sha(ROOT / sample["path"]) == sample["sha256"]
    for entry in verification["files"]:
        path = ROOT / entry["path"]
        assert path.stat().st_size == entry["bytes"]
        assert sha(path) == entry["sha256"]
        assert not entry["full_decode_errors"]
        assert entry["decoded_frames"] == 13602
    assert verification["same_video_bitstream"]
    assert verification["presenter_original_color"] and verification["background_black"]

    qa_dir = OUT / "revisao"
    qa_dir.mkdir(exist_ok=True)
    reports = []
    for source in [TMP / "qa_intro_early_final.json", TMP / "qa_late_final.json",
                   TMP / "audit_edicao_independente_v10.json", music_path]:
        target = qa_dir / source.name
        shutil.copy2(source, target)
        reports.append({"path": rel(target), "sha256": sha(target)})

    central_contacts = []
    for index in [4, 5, 6]:
        path = OUT / "verificacao_final" / f"contato_v10_{index}.png"
        central_contacts.append({"path": rel(path), "sha256": sha(path)})
    root_review = {
        "scope": "Visual sampling of all 36 frames in contact sheets 4, 5 and 6.",
        "sample_count": 36,
        "contact_sheets": central_contacts,
        "sampled_visual_review_passed": True,
        "material_findings_remaining": [],
        "confirmed": [
            "Data distributions, history windows and locality inputs are legible.",
            "Training/validation/test years and model/task diagrams remain legible.",
            "Quantization and MAE illustrations are clear in sampled frames.",
            "Captions do not obscure the sampled chart and diagram content.",
        ],
        "audio_listening_performed": False,
        "full_realtime_playback_reviewed": False,
    }
    write(qa_dir / "qa_central_final.json", root_review)
    reports.append({"path": rel(qa_dir / "qa_central_final.json"),
                    "sha256": sha(qa_dir / "qa_central_final.json")})

    consolidated = {
        "version": 10,
        "status": "complete",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "files": verification["files"],
        "duration_seconds": 453.4,
        "resolution": [1920, 1080],
        "fps": 30,
        "decoded_frames_per_export": 13602,
        "full_decode_passed_both_exports": True,
        "visual_samples_reviewed": 99,
        "timeline_items_covered": 90,
        "sampled_visual_review_passed": True,
        "scope_limit": "Static visual samples and objective audio/source checks; no full realtime playback or human listening.",
        "full_realtime_playback_reviewed": False,
        "audio_listening_performed": False,
        "retakes": "All five specified later takes retained; discarded first attempts excluded.",
        "voice_synthesis_used": False,
        "voice_time_stretch_used": False,
        "opening": "Original presenter and chair colors; project title accents; solid black background; approved two-line title distribution.",
        "closing": "New recorded conclusion over clean factory animation, without presenter footage.",
        "lstm_exception_label_fixed": True,
        "same_video_bitstream_in_both_variants": True,
        "source_files_preserved": True,
        "reports": reports,
        "objective_mix_report": music,
    }
    write(OUT / "revisao_final_montagem_v10.json", consolidated)
    verification.update({
        "status": "complete",
        "sampled_visual_review_passed": True,
        "visual_samples_reviewed": 99,
        "timeline_items_covered": 90,
        "objective_audio_mix_review_completed": True,
        "audio_listening_performed": False,
        "review_report": rel(OUT / "revisao_final_montagem_v10.json"),
    })
    write(OUT / "verificacao_video_final_v10.json", verification)
    write(OUT / "progresso_montagem_v10.json", {
        "stage": "complete", "updated_unix": time.time(),
        "duration_seconds": 453.4, "exports": 2,
        "verification": rel(OUT / "verificacao_video_final_v10.json"),
    })

    (OUT / "LEIA_ME_VIDEO_FINAL_V10.txt").write_text(
        "VÍDEO FINAL NARRADO — V10\n\n"
        "Duração: 7min33,4s. Full HD 1920×1080, 30 quadros/s.\n\n"
        "ARQUIVOS PARA ASSISTIR OU PUBLICAR\n"
        "1. Video_TCC_Final_Somente_Voz_v10.mp4 — apresentação e narração, sem música.\n"
        "2. Video_TCC_Final_Com_Trilha_v10.mp4 — mesma imagem, com música instrumental baixa e redução sob a voz.\n"
        "Abra assistir_video_final_narrado_v10.html para alternar entre as duas versões.\n"
        "Na raiz do projeto, ASSISTIR_VIDEO_TCC.cmd também abre esse player.\n\n"
        "ABERTURA\n"
        "Rosto, corpo e cadeira nas cores da gravação original; fundo preto e títulos com cores do projeto.\n"
        "Título distribuído nas duas linhas aprovadas; créditos do autor, orientador e coorientador.\n"
        "Prévia: previas/Capa_Fundo_Preto_Apresentador_Colorido_v5.png.\n\n"
        "EDIÇÃO\n"
        "Cinco tomadas posteriores selecionadas nos trechos indicados; tentativas anteriores retiradas.\n"
        "Pausas e cenas ajustadas à gravação, sem acelerar ou sintetizar sua voz.\n"
        "Exceção da LSTM horária reposicionada para ficar legível na matriz histórica.\n"
        "Novo encerramento de Recording (2).m4a sobre a fábrica, sem reaparição em câmera.\n"
        "Os dois valores mensais falados cuja transcrição estava ambígua foram suprimidos;\n"
        "os valores corretos, 12,73 e 13,67 W/m², continuam nos gráficos.\n"
        "Legendas gravadas na imagem e disponíveis também em Legendas_Finais_v10.srt.\n\n"
        "CONFERÊNCIA\n"
        "Decodificação integral sem erros nos dois MP4s, conferência visual de 99 amostras\n"
        "cobrindo os 90 itens, auditoria dos cortes PCM e medições objetivas da mixagem.\n"
        "Não foi feita escuta humana nem reprodução integral em tempo real.\n"
        "Registros: verificacao_video_final_v10.json e revisao_final_montagem_v10.json.\n"
        "Relatório e gravações originais preservados. As versões anteriores permanecem disponíveis.\n",
        encoding="utf-8",
    )

    launcher = ROOT / "ASSISTIR_VIDEO_TCC.cmd"
    backup = ROOT / "ASSISTIR_VIDEO_TCC_ANTES_V10.cmd"
    if launcher.exists() and not backup.exists():
        shutil.copy2(launcher, backup)
    shutil.copy2(ROOT / "ASSISTIR_VIDEO_FINAL_NARRADO_V10.cmd", launcher)

    pending = ROOT / "documentacao/relatorio_final_ea019/video/completo_v9/PENDENCIAS_MONTAGEM_FINAL.txt"
    old_text = pending.read_text(encoding="utf-8-sig")
    marker = "ATUALIZAÇÃO — RESOLVIDO NA V10"
    if marker not in old_text:
        pending.write_text(
            marker + "\n"
            "Gravações recebidas e montagem concluída. A correção da LSTM foi aplicada na V10.\n"
            "As duas versões narradas estão em ../montagem_final_v10/.\n"
            "Duração final: 7min33,4s. Ver LEIA_ME_VIDEO_FINAL_V10.txt nessa pasta.\n"
            "O registro histórico abaixo descreve o estado anterior à montagem.\n\n"
            + old_text, encoding="utf-8",
        )
    print("V10_DELIVERY_COMPLETE: 2 exports, 453.4 seconds, original presenter colors, black background")


if __name__ == "__main__":
    main()
