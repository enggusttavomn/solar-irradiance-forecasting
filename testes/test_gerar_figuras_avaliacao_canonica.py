"""Testes do gerador de figuras do protocolo canônico."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from gerar_figuras_avaliacao_canonica import gerar, validar_execucao_concluida


def _criar_execucao_minima(pasta, *, modo: str = "completa") -> None:
    datas = pd.date_range("2024-01-31", periods=3, freq="ME")
    previsoes = pd.DataFrame(
        {
            "data_alvo": list(datas) * 2,
            "Localidade": ["BYD Camacari"] * 3 + ["Outra"] * 3,
            "y_wm2": [100, 120, 110, 200, 210, 220],
            "DeepNPTS": [102, 119, 111, 198, 211, 219],
            "Climatologia": [105, 115, 115, 195, 205, 225],
        }
    )
    metricas = pd.DataFrame(
        {
            "Localidade": ["BYD Camacari", "BYD Camacari", "Outra", "Outra"],
            "Modelo": ["DeepNPTS", "Climatologia"] * 2,
            "MAE_wm2": [1.0, 5.0, 2.0, 6.0],
        }
    )
    resumo = pd.DataFrame(
        {
            "Modelo": ["DeepNPTS", "Climatologia"],
            "MAE_media_wm2": [1.5, 5.5],
            "MAE_dp_sementes_wm2": [0.2, 0.0],
        }
    )
    pasta.mkdir()
    previsoes.to_csv(pasta / "previsoes_consolidadas.csv", index=False)
    metricas.to_csv(pasta / "metricas_por_localidade.csv", index=False)
    resumo.to_csv(pasta / "metricas_medias_modelos.csv", index=False)
    np.savez_compressed(
        pasta / "amostras_probabilisticas.npz",
        DeepNPTS_amostras_wm2=np.repeat(
            previsoes["DeepNPTS"].to_numpy()[:, None], 20, axis=1
        ),
    )
    (pasta / "status_execucao.json").write_text(
        json.dumps({"etapa": "concluido"}), encoding="utf-8"
    )
    (pasta / "manifesto_execucao.json").write_text(
        json.dumps(
            {
                "configuracao": {"modo_execucao": modo},
                "metadados": {
                    "protocolo_canonico": True,
                    "fonte_artigos_atuais": True,
                },
            }
        ),
        encoding="utf-8",
    )


def test_execucao_parcial_e_smoke_sao_rejeitadas(tmp_path) -> None:
    parcial = tmp_path / "parcial"
    parcial.mkdir()
    (parcial / "status_execucao.json").write_text(
        json.dumps({"etapa": "redes_recorrentes"}), encoding="utf-8"
    )
    with pytest.raises(FileNotFoundError, match="incompleta"):
        validar_execucao_concluida(parcial)

    smoke = tmp_path / "smoke"
    _criar_execucao_minima(smoke, modo="smoke")
    with pytest.raises(RuntimeError, match="smoke"):
        validar_execucao_concluida(smoke)


def test_figuras_canonicas_e_exportacao_png(tmp_path) -> None:
    execucao = tmp_path / "completa"
    _criar_execucao_minima(execucao)
    exportacao = tmp_path / "overlief" / "figuras"

    artefatos = gerar(execucao, exportacao)

    assert len(artefatos) == 8
    assert all(caminho.is_file() for caminho in artefatos)
    assert all("figuras" in caminho.parts for caminho in artefatos)
    exportados = sorted(exportacao.glob("*"))
    assert len(exportados) == 4
    assert all(caminho.suffix == ".png" for caminho in exportados)
