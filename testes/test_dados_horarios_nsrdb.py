from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from codigo_fonte.dados_horarios_nsrdb import carregar_dados_horarios


def _gravar_ano(pasta: Path, ano: int, horas: int) -> None:
    tempo = pd.date_range(
        f"{ano}-01-01",
        periods=horas,
        freq="1h",
        tz="UTC",
    )
    quadro = pd.DataFrame(
        {
            "timestamp_utc": tempo,
            "site_id_nsrdb": 1,
            "ghi": np.maximum(0, np.sin(np.arange(horas) * np.pi / 12)) * 800,
            "localidade": "Fábrica teste",
        }
    )
    quadro.to_csv(
        pasta / f"nsrdb_ghi_horaria_{ano}.csv.gz",
        index=False,
        compression="gzip",
    )


def test_carregar_dados_horarios_valida_serie_continua(tmp_path):
    _gravar_ano(tmp_path, 2023, 8760)
    dados = carregar_dados_horarios(tmp_path, anos=[2023])
    assert len(dados) == 8760
    assert dados["timestamp_utc"].dt.tz is not None
    assert dados["ghi"].min() >= 0


def test_carregar_dados_horarios_rejeita_lacuna(tmp_path):
    _gravar_ano(tmp_path, 2023, 100)
    caminho = tmp_path / "nsrdb_ghi_horaria_2023.csv.gz"
    dados = pd.read_csv(caminho)
    dados = dados.drop(index=50)
    dados.to_csv(caminho, index=False, compression="gzip")
    with pytest.raises(ValueError, match="descontínua"):
        carregar_dados_horarios(tmp_path, anos=[2023])
