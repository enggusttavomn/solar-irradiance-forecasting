import numpy as np
import pandas as pd
import pytest

from codigo_fonte.historico_nsrdb_expandido import verificar_ano_horario, serializar_tempo_ns
from codigo_fonte.historico_nsrdb_agregacao import media_diaria_api


def exemplo(ano=2000):
    registro = pd.DataFrame([dict(site_id_nsrdb=7, localidade="Local", lat_grade_nsrdb=10.0,
                                  lon_grade_nsrdb=-50.0, timezone_nsrdb=-3)])
    grade = pd.date_range(f"{ano}-01-01", f"{ano+1}-01-01", freq="h", inclusive="left", tz="UTC")
    dados = pd.DataFrame({"timestamp_utc": grade, "ghi": np.ones(len(grade))})
    for coluna in registro.columns:
        dados[coluna] = registro.iloc[0][coluna]
    return dados, registro


def test_grade_bissexta_e_dezembro_inteiro():
    dados, registro = exemplo()
    assert verificar_ano_horario(dados, 2000, registro)["horas_por_localidade"] == 8784


@pytest.mark.parametrize("defeito", ["lacuna", "duplicata", "negativo", "infinito", "localidade", "fuso"])
def test_bloqueia_dados_invalidos(defeito):
    dados, registro = exemplo()
    if defeito == "lacuna":
        dados = dados.iloc[:-1]
    elif defeito == "duplicata":
        dados.loc[1, "timestamp_utc"] = dados.loc[0, "timestamp_utc"]
    elif defeito == "negativo":
        dados.loc[0, "ghi"] = -1
    elif defeito == "infinito":
        dados.loc[0, "ghi"] = np.inf
    elif defeito == "localidade":
        dados.loc[0, "localidade"] = "Outro"
    else:
        dados.loc[0, "timezone_nsrdb"] = -4
    with pytest.raises(ValueError):
        verificar_ano_horario(dados, 2000, registro)


def test_diario_usa_minuto30_em_vez_da_media_das_duas_amostras():
    bruto = np.tile([0, 10], 365 * 24)
    assert np.array_equal(media_diaria_api(bruto, -3, 1999), np.full(365, 10.0))


def test_fronteira_explicitamente_circular_do_mesmo_ano():
    bruto = np.zeros(365 * 48)
    bruto[1] = 24
    esperado = np.zeros(365)
    esperado[-1] = 1
    assert np.array_equal(media_diaria_api(bruto, -3, 1999), esperado)


def test_diario_incompleto_nao_e_preenchido():
    with pytest.raises(ValueError):
        media_diaria_api(np.zeros(365 * 48 - 1), -3, 1999)


def test_bissexto_nao_e_tratado_como_365_dias():
    assert len(media_diaria_api(np.ones(366 * 48), -3, 2000)) == 366
    with pytest.raises(ValueError):
        media_diaria_api(np.ones(365 * 48), -3, 2000)


@pytest.mark.parametrize("unidade_pandas", ["ms", "us", "ns"])
def test_cache_temporal_preserva_instante_independente_da_precisao_pandas(unidade_pandas):
    origem = pd.date_range("2000-01-01", periods=3, freq="30min", tz="UTC").as_unit(unidade_pandas)
    inteiro = serializar_tempo_ns(origem)
    assert inteiro[0] == 946684800000000000
    assert np.array_equal(np.diff(inteiro), [1800000000000, 1800000000000])
    restaurado = pd.to_datetime(inteiro, unit="ns", utc=True)
    assert restaurado.equals(origem.as_unit("ns"))
