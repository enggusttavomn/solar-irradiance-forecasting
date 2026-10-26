from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scripts.auditar_quantizacao_todos_modelos import conferir_hashes, normalizacao_independente
from scripts.metricas_quantizacao_todos import sha256
from scripts.rodar_quantizacao_todos_modelos import comando, recurso


@pytest.mark.parametrize("niveis", [None, 64, 128, 256])
def test_quantizacao_por_localidade_sem_consultar_alvo(niveis):
    j = SimpleNamespace(localidade_id=np.array([0, 1]),
                        x_bruto=np.array([[0., 15., 30.], [100., 125., 200.]]),
                        y_bruto=np.full((2, 1), np.nan))
    escalas = pd.DataFrame({"localidade_id": [0, 1], "minimo_treino_wm2": [10., 100.],
                           "amplitude_escala_wm2": [10., 50.]})
    esperado = np.array([[-1., .5, 2.], [0., .5, 2.]], np.float32)
    if niveis:
        meio = round(.5 * (niveis - 1)) / (niveis - 1)
        esperado = np.array([[0., meio, 1.], [0., meio, 1.]], np.float32)
    np.testing.assert_array_equal(normalizacao_independente(j, escalas, niveis), esperado)
    assert np.isnan(j.y_bruto).all()


def test_hash_recusa_fonte_modificada(tmp_path):
    p = tmp_path / "fonte.txt"
    p.write_text("original", encoding="utf-8")
    fontes = {str(p): sha256(p)}
    conferir_hashes(fontes)
    p.write_text("alterado", encoding="utf-8")
    with pytest.raises(AssertionError):
        conferir_hashes(fontes)


@pytest.mark.parametrize("tarefa,modelo,esperado", [
    ("daily_30", "GRU", "gpu"), ("hourly_72_extension", "LSTM", "gpu"),
    ("monthly_1", "GRU", "cpu"), ("daily_30", "ARIMA", "cpu"),
    ("daily_30", "XGBoost", "cpu"),
])
def test_agendamento_e_comando_consistentes(tmp_path, tarefa, modelo, esperado):
    args = SimpleNamespace(regime="atual", saida=tmp_path, smoke=False, protocolo=None,
                           gpu_modelos=["LSTM", "GRU", "DilatedRNN", "Transformer", "Informer", "TimesNet"])
    assert recurso(args, tarefa, modelo) == esperado
    cmd = comando(args, tarefa, modelo, "selecao")
    if modelo in ("GRU", "LSTM") and esperado == "gpu":
        assert cmd[cmd.index("--dispositivo") + 1] == "cuda"
    else:
        assert "--dispositivo" not in cmd
    modulo = cmd[cmd.index("-m") + 1]
    assert modulo.endswith("estatisticos" if modelo == "ARIMA" else "concorrentes")


def test_argumento_modelo_com_espaco_e_um_argumento(tmp_path):
    args = SimpleNamespace(regime="atual", saida=tmp_path, smoke=True, protocolo=None)
    cmd = comando(args, "monthly_1", "Sazonal ingenuo", "refit")
    assert cmd[cmd.index("--modelo") + 1] == "Sazonal ingenuo"
    assert "--smoke" in cmd
