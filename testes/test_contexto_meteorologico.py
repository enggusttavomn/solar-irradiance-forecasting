"""Testes do contexto independente de chuva e nebulosidade."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from codigo_fonte.contexto_meteorologico import (
    PARAMETROS_POWER,
    coletar_contexto_meteorologico,
    construir_url_power,
    interpretar_resposta_power,
)


def _resposta() -> dict[str, object]:
    return {
        "properties": {
            "parameter": {
                "PRECTOTCORR": {"20240101": 0.0, "20240102": 3.5},
                "CLOUD_AMT": {"20240101": 20.0, "20240102": 85.0},
                "ALLSKY_SFC_SW_DWN": {"20240101": 6.0, "20240102": 1.0},
                "CLRSKY_SFC_SW_DWN": {"20240101": 7.5, "20240102": 0.0},
            }
        }
    }


def test_url_fixa_parametros_e_tempo_solar_local() -> None:
    url = construir_url_power(
        latitude=-12.6733774,
        longitude=-38.2812339,
        inicio="2024-01-01",
        fim="2024-12-31",
    )
    assert "time-standard=LST" in url
    assert "start=20240101" in url and "end=20241231" in url
    assert "%2C".join(PARAMETROS_POWER) in url


def test_interpretacao_classifica_condicao_sem_usar_ghi_do_modelo() -> None:
    tabela = interpretar_resposta_power(
        _resposta(), localidade="Local", latitude=1.0, longitude=2.0
    )
    assert tabela["chuva_relevante"].tolist() == [False, True]
    assert tabela["muito_nublado"].tolist() == [False, True]
    assert tabela["condicao_adversa_independente"].tolist() == [False, True]
    assert np.isclose(tabela.loc[0, "indice_all_sky_clear_sky"], 0.8)
    assert np.isnan(tabela.loc[1, "indice_all_sky_clear_sky"])


def test_coleta_reutiliza_cache_e_registra_hash(tmp_path: Path) -> None:
    cadastro = [{"nome": "Fabrica Teste", "lat": 1.0, "lon": 2.0}]
    chamadas: list[str] = []

    def baixar(url: str) -> dict[str, object]:
        chamadas.append(url)
        return _resposta()

    tabela, proveniencia = coletar_contexto_meteorologico(
        inicio="2024-01-01",
        fim="2024-01-02",
        pasta_cache=tmp_path,
        localidades=cadastro,
        baixar=baixar,
        espera_entre_consultas_s=0,
    )
    assert len(tabela) == 2
    assert len(chamadas) == 1
    assert proveniencia[0]["origem_execucao"] == "api"
    assert len(proveniencia[0]["sha256"]) == 64

    tabela_cache, segunda_proveniencia = coletar_contexto_meteorologico(
        inicio="2024-01-01",
        fim="2024-01-02",
        pasta_cache=tmp_path,
        localidades=cadastro,
        baixar=lambda _: (_ for _ in ()).throw(AssertionError("nao baixar")),
        espera_entre_consultas_s=0,
    )
    assert tabela_cache.equals(tabela)
    assert segunda_proveniencia[0]["origem_execucao"] == "cache"
    json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
