"""Testes do contrato auditavel dos CSVs oficiais NSRDB."""

from __future__ import annotations

import pandas as pd
import pytest

from codigo_fonte.localidades_ev import LOCALIDADES_EV
from codigo_fonte.preprocessamento import (
    NSRDB_API_URL,
    NSRDB_DAILY_AGGREGATION,
    NSRDB_GHI_UNIT,
    NSRDB_PRODUCT,
    NSRDB_SOURCE,
)
from treinar_todas_localidades import validar_csv_nrel_localidade


@pytest.fixture()
def csv_oficial() -> tuple[dict, pd.DataFrame]:
    local = LOCALIDADES_EV[0]
    datas = pd.date_range("2019-01-01", "2024-12-31", freq="D")
    dados = pd.DataFrame(
        {
            "data": datas,
            "ghi": 220.0,
            "localidade": local["nome"],
            "pais": local["pais"],
            "lat": local["lat"],
            "lon": local["lon"],
            "endereco_localidade": local["endereco"],
            "fonte_localidade": local["fonte_localidade"],
            "fonte_coordenadas": local["fonte_coordenadas"],
            "metodo_coordenadas": local["metodo_coordenadas"],
            "osm_elemento": local["osm_elemento"],
            "ano": datas.year,
            "fonte_dados": NSRDB_SOURCE,
            "produto_dados": NSRDB_PRODUCT,
            "versao_dados": "4.1.2",
            "endpoint_api": NSRDB_API_URL,
            "intervalo_minutos": 60,
            "agregacao": NSRDB_DAILY_AGGREGATION,
            "unidade_ghi": NSRDB_GHI_UNIT,
            "lat_grade_nsrdb": local["lat"],
            "lon_grade_nsrdb": local["lon"],
            "site_id_nsrdb": 123,
            "source_nsrdb": "NSRDB",
            "timezone_nsrdb": -3,
            "elevacao_grade_m": 10,
            "ghi_unidade_api": "w/m2",
            "data_coleta_utc": "2026-06-06T00:00:00+00:00",
        }
    )
    return local, dados


def _validar(tmp_path, local: dict, dados: pd.DataFrame) -> tuple[bool, str]:
    arquivo = tmp_path / "localidade.csv"
    dados.to_csv(arquivo, index=False)
    return validar_csv_nrel_localidade(arquivo, local)


def test_csv_oficial_completo_e_aceito(tmp_path, csv_oficial) -> None:
    local, dados = csv_oficial

    valido, motivo = _validar(tmp_path, local, dados)

    assert valido, motivo
    assert motivo == "CSV validado como NLR/NSRDB"


@pytest.mark.parametrize(
    ("mutacao", "trecho_motivo"),
    [
        (lambda df: df.drop(columns=["endpoint_api"]), "colunas de proveniencia ausentes"),
        (lambda df: df.iloc[:-1].copy(), "cobertura diaria deve ser completa"),
        (lambda df: df.assign(ghi=501.0), "GHI diario deve estar entre 0 e 500"),
        (lambda df: df.assign(fonte_dados="desconhecida"), "fonte_dados deve ser"),
        (lambda df: df.assign(lat_grade_nsrdb=0.0, lon_grade_nsrdb=0.0), "distante demais"),
    ],
)
def test_csv_invalido_e_rejeitado(
    tmp_path, csv_oficial, mutacao, trecho_motivo: str
) -> None:
    local, dados = csv_oficial

    valido, motivo = _validar(tmp_path, local, mutacao(dados))

    assert not valido
    assert trecho_motivo in motivo

