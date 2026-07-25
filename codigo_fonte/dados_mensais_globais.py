"""Base mensal global do protocolo comparativo canonico.

O modulo transforma as dez series de GHI em janelas causais de um mes a
frente. Todas as transformacoes numericas sao ajustadas apenas no intervalo de
treino de cada localidade. A mesma informacao fica disponivel em dois formatos:

* vetor tabular, para XGBoost e MLP;
* sequencia cronologica mais covariaveis conhecidas, para RNN, LSTM e
  DilatedRNN.

DeepAR e DeepNPTS recebem as mesmas series normalizadas diretamente por meio
do GluonTS. A quantizacao uniforme em 128 niveis e uma escolha experimental
deste protocolo, distinta do alvo continuo dos fluxos legados.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from codigo_fonte.configuracao import PASTA_DADOS_BRUTOS
from codigo_fonte.localidades_ev import LOCALIDADES_EV


NIVEIS_QUANTIZACAO = 128
CONTEXTO_MENSAL = 12
PROPORCAO_TREINO = 0.8


def nome_arquivo(nome: str) -> str:
    """Converte o nome cadastrado para o nome dos CSVs locais."""

    return nome.lower().replace(" ", "_").replace("-", "_")


@dataclass(frozen=True)
class SerieMensalGlobal:
    """Serie mensal e parametros ajustados exclusivamente no treino."""

    localidade_id: int
    localidade: str
    pais: str
    datas: pd.DatetimeIndex
    ghi_wm2: np.ndarray
    ghi_modelo: np.ndarray
    minimo_treino: float
    maximo_treino: float
    indice_corte_alvo: int
    indice_corte_transformacao: int

    def inverter(self, valores: np.ndarray | pd.Series) -> np.ndarray:
        """Retorna valores normalizados para W/m2 na escala desta serie."""

        arr = np.asarray(valores, dtype=float)
        invertidos = arr * (self.maximo_treino - self.minimo_treino) + self.minimo_treino
        # GHI nao pode ser negativa. Nao se aplica limite superior: previsoes
        # acima do maximo do treino precisam continuar representadas nas
        # metricas pontuais e, sobretudo, nas caudas probabilisticas.
        return np.maximum(invertidos, 0.0)


@dataclass(frozen=True)
class BaseMensalGlobal:
    """Janelas agrupadas das localidades e metadados para auditoria."""

    series: tuple[SerieMensalGlobal, ...]
    janelas: pd.DataFrame
    colunas_lag: tuple[str, ...]
    colunas_auxiliares: tuple[str, ...]
    colunas_localidade: tuple[str, ...]
    colunas_tabulares: tuple[str, ...]
    contexto: int
    niveis_quantizacao: int
    train_ratio: float
    limite_ajuste_transformacao: pd.Timestamp | None

    @property
    def treino(self) -> pd.DataFrame:
        return self.janelas.loc[self.janelas["particao"] == "treino"].copy()

    @property
    def teste(self) -> pd.DataFrame:
        return self.janelas.loc[self.janelas["particao"] == "teste"].copy()


def _carregar_mensal(caminho: Path) -> pd.Series:
    """Carrega um CSV diario completo e calcula a media do mes civil.

    Dados invalidos, dias repetidos e lacunas geram erro em vez de serem
    descartados silenciosamente. Como cada linha representa a media das mesmas
    24 horas de um dia, a media dos dias equivale a ponderar igualmente todas
    as horas do mes.
    """

    dados = pd.read_csv(caminho, usecols=["data", "ghi"])
    datas = pd.to_datetime(dados["data"], errors="coerce")
    ghi = pd.to_numeric(dados["ghi"], errors="coerce")
    if datas.isna().any():
        raise ValueError(f"Datas invalidas em {caminho.name}.")
    if ghi.isna().any() or not np.isfinite(ghi.to_numpy(dtype=float)).all():
        raise ValueError(f"Valores de GHI invalidos em {caminho.name}.")
    if (ghi < 0).any():
        raise ValueError(f"Valores de GHI negativos em {caminho.name}.")

    dias = datas.dt.normalize()
    if dias.duplicated().any():
        raise ValueError(f"Dias duplicados em {caminho.name}.")
    ordem = np.argsort(dias.to_numpy())
    dias_ordenados = pd.DatetimeIndex(dias.iloc[ordem])
    grade_diaria = pd.date_range(dias_ordenados[0], dias_ordenados[-1], freq="D")
    if not dias_ordenados.equals(grade_diaria):
        ausentes = grade_diaria.difference(dias_ordenados).strftime("%Y-%m-%d")
        amostra = ", ".join(ausentes[:5])
        sufixo = "..." if len(ausentes) > 5 else ""
        raise ValueError(f"Dias ausentes em {caminho.name}: {amostra}{sufixo}")

    serie_diaria = pd.Series(
        ghi.iloc[ordem].to_numpy(dtype=float),
        index=dias_ordenados,
        name="ghi",
    )
    mensal = serie_diaria.resample("ME").mean()
    if mensal.isna().any():
        ausentes = mensal.index[mensal.isna()].strftime("%Y-%m").tolist()
        raise ValueError(f"Meses sem GHI em {caminho.name}: {', '.join(ausentes)}")
    grade = pd.date_range(mensal.index.min(), mensal.index.max(), freq="ME")
    if not mensal.index.equals(grade):
        raise ValueError(f"A serie mensal de {caminho.name} nao possui grade regular.")
    return mensal.astype(float)


def auditar_arquivos_diarios(
    pasta_csv: str | Path | None = None,
) -> pd.DataFrame:
    """Resume cobertura, problemas de qualidade e proveniencia dos CSVs.

    A auditoria e deliberadamente anterior a qualquer descarte: seus totais
    registram quantos valores ausentes, duplicados, invalidos ou negativos
    existiam nos arquivos recebidos.
    """

    pasta = (
        Path(pasta_csv)
        if pasta_csv is not None
        else PASTA_DADOS_BRUTOS / "localidades_ev"
    )
    linhas: list[dict[str, object]] = []
    for cadastro in LOCALIDADES_EV:
        caminho = pasta / f"{nome_arquivo(cadastro['nome'])}.csv"
        if not caminho.is_file():
            raise FileNotFoundError(f"CSV da localidade nao encontrado: {caminho}")
        dados = pd.read_csv(caminho)
        if not {"data", "ghi"}.issubset(dados.columns):
            raise ValueError(f"{caminho.name} nao contem as colunas data e ghi.")
        datas = pd.to_datetime(dados["data"], errors="coerce")
        ghi = pd.to_numeric(dados["ghi"], errors="coerce")
        datas_validas = datas.dropna()
        if datas_validas.empty:
            raise ValueError(f"{caminho.name} nao contem nenhuma data valida.")
        data_inicial = datas_validas.min().normalize()
        data_final = datas_validas.max().normalize()
        dias_esperados = len(pd.date_range(data_inicial, data_final, freq="D"))
        dias_unicos = datas_validas.dt.normalize().nunique()

        def valor_constante(coluna: str) -> object | None:
            if coluna not in dados:
                return None
            valores = dados[coluna].dropna().astype(str).unique()
            return valores[0] if len(valores) == 1 else ";".join(sorted(valores))

        linhas.append(
            {
                "Localidade": cadastro["nome"],
                "arquivo": caminho.name,
                "data_inicial": data_inicial,
                "data_final": data_final,
                "linhas_brutas": int(len(dados)),
                "datas_invalidas": int(datas.isna().sum()),
                "ghi_invalidas": int(
                    (ghi.isna() | ~np.isfinite(ghi.to_numpy(dtype=float))).sum()
                ),
                "ghi_negativas": int((ghi < 0).sum()),
                "datas_duplicadas": int(
                    datas.dropna().dt.normalize().duplicated().sum()
                ),
                "dias_esperados": int(dias_esperados),
                "dias_ausentes": int(max(0, dias_esperados - dias_unicos)),
                "produto_dados": valor_constante("produto_dados"),
                "intervalo_minutos": valor_constante("intervalo_minutos"),
                "agregacao_origem": valor_constante("agregacao"),
                "unidade_ghi": valor_constante("unidade_ghi"),
            }
        )
    return pd.DataFrame(linhas).sort_values("Localidade", ignore_index=True)


def _quantizar_minmax(
    valores: np.ndarray,
    minimo: float,
    maximo: float,
    niveis: int,
) -> np.ndarray:
    """Aplica min--max do treino e quantizacao uniforme em ``niveis``."""

    if niveis < 2:
        raise ValueError("A quantizacao precisa de pelo menos dois niveis.")
    amplitude = maximo - minimo
    if np.isclose(amplitude, 0.0):
        return np.zeros_like(valores, dtype=float)
    continuo = np.clip((valores - minimo) / amplitude, 0.0, 1.0)
    return np.rint(continuo * (niveis - 1)) / (niveis - 1)


def carregar_base_mensal_global(
    *,
    contexto: int = CONTEXTO_MENSAL,
    train_ratio: float = PROPORCAO_TREINO,
    niveis_quantizacao: int = NIVEIS_QUANTIZACAO,
    pasta_csv: str | Path | None = None,
    limite_ajuste_transformacao: str | pd.Timestamp | None = None,
) -> BaseMensalGlobal:
    """Monta as janelas mensais das dez localidades sem vazamento temporal.

    A divisao 80/20 e aplicada aos exemplos supervisionados depois da janela de
    contexto. Com 72 meses e contexto de 12 meses, cada localidade possui 60
    alvos: 48 de treino (jan./2020--dez./2023) e 12 de teste (2024).
    """

    if contexto < 12:
        raise ValueError("contexto deve ser pelo menos 12 para as medias mensais.")
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio deve estar entre zero e um.")
    if niveis_quantizacao < 2:
        raise ValueError("niveis_quantizacao deve ser pelo menos dois.")
    limite_transformacao = (
        pd.Timestamp(limite_ajuste_transformacao)
        if limite_ajuste_transformacao is not None
        else None
    )
    if limite_transformacao is not None and limite_transformacao.tz is not None:
        raise ValueError("limite_ajuste_transformacao nao pode possuir fuso horario.")
    pasta = (
        Path(pasta_csv)
        if pasta_csv is not None
        else PASTA_DADOS_BRUTOS / "localidades_ev"
    )

    series: list[SerieMensalGlobal] = []
    linhas: list[dict[str, object]] = []
    colunas_lag = tuple(f"ghi_t-{passos}" for passos in range(contexto, 0, -1))
    colunas_aux = (
        "media_3m",
        "media_6m",
        "media_12m",
        "mes_alvo_sin",
        "mes_alvo_cos",
    )
    colunas_local = tuple(f"localidade_{i}" for i in range(len(LOCALIDADES_EV)))

    grade_mensal_comum: pd.DatetimeIndex | None = None
    for localidade_id, cadastro in enumerate(LOCALIDADES_EV):
        caminho = pasta / f"{nome_arquivo(cadastro['nome'])}.csv"
        if not caminho.is_file():
            raise FileNotFoundError(f"CSV da localidade nao encontrado: {caminho}")
        mensal = _carregar_mensal(caminho)
        if grade_mensal_comum is None:
            grade_mensal_comum = pd.DatetimeIndex(mensal.index)
        elif not mensal.index.equals(grade_mensal_comum):
            raise ValueError(
                f"A cobertura mensal de {cadastro['nome']} difere das demais localidades."
            )
        quantidade_exemplos = len(mensal) - contexto
        n_treino = int(quantidade_exemplos * train_ratio)
        if n_treino <= 0 or n_treino >= quantidade_exemplos:
            raise ValueError(f"Serie insuficiente para dividir {cadastro['nome']}.")

        # O ultimo alvo de treino esta no indice contexto+n_treino-1. Os limites
        # podem usar todas as observacoes disponiveis ate esse instante.
        indice_corte_alvo = contexto + n_treino
        valores = mensal.to_numpy(dtype=float)
        indice_corte_transformacao = indice_corte_alvo
        if limite_transformacao is not None:
            indice_corte_transformacao = int((mensal.index < limite_transformacao).sum())
            if not contexto < indice_corte_transformacao <= indice_corte_alvo:
                raise ValueError(
                    "O limite da transformacao deve ficar depois do contexto e "
                    "nao pode ultrapassar o ultimo alvo de treino."
                )
        trecho_treino = valores[:indice_corte_transformacao]
        minimo = float(trecho_treino.min())
        maximo = float(trecho_treino.max())
        valores_modelo = _quantizar_minmax(
            valores,
            minimo,
            maximo,
            niveis_quantizacao,
        )
        serie = SerieMensalGlobal(
            localidade_id=localidade_id,
            localidade=cadastro["nome"],
            pais=cadastro["pais"],
            datas=pd.DatetimeIndex(mensal.index),
            ghi_wm2=valores,
            ghi_modelo=valores_modelo,
            minimo_treino=minimo,
            maximo_treino=maximo,
            indice_corte_alvo=indice_corte_alvo,
            indice_corte_transformacao=indice_corte_transformacao,
        )
        series.append(serie)

        for alvo_idx in range(contexto, len(mensal)):
            sequencia = valores_modelo[alvo_idx - contexto : alvo_idx]
            data_alvo = mensal.index[alvo_idx]
            linha: dict[str, object] = {
                "localidade_id": localidade_id,
                "Localidade": cadastro["nome"],
                "Pais": cadastro["pais"],
                "data_alvo": data_alvo,
                "indice_alvo": alvo_idx,
                "particao": "treino" if alvo_idx < indice_corte_alvo else "teste",
                "y_normalizado": float(valores_modelo[alvo_idx]),
                "y_wm2": float(valores[alvo_idx]),
                "minimo_treino": minimo,
                "maximo_treino": maximo,
            }
            linha.update(dict(zip(colunas_lag, sequencia, strict=True)))
            linha.update(
                {
                    "media_3m": float(sequencia[-3:].mean()),
                    "media_6m": float(sequencia[-6:].mean()),
                    "media_12m": float(sequencia[-12:].mean()),
                    "mes_alvo_sin": float(
                        np.sin(2 * np.pi * (data_alvo.month - 1) / 12)
                    ),
                    "mes_alvo_cos": float(
                        np.cos(2 * np.pi * (data_alvo.month - 1) / 12)
                    ),
                }
            )
            linha.update(
                {
                    coluna: float(i == localidade_id)
                    for i, coluna in enumerate(colunas_local)
                }
            )
            linhas.append(linha)

    janelas = pd.DataFrame(linhas).sort_values(
        ["data_alvo", "localidade_id"], ignore_index=True
    )
    colunas_tabulares = colunas_lag + colunas_aux + colunas_local
    return BaseMensalGlobal(
        series=tuple(series),
        janelas=janelas,
        colunas_lag=colunas_lag,
        colunas_auxiliares=colunas_aux,
        colunas_localidade=colunas_local,
        colunas_tabulares=colunas_tabulares,
        contexto=contexto,
        niveis_quantizacao=niveis_quantizacao,
        train_ratio=train_ratio,
        limite_ajuste_transformacao=limite_transformacao,
    )


def matrizes_keras(
    dados: pd.DataFrame,
    base: BaseMensalGlobal,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Retorna sequencia, covariaveis auxiliares e alvo para redes Keras."""

    if not isinstance(dados, pd.DataFrame) or dados.empty:
        raise ValueError("dados deve ser um DataFrame nao vazio.")
    obrigatorias = set(
        base.colunas_lag
        + base.colunas_auxiliares
        + base.colunas_localidade
        + ("y_normalizado",)
    )
    faltantes = sorted(obrigatorias - set(dados.columns))
    if faltantes:
        raise ValueError(f"Colunas ausentes para Keras: {', '.join(faltantes)}")
    sequencias = dados.loc[:, base.colunas_lag].to_numpy(dtype=np.float32)[..., None]
    auxiliares = dados.loc[
        :, base.colunas_auxiliares + base.colunas_localidade
    ].to_numpy(dtype=np.float32)
    alvos = dados["y_normalizado"].to_numpy(dtype=np.float32)
    if not all(np.isfinite(valores).all() for valores in (sequencias, auxiliares, alvos)):
        raise ValueError("As matrizes Keras devem conter apenas valores finitos.")
    return sequencias, auxiliares, alvos


__all__ = [
    "BaseMensalGlobal",
    "CONTEXTO_MENSAL",
    "NIVEIS_QUANTIZACAO",
    "PROPORCAO_TREINO",
    "SerieMensalGlobal",
    "auditar_arquivos_diarios",
    "carregar_base_mensal_global",
    "matrizes_keras",
    "nome_arquivo",
]
