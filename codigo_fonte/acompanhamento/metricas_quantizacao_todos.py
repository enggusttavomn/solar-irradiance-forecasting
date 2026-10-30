"""Calculo independente e validacao tabular dos novos experimentos."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

TAREFAS = {
    "hourly_72_extension": (24, 48, 72),
    "daily_30": (1, 3, 7, 14, 30),
    "monthly_1": (1,),
    "monthly_6": (1, 3, 6),
}
MODELOS = ("TimesNet", "XGBoost", "LSTM", "DilatedRNN", "GRU", "Transformer", "Informer",
           "ARIMA", "Persistencia", "Sazonal ingenuo", "Climatologia")
VARIANTES = {"sem_quantizacao": None, "q64": 64, "q128": 128, "q256": 256}
CHAVES = ["localidade", "origem", "data_alvo", "passo"]
METRICAS = ["MAE_wm2", "MSE_w2m4", "RMSE_wm2", "nRMSE", "R2"]


def sha256(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalizar_chaves(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.rename(columns={"origem_utc": "origem", "timestamp_alvo_utc": "data_alvo",
                                "passo_h": "passo"}).copy()
    faltantes = set(CHAVES + ["ghi_real_wm2"]) - set(out)
    if faltantes:
        raise ValueError(f"Chaves/observacoes ausentes: {sorted(faltantes)}")
    for col in ("origem", "data_alvo"):
        out[col] = pd.to_datetime(out[col], utc=True, format="mixed", errors="raise").astype("datetime64[ns, UTC]")
    if out[CHAVES].isna().any().any() or out.duplicated(CHAVES).any():
        raise ValueError("Chaves nulas ou duplicadas.")
    return out.sort_values(CHAVES).reset_index(drop=True)


def validar_previsoes(frame: pd.DataFrame, tarefa: str, modelo: str, n_locais: int = 10) -> pd.DataFrame:
    df = normalizar_chaves(frame)
    if tarefa not in TAREFAS:
        raise ValueError("Tarefa desconhecida.")
    bruto, pos = f"{modelo}_bruta_wm2", f"{modelo}_wm2"
    if not np.isfinite(df[["ghi_real_wm2", bruto, pos]].to_numpy(float)).all():
        raise ValueError("Valores observados ou previstos nao finitos.")
    horizonte = max(TAREFAS[tarefa])
    agrupado = df.groupby(["localidade", "origem"])["passo"]
    if (df.localidade.nunique() != n_locais
            or not (agrupado.size() == horizonte).all()
            or not (agrupado.min() == 1).all()
            or not (agrupado.max() == horizonte).all()
            or not np.equal(df.passo, np.floor(df.passo)).all()
            or (df.data_alvo < df.origem).any()):
        raise ValueError("Localidades, horizontes ou causalidade invalidos.")
    esperado = np.maximum(df[bruto].to_numpy(float), 0)
    if tarefa == "hourly_72_extension":
        if "elevacao_solar_graus" not in df:
            raise ValueError("Horario sem elevacao solar auditavel.")
        elev = df.elevacao_solar_graus.to_numpy(float)
        if not np.isfinite(elev).all() or (np.abs(elev) > 90).any():
            raise ValueError("Elevacao solar invalida.")
        esperado[elev <= 0] = 0
    if not np.allclose(df[pos], esperado, atol=1e-6, rtol=0):
        raise ValueError("Pos-processamento diverge do piso zero/mascara solar.")
    return df


def comparar_amostras(a: pd.DataFrame, b: pd.DataFrame) -> None:
    a, b = normalizar_chaves(a), normalizar_chaves(b)
    if not a[CHAVES].equals(b[CHAVES]) or not np.allclose(
            a.ghi_real_wm2, b.ghi_real_wm2, rtol=0, atol=1e-6):
        raise ValueError("Origens, alvos, localidades ou observacoes divergentes.")


def calcular_metricas(frame: pd.DataFrame, tarefa: str, modelo: str) -> pd.DataFrame:
    """Media de metricas por localidade; macro-MSE nao e macro-RMSE ao quadrado."""
    df = normalizar_chaves(frame)
    linhas = []
    for horizonte in TAREFAS[tarefa]:
        recorte = df.loc[df.passo <= horizonte]
        locais = []
        for _, g in recorte.groupby("localidade", sort=True):
            real = g.ghi_real_wm2.to_numpy(float)
            prev = g[f"{modelo}_wm2"].to_numpy(float)
            if not np.isfinite(np.r_[real, prev]).all():
                raise ValueError("Metrica com observacao/previsao nao finita.")
            erro = prev - real
            mse = float(np.mean(erro ** 2))
            rmse = float(np.sqrt(mse))
            media = float(np.mean(real))
            denominador = float(np.sum((real - media) ** 2))
            locais.append({"MAE_wm2": float(np.mean(np.abs(erro))),
                           "MSE_w2m4": mse, "RMSE_wm2": rmse,
                           "nRMSE": np.nan if np.isclose(media, 0) else rmse / media,
                           "R2": np.nan if len(real) < 2 or np.isclose(denominador, 0)
                                 else 1 - float(np.sum(erro ** 2)) / denominador})
        if not locais:
            raise ValueError("Recorte sem observacoes.")
        medias = pd.DataFrame(locais).mean().to_dict()
        linhas.append({"tarefa": tarefa, "modelo": modelo, "horizonte": horizonte,
                       "N_localidades": len(locais), "N_pontos": len(recorte),
                       "N_origens": recorte[["localidade", "origem"]].drop_duplicates().shape[0],
                       **medias})
    return pd.DataFrame(linhas)


def comparar_metricas(salvas: pd.DataFrame, recalculadas: pd.DataFrame) -> None:
    if salvas.horizonte.duplicated().any() or set(salvas.horizonte) != set(recalculadas.horizonte):
        raise ValueError("Horizontes das metricas inconsistentes.")
    a, b = (x.set_index("horizonte").sort_index() for x in (salvas, recalculadas))
    if not np.allclose(a[METRICAS], b[METRICAS], rtol=1e-9, atol=1e-7, equal_nan=True):
        raise ValueError("Metricas salvas divergem do recalculo independente.")
    for col in ("N_localidades", "N_pontos", "N_origens"):
        if col in a and not np.array_equal(a[col], b[col]):
            raise ValueError(f"Contagem divergente: {col}")
