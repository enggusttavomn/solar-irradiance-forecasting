"""Auditoria independente das agregacoes e preservacao da base historica."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
REL = RAIZ / "relatorios/quantizacao_todos_modelos_20260929/historico"


def digest(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def executar() -> dict:
    status = json.loads((REL / "status_coleta.json").read_text(encoding="utf-8"))
    manifesto = json.loads((RAIZ / "dados/brutos/localidades_ev_horario_1998_2022/manifesto_historico.json").read_text(encoding="utf-8"))
    agregado = json.loads((REL / "auditoria_agregacao_completa.json").read_text(encoding="utf-8"))
    cobertura = json.loads((REL / "cobertura_remota.json").read_text(encoding="utf-8"))
    assert status["status"] == "concluido" and manifesto["completo"] and agregado["ok"]
    assert {x["ano"] for x in cobertura["anos"]} == set(range(1998, 2023))
    assert all(x["range_status"] == 206 and x["range_bytes_transferidos"] == 8 for x in cobertura["anos"])
    for nome, esperado in {**status["codigo_sha256"], **status["originais_sha256"]}.items():
        assert digest(RAIZ / nome) == esperado, nome
    registro = manifesto["registro"]
    ids = np.asarray([x["site_id_nsrdb"] for x in registro])
    referencia_diaria = {x["site_id_nsrdb"]: [] for x in registro}
    linhas_horarias = 0
    minimo_30min = float("inf")
    maximo_30min = float("-inf")
    for ano in range(1998, 2023):
        registro_ano = manifesto["arquivos"][str(ano)]
        caminho = RAIZ / registro_ano["arquivo"]
        assert digest(caminho) == registro_ano["sha256"]
        caminho_bruto = RAIZ / registro_ano["amostras_30min"]["arquivo"]
        assert digest(caminho_bruto) == registro_ano["amostras_30min"]["sha256"]
        horas = pd.date_range(f"{ano}-01-01", f"{ano+1}-01-01", freq="h", inclusive="left", tz="UTC")
        with np.load(caminho_bruto, allow_pickle=False) as bruto:
            assert np.array_equal(ids, bruto["site_ids"])
            matriz = bruto["ghi"].astype(np.float64)
            assert matriz.shape == (2 * len(horas), 10)
            assert np.isfinite(matriz).all() and (matriz >= 0).all()
            minimo_30min = min(minimo_30min, float(matriz.min()))
            maximo_30min = max(maximo_30min, float(matriz.max()))
            assert not np.any(matriz == 65535), "Possivel sentinela uint16 na fonte GHI"
            assert np.array_equal(bruto["timestamp_ns"], pd.date_range(horas[0], periods=len(matriz), freq="30min").as_unit("ns").asi8)
        horario = pd.read_csv(caminho, usecols=["timestamp_utc", "site_id_nsrdb", "ghi"])
        horario["timestamp_utc"] = pd.to_datetime(horario.timestamp_utc, utc=True)
        tabela = horario.pivot(index="timestamp_utc", columns="site_id_nsrdb", values="ghi").sort_index()
        assert pd.DatetimeIndex(tabela.index).equals(horas)
        esperado_horario = (matriz[0::2] + matriz[1::2]) / 2.0
        assert np.array_equal(tabela[ids].to_numpy(), esperado_horario)
        linhas_horarias += len(horario)
        for coluna, ponto in enumerate(registro):
            # Metodo independente: seleciona os indices UTC correspondentes a
            # cada relogio local anual, em vez de usar np.roll/media_diaria_api.
            indices_utc = (2 * np.arange(len(horas)) + 1 - 2 * int(ponto["timezone_nsrdb"])) % len(matriz)
            amostras = matriz[indices_utc, coluna]
            dia = np.arange(len(horas)) // 24
            medias = np.bincount(dia, weights=amostras) / np.bincount(dia)
            datas = pd.date_range(f"{ano}-01-01", periods=len(medias), freq="D")
            referencia_diaria[ponto["site_id_nsrdb"]].append(pd.Series(medias, index=datas))
    maior_diario = 0.0
    maior_mensal = 0.0
    linhas_diarias = 0
    linhas_mensais = 0
    for ponto in agregado["localidades"]:
        esperado = pd.concat(referencia_diaria[ponto["site_id_nsrdb"]])
        caminho = RAIZ / ponto["arquivo_diario"]
        assert digest(caminho) == ponto["sha256_diario"]
        diario = pd.read_csv(caminho, usecols=["data", "ghi"], index_col="data", parse_dates=True).ghi
        assert diario.index.equals(pd.date_range("1998-01-01", "2022-12-31", freq="D"))
        dif_diaria = float(np.max(np.abs(diario.to_numpy() - esperado.to_numpy())))
        assert dif_diaria < 1e-10
        maior_diario = max(maior_diario, dif_diaria)
        linhas_diarias += len(diario)
        fonte_original = RAIZ / "dados/brutos/localidades_ev" / Path(ponto["arquivo_diario"]).name
        original = pd.read_csv(fonte_original, usecols=["data", "ghi"], index_col="data", parse_dates=True).ghi.loc["2019":"2022"]
        assert diario.reindex(original.index).index.equals(original.index)
        assert np.array_equal(diario.reindex(original.index).to_numpy(dtype=np.float32), original.to_numpy(dtype=np.float32))
        caminho = RAIZ / ponto["arquivo_mensal"]
        assert digest(caminho) == ponto["sha256_mensal"]
        mensal = pd.read_csv(caminho, usecols=["data", "ghi"], index_col="data", parse_dates=True).ghi
        assert len(mensal) == 300 and mensal.index.equals(pd.date_range("1998-01-31", "2022-12-31", freq="ME"))
        medias_por_mes = esperado.groupby(esperado.index.to_period("M")).mean().to_numpy()
        dif_mensal = float(np.max(np.abs(mensal.to_numpy() - medias_por_mes)))
        assert dif_mensal < 1e-10
        maior_mensal = max(maior_mensal, dif_mensal)
        linhas_mensais += len(mensal)
    assert linhas_horarias == 2191440 and linhas_diarias == 91310 and linhas_mensais == 3000
    assert len(agregado["fronteiras_anuais"]) == 250
    assert all(x["dias_diferentes_tol_1e_8"] == 0 for x in agregado["sobreposicao_2019_2022"])
    resultado = {"ok": True, "anos": 25, "localidades": 10, "linhas_horarias": linhas_horarias,
                 "linhas_diarias": linhas_diarias, "linhas_mensais": linhas_mensais,
                 "max_diferenca_horaria_wm2": 0.0, "max_diferenca_diaria_wm2": maior_diario,
                 "max_diferenca_mensal_wm2": maior_mensal, "sobreposicao_original_2019_2022_aprovada": True,
                 "sobreposicao_diaria_float32_exata": True,
                 "ghi_30min_min_wm2": minimo_30min, "ghi_30min_max_wm2": maximo_30min,
                 "arquivos_originais_preservados": len(status["originais_sha256"]),
                 "fronteiras_anuais_explicitamente_documentadas": 250,
                 "metodo_auditoria": "reconstrucao independente a partir de indices UTC modulares e somas por dia; nenhuma chamada ao agregador produtivo",
                 "auditoria_fonte_sha256": digest(Path(__file__).resolve())}
    destino = REL / "auditoria_historico_independente.json"
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False), flush=True)
    return resultado


if __name__ == "__main__":
    executar()
