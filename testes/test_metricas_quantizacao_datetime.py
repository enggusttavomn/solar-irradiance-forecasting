"""Datas lidas do CSV devem ter a mesma semantica que datas do contexto."""
import pandas as pd
import pytest
from codigo_fonte.acompanhamento.metricas_quantizacao_todos import comparar_amostras, normalizar_chaves


def exemplo(unidade):
    datas = pd.Series(pd.to_datetime(['2023-01-31', '2023-02-28'], utc=True)).astype(f'datetime64[{unidade}, UTC]')
    return pd.DataFrame({'localidade': ['A', 'A'], 'origem': datas, 'data_alvo': datas,
                         'passo': [1, 1], 'ghi_real_wm2': [10., 20.]})


def test_chaves_us_ns_com_mesmos_instantes():
    a, b = exemplo('us'), exemplo('ns')
    comparar_amostras(a, b)
    assert normalizar_chaves(a).origem.dtype == normalizar_chaves(b).origem.dtype


def test_chave_alterada_continua_rejeitada():
    a, b = exemplo('us'), exemplo('ns')
    b.loc[0, 'origem'] += pd.Timedelta(nanoseconds=1)
    with pytest.raises(ValueError, match='divergentes'):
        comparar_amostras(a, b)
