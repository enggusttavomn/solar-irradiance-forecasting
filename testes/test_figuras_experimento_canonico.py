"""Smoke tests das figuras do protocolo canônico."""

from __future__ import annotations

import numpy as np
import pandas as pd

from codigo_fonte.figuras_experimento_canonico import (
    figura_deepnpts_vs_melhor_concorrente,
    figura_intervalo_deepnpts,
    figura_ranking_mae,
    figura_serie_previsoes,
)


def _dados():
    datas = pd.date_range("2024-01-31", periods=3, freq="ME")
    previsoes = pd.DataFrame(
        {
            "data_alvo": list(datas) * 2,
            "Localidade": ["A"] * 3 + ["B"] * 3,
            "y_wm2": [100, 120, 110, 200, 210, 220],
            "DeepNPTS": [102, 119, 111, 198, 211, 219],
            "Climatologia": [105, 115, 115, 195, 205, 225],
        }
    )
    metricas = pd.DataFrame(
        {
            "Localidade": ["A", "A", "B", "B"],
            "Modelo": ["DeepNPTS", "Climatologia"] * 2,
            "MAE_wm2": [1, 5, 2, 6],
        }
    )
    resumo = pd.DataFrame(
        {
            "Modelo": ["DeepNPTS", "Climatologia"],
            "MAE_media_wm2": [1.5, 5.5],
            "MAE_dp_sementes_wm2": [0.2, 0.0],
        }
    )
    return previsoes, metricas, resumo


def test_figuras_sao_salvas_em_png_e_pdf(tmp_path) -> None:
    previsoes, metricas, resumo = _dados()
    amostras = np.repeat(previsoes["DeepNPTS"].to_numpy()[:, None], 20, axis=1)
    chamadas = [
        figura_ranking_mae(resumo, tmp_path / "ranking"),
        figura_deepnpts_vs_melhor_concorrente(metricas, tmp_path / "local"),
        figura_serie_previsoes(previsoes, "A", "Climatologia", tmp_path / "serie"),
        figura_intervalo_deepnpts(previsoes, amostras, "A", tmp_path / "intervalo"),
    ]

    assert all(png.is_file() and pdf.is_file() for png, pdf in chamadas)
