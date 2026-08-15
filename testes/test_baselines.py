"""Testes das referencias temporais obrigatorias da avaliacao mensal."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from codigo_fonte.baselines import normalizar_previsoes_fisicas, prever_baselines


def _ghi(data: pd.Timestamp) -> float:
    """Valor identificavel por ano/mes para expor qualquer desalinhamento."""
    return float((data.year - 2020) * 100 + data.month)


def _linha_mensal(data: str, alvo: str, *, alvo_original: float | None = None) -> dict:
    data_timestamp = pd.Timestamp(data)
    alvo_timestamp = pd.Timestamp(alvo)
    return {
        "data": data_timestamp,
        "data_alvo": alvo_timestamp,
        "ghi": _ghi(data_timestamp),
        "ghi_alvo_original": (
            _ghi(alvo_timestamp) if alvo_original is None else alvo_original
        ),
    }


def _treino_dois_anos() -> pd.DataFrame:
    datas = pd.date_range("2021-12-31", "2023-11-30", freq="ME")
    alvos = datas + pd.offsets.MonthEnd(1)
    return pd.DataFrame(
        {
            "data": datas,
            "data_alvo": alvos,
            "ghi": [_ghi(data) for data in datas],
            "ghi_alvo_original": [_ghi(data) for data in alvos],
        }
    )


def test_baselines_mensais_alinham_janeiro_com_janeiro_anterior() -> None:
    treino = _treino_dois_anos()
    teste = pd.DataFrame(
        [_linha_mensal("2023-12-31", "2024-01-31", alvo_original=9999.0)],
        index=[77],
    )

    previsoes = prever_baselines(treino, teste, frequencia="mensal")

    # Persistencia usa dezembro de 2023; sazonal usa janeiro de 2023.
    assert previsoes["Persistencia"].loc[77] == pytest.approx(_ghi(pd.Timestamp("2023-12-31")))
    assert previsoes["SazonalIngenuo"].loc[77] == pytest.approx(
        _ghi(pd.Timestamp("2023-01-31"))
    )
    # A climatologia de janeiro usa somente os alvos Jan/2022 e Jan/2023.
    assert previsoes["Climatologia"].loc[77] == pytest.approx((201.0 + 301.0) / 2)


def test_climatologia_nao_consulta_alvo_do_teste() -> None:
    treino = _treino_dois_anos()
    base_teste = _linha_mensal("2023-12-31", "2024-01-31", alvo_original=-1.0)
    teste_a = pd.DataFrame([base_teste])
    teste_b = teste_a.copy()
    teste_b["ghi_alvo_original"] = 1_000_000.0

    clima_a = prever_baselines(treino, teste_a, "mensal")["Climatologia"]
    clima_b = prever_baselines(treino, teste_b, "mensal")["Climatologia"]

    pd.testing.assert_series_equal(clima_a, clima_b)


def test_sazonal_walk_forward_pode_usar_observacao_ja_ocorrida_no_teste() -> None:
    treino = _treino_dois_anos()
    # Para fevereiro/2024, fevereiro/2023 esta no historico de treino; para
    # janeiro/2025, janeiro/2024 ja aparece como observacao no trecho de teste.
    teste = pd.DataFrame(
        [
            _linha_mensal("2023-12-31", "2024-01-31"),
            _linha_mensal("2024-01-31", "2024-02-29"),
            _linha_mensal("2024-12-31", "2025-01-31"),
        ]
    )

    sazonal = prever_baselines(treino, teste, "mensal")["SazonalIngenuo"]

    assert sazonal.tolist() == pytest.approx(
        [
            _ghi(pd.Timestamp("2023-01-31")),
            _ghi(pd.Timestamp("2023-02-28")),
            _ghi(pd.Timestamp("2024-01-31")),
        ]
    )


def test_baseline_sazonal_falha_quando_historico_nao_existe() -> None:
    treino = pd.DataFrame([_linha_mensal("2023-06-30", "2023-07-31")])
    teste = pd.DataFrame([_linha_mensal("2023-12-31", "2024-01-31")])

    with pytest.raises(ValueError, match="Historico sazonal indisponivel.*2024-01-31"):
        prever_baselines(treino, teste, "mensal")


def test_normalizacao_das_previsoes_fisicas_aplica_faixa_do_treino() -> None:
    previsoes = {
        "A": pd.Series([50.0, 100.0, 200.0, 250.0], index=[4, 5, 6, 7]),
        "B": pd.Series([150.0]),
    }

    normalizadas = normalizar_previsoes_fisicas(
        previsoes, {"min": 100.0, "max": 200.0}
    )

    assert normalizadas["A"].tolist() == pytest.approx([0.0, 0.0, 1.0, 1.0])
    assert normalizadas["B"].tolist() == pytest.approx([0.5])
    assert normalizadas["A"].index.tolist() == [0, 1, 2, 3]


def test_normalizacao_constante_retorna_zero_para_cada_modelo() -> None:
    previsoes = {"A": pd.Series([100.0, 101.0]), "B": pd.Series([99.0])}

    normalizadas = normalizar_previsoes_fisicas(
        previsoes, {"min": 100.0, "max": 100.0}
    )

    assert np.array_equal(normalizadas["A"], np.zeros(2))
    assert np.array_equal(normalizadas["B"], np.zeros(1))


@pytest.mark.parametrize("frequencia", ["horaria", "semanal", ""])
def test_baselines_rejeitam_frequencia_desconhecida(frequencia: str) -> None:
    frame = pd.DataFrame([_linha_mensal("2023-12-31", "2024-01-31")])

    with pytest.raises(ValueError, match="frequencia"):
        prever_baselines(frame, frame, frequencia)


@pytest.mark.parametrize(("conjunto", "nome"), [("treino", "treino"), ("teste", "teste")])
def test_baselines_informam_colunas_ausentes(conjunto: str, nome: str) -> None:
    treino = _treino_dois_anos()
    teste = pd.DataFrame([_linha_mensal("2023-12-31", "2024-01-31")])
    if conjunto == "treino":
        treino = treino.drop(columns=["ghi_alvo_original"])
    else:
        teste = teste.drop(columns=["data_alvo"])

    with pytest.raises(ValueError, match=rf"Colunas ausentes em {nome}"):
        prever_baselines(treino, teste, "mensal")
