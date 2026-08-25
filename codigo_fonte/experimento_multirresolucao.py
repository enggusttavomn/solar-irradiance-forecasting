"""Avaliacao pareada de previsao de GHI em varias resolucoes temporais.

Este modulo implementa, em arquivos novos, a extensao experimental do artigo
unificado. O protocolo diario e mensal usa exatamente a mesma informacao para
todos os modelos aprendidos: uma sequencia causal de GHI e o identificador da
localidade. A selecao temporal usa 2023 somente para escolher o numero de
epocas das redes; os modelos sao reinicializados e reajustados em 2020--2023
antes da avaliacao retrospectiva de 2024.

O artigo BTSym e uma fonte de evidencia sobre o modelo DilatedRNN. Seus
resultados quantizados nao sao importados nem misturados aos resultados deste
protocolo, que usa regressao continua pareada.

O modo smoke reduz localidades, origens, sementes, epocas e arvores. Ele
verifica o caminho de codigo, mas seus numeros sao sempre marcados como nao
publicaveis.
"""

from __future__ import annotations

import argparse
import copy
import gc
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import sys
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import joblib
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from codigo_fonte.configuracao import PASTA_DADOS_BRUTOS, PASTA_RESULTADOS
from codigo_fonte.dilated_rnn_direta import DilatedRNNDireta
from codigo_fonte.experimento_horario_timesnet import LSTMEncoderDireto
from codigo_fonte.localidades_ev import LOCALIDADES_EV
from codigo_fonte.timesnet_horario import TimesNetHorario


SEMENTES_CANONICAS = (11, 23, 42, 67, 89)
MODELOS_DETERMINISTICOS = ("Persistencia", "Sazonal ingenuo", "Climatologia")
MODELOS_APRENDIDOS = ("XGBoost", "LSTM", "TimesNet", "DilatedRNN")
MODELOS = MODELOS_DETERMINISTICOS + MODELOS_APRENDIDOS
SLUG_MODELO = {
    "Persistencia": "persistencia",
    "Sazonal ingenuo": "sazonal_ingenuo",
    "Climatologia": "climatologia",
    "XGBoost": "xgboost",
    "LSTM": "lstm",
    "TimesNet": "timesnet",
    "DilatedRNN": "dilatedrnn",
}


def _inteiro_positivo(valor: object, nome: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, (int, np.integer)):
        raise ValueError(f"{nome} deve ser um inteiro positivo.")
    convertido = int(valor)
    if convertido < 1:
        raise ValueError(f"{nome} deve ser um inteiro positivo.")
    return convertido


@dataclass(frozen=True)
class IntervaloParticao:
    """Limites inclusivos da primeira e da ultima origem de uma particao."""

    inicio_origem: str
    fim_origem: str
    fim_alvo: str
    origens_esperadas_por_localidade: int

    def datas(self) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
        inicio = pd.Timestamp(self.inicio_origem)
        fim = pd.Timestamp(self.fim_origem)
        fim_alvo = pd.Timestamp(self.fim_alvo)
        if inicio.tz is not None or fim.tz is not None or fim_alvo.tz is not None:
            raise ValueError("Os cortes devem usar datas locais sem fuso.")
        if not inicio <= fim <= fim_alvo:
            raise ValueError("Intervalo temporal invalido.")
        return inicio, fim, fim_alvo


@dataclass(frozen=True)
class EspecificacaoTarefa:
    """Contrato temporal fixo de uma tarefa de previsao direta."""

    slug: str
    resolucao: str
    frequencia: str
    seq_len: int
    pred_len: int
    horizontes: tuple[int, ...]
    ajuste: IntervaloParticao
    validacao: IntervaloParticao
    refit: IntervaloParticao
    teste: IntervaloParticao
    exploratoria: bool = False

    def __post_init__(self) -> None:
        if self.resolucao not in {"horaria", "diaria", "mensal"}:
            raise ValueError("Resolucao deve ser horaria, diaria ou mensal.")
        _inteiro_positivo(self.seq_len, "seq_len")
        _inteiro_positivo(self.pred_len, "pred_len")
        horizontes = tuple(_inteiro_positivo(h, "horizonte") for h in self.horizontes)
        if tuple(sorted(set(horizontes))) != horizontes or horizontes[-1] != self.pred_len:
            raise ValueError("Horizontes devem ser crescentes e terminar em pred_len.")
        for particao in (self.ajuste, self.validacao, self.refit, self.teste):
            particao.datas()


TAREFAS_CANONICAS: dict[str, EspecificacaoTarefa] = {
    "daily_30": EspecificacaoTarefa(
        slug="daily_30",
        resolucao="diaria",
        frequencia="D",
        seq_len=365,
        pred_len=30,
        horizontes=(1, 3, 7, 14, 30),
        ajuste=IntervaloParticao("2020-01-01", "2022-12-02", "2022-12-31", 1067),
        validacao=IntervaloParticao("2023-01-01", "2023-12-02", "2023-12-31", 336),
        refit=IntervaloParticao("2020-01-01", "2023-12-02", "2023-12-31", 1432),
        teste=IntervaloParticao("2024-01-01", "2024-12-02", "2024-12-31", 337),
    ),
    "monthly_1": EspecificacaoTarefa(
        slug="monthly_1",
        resolucao="mensal",
        frequencia="ME",
        seq_len=12,
        pred_len=1,
        horizontes=(1,),
        ajuste=IntervaloParticao("2020-01-31", "2022-12-31", "2022-12-31", 36),
        validacao=IntervaloParticao("2023-01-31", "2023-12-31", "2023-12-31", 12),
        refit=IntervaloParticao("2020-01-31", "2023-12-31", "2023-12-31", 48),
        teste=IntervaloParticao("2024-01-31", "2024-12-31", "2024-12-31", 12),
    ),
    "monthly_6": EspecificacaoTarefa(
        slug="monthly_6",
        resolucao="mensal",
        frequencia="ME",
        seq_len=12,
        pred_len=6,
        horizontes=(1, 3, 6),
        ajuste=IntervaloParticao("2020-01-31", "2022-07-31", "2022-12-31", 31),
        validacao=IntervaloParticao("2023-01-31", "2023-07-31", "2023-12-31", 7),
        refit=IntervaloParticao("2020-01-31", "2023-07-31", "2023-12-31", 43),
        teste=IntervaloParticao("2024-01-31", "2024-07-31", "2024-12-31", 7),
        exploratoria=True,
    ),
}

TAREFA_HORARIA_EXTENSAO = EspecificacaoTarefa(
    slug="hourly_72_extension",
    resolucao="horaria",
    frequencia="h",
    seq_len=336,
    pred_len=72,
    horizontes=(24, 48, 72),
    ajuste=IntervaloParticao("2019-01-15", "2022-12-29", "2022-12-31", 1445),
    validacao=IntervaloParticao("2023-01-01", "2023-12-29", "2023-12-31", 363),
    refit=IntervaloParticao("2019-01-15", "2023-12-29", "2023-12-31", 1810),
    teste=IntervaloParticao("2024-01-01", "2024-12-28", "2024-12-31", 363),
)


@dataclass(frozen=True)
class ConfiguracaoMultirresolucao:
    """Hiperparametros comuns e limites operacionais da execucao."""

    modo_execucao: str = "completa"
    sementes: tuple[int, ...] = SEMENTES_CANONICAS
    batch_size_diario: int = 128
    batch_size_mensal: int = 32
    taxa_aprendizado: float = 1e-3
    peso_decay: float = 1e-5
    max_epocas_diario: int = 30
    paciencia_diario: int = 5
    max_epocas_mensal: int = 300
    paciencia_mensal: int = 30
    lstm_ocultos: int = 32
    lstm_camadas: int = 1
    embedding_localidade: int = 8
    timesnet_d_model: int = 8
    timesnet_d_ff: int = 16
    timesnet_blocos: int = 1
    timesnet_top_k: int = 3
    timesnet_kernels: int = 2
    timesnet_dropout: float = 0.1
    dilated_dilatacoes: tuple[int, ...] = (1, 2, 4)
    dilated_unidades: int = 16
    dilated_unidades_densas: int = 16
    dilated_dropout: float = 0.0
    xgb_estimadores: int = 150
    xgb_profundidade: int = 3
    xgb_taxa_aprendizado: float = 0.05
    xgb_subsample: float = 0.8
    xgb_colsample: float = 0.8
    xgb_n_jobs: int = 1
    threads_torch: int = 1
    limite_localidades_smoke: int = 2
    limite_origens_smoke: int = 3
    epocas_smoke: int = 1
    xgb_estimadores_smoke: int = 2

    def __post_init__(self) -> None:
        if self.modo_execucao not in {"completa", "smoke"}:
            raise ValueError("modo_execucao deve ser completa ou smoke.")
        sementes = tuple(int(s) for s in self.sementes)
        if not sementes or len(set(sementes)) != len(sementes):
            raise ValueError("sementes deve conter inteiros unicos.")
        if any(s < 0 or s >= 2**32 for s in sementes):
            raise ValueError("Cada semente deve pertencer a [0, 2**32).")
        inteiros = (
            "batch_size_diario",
            "batch_size_mensal",
            "max_epocas_diario",
            "paciencia_diario",
            "max_epocas_mensal",
            "paciencia_mensal",
            "lstm_ocultos",
            "lstm_camadas",
            "embedding_localidade",
            "timesnet_d_model",
            "timesnet_d_ff",
            "timesnet_blocos",
            "timesnet_top_k",
            "timesnet_kernels",
            "dilated_unidades",
            "dilated_unidades_densas",
            "xgb_estimadores",
            "xgb_profundidade",
            "xgb_n_jobs",
            "threads_torch",
            "limite_localidades_smoke",
            "limite_origens_smoke",
            "epocas_smoke",
            "xgb_estimadores_smoke",
        )
        for nome in inteiros:
            _inteiro_positivo(getattr(self, nome), nome)
        if not math.isfinite(self.taxa_aprendizado) or self.taxa_aprendizado <= 0:
            raise ValueError("taxa_aprendizado deve ser positiva.")
        if not math.isfinite(self.peso_decay) or self.peso_decay < 0:
            raise ValueError("peso_decay nao pode ser negativo.")
        if not 0 <= self.timesnet_dropout < 1 or not 0 <= self.dilated_dropout < 1:
            raise ValueError("Dropout deve pertencer a [0, 1).")
        if not 0 < self.xgb_subsample <= 1 or not 0 < self.xgb_colsample <= 1:
            raise ValueError("Amostragem XGBoost deve pertencer a (0, 1].")

    @property
    def sementes_efetivas(self) -> tuple[int, ...]:
        return self.sementes[:1] if self.modo_execucao == "smoke" else self.sementes

    def batch_size(self, tarefa: EspecificacaoTarefa) -> int:
        return self.batch_size_diario if tarefa.resolucao == "diaria" else self.batch_size_mensal

    def max_epocas(self, tarefa: EspecificacaoTarefa) -> int:
        if self.modo_execucao == "smoke":
            return self.epocas_smoke
        return self.max_epocas_diario if tarefa.resolucao == "diaria" else self.max_epocas_mensal

    def paciencia(self, tarefa: EspecificacaoTarefa) -> int:
        return self.paciencia_diario if tarefa.resolucao == "diaria" else self.paciencia_mensal

    @property
    def estimadores_xgb(self) -> int:
        return self.xgb_estimadores_smoke if self.modo_execucao == "smoke" else self.xgb_estimadores


@dataclass(frozen=True)
class SerieResolucao:
    """Serie univariada regular de uma fabrica."""

    localidade: str
    localidade_id: int
    pais: str
    datas: pd.DatetimeIndex
    ghi: np.ndarray
    frequencia: str
    caminho_fonte: Path

    def __post_init__(self) -> None:
        if len(self.datas) != len(self.ghi) or len(self.datas) < 1:
            raise ValueError("Datas e GHI possuem tamanhos incompativeis.")
        if self.datas.has_duplicates or not self.datas.is_monotonic_increasing:
            raise ValueError(f"Grade temporal invalida em {self.localidade}.")
        if not np.isfinite(self.ghi).all() or (self.ghi < 0).any():
            raise ValueError(f"GHI invalida em {self.localidade}.")
        grade = pd.date_range(self.datas[0], self.datas[-1], freq=self.frequencia)
        if not self.datas.equals(grade):
            raise ValueError(f"Serie {self.frequencia} descontinua em {self.localidade}.")


@dataclass(frozen=True)
class JanelasDiretas:
    """Matrizes alinhadas de contexto, alvo e metadados."""

    x_bruto: np.ndarray
    y_bruto: np.ndarray
    localidade_id: np.ndarray
    localidade: np.ndarray
    origem: pd.DatetimeIndex
    datas_alvo: np.ndarray
    seq_len: int
    pred_len: int
    particao: str

    def __post_init__(self) -> None:
        n = len(self.x_bruto)
        if self.x_bruto.shape != (n, self.seq_len):
            raise ValueError("x_bruto possui forma invalida.")
        if self.y_bruto.shape != (n, self.pred_len):
            raise ValueError("y_bruto possui forma invalida.")
        if self.datas_alvo.shape != (n, self.pred_len):
            raise ValueError("datas_alvo possui forma invalida.")
        if (
            self.localidade_id.shape != (n,)
            or self.localidade.shape != (n,)
            or len(self.origem) != n
            or n < 1
        ):
            raise ValueError("Metadados das janelas possuem forma invalida.")
        if not np.isfinite(self.x_bruto).all() or not np.isfinite(self.y_bruto).all():
            raise ValueError("Janelas contem valores nao finitos.")

    def normalizar(self, escalas: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        por_id = escalas.set_index("localidade_id")
        ids = self.localidade_id.astype(int)
        if not set(ids).issubset(set(por_id.index)):
            raise ValueError("Ha localidade sem escala ajustada.")
        minimo = por_id.loc[ids, "minimo_treino_wm2"].to_numpy(dtype=np.float32)
        amplitude = por_id.loc[ids, "amplitude_escala_wm2"].to_numpy(dtype=np.float32)
        x = (self.x_bruto.astype(np.float32) - minimo[:, None]) / amplitude[:, None]
        y = (self.y_bruto.astype(np.float32) - minimo[:, None]) / amplitude[:, None]
        return x.astype(np.float32, copy=False), y.astype(np.float32, copy=False)

    def inverter(self, valores: np.ndarray, escalas: pd.DataFrame) -> np.ndarray:
        arr = np.asarray(valores, dtype=float)
        if arr.shape != self.y_bruto.shape or not np.isfinite(arr).all():
            raise ValueError("Previsao normalizada invalida.")
        por_id = escalas.set_index("localidade_id")
        ids = self.localidade_id.astype(int)
        minimo = por_id.loc[ids, "minimo_treino_wm2"].to_numpy(dtype=float)
        amplitude = por_id.loc[ids, "amplitude_escala_wm2"].to_numpy(dtype=float)
        return arr * amplitude[:, None] + minimo[:, None]


def nome_arquivo_localidade(nome: str) -> str:
    return nome.lower().replace(" ", "_").replace("-", "_")


def carregar_series_diarias(
    pasta_csv: str | Path | None = None,
) -> tuple[tuple[SerieResolucao, ...], pd.DataFrame]:
    """Carrega e audita os dez CSVs diarios sem usar features derivadas."""

    pasta = Path(pasta_csv) if pasta_csv is not None else PASTA_DADOS_BRUTOS / "localidades_ev"
    series: list[SerieResolucao] = []
    auditoria: list[dict[str, object]] = []
    grade_comum: pd.DatetimeIndex | None = None
    for localidade_id, cadastro in enumerate(LOCALIDADES_EV):
        caminho = pasta / f"{nome_arquivo_localidade(cadastro['nome'])}.csv"
        if not caminho.is_file():
            raise FileNotFoundError(f"CSV diario ausente: {caminho}")
        dados = pd.read_csv(caminho)
        faltantes = {"data", "ghi"} - set(dados.columns)
        if faltantes:
            raise ValueError(f"{caminho.name} nao contem data e ghi.")
        datas = pd.to_datetime(dados["data"], errors="coerce").dt.normalize()
        ghi = pd.to_numeric(dados["ghi"], errors="coerce")
        if datas.isna().any() or ghi.isna().any():
            raise ValueError(f"Data ou GHI invalida em {caminho.name}.")
        ordem = np.argsort(datas.to_numpy())
        indice = pd.DatetimeIndex(datas.iloc[ordem])
        valores = ghi.iloc[ordem].to_numpy(dtype=np.float32)
        if grade_comum is None:
            grade_comum = indice
        elif not indice.equals(grade_comum):
            raise ValueError(f"A grade diaria de {cadastro['nome']} difere das demais.")
        if "localidade" in dados:
            nomes = dados["localidade"].dropna().astype(str).unique()
            if len(nomes) != 1 or nomes[0] != cadastro["nome"]:
                raise ValueError(f"Identidade divergente em {caminho.name}.")
        serie = SerieResolucao(
            localidade=cadastro["nome"],
            localidade_id=localidade_id,
            pais=cadastro["pais"],
            datas=indice,
            ghi=valores,
            frequencia="D",
            caminho_fonte=caminho.resolve(),
        )
        series.append(serie)
        auditoria.append(
            {
                "localidade": serie.localidade,
                "localidade_id": serie.localidade_id,
                "pais": serie.pais,
                "arquivo": str(caminho.resolve()),
                "registros": len(serie.ghi),
                "inicio": serie.datas.min().date().isoformat(),
                "fim": serie.datas.max().date().isoformat(),
                "ghi_min_wm2": float(np.min(serie.ghi)),
                "ghi_max_wm2": float(np.max(serie.ghi)),
                "datas_duplicadas": int(indice.duplicated().sum()),
                "valores_nao_finitos": int((~np.isfinite(valores)).sum()),
                "valores_negativos": int((valores < 0).sum()),
            }
        )
    return tuple(series), pd.DataFrame(auditoria)


def agregar_series_mensais(
    series_diarias: Sequence[SerieResolucao],
) -> tuple[SerieResolucao, ...]:
    """Calcula a media de cada mes civil diretamente dos CSVs diarios."""

    resultado: list[SerieResolucao] = []
    grade_comum: pd.DatetimeIndex | None = None
    for serie in series_diarias:
        mensal = pd.Series(serie.ghi.astype(float), index=serie.datas).resample("ME").mean()
        if mensal.isna().any():
            raise ValueError(f"Mes sem observacoes em {serie.localidade}.")
        indice = pd.DatetimeIndex(mensal.index)
        if grade_comum is None:
            grade_comum = indice
        elif not indice.equals(grade_comum):
            raise ValueError("As grades mensais nao sao comuns.")
        resultado.append(
            SerieResolucao(
                localidade=serie.localidade,
                localidade_id=serie.localidade_id,
                pais=serie.pais,
                datas=indice,
                ghi=mensal.to_numpy(dtype=np.float32),
                frequencia="ME",
                caminho_fonte=serie.caminho_fonte,
            )
        )
    return tuple(resultado)


def _limitar_posicoes(posicoes: np.ndarray, limite: int | None) -> np.ndarray:
    if limite is None or len(posicoes) <= limite:
        return posicoes
    limite = _inteiro_positivo(limite, "limite_origens")
    indices = np.linspace(0, len(posicoes) - 1, num=limite, dtype=int)
    return posicoes[np.unique(indices)]


def construir_janelas(
    series: Sequence[SerieResolucao],
    *,
    seq_len: int,
    pred_len: int,
    intervalo: IntervaloParticao,
    particao: str,
    limite_origens_por_localidade: int | None = None,
) -> JanelasDiretas:
    """Constroi janelas diretas e rejeita qualquer alvo alem do corte."""

    seq_len = _inteiro_positivo(seq_len, "seq_len")
    pred_len = _inteiro_positivo(pred_len, "pred_len")
    inicio, fim, fim_alvo = intervalo.datas()
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    ids: list[np.ndarray] = []
    nomes: list[np.ndarray] = []
    origens: list[np.ndarray] = []
    alvos: list[np.ndarray] = []
    for serie in series:
        candidatas = np.flatnonzero((serie.datas >= inicio) & (serie.datas <= fim))
        completas = candidatas[
            (candidatas >= seq_len)
            & (candidatas + pred_len <= len(serie.datas))
        ]
        completas = np.asarray(
            [
                i
                for i in completas
                if pd.Timestamp(serie.datas[i + pred_len - 1]) <= fim_alvo
            ],
            dtype=int,
        )
        completas = _limitar_posicoes(completas, limite_origens_por_localidade)
        if len(completas) < 1:
            raise ValueError(f"Sem janela completa em {serie.localidade}/{particao}.")
        xs.append(np.stack([serie.ghi[i - seq_len : i] for i in completas]))
        ys.append(np.stack([serie.ghi[i : i + pred_len] for i in completas]))
        ids.append(np.full(len(completas), serie.localidade_id, dtype=np.int64))
        nomes.append(np.full(len(completas), serie.localidade, dtype=object))
        origens.append(serie.datas[completas].to_numpy(dtype="datetime64[ns]"))
        alvos.append(
            np.stack(
                [
                    serie.datas[i : i + pred_len].to_numpy(dtype="datetime64[ns]")
                    for i in completas
                ]
            )
        )
    x = np.concatenate(xs).astype(np.float32, copy=False)
    y = np.concatenate(ys).astype(np.float32, copy=False)
    localidade_id = np.concatenate(ids)
    localidade = np.concatenate(nomes)
    origem = pd.DatetimeIndex(np.concatenate(origens))
    datas_alvo = np.concatenate(alvos)
    ordem = np.lexsort((localidade_id, origem.asi8))
    janelas = JanelasDiretas(
        x_bruto=x[ordem],
        y_bruto=y[ordem],
        localidade_id=localidade_id[ordem],
        localidade=localidade[ordem],
        origem=origem[ordem],
        datas_alvo=datas_alvo[ordem],
        seq_len=seq_len,
        pred_len=pred_len,
        particao=particao,
    )
    if limite_origens_por_localidade is None:
        contagens = pd.Series(janelas.localidade_id).value_counts()
        if set(contagens.astype(int)) != {intervalo.origens_esperadas_por_localidade}:
            raise AssertionError(
                f"Contagem canonica divergente em {particao}: {contagens.to_dict()}."
            )
    if bool((janelas.datas_alvo > np.datetime64(fim_alvo)).any()):
        raise AssertionError("Uma janela cruzou o corte da particao.")
    return janelas


def ajustar_escalas_pre_corte(
    series: Sequence[SerieResolucao],
    *,
    fim_exclusivo: str | pd.Timestamp,
    nome_ajuste: str,
) -> pd.DataFrame:
    """Ajusta min--max por fabrica usando somente observacoes pre-corte."""

    fim = pd.Timestamp(fim_exclusivo)
    linhas: list[dict[str, object]] = []
    for serie in series:
        valores = serie.ghi[serie.datas < fim]
        if len(valores) < 1:
            raise ValueError(f"Sem dado pre-corte em {serie.localidade}.")
        minimo = float(np.min(valores))
        maximo = float(np.max(valores))
        amplitude_real = maximo - minimo
        linhas.append(
            {
                "ajuste": nome_ajuste,
                "localidade": serie.localidade,
                "localidade_id": serie.localidade_id,
                "fim_exclusivo": fim.isoformat(),
                "N_observacoes": int(len(valores)),
                "minimo_treino_wm2": minimo,
                "maximo_treino_wm2": maximo,
                "amplitude_real_wm2": amplitude_real,
                "amplitude_escala_wm2": amplitude_real if amplitude_real > 0 else 1.0,
            }
        )
    return pd.DataFrame(linhas)


def prever_persistencia(janelas: JanelasDiretas) -> np.ndarray:
    """Mantem o ultimo valor observado em todos os passos futuros."""

    return np.repeat(janelas.x_bruto[:, -1:], janelas.pred_len, axis=1).astype(float)


def _data_ano_anterior(data: pd.Timestamp, *, mensal: bool) -> pd.Timestamp:
    if mensal:
        return data - pd.DateOffset(years=1)
    if data.month == 2 and data.day == 29:
        return data.replace(year=data.year - 1, day=28)
    return data.replace(year=data.year - 1)


def prever_sazonal_anual(
    janelas: JanelasDiretas,
    series: Sequence[SerieResolucao],
) -> np.ndarray:
    """Busca o mesmo dia ou mes do ano anterior sem consultar o futuro."""

    por_id = {s.localidade_id: s for s in series}
    resultado = np.empty_like(janelas.y_bruto, dtype=float)
    mensal = series[0].frequencia == "ME"
    for linha, localidade_id in enumerate(janelas.localidade_id):
        serie = por_id[int(localidade_id)]
        refs = pd.DatetimeIndex(
            [
                _data_ano_anterior(pd.Timestamp(data), mensal=mensal)
                for data in janelas.datas_alvo[linha]
            ]
        )
        if not bool((refs < janelas.origem[linha]).all()):
            raise AssertionError("Baseline sazonal tentou consultar dado nao causal.")
        posicoes = serie.datas.get_indexer(refs)
        if (posicoes < 0).any():
            raise ValueError(f"Referencia anual ausente em {serie.localidade}.")
        resultado[linha] = serie.ghi[posicoes]
    return resultado


def prever_climatologia(
    janelas: JanelasDiretas,
    series: Sequence[SerieResolucao],
    *,
    fim_ajuste_exclusivo: str | pd.Timestamp,
) -> np.ndarray:
    """Media calendarizada fixa, ajustada apenas antes do corte informado."""

    fim = pd.Timestamp(fim_ajuste_exclusivo)
    por_id = {s.localidade_id: s for s in series}
    resultado = np.empty_like(janelas.y_bruto, dtype=float)
    for linha, localidade_id in enumerate(janelas.localidade_id):
        serie = por_id[int(localidade_id)]
        mascara = serie.datas < fim
        datas = serie.datas[mascara]
        valores = serie.ghi[mascara].astype(float)
        if serie.frequencia == "ME":
            chaves = pd.Index(datas.month)
            alvo_chaves = [pd.Timestamp(d).month for d in janelas.datas_alvo[linha]]
        else:
            chaves = pd.Index(datas.strftime("%m-%d"))
            alvo_chaves = [
                pd.Timestamp(d).strftime("%m-%d")
                for d in janelas.datas_alvo[linha]
            ]
        tabela = pd.Series(valores).groupby(chaves).mean()
        global_media = float(np.mean(valores))
        previsoes = []
        for chave in alvo_chaves:
            if chave in tabela.index:
                previsoes.append(float(tabela.loc[chave]))
            elif chave == "02-29" and "02-28" in tabela.index:
                previsoes.append(float(tabela.loc["02-28"]))
            else:
                previsoes.append(global_media)
        resultado[linha] = previsoes
    return resultado


def previsoes_baselines(
    janelas: JanelasDiretas,
    series: Sequence[SerieResolucao],
    *,
    fim_ajuste_exclusivo: str | pd.Timestamp,
) -> dict[str, np.ndarray]:
    return {
        "Persistencia": prever_persistencia(janelas),
        "Sazonal ingenuo": prever_sazonal_anual(janelas, series),
        "Climatologia": prever_climatologia(
            janelas,
            series,
            fim_ajuste_exclusivo=fim_ajuste_exclusivo,
        ),
    }


def fixar_semente(semente: int, threads_torch: int = 1) -> None:
    """Fixa geradores e torna o caminho PyTorch deterministico em CPU."""

    random.seed(int(semente))
    np.random.seed(int(semente))
    torch.manual_seed(int(semente))
    torch.set_num_threads(_inteiro_positivo(threads_torch, "threads_torch"))
    torch.use_deterministic_algorithms(True, warn_only=True)


def criar_modelo_neural(
    modelo: str,
    *,
    tarefa: EspecificacaoTarefa,
    configuracao: ConfiguracaoMultirresolucao,
    num_localidades: int,
    semente: int,
) -> nn.Module:
    """Cria uma das tres redes sob o mesmo contrato de entrada."""

    fixar_semente(semente, configuracao.threads_torch)
    if modelo == "LSTM":
        return LSTMEncoderDireto(
            seq_len=tarefa.seq_len,
            pred_len=tarefa.pred_len,
            ocultos=configuracao.lstm_ocultos,
            camadas=configuracao.lstm_camadas,
            num_localidades=num_localidades,
            dimensao_embedding_localidade=configuracao.embedding_localidade,
        )
    if modelo == "TimesNet":
        return TimesNetHorario(
            seq_len=tarefa.seq_len,
            pred_len=tarefa.pred_len,
            d_model=configuracao.timesnet_d_model,
            d_ff=configuracao.timesnet_d_ff,
            num_blocos=configuracao.timesnet_blocos,
            top_k=configuracao.timesnet_top_k,
            num_kernels=configuracao.timesnet_kernels,
            num_localidades=num_localidades,
            dropout=configuracao.timesnet_dropout,
        )
    if modelo == "DilatedRNN":
        return DilatedRNNDireta(
            seq_len=tarefa.seq_len,
            pred_len=tarefa.pred_len,
            dilatacoes=configuracao.dilated_dilatacoes,
            unidades=configuracao.dilated_unidades,
            unidades_densas=configuracao.dilated_unidades_densas,
            num_localidades=num_localidades,
            dimensao_embedding_localidade=configuracao.embedding_localidade,
            dropout=configuracao.dilated_dropout,
        )
    raise ValueError(f"Modelo neural desconhecido: {modelo}.")


def _carregador(
    x: np.ndarray,
    y: np.ndarray | None,
    ids: np.ndarray,
    *,
    batch_size: int,
    embaralhar: bool,
    semente: int,
) -> DataLoader:
    tensores: list[torch.Tensor] = [
        torch.as_tensor(x, dtype=torch.float32),
        torch.as_tensor(ids, dtype=torch.long),
    ]
    if y is not None:
        tensores.insert(1, torch.as_tensor(y, dtype=torch.float32))
    return DataLoader(
        TensorDataset(*tensores),
        batch_size=min(batch_size, len(x)),
        shuffle=embaralhar,
        num_workers=0,
        generator=torch.Generator().manual_seed(int(semente)),
    )


def _mse_rede(modelo: nn.Module, carregador: DataLoader) -> float:
    modelo.eval()
    soma = 0.0
    quantidade = 0
    with torch.no_grad():
        for x, y, ids in carregador:
            previsto = modelo(x, ids)
            soma += float(torch.sum((previsto - y) ** 2).item())
            quantidade += int(y.numel())
    return soma / quantidade


def treinar_rede(
    modelo: nn.Module,
    *,
    x_treino: np.ndarray,
    y_treino: np.ndarray,
    ids_treino: np.ndarray,
    batch_size: int,
    taxa_aprendizado: float,
    peso_decay: float,
    semente: int,
    threads_torch: int,
    max_epocas: int,
    paciencia: int,
    x_validacao: np.ndarray | None = None,
    y_validacao: np.ndarray | None = None,
    ids_validacao: np.ndarray | None = None,
    epocas_fixas: int | None = None,
) -> tuple[nn.Module, int, list[dict[str, float | int]]]:
    """Treina com early stopping ou por numero fixo de epocas no refit."""

    fixar_semente(semente, threads_torch)
    possui_validacao = x_validacao is not None
    if possui_validacao != (y_validacao is not None) or possui_validacao != (
        ids_validacao is not None
    ):
        raise ValueError("Informe todas ou nenhuma das matrizes de validacao.")
    if possui_validacao and epocas_fixas is not None:
        raise ValueError("epocas_fixas nao pode acompanhar validacao.")
    limite_epocas = (
        _inteiro_positivo(epocas_fixas, "epocas_fixas")
        if epocas_fixas is not None
        else _inteiro_positivo(max_epocas, "max_epocas")
    )
    treino = _carregador(
        x_treino,
        y_treino,
        ids_treino,
        batch_size=batch_size,
        embaralhar=True,
        semente=semente,
    )
    validacao = (
        _carregador(
            x_validacao,
            y_validacao,
            ids_validacao,
            batch_size=batch_size,
            embaralhar=False,
            semente=semente,
        )
        if possui_validacao
        else None
    )
    otimizador = torch.optim.Adam(
        modelo.parameters(),
        lr=taxa_aprendizado,
        weight_decay=peso_decay,
    )
    melhor_estado = copy.deepcopy(modelo.state_dict())
    melhor_perda = math.inf
    melhor_epoca = 1
    sem_melhora = 0
    historico: list[dict[str, float | int]] = []
    for epoca in range(1, limite_epocas + 1):
        modelo.train()
        soma = 0.0
        quantidade = 0
        for x, y, ids in treino:
            otimizador.zero_grad(set_to_none=True)
            previsto = modelo(x, ids)
            perda = torch.mean((previsto - y) ** 2)
            perda.backward()
            otimizador.step()
            soma += float(perda.item()) * int(y.numel())
            quantidade += int(y.numel())
        perda_treino = soma / quantidade
        perda_val = _mse_rede(modelo, validacao) if validacao is not None else perda_treino
        historico.append(
            {
                "epoca": epoca,
                "mse_treino_normalizado": perda_treino,
                "mse_validacao_normalizado": perda_val,
            }
        )
        if perda_val < melhor_perda - 1e-12:
            melhor_perda = perda_val
            melhor_epoca = epoca
            melhor_estado = copy.deepcopy(modelo.state_dict())
            sem_melhora = 0
        else:
            sem_melhora += 1
            if validacao is not None and sem_melhora >= paciencia:
                break
    if validacao is not None:
        modelo.load_state_dict(melhor_estado)
    return modelo, (melhor_epoca if validacao is not None else limite_epocas), historico


def prever_rede(
    modelo: nn.Module,
    x: np.ndarray,
    ids: np.ndarray,
    *,
    batch_size: int,
) -> np.ndarray:
    carregador = _carregador(
        x,
        None,
        ids,
        batch_size=batch_size,
        embaralhar=False,
        semente=0,
    )
    saidas: list[np.ndarray] = []
    modelo.eval()
    with torch.no_grad():
        for x_lote, ids_lote in carregador:
            saidas.append(modelo(x_lote, ids_lote).cpu().numpy())
    resultado = np.concatenate(saidas).astype(float)
    if not np.isfinite(resultado).all():
        raise ValueError("Rede produziu previsao nao finita.")
    return resultado


def matriz_xgboost(x: np.ndarray, ids: np.ndarray, num_localidades: int) -> np.ndarray:
    one_hot = np.eye(num_localidades, dtype=np.float32)[np.asarray(ids, dtype=int)]
    return np.concatenate((np.asarray(x, dtype=np.float32), one_hot), axis=1)


def criar_xgboost(
    configuracao: ConfiguracaoMultirresolucao,
    *,
    semente: int,
    pred_len: int,
):
    from xgboost import XGBRegressor

    parametros: dict[str, object] = {
        "objective": "reg:squarederror",
        "n_estimators": configuracao.estimadores_xgb,
        "max_depth": configuracao.xgb_profundidade,
        "learning_rate": configuracao.xgb_taxa_aprendizado,
        "subsample": configuracao.xgb_subsample,
        "colsample_bytree": configuracao.xgb_colsample,
        "random_state": int(semente),
        "n_jobs": configuracao.xgb_n_jobs,
        "tree_method": "hist",
        "verbosity": 0,
    }
    if pred_len > 1:
        parametros["multi_strategy"] = "multi_output_tree"
    return XGBRegressor(**parametros)


def _caminho_temporario(destino: Path) -> Path:
    return destino.with_name(f".{destino.name}.{uuid.uuid4().hex}.tmp")


ATRASOS_SUBSTITUICAO_ATOMICA_S = (0.0, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2)


def _erro_bloqueio_transitorio(erro: OSError) -> bool:
    """Reconhece bloqueios de antivirus/indexador, sem ocultar outros erros."""

    winerror = getattr(erro, "winerror", None)
    return isinstance(erro, PermissionError) or winerror in {5, 32, 33}


def _sincronizar_arquivo(caminho: Path) -> None:
    """Forca os bytes do temporario ao disco antes da troca de namespace."""

    with caminho.open("r+b") as arquivo:
        arquivo.flush()
        os.fsync(arquivo.fileno())


def _remover_temporario(caminho: Path) -> None:
    for atraso in ATRASOS_SUBSTITUICAO_ATOMICA_S[:5]:
        if atraso:
            time.sleep(atraso)
        try:
            caminho.unlink(missing_ok=True)
            return
        except OSError as erro:
            if not _erro_bloqueio_transitorio(erro):
                raise


def _eh_temporario_do_modulo(caminho: Path) -> bool:
    """Aceita somente o padrao .nome.<uuid-hex-32>.tmp criado acima."""

    if not caminho.is_file() or not caminho.name.startswith("."):
        return False
    partes = caminho.name.rsplit(".", 2)
    if len(partes) != 3 or partes[-1] != "tmp":
        return False
    identificador = partes[-2]
    return len(identificador) == 32 and all(
        caractere in "0123456789abcdef" for caractere in identificador
    )


def limpar_temporarios_orfaos(pasta_tarefa: str | Path) -> list[str]:
    """Remove temporarios proprios somente dentro da pasta de uma tarefa.

    Um arquivo ainda bloqueado e ignorado pelo contrato e pelo manifesto. Isso
    permite retomar uma execucao interrompida sem ampliar a limpeza para fora
    da pasta explicitamente selecionada.
    """

    pasta = Path(pasta_tarefa).resolve()
    if not pasta.is_dir():
        return []
    ignorados: list[str] = []
    for caminho in sorted(pasta.rglob(".*.tmp")):
        resolvido = caminho.resolve()
        if pasta not in resolvido.parents or not _eh_temporario_do_modulo(resolvido):
            continue
        _remover_temporario(resolvido)
        if resolvido.exists():
            ignorados.append(resolvido.relative_to(pasta).as_posix())
    return ignorados


def _fallback_atomico_windows(temporario: Path, destino: Path) -> None:
    """Fallback seguro quando MoveFileEx fica bloqueado no Windows.

    Para um destino novo, criar um hard link publica atomicamente os bytes ja
    sincronizados no mesmo volume. Para um destino existente, ReplaceFileW
    efetua a troca atomica nativa. Nenhum fallback sobrescreve o arquivo final
    por copia direta.
    """

    if os.name != "nt":
        raise OSError("Fallback atomico especifico do Windows indisponivel.")
    hash_esperado = sha256_arquivo(temporario)
    if not destino.exists():
        os.link(temporario, destino)
        if sha256_arquivo(destino) != hash_esperado:
            raise OSError("Hard link atomico produziu conteudo divergente.")
        _remover_temporario(temporario)
        return
    import ctypes
    from ctypes import wintypes

    replace_file = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
    replace_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    replace_file.restype = wintypes.BOOL
    substituiu = replace_file(
        str(destino),
        str(temporario),
        None,
        0x00000002,
        None,
        None,
    )
    if not substituiu:
        raise ctypes.WinError(ctypes.get_last_error())
    if sha256_arquivo(destino) != hash_esperado:
        raise OSError("ReplaceFileW atomico produziu conteudo divergente.")


def _substituir_atomico(temporario: Path, destino: Path) -> None:
    """Troca um temporario sincronizado com retries e fallback Windows."""

    _sincronizar_arquivo(temporario)
    ultimo_erro: OSError | None = None
    for atraso in ATRASOS_SUBSTITUICAO_ATOMICA_S:
        if atraso:
            time.sleep(atraso)
        try:
            os.replace(temporario, destino)
            return
        except OSError as erro:
            if not _erro_bloqueio_transitorio(erro):
                raise
            ultimo_erro = erro
    if destino.is_file():
        try:
            if sha256_arquivo(destino) == sha256_arquivo(temporario):
                _remover_temporario(temporario)
                return
        except OSError:
            pass
    try:
        _fallback_atomico_windows(temporario, destino)
    except OSError as fallback:
        if ultimo_erro is not None:
            raise OSError(
                "Falha ao publicar artefato apos retries exponenciais e "
                f"fallback atomico do Windows: {destino}"
            ) from fallback
        raise


def salvar_json_atomico(conteudo: object, destino: str | Path) -> None:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = _caminho_temporario(destino)
    temporario.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _substituir_atomico(temporario, destino)


def salvar_csv_atomico(quadro: pd.DataFrame, destino: str | Path) -> None:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = _caminho_temporario(destino)
    compressao = "gzip" if destino.name.endswith(".gz") else None
    quadro.to_csv(temporario, index=False, compression=compressao)
    _substituir_atomico(temporario, destino)


def salvar_npz_atomico(destino: str | Path, **matrizes: object) -> None:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = _caminho_temporario(destino)
    with temporario.open("wb") as arquivo:
        np.savez_compressed(arquivo, **matrizes)
    _substituir_atomico(temporario, destino)


def salvar_torch_atomico(conteudo: object, destino: str | Path) -> None:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = _caminho_temporario(destino)
    torch.save(conteudo, temporario)
    _substituir_atomico(temporario, destino)


def salvar_joblib_atomico(conteudo: object, destino: str | Path) -> None:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = _caminho_temporario(destino)
    joblib.dump(conteudo, temporario)
    _substituir_atomico(temporario, destino)


def sha256_arquivo(caminho: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _versao_pacote(nome: str) -> str:
    try:
        return importlib.metadata.version(nome)
    except importlib.metadata.PackageNotFoundError:
        return "nao_instalado"


def construir_contrato(
    *,
    tarefa: EspecificacaoTarefa,
    configuracao: ConfiguracaoMultirresolucao,
    arquivos_entrada: Sequence[Path],
    arquivos_codigo_extras: Sequence[Path] = (),
) -> dict[str, object]:
    """Liga entradas, codigo, parametros e dependencias em um unico hash."""

    arquivos_codigo = [
        Path(__file__).resolve(),
        Path(sys.modules[TimesNetHorario.__module__].__file__).resolve(),
        Path(sys.modules[DilatedRNNDireta.__module__].__file__).resolve(),
        Path(sys.modules[LSTMEncoderDireto.__module__].__file__).resolve(),
        *[Path(p).resolve() for p in arquivos_codigo_extras],
    ]
    entradas = {
        str(Path(p).resolve()): sha256_arquivo(p)
        for p in sorted({Path(p).resolve() for p in arquivos_entrada}, key=str)
    }
    codigo = {
        str(p): sha256_arquivo(p)
        for p in sorted(set(arquivos_codigo), key=str)
        if p.is_file()
    }
    base: dict[str, object] = {
        "versao_contrato": 1,
        "tarefa": asdict(tarefa),
        "configuracao": asdict(configuracao),
        "entradas_sha256": entradas,
        "codigo_sha256": codigo,
        "dependencias": {
            "python": platform.python_version(),
            "numpy": _versao_pacote("numpy"),
            "pandas": _versao_pacote("pandas"),
            "torch": _versao_pacote("torch"),
            "scikit-learn": _versao_pacote("scikit-learn"),
            "xgboost": _versao_pacote("xgboost"),
            "joblib": _versao_pacote("joblib"),
        },
        "regressao": "continua",
        "informacao_compartilhada": "sequencia_causal_ghi_mais_id_localidade",
        "resultados_btsym_importados": False,
        "gravacao_atomica": (
            "fsync; os.replace_com_retry_exponencial; fallback_Windows_por_"
            "hardlink_para_destino_novo_ou_ReplaceFileW_para_destino_existente"
        ),
    }
    serializado = json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    base["sha256_contrato"] = hashlib.sha256(serializado.encode("utf-8")).hexdigest()
    return base


def validar_ou_criar_contrato(
    pasta_tarefa: str | Path,
    contrato: Mapping[str, object],
    *,
    retomar: bool,
) -> None:
    """Permite retomada somente quando o contrato completo coincide."""

    pasta = Path(pasta_tarefa)
    pasta.mkdir(parents=True, exist_ok=True)
    limpar_temporarios_orfaos(pasta)
    caminho = pasta / "contrato_execucao.json"
    existentes = [
        p
        for p in pasta.iterdir()
        if p.name != caminho.name and not _eh_temporario_do_modulo(p)
    ]
    if caminho.is_file():
        anterior = json.loads(caminho.read_text(encoding="utf-8"))
        if anterior.get("sha256_contrato") != contrato.get("sha256_contrato"):
            raise RuntimeError(
                "A pasta contem artefatos de outro contrato; use uma saida nova."
            )
        if not retomar and existentes:
            raise RuntimeError("A pasta ja contem uma execucao; habilite a retomada.")
        return
    if existentes:
        raise RuntimeError("A pasta nao vazia nao possui contrato verificavel.")
    salvar_json_atomico(dict(contrato), caminho)


@dataclass
class Estimativa:
    modelo: str
    tipo: str
    semente: int | None
    previsao_bruta: np.ndarray
    previsao_pos: np.ndarray

    @property
    def identificador(self) -> str:
        slug = SLUG_MODELO[self.modelo]
        if self.tipo == "semente":
            return f"{slug}_seed{self.semente}"
        return f"{slug}_{self.tipo}"


def _carregar_cache_modelo(
    caminho: Path,
) -> tuple[np.ndarray, np.ndarray, int, list[dict[str, object]]]:
    with np.load(caminho, allow_pickle=False) as cache:
        previsao_validacao = np.asarray(cache["previsao_validacao_bruta"], dtype=float)
        previsao_teste = np.asarray(cache["previsao_teste_bruta"], dtype=float)
        epocas = int(np.asarray(cache["epocas_selecionadas"]).item())
        historico = json.loads(str(np.asarray(cache["historico_json"]).item()))
    return previsao_validacao, previsao_teste, epocas, historico


def executar_modelo_aprendido(
    modelo: str,
    *,
    tarefa: EspecificacaoTarefa,
    configuracao: ConfiguracaoMultirresolucao,
    semente: int,
    treino: JanelasDiretas,
    validacao: JanelasDiretas,
    refit: JanelasDiretas,
    teste: JanelasDiretas,
    escalas_selecao: pd.DataFrame,
    escalas_refit: pd.DataFrame,
    num_localidades: int,
    pasta_tarefa: Path,
    retomar: bool,
) -> tuple[np.ndarray, np.ndarray, int, list[dict[str, object]]]:
    """Seleciona, refaz e preve um modelo/seed, com cache atomico."""

    slug = SLUG_MODELO[modelo]
    cache = pasta_tarefa / "cache" / f"{slug}_seed{semente}.npz"
    if retomar and cache.is_file():
        return _carregar_cache_modelo(cache)
    x_treino, y_treino = treino.normalizar(escalas_selecao)
    x_val, y_val = validacao.normalizar(escalas_selecao)
    x_refit, y_refit = refit.normalizar(escalas_refit)
    x_teste, _ = teste.normalizar(escalas_refit)
    historico_total: list[dict[str, object]] = []
    pasta_modelos = pasta_tarefa / "modelos"
    if modelo == "XGBoost":
        selecionador = criar_xgboost(
            configuracao,
            semente=semente,
            pred_len=tarefa.pred_len,
        )
        alvo_treino: np.ndarray = y_treino[:, 0] if tarefa.pred_len == 1 else y_treino
        selecionador.fit(
            matriz_xgboost(x_treino, treino.localidade_id, num_localidades),
            alvo_treino,
        )
        previsto_val = np.asarray(
            selecionador.predict(
                matriz_xgboost(x_val, validacao.localidade_id, num_localidades)
            ),
            dtype=float,
        ).reshape(len(validacao.x_bruto), tarefa.pred_len)
        del selecionador
        gc.collect()
        final = criar_xgboost(
            configuracao,
            semente=semente,
            pred_len=tarefa.pred_len,
        )
        alvo_refit: np.ndarray = y_refit[:, 0] if tarefa.pred_len == 1 else y_refit
        final.fit(
            matriz_xgboost(x_refit, refit.localidade_id, num_localidades),
            alvo_refit,
        )
        previsto_teste = np.asarray(
            final.predict(matriz_xgboost(x_teste, teste.localidade_id, num_localidades)),
            dtype=float,
        ).reshape(len(teste.x_bruto), tarefa.pred_len)
        salvar_joblib_atomico(
            final,
            pasta_modelos / f"{slug}_seed{semente}_refit.joblib",
        )
        epocas = 0
        del final
    else:
        selecionador = criar_modelo_neural(
            modelo,
            tarefa=tarefa,
            configuracao=configuracao,
            num_localidades=num_localidades,
            semente=semente,
        )
        selecionador, epocas, historico = treinar_rede(
            selecionador,
            x_treino=x_treino,
            y_treino=y_treino,
            ids_treino=treino.localidade_id,
            batch_size=configuracao.batch_size(tarefa),
            taxa_aprendizado=configuracao.taxa_aprendizado,
            peso_decay=configuracao.peso_decay,
            semente=semente,
            threads_torch=configuracao.threads_torch,
            max_epocas=configuracao.max_epocas(tarefa),
            paciencia=configuracao.paciencia(tarefa),
            x_validacao=x_val,
            y_validacao=y_val,
            ids_validacao=validacao.localidade_id,
        )
        previsto_val = prever_rede(
            selecionador,
            x_val,
            validacao.localidade_id,
            batch_size=configuracao.batch_size(tarefa),
        )
        historico_total.extend(
            {"fase": "selecao_epocas", "modelo": modelo, "semente": semente, **linha}
            for linha in historico
        )
        del selecionador
        gc.collect()
        final = criar_modelo_neural(
            modelo,
            tarefa=tarefa,
            configuracao=configuracao,
            num_localidades=num_localidades,
            semente=semente,
        )
        final, _, historico = treinar_rede(
            final,
            x_treino=x_refit,
            y_treino=y_refit,
            ids_treino=refit.localidade_id,
            batch_size=configuracao.batch_size(tarefa),
            taxa_aprendizado=configuracao.taxa_aprendizado,
            peso_decay=configuracao.peso_decay,
            semente=semente,
            threads_torch=configuracao.threads_torch,
            max_epocas=epocas,
            paciencia=configuracao.paciencia(tarefa),
            epocas_fixas=epocas,
        )
        previsto_teste = prever_rede(
            final,
            x_teste,
            teste.localidade_id,
            batch_size=configuracao.batch_size(tarefa),
        )
        historico_total.extend(
            {"fase": "refit_epocas_fixas", "modelo": modelo, "semente": semente, **linha}
            for linha in historico
        )
        salvar_torch_atomico(
            {
                "state_dict": final.state_dict(),
                "classe": type(final).__name__,
                "modelo": modelo,
                "semente": semente,
                "epocas_refit": epocas,
                "tarefa": asdict(tarefa),
                "configuracao": asdict(configuracao),
            },
            pasta_modelos / f"{slug}_seed{semente}_refit.pt",
        )
        del final
    previsao_val_bruta = validacao.inverter(previsto_val, escalas_selecao)
    previsao_teste_bruta = teste.inverter(previsto_teste, escalas_refit)
    salvar_npz_atomico(
        cache,
        previsao_validacao_bruta=previsao_val_bruta,
        previsao_teste_bruta=previsao_teste_bruta,
        epocas_selecionadas=np.asarray(epocas, dtype=np.int64),
        historico_json=np.asarray(
            json.dumps(historico_total, ensure_ascii=False, sort_keys=True)
        ),
    )
    del x_treino, y_treino, x_val, y_val, x_refit, y_refit, x_teste
    gc.collect()
    return previsao_val_bruta, previsao_teste_bruta, epocas, historico_total


def _metricas_vetor(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    real = np.asarray(y_true, dtype=float).reshape(-1)
    previsto = np.asarray(y_pred, dtype=float).reshape(-1)
    if len(real) != len(previsto) or len(real) < 1:
        raise ValueError("Vetores de metricas incompativeis.")
    erro = real - previsto
    mae = float(np.mean(np.abs(erro)))
    rmse = float(np.sqrt(np.mean(erro**2)))
    media = float(np.mean(real))
    denominador = float(np.sum((real - media) ** 2))
    return {
        "MAE_wm2": mae,
        "RMSE_wm2": rmse,
        "nRMSE": np.nan if np.isclose(media, 0.0) else rmse / media,
        "R2": (
            np.nan
            if len(real) < 2 or np.isclose(denominador, 0.0)
            else 1.0 - float(np.sum(erro**2)) / denominador
        ),
    }


def calcular_metricas_estimativas(
    *,
    tarefa: EspecificacaoTarefa,
    particao: str,
    janelas: JanelasDiretas,
    estimativas: Sequence[Estimativa],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula prefixos cumulativos e leads exatos, primeiro por localidade."""

    linhas: list[dict[str, object]] = []
    for estimativa in estimativas:
        for localidade in sorted(set(janelas.localidade.astype(str))):
            mascara = janelas.localidade.astype(str) == localidade
            real = janelas.y_bruto[mascara]
            previsto = estimativa.previsao_pos[mascara]
            for horizonte in tarefa.horizontes:
                recortes = (
                    ("cumulativo", real[:, :horizonte], previsto[:, :horizonte]),
                    ("lead_exato", real[:, horizonte - 1], previsto[:, horizonte - 1]),
                )
                for tipo_horizonte, y_true, y_pred in recortes:
                    linhas.append(
                        {
                            "tarefa": tarefa.slug,
                            "resolucao": tarefa.resolucao,
                            "particao": particao,
                            "modelo": estimativa.modelo,
                            "tipo_estimativa": estimativa.tipo,
                            "semente": estimativa.semente,
                            "localidade": localidade,
                            "tipo_horizonte": tipo_horizonte,
                            "horizonte": horizonte,
                            "N_origens": int(mascara.sum()),
                            "N_pontos": int(np.asarray(y_true).size),
                            **_metricas_vetor(y_true, y_pred),
                        }
                    )
    local = pd.DataFrame(linhas)
    chaves = [
        "tarefa",
        "resolucao",
        "particao",
        "modelo",
        "tipo_estimativa",
        "semente",
        "tipo_horizonte",
        "horizonte",
    ]
    macro = (
        local.groupby(chaves, dropna=False, as_index=False)
        .agg(
            N_localidades=("localidade", "nunique"),
            N_origens=("N_origens", "sum"),
            N_pontos=("N_pontos", "sum"),
            MAE_wm2=("MAE_wm2", "mean"),
            RMSE_wm2=("RMSE_wm2", "mean"),
            nRMSE=("nRMSE", "mean"),
            R2=("R2", "mean"),
        )
    )
    macro["agregacao"] = "media_aritmetica_das_metricas_por_localidade"
    return local, macro


def montar_tabela_previsoes(
    *,
    tarefa: EspecificacaoTarefa,
    janelas: JanelasDiretas,
    estimativas: Sequence[Estimativa],
) -> pd.DataFrame:
    """Monta tabela larga para preservar previsoes brutas e pos-processadas."""

    n = len(janelas.x_bruto)
    quadro = pd.DataFrame(
        {
            "tarefa": tarefa.slug,
            "particao": janelas.particao,
            "localidade": np.repeat(janelas.localidade, tarefa.pred_len),
            "localidade_id": np.repeat(janelas.localidade_id, tarefa.pred_len),
            "origem": np.repeat(janelas.origem.to_numpy(), tarefa.pred_len),
            "data_alvo": janelas.datas_alvo.reshape(-1),
            "passo": np.tile(np.arange(1, tarefa.pred_len + 1), n),
            "ghi_real_wm2": janelas.y_bruto.reshape(-1).astype(float),
        }
    )
    for estimativa in estimativas:
        if estimativa.previsao_bruta.shape != janelas.y_bruto.shape:
            raise ValueError(f"Forma invalida para {estimativa.identificador}.")
        quadro[f"previsao_bruta_{estimativa.identificador}_wm2"] = (
            estimativa.previsao_bruta.reshape(-1)
        )
        quadro[f"previsao_pos_{estimativa.identificador}_wm2"] = (
            estimativa.previsao_pos.reshape(-1)
        )
    return quadro


def resumir_variabilidade_sementes(macro: pd.DataFrame) -> pd.DataFrame:
    sementes = macro.loc[macro["tipo_estimativa"] == "semente"].copy()
    if sementes.empty:
        return pd.DataFrame()
    chaves = [
        "tarefa",
        "resolucao",
        "particao",
        "modelo",
        "tipo_horizonte",
        "horizonte",
    ]
    linhas: list[dict[str, object]] = []
    for valores_chave, grupo in sementes.groupby(chaves, dropna=False):
        linha = dict(zip(chaves, valores_chave, strict=True))
        linha["N_sementes"] = int(grupo["semente"].nunique())
        for metrica in ("MAE_wm2", "RMSE_wm2", "nRMSE", "R2"):
            linha[f"{metrica}_media"] = float(grupo[metrica].mean())
            linha[f"{metrica}_desvio_padrao"] = float(grupo[metrica].std(ddof=1))
            linha[f"{metrica}_minimo"] = float(grupo[metrica].min())
            linha[f"{metrica}_maximo"] = float(grupo[metrica].max())
        linhas.append(linha)
    return pd.DataFrame(linhas)


def comparacao_pareada_timesnet_dilated(
    metricas_locais: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compara ensembles por fabrica, sem tratar janelas sobrepostas como iid."""

    base = metricas_locais.loc[
        (metricas_locais["particao"] == "teste_2024")
        & (metricas_locais["tipo_estimativa"] == "ensemble")
        & metricas_locais["modelo"].isin(["TimesNet", "DilatedRNN"])
    ].copy()
    chaves = [
        "tarefa",
        "resolucao",
        "tipo_horizonte",
        "horizonte",
        "localidade",
    ]
    linhas: list[dict[str, object]] = []
    for metrica in ("MAE_wm2", "RMSE_wm2", "nRMSE", "R2"):
        tabela = base.pivot(index=chaves, columns="modelo", values=metrica).reset_index()
        if tabela.empty:
            continue
        tabela["metrica"] = metrica
        tabela["valor_timesnet"] = tabela["TimesNet"]
        tabela["valor_dilatedrnn"] = tabela["DilatedRNN"]
        tabela["diferenca_timesnet_menos_dilatedrnn"] = (
            tabela["TimesNet"] - tabela["DilatedRNN"]
        )
        tabela["melhor_timesnet"] = (
            tabela["TimesNet"] > tabela["DilatedRNN"]
            if metrica == "R2"
            else tabela["TimesNet"] < tabela["DilatedRNN"]
        )
        tabela["unidade_pareamento"] = "localidade"
        linhas.extend(
            tabela[
                chaves
                + [
                    "metrica",
                    "valor_timesnet",
                    "valor_dilatedrnn",
                    "diferenca_timesnet_menos_dilatedrnn",
                    "melhor_timesnet",
                    "unidade_pareamento",
                ]
            ].to_dict("records")
        )
    pareada = pd.DataFrame(linhas)
    if pareada.empty:
        return pareada, pd.DataFrame()
    resumo = (
        pareada.groupby(
            ["tarefa", "resolucao", "tipo_horizonte", "horizonte", "metrica"],
            as_index=False,
        )
        .agg(
            N_localidades=("localidade", "nunique"),
            diferenca_media=("diferenca_timesnet_menos_dilatedrnn", "mean"),
            diferenca_mediana=("diferenca_timesnet_menos_dilatedrnn", "median"),
            vitorias_timesnet=("melhor_timesnet", "sum"),
        )
    )
    resumo["inferencia"] = (
        "descritiva_pareada_por_localidade_sem_teste_iid_sobre_janelas_sobrepostas"
    )
    return pareada, resumo


def _protocolo_temporal(
    tarefa: EspecificacaoTarefa,
    particoes: Mapping[str, JanelasDiretas],
) -> pd.DataFrame:
    linhas: list[dict[str, object]] = []
    intervalos = {
        "ajuste": tarefa.ajuste,
        "validacao_2023": tarefa.validacao,
        "refit": tarefa.refit,
        "teste_2024": tarefa.teste,
    }
    for nome, janelas in particoes.items():
        intervalo = intervalos[nome]
        contagens = pd.Series(janelas.localidade_id).value_counts()
        linhas.append(
            {
                "tarefa": tarefa.slug,
                "resolucao": tarefa.resolucao,
                "particao": nome,
                "inicio_origem_planejado": intervalo.inicio_origem,
                "fim_origem_planejado": intervalo.fim_origem,
                "fim_alvo_planejado": intervalo.fim_alvo,
                "primeira_origem_observada": janelas.origem.min().isoformat(),
                "ultima_origem_observada": janelas.origem.max().isoformat(),
                "ultimo_alvo_observado": pd.Timestamp(
                    janelas.datas_alvo.max()
                ).isoformat(),
                "N_localidades": int(contagens.size),
                "N_origens_total": int(len(janelas.x_bruto)),
                "N_origens_por_localidade_min": int(contagens.min()),
                "N_origens_por_localidade_max": int(contagens.max()),
                "N_origens_canonicas_por_localidade": (
                    intervalo.origens_esperadas_por_localidade
                ),
                "seq_len": tarefa.seq_len,
                "pred_len": tarefa.pred_len,
                "horizontes": "/".join(map(str, tarefa.horizontes)),
                "janelas_alvo_sobrepostas": tarefa.pred_len > 1,
                "carater_exploratorio": tarefa.exploratoria,
            }
        )
    return pd.DataFrame(linhas)


def gerar_manifesto_artefatos(pasta: str | Path) -> dict[str, object]:
    pasta = Path(pasta)
    arquivos = []
    for caminho in sorted(pasta.rglob("*")):
        if (
            not caminho.is_file()
            or caminho.name == "manifesto_artefatos.json"
            or _eh_temporario_do_modulo(caminho)
        ):
            continue
        arquivos.append(
            {
                "arquivo": caminho.relative_to(pasta).as_posix(),
                "bytes": caminho.stat().st_size,
                "sha256": sha256_arquivo(caminho),
            }
        )
    return {
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "N_arquivos": len(arquivos),
        "arquivos": arquivos,
    }


def executar_tarefa_diaria_mensal(
    tarefa: EspecificacaoTarefa,
    *,
    series_diarias: Sequence[SerieResolucao],
    auditoria_entradas: pd.DataFrame,
    configuracao: ConfiguracaoMultirresolucao,
    pasta_saida: str | Path,
    retomar: bool = True,
    arquivos_codigo_extras: Sequence[Path] = (),
) -> dict[str, object]:
    """Executa uma tarefa diaria ou mensal de ponta a ponta."""

    if tarefa.resolucao == "diaria":
        series_todas = tuple(series_diarias)
    else:
        series_todas = agregar_series_mensais(series_diarias)
    series = (
        series_todas[: configuracao.limite_localidades_smoke]
        if configuracao.modo_execucao == "smoke"
        else series_todas
    )
    if [s.localidade_id for s in series] != list(range(len(series))):
        raise ValueError("As localidades selecionadas devem possuir IDs contiguos.")
    pasta_tarefa = Path(pasta_saida) / tarefa.slug
    entradas = sorted({s.caminho_fonte for s in series_diarias}, key=str)
    contrato = construir_contrato(
        tarefa=tarefa,
        configuracao=configuracao,
        arquivos_entrada=entradas,
        arquivos_codigo_extras=arquivos_codigo_extras,
    )
    validar_ou_criar_contrato(pasta_tarefa, contrato, retomar=retomar)
    salvar_json_atomico(
        {
            "etapa": "em_execucao",
            "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
            "tarefa": tarefa.slug,
            "modo_execucao": configuracao.modo_execucao,
            "resultado_smoke_nao_publicavel": configuracao.modo_execucao == "smoke",
        },
        pasta_tarefa / "status_execucao.json",
    )
    limite = (
        configuracao.limite_origens_smoke
        if configuracao.modo_execucao == "smoke"
        else None
    )
    particoes = {
        "ajuste": construir_janelas(
            series,
            seq_len=tarefa.seq_len,
            pred_len=tarefa.pred_len,
            intervalo=tarefa.ajuste,
            particao="ajuste",
            limite_origens_por_localidade=limite,
        ),
        "validacao_2023": construir_janelas(
            series,
            seq_len=tarefa.seq_len,
            pred_len=tarefa.pred_len,
            intervalo=tarefa.validacao,
            particao="validacao_2023",
            limite_origens_por_localidade=limite,
        ),
        "refit": construir_janelas(
            series,
            seq_len=tarefa.seq_len,
            pred_len=tarefa.pred_len,
            intervalo=tarefa.refit,
            particao="refit",
            limite_origens_por_localidade=limite,
        ),
        "teste_2024": construir_janelas(
            series,
            seq_len=tarefa.seq_len,
            pred_len=tarefa.pred_len,
            intervalo=tarefa.teste,
            particao="teste_2024",
            limite_origens_por_localidade=limite,
        ),
    }
    escalas_selecao = ajustar_escalas_pre_corte(
        series,
        fim_exclusivo="2023-01-01",
        nome_ajuste="ajuste_para_validacao",
    )
    escalas_refit = ajustar_escalas_pre_corte(
        series,
        fim_exclusivo="2024-01-01",
        nome_ajuste="refit_para_teste",
    )
    escalas = pd.concat([escalas_selecao, escalas_refit], ignore_index=True)
    validacao = particoes["validacao_2023"]
    teste = particoes["teste_2024"]
    estimativas_val: list[Estimativa] = []
    estimativas_teste: list[Estimativa] = []
    for modelo, bruto in previsoes_baselines(
        validacao,
        series,
        fim_ajuste_exclusivo="2023-01-01",
    ).items():
        estimativas_val.append(
            Estimativa(modelo, "deterministica", None, bruto, np.maximum(bruto, 0.0))
        )
    for modelo, bruto in previsoes_baselines(
        teste,
        series,
        fim_ajuste_exclusivo="2024-01-01",
    ).items():
        estimativas_teste.append(
            Estimativa(modelo, "deterministica", None, bruto, np.maximum(bruto, 0.0))
        )
    historico_total: list[dict[str, object]] = []
    epocas_linhas: list[dict[str, object]] = []
    for modelo in MODELOS_APRENDIDOS:
        por_seed_val: list[np.ndarray] = []
        por_seed_teste: list[np.ndarray] = []
        for semente in configuracao.sementes_efetivas:
            print(f"[{tarefa.slug}] {modelo} seed={semente}", flush=True)
            bruto_val, bruto_teste, epocas, historico = executar_modelo_aprendido(
                modelo,
                tarefa=tarefa,
                configuracao=configuracao,
                semente=semente,
                treino=particoes["ajuste"],
                validacao=validacao,
                refit=particoes["refit"],
                teste=teste,
                escalas_selecao=escalas_selecao,
                escalas_refit=escalas_refit,
                num_localidades=len(series),
                pasta_tarefa=pasta_tarefa,
                retomar=retomar,
            )
            if bruto_val.shape != validacao.y_bruto.shape:
                raise ValueError(f"Cache de validacao invalido para {modelo}/{semente}.")
            if bruto_teste.shape != teste.y_bruto.shape:
                raise ValueError(f"Cache de teste invalido para {modelo}/{semente}.")
            por_seed_val.append(bruto_val)
            por_seed_teste.append(bruto_teste)
            estimativas_val.append(
                Estimativa(
                    modelo,
                    "semente",
                    semente,
                    bruto_val,
                    np.maximum(bruto_val, 0.0),
                )
            )
            estimativas_teste.append(
                Estimativa(
                    modelo,
                    "semente",
                    semente,
                    bruto_teste,
                    np.maximum(bruto_teste, 0.0),
                )
            )
            epocas_linhas.append(
                {
                    "tarefa": tarefa.slug,
                    "modelo": modelo,
                    "semente": semente,
                    "epocas_selecionadas_em_2023": epocas,
                }
            )
            historico_total.extend({"tarefa": tarefa.slug, **linha} for linha in historico)
            salvar_json_atomico(
                {
                    "etapa": "em_execucao",
                    "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
                    "tarefa": tarefa.slug,
                    "ultimo_modelo": modelo,
                    "ultima_semente": semente,
                    "modo_execucao": configuracao.modo_execucao,
                    "resultado_smoke_nao_publicavel": (
                        configuracao.modo_execucao == "smoke"
                    ),
                },
                pasta_tarefa / "status_execucao.json",
            )
        ensemble_val = np.mean(np.stack(por_seed_val), axis=0)
        ensemble_teste = np.mean(np.stack(por_seed_teste), axis=0)
        estimativas_val.append(
            Estimativa(
                modelo,
                "ensemble",
                None,
                ensemble_val,
                np.maximum(ensemble_val, 0.0),
            )
        )
        estimativas_teste.append(
            Estimativa(
                modelo,
                "ensemble",
                None,
                ensemble_teste,
                np.maximum(ensemble_teste, 0.0),
            )
        )
    metricas_locais: list[pd.DataFrame] = []
    metricas_macro: list[pd.DataFrame] = []
    for nome, janelas, estimativas in (
        ("validacao_2023", validacao, estimativas_val),
        ("teste_2024", teste, estimativas_teste),
    ):
        local, macro = calcular_metricas_estimativas(
            tarefa=tarefa,
            particao=nome,
            janelas=janelas,
            estimativas=estimativas,
        )
        metricas_locais.append(local)
        metricas_macro.append(macro)
    locais = pd.concat(metricas_locais, ignore_index=True)
    macro = pd.concat(metricas_macro, ignore_index=True)
    variabilidade = resumir_variabilidade_sementes(macro)
    pareada, resumo_pareado = comparacao_pareada_timesnet_dilated(locais)
    salvar_csv_atomico(
        montar_tabela_previsoes(
            tarefa=tarefa,
            janelas=validacao,
            estimativas=estimativas_val,
        ),
        pasta_tarefa / "previsoes_validacao.csv.gz",
    )
    salvar_csv_atomico(
        montar_tabela_previsoes(
            tarefa=tarefa,
            janelas=teste,
            estimativas=estimativas_teste,
        ),
        pasta_tarefa / "previsoes_teste.csv.gz",
    )
    salvar_csv_atomico(locais, pasta_tarefa / "metricas_por_localidade.csv")
    salvar_csv_atomico(macro, pasta_tarefa / "metricas_macro.csv")
    salvar_csv_atomico(variabilidade, pasta_tarefa / "variabilidade_sementes.csv")
    salvar_csv_atomico(pareada, pasta_tarefa / "comparacao_pareada_localidades.csv")
    salvar_csv_atomico(resumo_pareado, pasta_tarefa / "comparacao_pareada_resumo.csv")
    salvar_csv_atomico(pd.DataFrame(epocas_linhas), pasta_tarefa / "epocas_selecionadas.csv")
    salvar_csv_atomico(pd.DataFrame(historico_total), pasta_tarefa / "historico_treinamento.csv")
    salvar_csv_atomico(escalas, pasta_tarefa / "escalas_minmax_pre_corte.csv")
    salvar_csv_atomico(_protocolo_temporal(tarefa, particoes), pasta_tarefa / "protocolo_temporal.csv")
    salvar_csv_atomico(
        auditoria_entradas.loc[
            auditoria_entradas["localidade"].isin([s.localidade for s in series])
        ].reset_index(drop=True),
        pasta_tarefa / "auditoria_entradas.csv",
    )
    salvar_json_atomico(
        {
            "tarefa": asdict(tarefa),
            "configuracao": asdict(configuracao),
            "modelos": list(MODELOS),
            "pos_processamento": "somente_piso_zero_sem_limite_superior",
            "metrica_primaria": "macro_MAE_por_localidade",
            "avaliacoes_horizonte": ["prefixo_cumulativo", "lead_exato"],
            "comparacao_pareada": "unidade_localidade; inferencia_descritiva",
            "observacao_dependencia": (
                "janelas_sobrepostas_nao_sao_tratadas_como_observacoes_iid"
            ),
            "btsym": (
                "artigo_fonte_do_DilatedRNN; numeros_quantizados_nao_importados"
            ),
        },
        pasta_tarefa / "hiperparametros_e_metodo.json",
    )
    resultado_publicavel = (
        configuracao.modo_execucao == "completa"
        and configuracao.sementes == SEMENTES_CANONICAS
    )
    resumo = {
        "tarefa": tarefa.slug,
        "etapa": "concluida",
        "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
        "modo_execucao": configuracao.modo_execucao,
        "resultado_publicavel": resultado_publicavel,
        "resultado_smoke_nao_publicavel": configuracao.modo_execucao == "smoke",
        "carater_exploratorio": tarefa.exploratoria,
        "N_localidades": len(series),
        "sementes_efetivas": list(configuracao.sementes_efetivas),
        "sha256_contrato": contrato["sha256_contrato"],
    }
    salvar_json_atomico(resumo, pasta_tarefa / "status_execucao.json")
    salvar_json_atomico(gerar_manifesto_artefatos(pasta_tarefa), pasta_tarefa / "manifesto_artefatos.json")
    return resumo


def _montar_base_horaria(janelas: object) -> pd.DataFrame:
    from codigo_fonte.experimento_horario_timesnet import timestamps_alvo

    utc, _ = timestamps_alvo(janelas)
    n = len(janelas.x_bruto)
    return pd.DataFrame(
        {
            "localidade": np.repeat(janelas.localidade, janelas.pred_len),
            "origem_utc": np.repeat(janelas.origem_utc, janelas.pred_len),
            "timestamp_alvo_utc": utc,
            "passo_h": np.tile(np.arange(1, janelas.pred_len + 1), n),
            "ghi_real_esperado_wm2": janelas.y_bruto.reshape(-1).astype(float),
        }
    )


def anexar_dilated_a_previsoes_oficiais(
    *,
    caminho_oficial: str | Path,
    janelas: object,
    previsao_bruta: np.ndarray,
    previsao_pos: np.ndarray,
) -> pd.DataFrame:
    """Alinha por chaves e acrescenta DilatedRNN sem regravar a fonte oficial."""

    base = _montar_base_horaria(janelas)
    bruto = np.asarray(previsao_bruta, dtype=float)
    pos = np.asarray(previsao_pos, dtype=float)
    if bruto.shape != janelas.y_bruto.shape or pos.shape != janelas.y_bruto.shape:
        raise ValueError("Previsoes DilatedRNN horarias possuem forma invalida.")
    base["previsao_bruta_dilatedrnn_wm2"] = bruto.reshape(-1)
    base["previsao_pos_dilatedrnn_wm2"] = pos.reshape(-1)
    oficial = pd.read_csv(caminho_oficial)
    chaves = ["localidade", "origem_utc", "timestamp_alvo_utc", "passo_h"]
    faltantes = set(chaves + ["ghi_real_wm2", "previsao_pos_timesnet_wm2"]) - set(
        oficial.columns
    )
    if faltantes:
        raise ValueError(f"Artefato horario oficial incompleto: {sorted(faltantes)}.")
    for coluna in ("origem_utc", "timestamp_alvo_utc"):
        oficial[coluna] = pd.to_datetime(oficial[coluna], utc=True, errors="raise")
        base[coluna] = pd.to_datetime(base[coluna], utc=True, errors="raise")
    if oficial.duplicated(chaves).any() or base.duplicated(chaves).any():
        raise ValueError("As chaves de previsao horaria nao sao unicas.")
    combinado = base.merge(
        oficial,
        on=chaves,
        how="left",
        validate="one_to_one",
        sort=False,
    )
    if combinado["ghi_real_wm2"].isna().any():
        raise ValueError("Ha janela nova sem correspondente no artefato oficial.")
    if len(combinado) != len(base):
        raise AssertionError("O alinhamento horario alterou a quantidade de linhas.")
    if not np.allclose(
        combinado["ghi_real_esperado_wm2"],
        combinado["ghi_real_wm2"],
        rtol=0,
        atol=1e-6,
    ):
        raise ValueError("O alvo horario diverge do artefato oficial.")
    combinado = combinado.drop(columns=["ghi_real_esperado_wm2"])
    colunas_fonte = list(oficial.columns)
    return combinado[
        colunas_fonte
        + [
            "previsao_bruta_dilatedrnn_wm2",
            "previsao_pos_dilatedrnn_wm2",
        ]
    ]


def calcular_metricas_horarias_extensao(
    tabela: pd.DataFrame,
    *,
    particao: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recalcula todos os comparadores oficiais e o novo DilatedRNN."""

    colunas_modelos = {
        "Persistencia": "previsao_pos_persistencia_wm2",
        "Sazonal ingenuo": "previsao_pos_sazonal_ingenuo_wm2",
        "XGBoost": "previsao_pos_xgboost_wm2",
        "LSTM": "previsao_pos_lstm_wm2",
        "TimesNet": "previsao_pos_timesnet_wm2",
        "DilatedRNN": "previsao_pos_dilatedrnn_wm2",
    }
    faltantes = set(colunas_modelos.values()) - set(tabela.columns)
    if faltantes:
        raise ValueError(f"Colunas horarias ausentes: {sorted(faltantes)}.")
    linhas: list[dict[str, object]] = []
    for localidade, grupo_local in tabela.groupby("localidade", sort=True):
        for modelo, coluna in colunas_modelos.items():
            for horizonte in TAREFA_HORARIA_EXTENSAO.horizontes:
                cumulativo = grupo_local.loc[
                    grupo_local["passo_h"] <= horizonte
                ]
                exato = grupo_local.loc[grupo_local["passo_h"] == horizonte]
                for tipo, recorte in (("cumulativo", cumulativo), ("lead_exato", exato)):
                    tipo_estimativa = (
                        "deterministica"
                        if modelo in {"Persistencia", "Sazonal ingenuo"}
                        else "semente"
                    )
                    linhas.append(
                        {
                            "tarefa": TAREFA_HORARIA_EXTENSAO.slug,
                            "resolucao": "horaria",
                            "particao": particao,
                            "modelo": modelo,
                            "tipo_estimativa": tipo_estimativa,
                            "semente": None if tipo_estimativa == "deterministica" else 42,
                            "localidade": localidade,
                            "tipo_horizonte": tipo,
                            "horizonte": horizonte,
                            "N_origens": int(recorte["origem_utc"].nunique()),
                            "N_pontos": int(len(recorte)),
                            **_metricas_vetor(
                                recorte["ghi_real_wm2"].to_numpy(),
                                recorte[coluna].to_numpy(),
                            ),
                        }
                    )
    local = pd.DataFrame(linhas)
    chaves = [
        "tarefa",
        "resolucao",
        "particao",
        "modelo",
        "tipo_estimativa",
        "semente",
        "tipo_horizonte",
        "horizonte",
    ]
    macro = (
        local.groupby(chaves, dropna=False, as_index=False)
        .agg(
            N_localidades=("localidade", "nunique"),
            N_origens=("N_origens", "sum"),
            N_pontos=("N_pontos", "sum"),
            MAE_wm2=("MAE_wm2", "mean"),
            RMSE_wm2=("RMSE_wm2", "mean"),
            nRMSE=("nRMSE", "mean"),
            R2=("R2", "mean"),
        )
    )
    macro["agregacao"] = "media_aritmetica_das_metricas_por_localidade"
    return local, macro


def comparacao_pareada_horaria(
    metricas_locais: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = metricas_locais.loc[
        (metricas_locais["particao"] == "teste_2024")
        & metricas_locais["modelo"].isin(["TimesNet", "DilatedRNN"])
    ]
    chaves = ["tarefa", "resolucao", "tipo_horizonte", "horizonte", "localidade"]
    linhas: list[dict[str, object]] = []
    for metrica in ("MAE_wm2", "RMSE_wm2", "nRMSE", "R2"):
        tabela = base.pivot(index=chaves, columns="modelo", values=metrica).reset_index()
        tabela["metrica"] = metrica
        tabela["valor_timesnet"] = tabela["TimesNet"]
        tabela["valor_dilatedrnn"] = tabela["DilatedRNN"]
        tabela["diferenca_timesnet_menos_dilatedrnn"] = (
            tabela["TimesNet"] - tabela["DilatedRNN"]
        )
        tabela["melhor_timesnet"] = (
            tabela["TimesNet"] > tabela["DilatedRNN"]
            if metrica == "R2"
            else tabela["TimesNet"] < tabela["DilatedRNN"]
        )
        tabela["unidade_pareamento"] = "localidade"
        linhas.extend(
            tabela[
                chaves
                + [
                    "metrica",
                    "valor_timesnet",
                    "valor_dilatedrnn",
                    "diferenca_timesnet_menos_dilatedrnn",
                    "melhor_timesnet",
                    "unidade_pareamento",
                ]
            ].to_dict("records")
        )
    pareada = pd.DataFrame(linhas)
    resumo = (
        pareada.groupby(
            ["tarefa", "resolucao", "tipo_horizonte", "horizonte", "metrica"],
            as_index=False,
        )
        .agg(
            N_localidades=("localidade", "nunique"),
            diferenca_media=("diferenca_timesnet_menos_dilatedrnn", "mean"),
            diferenca_mediana=("diferenca_timesnet_menos_dilatedrnn", "median"),
            vitorias_timesnet=("melhor_timesnet", "sum"),
        )
    )
    resumo["inferencia"] = (
        "descritiva_pareada_por_localidade_sem_teste_iid_sobre_janelas_sobrepostas"
    )
    return pareada, resumo


def executar_extensao_horaria(
    *,
    configuracao: ConfiguracaoMultirresolucao,
    pasta_saida: str | Path,
    pasta_dados_horarios: str | Path | None = None,
    pasta_oficial: str | Path | None = None,
    retomar: bool = True,
    arquivos_codigo_extras: Sequence[Path] = (),
) -> dict[str, object]:
    """Acrescenta DilatedRNN seed 42 ao protocolo horario oficial imutavel."""

    from codigo_fonte.dados_horarios_nsrdb import (
        PASTA_HORARIA_PADRAO,
        carregar_dados_horarios,
    )
    from codigo_fonte.experimento_horario_timesnet import (
        ConfiguracaoExperimentoHorario,
        ajustar_escalas_pre_corte as ajustar_escalas_horarias,
        aplicar_pos_processamento_fisico,
        calcular_elevacao_solar,
        construir_janelas_diarias,
        preparar_series_localidades,
    )

    tarefa = TAREFA_HORARIA_EXTENSAO
    pasta_dados = (
        Path(pasta_dados_horarios)
        if pasta_dados_horarios is not None
        else PASTA_HORARIA_PADRAO
    ).resolve()
    fonte_oficial = (
        Path(pasta_oficial)
        if pasta_oficial is not None
        else PASTA_RESULTADOS / "avaliacao_horaria_timesnet"
    ).resolve()
    pasta_tarefa = (Path(pasta_saida) / tarefa.slug).resolve()
    if fonte_oficial == pasta_tarefa or fonte_oficial in pasta_tarefa.parents:
        raise ValueError("A saida da extensao nao pode ficar dentro da pasta oficial.")
    obrigatorios = (
        "configuracao_execucao.json",
        "status_execucao.json",
        "manifesto_artefatos.json",
        "previsoes_validacao.csv.gz",
        "previsoes_teste.csv.gz",
        "protocolo_temporal.csv",
    )
    ausentes = [nome for nome in obrigatorios if not (fonte_oficial / nome).is_file()]
    if ausentes:
        raise FileNotFoundError(f"Artefatos horarios oficiais ausentes: {ausentes}.")
    status_oficial = json.loads(
        (fonte_oficial / "status_execucao.json").read_text(encoding="utf-8")
    )
    config_oficial = json.loads(
        (fonte_oficial / "configuracao_execucao.json").read_text(encoding="utf-8")
    )
    if status_oficial.get("etapa") != "concluida":
        raise RuntimeError("O experimento horario oficial nao esta concluido.")
    esperado = {
        "seq_len": 336,
        "pred_len": 72,
        "horizontes": [24, 48, 72],
        "anos_treino": [2019, 2020, 2021, 2022],
        "ano_validacao": 2023,
        "ano_teste": 2024,
        "semente": 42,
        "modo_execucao": "completa",
    }
    divergentes = [k for k, v in esperado.items() if config_oficial.get(k) != v]
    if divergentes:
        raise ValueError(f"Configuracao horaria oficial divergente: {divergentes}.")
    arquivos_dados = [
        pasta_dados / f"nsrdb_ghi_horaria_{ano}.csv.gz"
        for ano in range(2019, 2025)
    ]
    faltantes_dados = [str(p) for p in arquivos_dados if not p.is_file()]
    if faltantes_dados:
        raise FileNotFoundError(f"Dados horarios ausentes: {faltantes_dados}.")
    arquivos_oficiais = sorted(
        (p for p in fonte_oficial.rglob("*") if p.is_file()),
        key=str,
    )
    contrato = construir_contrato(
        tarefa=tarefa,
        configuracao=configuracao,
        arquivos_entrada=arquivos_dados + arquivos_oficiais,
        arquivos_codigo_extras=arquivos_codigo_extras,
    )
    contrato["fonte_horaria_oficial"] = str(fonte_oficial)
    contrato["politica_extensao"] = (
        "somente_DilatedRNN_seed42; demais_previsoes_lidas_sem_modificacao"
    )
    contrato.pop("sha256_contrato", None)
    serializado_contrato = json.dumps(
        contrato,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    contrato["sha256_contrato"] = hashlib.sha256(
        serializado_contrato.encode("utf-8")
    ).hexdigest()
    validar_ou_criar_contrato(pasta_tarefa, contrato, retomar=retomar)
    salvar_json_atomico(
        {
            "etapa": "em_execucao",
            "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
            "tarefa": tarefa.slug,
            "modo_execucao": configuracao.modo_execucao,
            "fonte_oficial_somente_leitura": str(fonte_oficial),
            "resultado_smoke_nao_publicavel": configuracao.modo_execucao == "smoke",
        },
        pasta_tarefa / "status_execucao.json",
    )
    config_horaria = ConfiguracaoExperimentoHorario(
        modo_execucao=configuracao.modo_execucao,
        semente=42,
    )
    dados = carregar_dados_horarios(pasta_dados)
    series = preparar_series_localidades(dados, config_horaria)
    limite = (
        configuracao.limite_origens_smoke
        if configuracao.modo_execucao == "smoke"
        else None
    )
    treino = construir_janelas_diarias(
        series,
        anos_origem=config_horaria.anos_treino,
        seq_len=336,
        pred_len=72,
        particao="treino_2019_2022",
        limite_origens_por_localidade=limite,
    )
    validacao = construir_janelas_diarias(
        series,
        anos_origem=(2023,),
        seq_len=336,
        pred_len=72,
        particao="validacao_2023",
        limite_origens_por_localidade=limite,
    )
    refit = construir_janelas_diarias(
        series,
        anos_origem=(*config_horaria.anos_treino, 2023),
        seq_len=336,
        pred_len=72,
        particao="refit_2019_2023",
        limite_origens_por_localidade=limite,
    )
    teste = construir_janelas_diarias(
        series,
        anos_origem=(2024,),
        seq_len=336,
        pred_len=72,
        particao="teste_2024",
        limite_origens_por_localidade=limite,
    )
    escalas_selecao = ajustar_escalas_horarias(
        series,
        primeiro_ano=2019,
        fim_local_exclusivo="2023-01-01",
        nome_ajuste="treino_para_validacao",
    )
    escalas_refit = ajustar_escalas_horarias(
        series,
        primeiro_ano=2019,
        fim_local_exclusivo="2024-01-01",
        nome_ajuste="refit_para_teste",
    )
    cache = pasta_tarefa / "cache" / "dilatedrnn_seed42.npz"
    if retomar and cache.is_file():
        bruto_val, bruto_teste, epocas, historico = _carregar_cache_modelo(cache)
    else:
        x_treino, y_treino = treino.normalizar(escalas_selecao)
        x_val, y_val = validacao.normalizar(escalas_selecao)
        x_refit, y_refit = refit.normalizar(escalas_refit)
        x_teste, _ = teste.normalizar(escalas_refit)
        selecionador = criar_modelo_neural(
            "DilatedRNN",
            tarefa=tarefa,
            configuracao=configuracao,
            num_localidades=len(series),
            semente=42,
        )
        selecionador, epocas, hist_selecao = treinar_rede(
            selecionador,
            x_treino=x_treino,
            y_treino=y_treino,
            ids_treino=treino.localidade_id,
            batch_size=configuracao.batch_size_diario,
            taxa_aprendizado=configuracao.taxa_aprendizado,
            peso_decay=configuracao.peso_decay,
            semente=42,
            threads_torch=configuracao.threads_torch,
            max_epocas=(
                configuracao.epocas_smoke
                if configuracao.modo_execucao == "smoke"
                else configuracao.max_epocas_diario
            ),
            paciencia=configuracao.paciencia_diario,
            x_validacao=x_val,
            y_validacao=y_val,
            ids_validacao=validacao.localidade_id,
        )
        previsto_val = prever_rede(
            selecionador,
            x_val,
            validacao.localidade_id,
            batch_size=configuracao.batch_size_diario,
        )
        del selecionador
        gc.collect()
        final = criar_modelo_neural(
            "DilatedRNN",
            tarefa=tarefa,
            configuracao=configuracao,
            num_localidades=len(series),
            semente=42,
        )
        final, _, hist_refit = treinar_rede(
            final,
            x_treino=x_refit,
            y_treino=y_refit,
            ids_treino=refit.localidade_id,
            batch_size=configuracao.batch_size_diario,
            taxa_aprendizado=configuracao.taxa_aprendizado,
            peso_decay=configuracao.peso_decay,
            semente=42,
            threads_torch=configuracao.threads_torch,
            max_epocas=epocas,
            paciencia=configuracao.paciencia_diario,
            epocas_fixas=epocas,
        )
        previsto_teste = prever_rede(
            final,
            x_teste,
            teste.localidade_id,
            batch_size=configuracao.batch_size_diario,
        )
        bruto_val = validacao.inverter(previsto_val, escalas_selecao)
        bruto_teste = teste.inverter(previsto_teste, escalas_refit)
        historico = [
            {"fase": "selecao_epocas", "modelo": "DilatedRNN", "semente": 42, **h}
            for h in hist_selecao
        ] + [
            {"fase": "refit_epocas_fixas", "modelo": "DilatedRNN", "semente": 42, **h}
            for h in hist_refit
        ]
        salvar_torch_atomico(
            {
                "state_dict": final.state_dict(),
                "classe": type(final).__name__,
                "modelo": "DilatedRNN",
                "semente": 42,
                "epocas_refit": epocas,
                "tarefa": asdict(tarefa),
                "configuracao": asdict(configuracao),
            },
            pasta_tarefa / "modelos" / "dilatedrnn_seed42_refit.pt",
        )
        salvar_npz_atomico(
            cache,
            previsao_validacao_bruta=bruto_val,
            previsao_teste_bruta=bruto_teste,
            epocas_selecionadas=np.asarray(epocas, dtype=np.int64),
            historico_json=np.asarray(
                json.dumps(historico, ensure_ascii=False, sort_keys=True)
            ),
        )
        del final, x_treino, y_treino, x_val, y_val, x_refit, y_refit, x_teste
        gc.collect()
    elevacao_val = calcular_elevacao_solar(
        validacao,
        series,
        minutos_centro_intervalo=30,
    )
    elevacao_teste = calcular_elevacao_solar(
        teste,
        series,
        minutos_centro_intervalo=30,
    )
    pos_val = aplicar_pos_processamento_fisico(bruto_val, elevacao_val)
    pos_teste = aplicar_pos_processamento_fisico(bruto_teste, elevacao_teste)
    tabela_val = anexar_dilated_a_previsoes_oficiais(
        caminho_oficial=fonte_oficial / "previsoes_validacao.csv.gz",
        janelas=validacao,
        previsao_bruta=bruto_val,
        previsao_pos=pos_val,
    )
    tabela_teste = anexar_dilated_a_previsoes_oficiais(
        caminho_oficial=fonte_oficial / "previsoes_teste.csv.gz",
        janelas=teste,
        previsao_bruta=bruto_teste,
        previsao_pos=pos_teste,
    )
    local_val, macro_val = calcular_metricas_horarias_extensao(
        tabela_val,
        particao="validacao_2023",
    )
    local_teste, macro_teste = calcular_metricas_horarias_extensao(
        tabela_teste,
        particao="teste_2024",
    )
    locais = pd.concat([local_val, local_teste], ignore_index=True)
    macro = pd.concat([macro_val, macro_teste], ignore_index=True)
    pareada, resumo_pareado = comparacao_pareada_horaria(locais)
    salvar_csv_atomico(tabela_val, pasta_tarefa / "previsoes_validacao.csv.gz")
    salvar_csv_atomico(tabela_teste, pasta_tarefa / "previsoes_teste.csv.gz")
    salvar_csv_atomico(locais, pasta_tarefa / "metricas_por_localidade.csv")
    salvar_csv_atomico(macro, pasta_tarefa / "metricas_macro.csv")
    salvar_csv_atomico(pareada, pasta_tarefa / "comparacao_pareada_localidades.csv")
    salvar_csv_atomico(resumo_pareado, pasta_tarefa / "comparacao_pareada_resumo.csv")
    salvar_csv_atomico(pd.DataFrame(historico), pasta_tarefa / "historico_treinamento.csv")
    salvar_csv_atomico(
        pd.DataFrame(
            [
                {
                    "tarefa": tarefa.slug,
                    "modelo": "DilatedRNN",
                    "semente": 42,
                    "epocas_selecionadas_em_2023": epocas,
                }
            ]
        ),
        pasta_tarefa / "epocas_selecionadas.csv",
    )
    salvar_csv_atomico(
        pd.concat([escalas_selecao, escalas_refit], ignore_index=True),
        pasta_tarefa / "escalas_minmax_pre_corte.csv",
    )
    protocolo_oficial = pd.read_csv(fonte_oficial / "protocolo_temporal.csv")
    protocolo_oficial["extensao_modelo"] = "DilatedRNN_direta"
    protocolo_oficial["extensao_semente"] = 42
    protocolo_oficial["fonte_oficial_somente_leitura"] = str(fonte_oficial)
    protocolo_oficial = protocolo_oficial.loc[
        protocolo_oficial["Localidade"].isin([s.localidade for s in series])
    ]
    salvar_csv_atomico(protocolo_oficial, pasta_tarefa / "protocolo_temporal.csv")
    salvar_json_atomico(
        {
            "tarefa": asdict(tarefa),
            "modelo_adicionado": "DilatedRNN",
            "semente": 42,
            "dilatacoes": list(configuracao.dilated_dilatacoes),
            "unidades_por_camada": configuracao.dilated_unidades,
            "unidades_densas": configuracao.dilated_unidades_densas,
            "embedding_localidade": configuracao.embedding_localidade,
            "dropout": configuracao.dilated_dropout,
            "batch_size": configuracao.batch_size_diario,
            "max_epocas": configuracao.max_epocas_diario,
            "paciencia": configuracao.paciencia_diario,
            "taxa_aprendizado": configuracao.taxa_aprendizado,
            "pos_processamento": (
                "piso_zero_e_mascara_noturna_identicos_ao_protocolo_oficial"
            ),
            "modelos_existentes": "lidos_dos_artefatos_oficiais_sem_retreino",
            "metrica_primaria": "macro_MAE_por_localidade",
        },
        pasta_tarefa / "hiperparametros_e_metodo.json",
    )
    salvar_json_atomico(
        {
            "pasta_oficial_somente_leitura": str(fonte_oficial),
            "sha256_manifesto_oficial": sha256_arquivo(
                fonte_oficial / "manifesto_artefatos.json"
            ),
            "arquivos_oficiais_vinculados": {
                str(caminho.relative_to(fonte_oficial)): contrato[
                    "entradas_sha256"
                ][str(caminho.resolve())]
                for caminho in arquivos_oficiais
            },
        },
        pasta_tarefa / "vinculo_artefatos_oficiais.json",
    )
    for caminho in arquivos_oficiais:
        esperado_hash = contrato["entradas_sha256"][str(caminho.resolve())]
        if sha256_arquivo(caminho) != esperado_hash:
            raise RuntimeError("Um artefato horario oficial foi alterado durante a extensao.")
    resumo = {
        "tarefa": tarefa.slug,
        "etapa": "concluida",
        "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
        "modo_execucao": configuracao.modo_execucao,
        "resultado_publicavel": configuracao.modo_execucao == "completa",
        "resultado_smoke_nao_publicavel": configuracao.modo_execucao == "smoke",
        "modelo_adicionado": "DilatedRNN",
        "semente": 42,
        "fonte_oficial_somente_leitura": str(fonte_oficial),
        "N_localidades": len(series),
        "sha256_contrato": contrato["sha256_contrato"],
    }
    salvar_json_atomico(resumo, pasta_tarefa / "status_execucao.json")
    salvar_json_atomico(
        gerar_manifesto_artefatos(pasta_tarefa),
        pasta_tarefa / "manifesto_artefatos.json",
    )
    return resumo


def _normalizar_tarefas(tarefas: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(tarefas, str):
        itens = [item.strip() for item in tarefas.split(",") if item.strip()]
    else:
        itens = [str(item).strip() for item in tarefas if str(item).strip()]
    expandidas: list[str] = []
    for item in itens:
        if item == "all":
            expandidas.extend(
                ["daily_30", "monthly_1", "monthly_6", "hourly_72_extension"]
            )
        else:
            expandidas.append(item)
    unicas = tuple(dict.fromkeys(expandidas))
    permitidas = set(TAREFAS_CANONICAS) | {"hourly_72_extension"}
    invalidas = sorted(set(unicas) - permitidas)
    if not unicas or invalidas:
        raise ValueError(f"Tarefas invalidas: {invalidas or itens}.")
    return unicas


def executar_avaliacao_multirresolucao(
    *,
    tarefas: str | Iterable[str] = "all",
    configuracao: ConfiguracaoMultirresolucao | None = None,
    pasta_saida: str | Path | None = None,
    pasta_dados_diarios: str | Path | None = None,
    pasta_dados_horarios: str | Path | None = None,
    pasta_oficial_horaria: str | Path | None = None,
    retomar: bool = True,
) -> list[dict[str, object]]:
    """Executa as tarefas selecionadas sem iniciar trabalho por importacao."""

    config = configuracao or ConfiguracaoMultirresolucao()
    selecionadas = _normalizar_tarefas(tarefas)
    saida = (
        Path(pasta_saida)
        if pasta_saida is not None
        else PASTA_RESULTADOS / "avaliacao_multirresolucao"
    )
    wrapper = Path(__file__).resolve().parents[1] / "executar_avaliacao_multirresolucao.py"
    extras = (wrapper,) if wrapper.is_file() else ()
    precisa_diario = any(nome in TAREFAS_CANONICAS for nome in selecionadas)
    if precisa_diario:
        series_diarias, auditoria = carregar_series_diarias(pasta_dados_diarios)
    else:
        series_diarias, auditoria = (), pd.DataFrame()
    resumos: list[dict[str, object]] = []
    for nome in selecionadas:
        if nome == "hourly_72_extension":
            resumo = executar_extensao_horaria(
                configuracao=config,
                pasta_saida=saida,
                pasta_dados_horarios=pasta_dados_horarios,
                pasta_oficial=pasta_oficial_horaria,
                retomar=retomar,
                arquivos_codigo_extras=extras,
            )
        else:
            resumo = executar_tarefa_diaria_mensal(
                TAREFAS_CANONICAS[nome],
                series_diarias=series_diarias,
                auditoria_entradas=auditoria,
                configuracao=config,
                pasta_saida=saida,
                retomar=retomar,
                arquivos_codigo_extras=extras,
            )
        resumos.append(resumo)
    salvar_json_atomico(
        {
            "etapa": "concluida",
            "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
            "modo_execucao": config.modo_execucao,
            "tarefas": list(selecionadas),
            "resultados": resumos,
        },
        saida / "resumo_execucao.json",
    )
    return resumos


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Avaliacao pareada TimesNet/DilatedRNN diaria, mensal e horaria."
        )
    )
    parser.add_argument(
        "--tarefas",
        default="all",
        help=(
            "Lista separada por virgulas: daily_30, monthly_1, monthly_6, "
            "hourly_72_extension ou all."
        ),
    )
    parser.add_argument(
        "--modo",
        choices=("smoke", "completa"),
        default="smoke",
        help="Smoke nao e publicavel; completa executa o protocolo cientifico.",
    )
    parser.add_argument(
        "--sementes",
        default=",".join(map(str, SEMENTES_CANONICAS)),
        help="Sementes dos modelos aprendidos, separadas por virgula.",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=PASTA_RESULTADOS / "avaliacao_multirresolucao",
    )
    parser.add_argument("--dados-diarios", type=Path, default=None)
    parser.add_argument("--dados-horarios", type=Path, default=None)
    parser.add_argument("--oficial-horario", type=Path, default=None)
    parser.add_argument(
        "--retomar",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reutiliza apenas caches cujo contrato completo coincide.",
    )
    parser.add_argument(
        "--confirmar-execucao-longa",
        action="store_true",
        help="Obrigatorio no modo completa.",
    )
    parser.add_argument(
        "--listar-tarefas",
        action="store_true",
        help="Lista as tarefas e termina sem executar.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    if args.listar_tarefas:
        for nome in ("daily_30", "monthly_1", "monthly_6", "hourly_72_extension"):
            tarefa = (
                TAREFA_HORARIA_EXTENSAO
                if nome == "hourly_72_extension"
                else TAREFAS_CANONICAS[nome]
            )
            rotulo = "exploratoria" if tarefa.exploratoria else "principal"
            print(
                f"{nome}: {tarefa.seq_len}->{tarefa.pred_len}; "
                f"horizontes={tarefa.horizontes}; {rotulo}"
            )
        return 0
    if args.modo == "completa" and not args.confirmar_execucao_longa:
        parser.error(
            "O modo completa exige --confirmar-execucao-longa; "
            "o comando pode consumir dezenas de horas de CPU."
        )
    try:
        sementes = tuple(
            int(item.strip())
            for item in args.sementes.split(",")
            if item.strip()
        )
        config = ConfiguracaoMultirresolucao(
            modo_execucao=args.modo,
            sementes=sementes,
        )
        executar_avaliacao_multirresolucao(
            tarefas=args.tarefas,
            configuracao=config,
            pasta_saida=args.saida,
            pasta_dados_diarios=args.dados_diarios,
            pasta_dados_horarios=args.dados_horarios,
            pasta_oficial_horaria=args.oficial_horario,
            retomar=args.retomar,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as erro:
        parser.error(str(erro))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
