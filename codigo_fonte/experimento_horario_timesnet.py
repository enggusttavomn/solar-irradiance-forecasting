"""Protocolo horário multistep para previsão de GHI com TimesNet.

O protocolo principal usa as dez localidades do projeto, 336 horas de
contexto e uma única previsão direta de 72 horas, avaliada nos prefixos de
24, 48 e 72 horas. As origens são diárias, sempre às 00:00 no horário local
fixo informado pela NSRDB (UTC somado a ``timezone_nsrdb``; não se aplica
horário de verão).

Há dois ajustes completamente separados:

* treino 2019--2022 e validação em 2023, usados para escolher somente a
  quantidade de épocas das redes neurais;
* refit do zero em 2019--2023 e avaliação retrospectiva, sem novo ajuste, nas
  origens de 2024.

Cada escala min--max é estimada por localidade e apenas com observações
anteriores ao respectivo corte. A inversão da escala ocorre antes do
pós-processamento físico. Tanto a previsão bruta em W/m² quanto a previsão
final são preservadas: primeiro valores negativos são truncados em zero e,
depois, horas cuja elevação solar no centro do intervalo é menor ou igual a
zero são zeradas com ``pvlib``.

O modo ``smoke`` reduz localidades, origens, árvores e épocas. Ele existe
somente para verificar o caminho de código e seus artefatos; seus números não
constituem resultados científicos.
"""

from __future__ import annotations

import argparse
import copy
import gc
import hashlib
import json
import math
import os
import platform
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache-tcc")

import joblib
import numpy as np
import pandas as pd
import pvlib
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader, TensorDataset

from codigo_fonte.configuracao import PASTA_RESULTADOS
from codigo_fonte.dados_horarios_nsrdb import (
    PASTA_HORARIA_PADRAO,
    carregar_dados_horarios,
)
from codigo_fonte.localidades_ev import LOCALIDADES_EV
from codigo_fonte.timesnet_horario import TimesNetHorario


MODELOS = (
    "Persistência",
    "Sazonal Ingênuo",
    "XGBoost",
    "LSTM",
    "TimesNet",
)
SLUG_MODELOS = {
    "Persistência": "persistencia",
    "Sazonal Ingênuo": "sazonal_ingenuo",
    "XGBoost": "xgboost",
    "LSTM": "lstm",
    "TimesNet": "timesnet",
}
COLUNAS_DADOS = {
    "timestamp_utc",
    "localidade",
    "ghi",
    "timezone_nsrdb",
    "lat_grade_nsrdb",
    "lon_grade_nsrdb",
}


def _inteiro_positivo(valor: object, nome: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, (int, np.integer)):
        raise ValueError(f"{nome} deve ser um inteiro positivo.")
    convertido = int(valor)
    if convertido < 1:
        raise ValueError(f"{nome} deve ser um inteiro positivo.")
    return convertido


@dataclass(frozen=True)
class ConfiguracaoExperimentoHorario:
    """Configuração reproduzível do protocolo horário.

    Os valores científicos são os padrões. Parâmetros menores podem ser
    informados em testes unitários, mas uma execução ``completa`` exige
    explicitamente 336/72 horas, horizontes 24/48/72 e os anos canônicos.
    """

    seq_len: int = 336
    pred_len: int = 72
    horizontes: tuple[int, ...] = (24, 48, 72)
    anos_treino: tuple[int, ...] = (2019, 2020, 2021, 2022)
    ano_validacao: int = 2023
    ano_teste: int = 2024
    semente: int = 42
    modo_execucao: str = "completa"

    batch_size: int = 128
    taxa_aprendizado: float = 1e-3
    max_epocas: int = 30
    paciencia: int = 5
    peso_decay: float = 1e-5

    lstm_ocultos: int = 32
    lstm_camadas: int = 1
    embedding_localidade_lstm: int = 8

    timesnet_d_model: int = 8
    timesnet_d_ff: int = 16
    timesnet_blocos: int = 1
    timesnet_top_k: int = 3
    timesnet_kernels: int = 2
    timesnet_dropout: float = 0.1

    xgb_estimadores: int = 150
    # Profundidade 3 mantém o histograma vetorial de 72 saídas dentro da
    # memória disponível (2 vCPU/7,8 GiB) e regulariza a referência tabular.
    xgb_profundidade: int = 3
    xgb_taxa_aprendizado: float = 0.05
    xgb_subsample: float = 0.8
    xgb_colsample: float = 0.8
    xgb_n_jobs: int = 1

    minutos_centro_intervalo: int = 30
    limite_localidades_smoke: int = 2
    limite_origens_smoke: int = 3
    epocas_smoke: int = 1
    xgb_estimadores_smoke: int = 2
    threads_torch: int = 1

    def __post_init__(self) -> None:
        if self.modo_execucao not in {"completa", "smoke"}:
            raise ValueError("modo_execucao deve ser 'completa' ou 'smoke'.")
        seq_len = _inteiro_positivo(self.seq_len, "seq_len")
        pred_len = _inteiro_positivo(self.pred_len, "pred_len")
        if seq_len < 24:
            raise ValueError("seq_len deve conter pelo menos 24 horas.")
        horizontes = tuple(
            _inteiro_positivo(valor, "horizontes") for valor in self.horizontes
        )
        if (
            not horizontes
            or tuple(sorted(set(horizontes))) != horizontes
            or horizontes[-1] != pred_len
        ):
            raise ValueError(
                "horizontes deve ser crescente, único e terminar em pred_len."
            )
        anos = tuple(int(ano) for ano in self.anos_treino)
        if (
            not anos
            or tuple(sorted(set(anos))) != anos
            or any(b - a != 1 for a, b in zip(anos, anos[1:]))
            or self.ano_validacao != anos[-1] + 1
            or self.ano_teste != self.ano_validacao + 1
        ):
            raise ValueError(
                "Treino, validação e teste devem formar anos consecutivos."
            )
        if (
            isinstance(self.semente, bool)
            or not isinstance(self.semente, (int, np.integer))
            or not 0 <= int(self.semente) < 2**32
        ):
            raise ValueError("semente deve ser um inteiro em [0, 2**32).")

        inteiros = (
            "batch_size",
            "max_epocas",
            "paciencia",
            "lstm_ocultos",
            "lstm_camadas",
            "embedding_localidade_lstm",
            "timesnet_d_model",
            "timesnet_d_ff",
            "timesnet_blocos",
            "timesnet_top_k",
            "timesnet_kernels",
            "xgb_estimadores",
            "xgb_profundidade",
            "xgb_n_jobs",
            "limite_localidades_smoke",
            "limite_origens_smoke",
            "epocas_smoke",
            "xgb_estimadores_smoke",
            "threads_torch",
        )
        for nome in inteiros:
            _inteiro_positivo(getattr(self, nome), nome)
        if self.timesnet_top_k > seq_len // 2:
            raise ValueError("timesnet_top_k excede as frequências disponíveis.")
        if not 0.0 < float(self.taxa_aprendizado):
            raise ValueError("taxa_aprendizado deve ser positiva.")
        if not 0.0 <= float(self.peso_decay):
            raise ValueError("peso_decay não pode ser negativo.")
        for nome in ("xgb_taxa_aprendizado", "xgb_subsample", "xgb_colsample"):
            valor = float(getattr(self, nome))
            if nome == "xgb_taxa_aprendizado":
                valido = valor > 0
            else:
                valido = 0 < valor <= 1
            if not valido or not math.isfinite(valor):
                raise ValueError(f"{nome} possui valor inválido.")
        if not 0 <= int(self.minutos_centro_intervalo) < 60:
            raise ValueError(
                "minutos_centro_intervalo deve pertencer a [0, 60)."
            )
        if not 0 <= float(self.timesnet_dropout) < 1:
            raise ValueError("timesnet_dropout deve pertencer a [0, 1).")

        if self.modo_execucao == "completa":
            esperado = {
                "seq_len": 336,
                "pred_len": 72,
                "horizontes": (24, 48, 72),
                "anos_treino": (2019, 2020, 2021, 2022),
                "ano_validacao": 2023,
                "ano_teste": 2024,
            }
            divergentes = [
                nome for nome, valor in esperado.items() if getattr(self, nome) != valor
            ]
            if divergentes:
                raise ValueError(
                    "Execução completa exige o protocolo canônico; divergências: "
                    + ", ".join(divergentes)
                )

    @property
    def epocas_efetivas(self) -> int:
        return self.epocas_smoke if self.modo_execucao == "smoke" else self.max_epocas

    @property
    def estimadores_xgb_efetivos(self) -> int:
        if self.modo_execucao == "smoke":
            return self.xgb_estimadores_smoke
        return self.xgb_estimadores


@dataclass(frozen=True)
class SerieLocalidade:
    """Série contínua e metadados fixos de uma localidade."""

    localidade: str
    localidade_id: int
    timestamp_utc: pd.DatetimeIndex
    timestamp_local: pd.DatetimeIndex
    ghi: np.ndarray
    offset_horas: float
    latitude: float
    longitude: float


@dataclass(frozen=True)
class JanelasHorarias:
    """Matrizes alinhadas de contexto e alvo para origens diárias."""

    x_bruto: np.ndarray
    y_bruto: np.ndarray
    localidade_id: np.ndarray
    localidade: np.ndarray
    origem_utc: pd.DatetimeIndex
    origem_local: pd.DatetimeIndex
    seq_len: int
    pred_len: int
    particao: str

    def __post_init__(self) -> None:
        n = len(self.x_bruto)
        if self.x_bruto.shape != (n, self.seq_len):
            raise ValueError("x_bruto possui forma incompatível.")
        if self.y_bruto.shape != (n, self.pred_len):
            raise ValueError("y_bruto possui forma incompatível.")
        if (
            self.localidade_id.shape != (n,)
            or self.localidade.shape != (n,)
            or len(self.origem_utc) != n
            or len(self.origem_local) != n
        ):
            raise ValueError("Metadados das janelas possuem tamanhos incompatíveis.")
        if n < 1:
            raise ValueError(f"A partição {self.particao} não contém janelas.")
        if not np.isfinite(self.x_bruto).all() or not np.isfinite(
            self.y_bruto
        ).all():
            raise ValueError("As janelas contêm valores não finitos.")

    def normalizar(
        self,
        escalas: pd.DataFrame,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Aplica a escala da localidade sem truncar extrapolações."""

        por_id = escalas.set_index("localidade_id")
        ids = self.localidade_id.astype(int)
        if not set(ids).issubset(por_id.index):
            raise ValueError("Há localidade sem escala min--max ajustada.")
        minimos = por_id.loc[ids, "minimo_treino_wm2"].to_numpy(dtype=np.float32)
        amplitudes = por_id.loc[ids, "amplitude_escala_wm2"].to_numpy(
            dtype=np.float32
        )
        x = (self.x_bruto.astype(np.float32) - minimos[:, None]) / amplitudes[
            :, None
        ]
        y = (self.y_bruto.astype(np.float32) - minimos[:, None]) / amplitudes[
            :, None
        ]
        return x.astype(np.float32, copy=False), y.astype(np.float32, copy=False)

    def inverter(
        self,
        previsao_normalizada: np.ndarray,
        escalas: pd.DataFrame,
    ) -> np.ndarray:
        """Inverte min--max por localidade, ainda sem pós-processamento."""

        previsao = np.asarray(previsao_normalizada, dtype=np.float64)
        if previsao.shape != (len(self.x_bruto), self.pred_len):
            raise ValueError("Previsão normalizada possui forma incompatível.")
        por_id = escalas.set_index("localidade_id")
        ids = self.localidade_id.astype(int)
        minimos = por_id.loc[ids, "minimo_treino_wm2"].to_numpy(dtype=float)
        amplitudes = por_id.loc[ids, "amplitude_escala_wm2"].to_numpy(dtype=float)
        return previsao * amplitudes[:, None] + minimos[:, None]


def _valor_unico(grupo: pd.DataFrame, coluna: str, localidade: str) -> float:
    valores = pd.to_numeric(grupo[coluna], errors="raise").drop_duplicates()
    if len(valores) != 1 or not np.isfinite(valores.iloc[0]):
        raise ValueError(f"{coluna} deve ser fixa em {localidade}.")
    return float(valores.iloc[0])


def preparar_series_localidades(
    dados: pd.DataFrame,
    configuracao: ConfiguracaoExperimentoHorario,
) -> tuple[SerieLocalidade, ...]:
    """Valida os dados horários e converte UTC para horário local fixo."""

    faltantes = sorted(COLUNAS_DADOS - set(dados.columns))
    if faltantes:
        raise ValueError(f"Colunas horárias ausentes: {', '.join(faltantes)}.")
    quadro = dados.copy()
    quadro["timestamp_utc"] = pd.to_datetime(
        quadro["timestamp_utc"], utc=True, errors="raise"
    )
    quadro["ghi"] = pd.to_numeric(quadro["ghi"], errors="raise")
    if not np.isfinite(quadro["ghi"]).all() or (quadro["ghi"] < 0).any():
        raise ValueError("GHI deve ser finita e fisicamente não negativa.")

    nomes = sorted(quadro["localidade"].astype(str).unique())
    esperados = sorted(item["nome"] for item in LOCALIDADES_EV)
    if configuracao.modo_execucao == "completa":
        if nomes != esperados:
            ausentes = sorted(set(esperados) - set(nomes))
            extras = sorted(set(nomes) - set(esperados))
            raise ValueError(
                "A execução completa exige as dez localidades cadastradas "
                f"(ausentes={ausentes}, extras={extras})."
            )
        selecionados = nomes
    else:
        selecionados = nomes[: configuracao.limite_localidades_smoke]
        if not selecionados:
            raise ValueError("O modo smoke requer pelo menos uma localidade.")

    series: list[SerieLocalidade] = []
    for localidade_id, localidade in enumerate(selecionados):
        grupo = (
            quadro.loc[quadro["localidade"].astype(str) == localidade]
            .sort_values("timestamp_utc")
            .reset_index(drop=True)
        )
        if grupo["timestamp_utc"].duplicated().any():
            raise ValueError(f"Há timestamps duplicados em {localidade}.")
        deltas = grupo["timestamp_utc"].diff().dropna()
        if not (deltas == pd.Timedelta(hours=1)).all():
            raise ValueError(f"A série horária é descontínua em {localidade}.")
        offset = _valor_unico(grupo, "timezone_nsrdb", localidade)
        latitude = _valor_unico(grupo, "lat_grade_nsrdb", localidade)
        longitude = _valor_unico(grupo, "lon_grade_nsrdb", localidade)
        if not -12 <= offset <= 14:
            raise ValueError(f"timezone_nsrdb fora do intervalo em {localidade}.")
        utc = pd.DatetimeIndex(grupo["timestamp_utc"])
        local = (utc + pd.to_timedelta(offset, unit="h")).tz_localize(None)
        ghi = grupo["ghi"].to_numpy(dtype=np.float32)
        series.append(
            SerieLocalidade(
                localidade=localidade,
                localidade_id=localidade_id,
                timestamp_utc=utc,
                timestamp_local=local,
                ghi=ghi,
                offset_horas=offset,
                latitude=latitude,
                longitude=longitude,
            )
        )
    return tuple(series)


def ajustar_escalas_pre_corte(
    series: Sequence[SerieLocalidade],
    *,
    primeiro_ano: int,
    fim_local_exclusivo: pd.Timestamp | str,
    nome_ajuste: str,
) -> pd.DataFrame:
    """Ajusta min--max por localidade usando apenas horas pré-corte."""

    fim = pd.Timestamp(fim_local_exclusivo)
    if fim.tz is not None:
        raise ValueError("fim_local_exclusivo deve representar horário local ingênuo.")
    inicio = pd.Timestamp(f"{int(primeiro_ano)}-01-01")
    linhas: list[dict[str, object]] = []
    for serie in series:
        mascara = (serie.timestamp_local >= inicio) & (serie.timestamp_local < fim)
        valores = serie.ghi[mascara]
        if len(valores) < 1:
            raise ValueError(f"Sem observações pré-corte em {serie.localidade}.")
        minimo = float(np.min(valores))
        maximo = float(np.max(valores))
        amplitude_real = maximo - minimo
        # Série constante é válida em testes/smoke. A amplitude unitária evita
        # divisão por zero sem usar qualquer observação posterior ao corte.
        amplitude = amplitude_real if amplitude_real > 0 else 1.0
        linhas.append(
            {
                "ajuste": nome_ajuste,
                "localidade": serie.localidade,
                "localidade_id": serie.localidade_id,
                "inicio_local_inclusivo": inicio.isoformat(),
                "fim_local_exclusivo": fim.isoformat(),
                "N_horas_ajuste": int(len(valores)),
                "minimo_treino_wm2": minimo,
                "maximo_treino_wm2": maximo,
                "amplitude_real_wm2": amplitude_real,
                "amplitude_escala_wm2": amplitude,
            }
        )
    return pd.DataFrame(linhas)


def _limitar_posicoes_smoke(posicoes: np.ndarray, limite: int) -> np.ndarray:
    if len(posicoes) <= limite:
        return posicoes
    indices = np.linspace(0, len(posicoes) - 1, num=limite, dtype=int)
    return posicoes[np.unique(indices)]


def construir_janelas_diarias(
    series: Sequence[SerieLocalidade],
    *,
    anos_origem: Iterable[int],
    seq_len: int,
    pred_len: int,
    particao: str,
    limite_origens_por_localidade: int | None = None,
) -> JanelasHorarias:
    """Constrói janelas cuja origem é 00:00 local e cujo alvo não cruza o corte."""

    anos = tuple(sorted({int(ano) for ano in anos_origem}))
    if not anos:
        raise ValueError("anos_origem não pode ser vazio.")
    if any(b - a != 1 for a, b in zip(anos, anos[1:])):
        raise ValueError("anos_origem deve ser consecutivo.")
    inicio = pd.Timestamp(f"{anos[0]}-01-01")
    fim = pd.Timestamp(f"{anos[-1] + 1}-01-01")

    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    ids: list[np.ndarray] = []
    nomes: list[np.ndarray] = []
    origens_utc: list[pd.DatetimeIndex] = []
    origens_local: list[pd.DatetimeIndex] = []
    for serie in series:
        local = serie.timestamp_local
        candidato = (
            (local >= inicio)
            & (local < fim)
            & (local.hour == 0)
            & (local.minute == 0)
            & (local.second == 0)
        )
        posicoes = np.flatnonzero(candidato)
        completas = posicoes[
            (posicoes >= seq_len)
            & (posicoes + pred_len <= len(serie.ghi))
            & ((local[posicoes] + pd.to_timedelta(pred_len, unit="h")) <= fim)
        ]
        if limite_origens_por_localidade is not None:
            completas = _limitar_posicoes_smoke(
                completas, _inteiro_positivo(limite_origens_por_localidade, "limite")
            )
        if len(completas) < 1:
            raise ValueError(
                f"Não há origem diária completa em {serie.localidade}/{particao}."
            )
        xs.append(
            np.stack(
                [serie.ghi[posicao - seq_len : posicao] for posicao in completas]
            )
        )
        ys.append(
            np.stack(
                [serie.ghi[posicao : posicao + pred_len] for posicao in completas]
            )
        )
        ids.append(np.full(len(completas), serie.localidade_id, dtype=np.int64))
        nomes.append(np.full(len(completas), serie.localidade, dtype=object))
        origens_utc.append(serie.timestamp_utc[completas])
        origens_local.append(serie.timestamp_local[completas])

    x = np.concatenate(xs).astype(np.float32, copy=False)
    y = np.concatenate(ys).astype(np.float32, copy=False)
    localidade_id = np.concatenate(ids)
    localidade = np.concatenate(nomes)
    utc = pd.DatetimeIndex(np.concatenate([item.to_numpy() for item in origens_utc]))
    local = pd.DatetimeIndex(
        np.concatenate([item.to_numpy() for item in origens_local])
    )
    ordem = np.lexsort((localidade_id, utc.asi8))
    return JanelasHorarias(
        x_bruto=x[ordem],
        y_bruto=y[ordem],
        localidade_id=localidade_id[ordem],
        localidade=localidade[ordem],
        origem_utc=utc[ordem],
        origem_local=local[ordem],
        seq_len=seq_len,
        pred_len=pred_len,
        particao=particao,
    )


def prever_persistencia_diaria(janelas: JanelasHorarias) -> np.ndarray:
    """Repete ciclicamente as últimas 24 horas observadas."""

    if janelas.seq_len < 24:
        raise ValueError("Persistência diária requer pelo menos 24 horas.")
    repeticoes = math.ceil(janelas.pred_len / 24)
    return np.tile(janelas.x_bruto[:, -24:], (1, repeticoes))[
        :, : janelas.pred_len
    ].astype(float)


def _hora_ano_anterior(instante: pd.Timestamp) -> pd.Timestamp:
    if instante.month == 2 and instante.day == 29:
        return instante.replace(year=instante.year - 1, day=28)
    return instante.replace(year=instante.year - 1)


def prever_sazonal_ingenuo_anual(
    janelas: JanelasHorarias,
    series: Sequence[SerieLocalidade],
) -> np.ndarray:
    """Busca a mesma hora local no ano anterior (29/2 mapeado para 28/2)."""

    por_id = {serie.localidade_id: serie for serie in series}
    resultado = np.empty((len(janelas.x_bruto), janelas.pred_len), dtype=float)
    passos = pd.to_timedelta(np.arange(janelas.pred_len), unit="h")
    for linha, (localidade_id, origem) in enumerate(
        zip(janelas.localidade_id, janelas.origem_local, strict=True)
    ):
        serie = por_id[int(localidade_id)]
        alvos = pd.DatetimeIndex(origem + passos)
        referencias = pd.DatetimeIndex(
            [_hora_ano_anterior(pd.Timestamp(instante)) for instante in alvos]
        )
        if not bool((referencias < origem).all()):
            raise AssertionError("Baseline sazonal tentou acessar hora não causal.")
        posicoes = serie.timestamp_local.get_indexer(referencias)
        if (posicoes < 0).any():
            faltante = referencias[int(np.flatnonzero(posicoes < 0)[0])]
            raise ValueError(
                f"Hora sazonal {faltante} ausente em {serie.localidade}."
            )
        resultado[linha] = serie.ghi[posicoes]
    return resultado


class LSTMEncoderDireto(nn.Module):
    """Encoder LSTM global cuja cabeça produz todo o horizonte de uma vez."""

    def __init__(
        self,
        *,
        seq_len: int,
        pred_len: int,
        ocultos: int,
        camadas: int,
        num_localidades: int,
        dimensao_embedding_localidade: int,
    ) -> None:
        super().__init__()
        self.seq_len = _inteiro_positivo(seq_len, "seq_len")
        self.pred_len = _inteiro_positivo(pred_len, "pred_len")
        self.num_localidades = _inteiro_positivo(
            num_localidades, "num_localidades"
        )
        ocultos = _inteiro_positivo(ocultos, "ocultos")
        camadas = _inteiro_positivo(camadas, "camadas")
        dimensao_embedding_localidade = _inteiro_positivo(
            dimensao_embedding_localidade,
            "dimensao_embedding_localidade",
        )
        self.encoder = nn.LSTM(
            input_size=1,
            hidden_size=ocultos,
            num_layers=camadas,
            batch_first=True,
        )
        self.embedding_localidade = nn.Embedding(
            self.num_localidades, dimensao_embedding_localidade
        )
        self.cabeca = nn.Linear(
            ocultos + dimensao_embedding_localidade, self.pred_len
        )

    def forward(self, x: Tensor, ids_localidade: Tensor) -> Tensor:
        if x.ndim == 2:
            x = x.unsqueeze(-1)
        if x.ndim != 3 or x.shape[1:] != (self.seq_len, 1):
            raise ValueError("x deve ter forma (lote, seq_len) ou (lote, seq_len, 1).")
        if ids_localidade.ndim != 1 or len(ids_localidade) != len(x):
            raise ValueError("ids_localidade deve ter forma (lote,).")
        ids = ids_localidade.to(device=x.device, dtype=torch.long)
        if bool((ids < 0).any()) or bool((ids >= self.num_localidades).any()):
            raise ValueError("ids_localidade contém índice fora do intervalo.")
        _, (estado, _) = self.encoder(x)
        representacao = torch.cat(
            (estado[-1], self.embedding_localidade(ids)), dim=1
        )
        return self.cabeca(representacao)


def _fixar_semente(semente: int, threads_torch: int) -> None:
    random.seed(semente)
    np.random.seed(semente)
    torch.manual_seed(semente)
    torch.set_num_threads(threads_torch)
    torch.use_deterministic_algorithms(True, warn_only=True)


def _carregador_torch(
    x: np.ndarray,
    y: np.ndarray,
    ids: np.ndarray,
    *,
    batch_size: int,
    embaralhar: bool,
    semente: int,
) -> DataLoader:
    conjunto = TensorDataset(
        torch.as_tensor(x, dtype=torch.float32),
        torch.as_tensor(y, dtype=torch.float32),
        torch.as_tensor(ids, dtype=torch.long),
    )
    gerador = torch.Generator().manual_seed(int(semente))
    return DataLoader(
        conjunto,
        batch_size=min(batch_size, len(conjunto)),
        shuffle=embaralhar,
        num_workers=0,
        generator=gerador,
    )


def _mse_rede(
    modelo: nn.Module,
    carregador: DataLoader,
) -> float:
    modelo.eval()
    soma = 0.0
    quantidade = 0
    with torch.no_grad():
        for x_lote, y_lote, ids_lote in carregador:
            previsto = modelo(x_lote, ids_lote)
            soma += float(torch.sum((previsto - y_lote) ** 2).item())
            quantidade += int(y_lote.numel())
    if quantidade < 1:
        raise ValueError("Carregador de avaliação vazio.")
    return soma / quantidade


def treinar_rede_direta(
    modelo: nn.Module,
    *,
    x_treino: np.ndarray,
    y_treino: np.ndarray,
    ids_treino: np.ndarray,
    configuracao: ConfiguracaoExperimentoHorario,
    x_validacao: np.ndarray | None = None,
    y_validacao: np.ndarray | None = None,
    ids_validacao: np.ndarray | None = None,
    epocas_fixas: int | None = None,
) -> tuple[nn.Module, int, list[dict[str, float | int]]]:
    """Treina em CPU, com early stopping opcional restrito à validação."""

    _fixar_semente(configuracao.semente, configuracao.threads_torch)
    if not (
        x_treino.shape[0] == y_treino.shape[0] == ids_treino.shape[0]
        and x_treino.shape[0] > 0
    ):
        raise ValueError("Matrizes de treino possuem tamanhos incompatíveis.")
    possui_validacao = x_validacao is not None
    if possui_validacao != (y_validacao is not None) or possui_validacao != (
        ids_validacao is not None
    ):
        raise ValueError("Informe todas ou nenhuma das matrizes de validação.")
    if possui_validacao and epocas_fixas is not None:
        raise ValueError("epocas_fixas não deve ser usada com validação.")
    epocas = (
        _inteiro_positivo(epocas_fixas, "epocas_fixas")
        if epocas_fixas is not None
        else configuracao.epocas_efetivas
    )

    treino = _carregador_torch(
        x_treino,
        y_treino,
        ids_treino,
        batch_size=configuracao.batch_size,
        embaralhar=True,
        semente=configuracao.semente,
    )
    validacao = (
        _carregador_torch(
            np.asarray(x_validacao),
            np.asarray(y_validacao),
            np.asarray(ids_validacao),
            batch_size=configuracao.batch_size,
            embaralhar=False,
            semente=configuracao.semente,
        )
        if possui_validacao
        else None
    )
    otimizador = torch.optim.Adam(
        modelo.parameters(),
        lr=configuracao.taxa_aprendizado,
        weight_decay=configuracao.peso_decay,
    )
    criterio = nn.MSELoss()
    melhor_estado = copy.deepcopy(modelo.state_dict())
    melhor_perda = math.inf
    melhor_epoca = 1
    sem_melhora = 0
    historico: list[dict[str, float | int]] = []

    for epoca in range(1, epocas + 1):
        modelo.train()
        soma = 0.0
        quantidade = 0
        for x_lote, y_lote, ids_lote in treino:
            otimizador.zero_grad(set_to_none=True)
            previsto = modelo(x_lote, ids_lote)
            perda = criterio(previsto, y_lote)
            perda.backward()
            otimizador.step()
            soma += float(perda.item()) * int(y_lote.numel())
            quantidade += int(y_lote.numel())
        perda_treino = soma / quantidade
        perda_validacao = (
            _mse_rede(modelo, validacao) if validacao is not None else perda_treino
        )
        historico.append(
            {
                "epoca": epoca,
                "MSE_treino_normalizado": perda_treino,
                "MSE_validacao_normalizado": (
                    perda_validacao if validacao is not None else np.nan
                ),
            }
        )
        if validacao is None:
            # No refit o número de épocas já foi escolhido em 2023. Conserva-se
            # exatamente o estado após a última época, sem uma nova seleção.
            melhor_perda = perda_validacao
            melhor_epoca = epoca
            melhor_estado = copy.deepcopy(modelo.state_dict())
            sem_melhora = 0
        elif perda_validacao < melhor_perda - 1e-12:
            melhor_perda = perda_validacao
            melhor_epoca = epoca
            melhor_estado = copy.deepcopy(modelo.state_dict())
            sem_melhora = 0
        else:
            sem_melhora += 1
            if validacao is not None and sem_melhora >= configuracao.paciencia:
                break

    modelo.load_state_dict(melhor_estado)
    return modelo, melhor_epoca, historico


def prever_rede_direta(
    modelo: nn.Module,
    x: np.ndarray,
    ids: np.ndarray,
    *,
    batch_size: int,
) -> np.ndarray:
    """Executa inferência determinística em CPU."""

    if len(x) != len(ids) or len(x) < 1:
        raise ValueError("x e ids devem ter o mesmo tamanho não vazio.")
    conjunto = TensorDataset(
        torch.as_tensor(x, dtype=torch.float32),
        torch.as_tensor(ids, dtype=torch.long),
    )
    carregador = DataLoader(
        conjunto,
        batch_size=min(batch_size, len(conjunto)),
        shuffle=False,
        num_workers=0,
    )
    previsoes = []
    modelo.eval()
    with torch.no_grad():
        for x_lote, ids_lote in carregador:
            previsoes.append(modelo(x_lote, ids_lote).cpu().numpy())
    resultado = np.concatenate(previsoes).astype(float)
    if not np.isfinite(resultado).all():
        raise ValueError("A rede produziu previsões não finitas.")
    return resultado


def _matriz_xgboost(
    x: np.ndarray,
    ids_localidade: np.ndarray,
    num_localidades: int,
) -> np.ndarray:
    """Acrescenta identificação one-hot sem codificar ordem entre localidades."""

    ids = np.asarray(ids_localidade, dtype=int)
    if len(x) != len(ids) or (ids < 0).any() or (ids >= num_localidades).any():
        raise ValueError("IDs de localidade inválidos para o XGBoost.")
    one_hot = np.eye(num_localidades, dtype=np.float32)[ids]
    return np.concatenate((np.asarray(x, dtype=np.float32), one_hot), axis=1)


def criar_xgboost_multioutput(
    configuracao: ConfiguracaoExperimentoHorario,
):
    """Cria um XGBRegressor nativamente multissaída para as 72 horas."""

    from xgboost import XGBRegressor

    return XGBRegressor(
        objective="reg:squarederror",
        n_estimators=configuracao.estimadores_xgb_efetivos,
        max_depth=configuracao.xgb_profundidade,
        learning_rate=configuracao.xgb_taxa_aprendizado,
        subsample=configuracao.xgb_subsample,
        colsample_bytree=configuracao.xgb_colsample,
        random_state=configuracao.semente,
        n_jobs=configuracao.xgb_n_jobs,
        tree_method="hist",
        # Árvore vetorial: cada folha produz conjuntamente os 72 passos.
        # A versão do XGBoost é preservada no manifesto do experimento.
        multi_strategy="multi_output_tree",
        verbosity=0,
    )


def criar_lstm(
    configuracao: ConfiguracaoExperimentoHorario,
    num_localidades: int,
) -> LSTMEncoderDireto:
    _fixar_semente(configuracao.semente, configuracao.threads_torch)
    return LSTMEncoderDireto(
        seq_len=configuracao.seq_len,
        pred_len=configuracao.pred_len,
        ocultos=configuracao.lstm_ocultos,
        camadas=configuracao.lstm_camadas,
        num_localidades=num_localidades,
        dimensao_embedding_localidade=configuracao.embedding_localidade_lstm,
    )


def criar_timesnet(
    configuracao: ConfiguracaoExperimentoHorario,
    num_localidades: int,
) -> TimesNetHorario:
    _fixar_semente(configuracao.semente, configuracao.threads_torch)
    return TimesNetHorario(
        seq_len=configuracao.seq_len,
        pred_len=configuracao.pred_len,
        d_model=configuracao.timesnet_d_model,
        d_ff=configuracao.timesnet_d_ff,
        num_blocos=configuracao.timesnet_blocos,
        top_k=configuracao.timesnet_top_k,
        num_kernels=configuracao.timesnet_kernels,
        num_localidades=num_localidades,
        dropout=configuracao.timesnet_dropout,
    )


def timestamps_alvo(janelas: JanelasHorarias) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Expande origens para os timestamps UTC e locais de cada passo."""

    passos = np.tile(np.arange(janelas.pred_len), len(janelas.x_bruto))
    deslocamentos = pd.to_timedelta(passos, unit="h")
    # Nao combine os inteiros de DatetimeIndex.asi8 diretamente. Desde o
    # pandas 3, a unidade interna pode ser microssegundos em vez de
    # nanossegundos; reconstruir o indice a partir desses inteiros deslocaria
    # as datas para 1970 e corromperia a mascara de elevacao solar. A aritmetica
    # entre indices e timedeltas preserva explicitamente unidade e fuso.
    utc = pd.DatetimeIndex(
        janelas.origem_utc.repeat(janelas.pred_len) + deslocamentos
    )
    local = pd.DatetimeIndex(
        janelas.origem_local.repeat(janelas.pred_len) + deslocamentos
    )
    return utc, local


def calcular_elevacao_solar(
    janelas: JanelasHorarias,
    series: Sequence[SerieLocalidade],
    *,
    minutos_centro_intervalo: int = 30,
) -> np.ndarray:
    """Calcula elevação solar no centro de cada média horária."""

    utc, _ = timestamps_alvo(janelas)
    ids = np.repeat(janelas.localidade_id, janelas.pred_len)
    resultado = np.empty(len(utc), dtype=float)
    por_id = {serie.localidade_id: serie for serie in series}
    deslocamento = pd.to_timedelta(minutos_centro_intervalo, unit="min")
    for localidade_id in np.unique(ids):
        mascara = ids == localidade_id
        serie = por_id[int(localidade_id)]
        posicao = pvlib.solarposition.get_solarposition(
            utc[mascara] + deslocamento,
            latitude=serie.latitude,
            longitude=serie.longitude,
        )
        resultado[mascara] = posicao["elevation"].to_numpy(dtype=float)
    if not np.isfinite(resultado).all():
        raise ValueError("pvlib produziu elevação solar não finita.")
    return resultado.reshape(len(janelas.x_bruto), janelas.pred_len)


def aplicar_pos_processamento_fisico(
    previsao_bruta: np.ndarray,
    elevacao_solar_graus: np.ndarray,
) -> np.ndarray:
    """Trunca negativos e zera toda previsão quando a elevação é <= 0°."""

    previsao = np.asarray(previsao_bruta, dtype=float)
    elevacao = np.asarray(elevacao_solar_graus, dtype=float)
    if previsao.shape != elevacao.shape or previsao.size == 0:
        raise ValueError("Previsão e elevação devem ter a mesma forma não vazia.")
    if not np.isfinite(previsao).all() or not np.isfinite(elevacao).all():
        raise ValueError("Previsão e elevação devem conter valores finitos.")
    truncada = np.clip(previsao, 0.0, None)
    return np.where(elevacao <= 0.0, 0.0, truncada)


def montar_tabela_previsoes(
    janelas: JanelasHorarias,
    previsoes_brutas: Mapping[str, np.ndarray],
    series: Sequence[SerieLocalidade],
    configuracao: ConfiguracaoExperimentoHorario,
) -> pd.DataFrame:
    """Monta tabela horária larga com saídas brutas e pós-processadas."""

    if set(previsoes_brutas) != set(MODELOS):
        raise ValueError("É necessária uma previsão para cada modelo do protocolo.")
    elevacao = calcular_elevacao_solar(
        janelas,
        series,
        minutos_centro_intervalo=configuracao.minutos_centro_intervalo,
    )
    utc, local = timestamps_alvo(janelas)
    n = len(janelas.x_bruto)
    passos = np.tile(np.arange(1, janelas.pred_len + 1), n)
    quadro = pd.DataFrame(
        {
            "particao": janelas.particao,
            "semente": int(configuracao.semente),
            "localidade": np.repeat(janelas.localidade, janelas.pred_len),
            "localidade_id": np.repeat(janelas.localidade_id, janelas.pred_len),
            "origem_utc": np.repeat(janelas.origem_utc, janelas.pred_len),
            "origem_local_fixa": np.repeat(janelas.origem_local, janelas.pred_len),
            "timestamp_alvo_utc": utc,
            "timestamp_alvo_local_fixo": local,
            "passo_h": passos,
            "ghi_real_wm2": janelas.y_bruto.reshape(-1).astype(float),
            "elevacao_solar_graus": elevacao.reshape(-1),
            "periodo_diurno": (elevacao.reshape(-1) > 0.0),
        }
    )
    for modelo in MODELOS:
        slug = SLUG_MODELOS[modelo]
        bruta = np.asarray(previsoes_brutas[modelo], dtype=float)
        if bruta.shape != janelas.y_bruto.shape or not np.isfinite(bruta).all():
            raise ValueError(f"Previsão bruta inválida para {modelo}.")
        pos = aplicar_pos_processamento_fisico(bruta, elevacao)
        quadro[f"previsao_bruta_{slug}_wm2"] = bruta.reshape(-1)
        quadro[f"previsao_pos_{slug}_wm2"] = pos.reshape(-1)
    return quadro


def _metricas_vetor(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    real = np.asarray(y_true, dtype=float).reshape(-1)
    previsto = np.asarray(y_pred, dtype=float).reshape(-1)
    if len(real) != len(previsto) or len(real) < 1:
        raise ValueError("Vetores de métricas devem ter o mesmo tamanho não vazio.")
    if not np.isfinite(real).all() or not np.isfinite(previsto).all():
        raise ValueError("Vetores de métricas devem ser finitos.")
    erro = real - previsto
    mae = float(np.mean(np.abs(erro)))
    rmse = float(np.sqrt(np.mean(erro**2)))
    media = float(np.mean(real))
    nrmse = np.nan if np.isclose(media, 0.0) else rmse / media
    denominador = float(np.sum((real - media) ** 2))
    r2 = (
        np.nan
        if len(real) < 2 or np.isclose(denominador, 0.0)
        else 1.0 - float(np.sum(erro**2)) / denominador
    )
    return {
        "MAE_wm2": mae,
        "RMSE_wm2": rmse,
        "nRMSE": float(nrmse),
        "nRMSE_percentual": float(nrmse * 100),
        "R2": float(r2),
    }


def calcular_metricas_horarias(
    previsoes: pd.DataFrame,
    horizontes: Sequence[int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula métricas locais e sua média macro, geral e somente diurna."""

    horizontes = tuple(int(valor) for valor in horizontes)
    linhas: list[dict[str, object]] = []
    for horizonte in horizontes:
        prefixo = previsoes.loc[previsoes["passo_h"] <= horizonte]
        if prefixo.empty:
            raise ValueError(f"Sem previsões para o horizonte {horizonte}.")
        for localidade, grupo_local in prefixo.groupby("localidade", sort=True):
            for escopo, mascara in (
                ("todas_horas", np.ones(len(grupo_local), dtype=bool)),
                (
                    "diurno_elevacao_gt_0",
                    grupo_local["periodo_diurno"].to_numpy(dtype=bool),
                ),
            ):
                grupo = grupo_local.loc[mascara]
                if grupo.empty:
                    raise ValueError(f"Escopo diurno vazio em {localidade}.")
                for modelo in MODELOS:
                    slug = SLUG_MODELOS[modelo]
                    for versao, coluna in (
                        ("bruta", f"previsao_bruta_{slug}_wm2"),
                        ("pos_processada", f"previsao_pos_{slug}_wm2"),
                    ):
                        metricas = _metricas_vetor(
                            grupo["ghi_real_wm2"].to_numpy(dtype=float),
                            grupo[coluna].to_numpy(dtype=float),
                        )
                        linhas.append(
                            {
                                "particao": str(grupo["particao"].iloc[0]),
                                "Localidade": localidade,
                                "Modelo": modelo,
                                "horizonte_h": horizonte,
                                "escopo": escopo,
                                "versao_previsao": versao,
                                "N_previsoes": int(len(grupo)),
                                **metricas,
                            }
                        )
    locais = pd.DataFrame(linhas)
    chaves = [
        "particao",
        "Modelo",
        "horizonte_h",
        "escopo",
        "versao_previsao",
    ]
    macro = (
        locais.groupby(chaves, sort=False, as_index=False)
        .agg(
            N_localidades=("Localidade", "nunique"),
            N_previsoes=("N_previsoes", "sum"),
            MAE_macro_wm2=("MAE_wm2", "mean"),
            RMSE_macro_wm2=("RMSE_wm2", "mean"),
            nRMSE_macro=("nRMSE", "mean"),
            nRMSE_macro_percentual=("nRMSE_percentual", "mean"),
            R2_macro=("R2", "mean"),
        )
        .reset_index(drop=True)
    )
    return locais, macro


def _previsoes_baselines(
    janelas: JanelasHorarias,
    series: Sequence[SerieLocalidade],
) -> dict[str, np.ndarray]:
    return {
        "Persistência": prever_persistencia_diaria(janelas),
        "Sazonal Ingênuo": prever_sazonal_ingenuo_anual(janelas, series),
    }


def _validar_cortes_sem_vazamento(
    treino: JanelasHorarias,
    validacao: JanelasHorarias,
    refit: JanelasHorarias,
    teste: JanelasHorarias,
    configuracao: ConfiguracaoExperimentoHorario,
) -> None:
    """Falha cedo se qualquer alvo cruzar uma fronteira do protocolo."""

    delta_final = pd.to_timedelta(configuracao.pred_len - 1, unit="h")
    inicio_validacao = pd.Timestamp(f"{configuracao.ano_validacao}-01-01")
    inicio_teste = pd.Timestamp(f"{configuracao.ano_teste}-01-01")
    fim_teste = pd.Timestamp(f"{configuracao.ano_teste + 1}-01-01")
    condicoes = (
        bool((treino.origem_local + delta_final < inicio_validacao).all()),
        bool((validacao.origem_local >= inicio_validacao).all()),
        bool((validacao.origem_local + delta_final < inicio_teste).all()),
        bool((refit.origem_local + delta_final < inicio_teste).all()),
        bool((teste.origem_local >= inicio_teste).all()),
        bool((teste.origem_local + delta_final < fim_teste).all()),
    )
    if not all(condicoes):
        raise AssertionError("Uma janela cruzou os cortes treino/validação/teste.")
    for janelas in (treino, validacao, refit, teste):
        if not bool(
            (
                (janelas.origem_local.hour == 0)
                & (janelas.origem_local.minute == 0)
            ).all()
        ):
            raise AssertionError("Há origem que não corresponde a 00:00 local.")


def _treinar_e_prever_validacao(
    *,
    treino: JanelasHorarias,
    validacao: JanelasHorarias,
    escalas: pd.DataFrame,
    series: Sequence[SerieLocalidade],
    configuracao: ConfiguracaoExperimentoHorario,
) -> tuple[
    dict[str, np.ndarray],
    dict[str, int],
    list[dict[str, object]],
]:
    """Ajusta em 2019--2022 e produz previsões de validação de 2023."""

    num_localidades = len(series)
    x_treino, y_treino = treino.normalizar(escalas)
    x_val, y_val = validacao.normalizar(escalas)
    previsoes = _previsoes_baselines(validacao, series)
    historico_total: list[dict[str, object]] = []

    xgb = criar_xgboost_multioutput(configuracao)
    xgb.fit(
        _matriz_xgboost(x_treino, treino.localidade_id, num_localidades),
        y_treino,
    )
    previsto_xgb = np.asarray(
        xgb.predict(
            _matriz_xgboost(x_val, validacao.localidade_id, num_localidades)
        ),
        dtype=float,
    ).reshape(len(validacao.x_bruto), configuracao.pred_len)
    previsoes["XGBoost"] = validacao.inverter(previsto_xgb, escalas)
    del xgb
    gc.collect()

    lstm = criar_lstm(configuracao, num_localidades)
    lstm, epocas_lstm, historico = treinar_rede_direta(
        lstm,
        x_treino=x_treino,
        y_treino=y_treino,
        ids_treino=treino.localidade_id,
        configuracao=configuracao,
        x_validacao=x_val,
        y_validacao=y_val,
        ids_validacao=validacao.localidade_id,
    )
    previsoes["LSTM"] = validacao.inverter(
        prever_rede_direta(
            lstm,
            x_val,
            validacao.localidade_id,
            batch_size=configuracao.batch_size,
        ),
        escalas,
    )
    historico_total.extend(
        {"fase": "selecao_epocas", "Modelo": "LSTM", **linha}
        for linha in historico
    )
    del lstm
    gc.collect()

    timesnet = criar_timesnet(configuracao, num_localidades)
    timesnet, epocas_timesnet, historico = treinar_rede_direta(
        timesnet,
        x_treino=x_treino,
        y_treino=y_treino,
        ids_treino=treino.localidade_id,
        configuracao=configuracao,
        x_validacao=x_val,
        y_validacao=y_val,
        ids_validacao=validacao.localidade_id,
    )
    previsoes["TimesNet"] = validacao.inverter(
        prever_rede_direta(
            timesnet,
            x_val,
            validacao.localidade_id,
            batch_size=configuracao.batch_size,
        ),
        escalas,
    )
    historico_total.extend(
        {"fase": "selecao_epocas", "Modelo": "TimesNet", **linha}
        for linha in historico
    )
    del timesnet, x_treino, y_treino, x_val, y_val
    gc.collect()

    return (
        previsoes,
        {"LSTM": epocas_lstm, "TimesNet": epocas_timesnet},
        historico_total,
    )


def _treinar_e_prever_teste(
    *,
    refit: JanelasHorarias,
    teste: JanelasHorarias,
    escalas: pd.DataFrame,
    series: Sequence[SerieLocalidade],
    configuracao: ConfiguracaoExperimentoHorario,
    epocas_selecionadas: Mapping[str, int],
    pasta_modelos: Path,
) -> tuple[dict[str, np.ndarray], list[dict[str, object]]]:
    """Refaz modelos do zero em 2019--2023 e infere 2024 sem reajuste."""

    num_localidades = len(series)
    x_refit, y_refit = refit.normalizar(escalas)
    x_teste, _ = teste.normalizar(escalas)
    previsoes = _previsoes_baselines(teste, series)
    historico_total: list[dict[str, object]] = []
    pasta_modelos.mkdir(parents=True, exist_ok=True)

    xgb = criar_xgboost_multioutput(configuracao)
    xgb.fit(
        _matriz_xgboost(x_refit, refit.localidade_id, num_localidades),
        y_refit,
    )
    previsto_xgb = np.asarray(
        xgb.predict(
            _matriz_xgboost(x_teste, teste.localidade_id, num_localidades)
        ),
        dtype=float,
    ).reshape(len(teste.x_bruto), configuracao.pred_len)
    previsoes["XGBoost"] = teste.inverter(previsto_xgb, escalas)
    joblib.dump(xgb, pasta_modelos / "xgboost_multioutput_refit.joblib")
    del xgb
    gc.collect()

    lstm = criar_lstm(configuracao, num_localidades)
    lstm, _, historico = treinar_rede_direta(
        lstm,
        x_treino=x_refit,
        y_treino=y_refit,
        ids_treino=refit.localidade_id,
        configuracao=configuracao,
        epocas_fixas=int(epocas_selecionadas["LSTM"]),
    )
    previsoes["LSTM"] = teste.inverter(
        prever_rede_direta(
            lstm,
            x_teste,
            teste.localidade_id,
            batch_size=configuracao.batch_size,
        ),
        escalas,
    )
    historico_total.extend(
        {"fase": "refit_epocas_fixas", "Modelo": "LSTM", **linha}
        for linha in historico
    )
    torch.save(
        {
            "state_dict": lstm.state_dict(),
            "classe": "LSTMEncoderDireto",
            "epocas_refit": int(epocas_selecionadas["LSTM"]),
            "configuracao": asdict(configuracao),
        },
        pasta_modelos / "lstm_encoder_direto_refit.pt",
    )
    del lstm
    gc.collect()

    timesnet = criar_timesnet(configuracao, num_localidades)
    timesnet, _, historico = treinar_rede_direta(
        timesnet,
        x_treino=x_refit,
        y_treino=y_refit,
        ids_treino=refit.localidade_id,
        configuracao=configuracao,
        epocas_fixas=int(epocas_selecionadas["TimesNet"]),
    )
    previsoes["TimesNet"] = teste.inverter(
        prever_rede_direta(
            timesnet,
            x_teste,
            teste.localidade_id,
            batch_size=configuracao.batch_size,
        ),
        escalas,
    )
    historico_total.extend(
        {"fase": "refit_epocas_fixas", "Modelo": "TimesNet", **linha}
        for linha in historico
    )
    torch.save(
        {
            "state_dict": timesnet.state_dict(),
            "classe": "TimesNetHorario",
            "epocas_refit": int(epocas_selecionadas["TimesNet"]),
            "configuracao": asdict(configuracao),
        },
        pasta_modelos / "timesnet_refit.pt",
    )
    del timesnet, x_refit, y_refit, x_teste
    gc.collect()
    return previsoes, historico_total


def _protocolo_por_localidade(
    *,
    series: Sequence[SerieLocalidade],
    treino: JanelasHorarias,
    validacao: JanelasHorarias,
    refit: JanelasHorarias,
    teste: JanelasHorarias,
    escalas_treino: pd.DataFrame,
    escalas_refit: pd.DataFrame,
    configuracao: ConfiguracaoExperimentoHorario,
) -> pd.DataFrame:
    escalas_1 = escalas_treino.set_index("localidade_id")
    escalas_2 = escalas_refit.set_index("localidade_id")
    particoes = {
        "treino_2019_2022": treino,
        "validacao_2023": validacao,
        "refit_2019_2023": refit,
        "teste_2024": teste,
    }
    linhas = []
    for serie in series:
        linha: dict[str, object] = {
            "Localidade": serie.localidade,
            "localidade_id": serie.localidade_id,
            "latitude_grade": serie.latitude,
            "longitude_grade": serie.longitude,
            "offset_fixo_nsrdb_horas": serie.offset_horas,
            "convencao_temporal": "timestamp_utc + offset_fixo_nsrdb",
            "hora_local_origem": "00:00",
            "frequencia_origens": "diaria",
            "politica_borda": (
                "excluir_origem_sem_pred_len_horas_totalmente_observadas"
            ),
            "seq_len_h": configuracao.seq_len,
            "pred_len_h": configuracao.pred_len,
            "horizontes_avaliacao_h": "/".join(
                str(valor) for valor in configuracao.horizontes
            ),
            "xgboost_multi_strategy": "multi_output_tree",
            "normalizacao": "minmax_por_localidade_pre_corte",
            "pos_processamento": (
                "clip_min_zero_e_mascara_elevacao_solar_le_zero"
            ),
            "centro_intervalo_solar_minutos": (
                configuracao.minutos_centro_intervalo
            ),
            "minimo_escala_validacao_wm2": float(
                escalas_1.loc[serie.localidade_id, "minimo_treino_wm2"]
            ),
            "maximo_escala_validacao_wm2": float(
                escalas_1.loc[serie.localidade_id, "maximo_treino_wm2"]
            ),
            "minimo_escala_refit_wm2": float(
                escalas_2.loc[serie.localidade_id, "minimo_treino_wm2"]
            ),
            "maximo_escala_refit_wm2": float(
                escalas_2.loc[serie.localidade_id, "maximo_treino_wm2"]
            ),
        }
        for nome, janelas in particoes.items():
            mascara = janelas.localidade_id == serie.localidade_id
            origens = janelas.origem_local[mascara]
            linha[f"N_origens_{nome}"] = int(mascara.sum())
            linha[f"primeira_origem_{nome}"] = pd.Timestamp(origens.min()).isoformat()
            linha[f"ultima_origem_{nome}"] = pd.Timestamp(origens.max()).isoformat()
        linhas.append(linha)
    return pd.DataFrame(linhas)


def _salvar_json(caminho: Path, conteudo: Mapping[str, object]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporario.replace(caminho)


def _salvar_csv(quadro: pd.DataFrame, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    if caminho.suffix == ".gz":
        quadro.to_csv(
            temporario,
            index=False,
            compression={"method": "gzip", "mtime": 0},
        )
    else:
        quadro.to_csv(temporario, index=False)
    temporario.replace(caminho)


def _sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def gerar_figura_timesnet_horaria(
    previsoes_teste: pd.DataFrame,
    series: Sequence[SerieLocalidade],
    configuracao: ConfiguracaoExperimentoHorario,
    caminho: Path,
) -> None:
    """Mostra contexto histórico, curva real e previsão TimesNet de 72 horas."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    localidades = sorted(previsoes_teste["localidade"].unique())
    primeira_localidade = (
        "BYD Camacari" if "BYD Camacari" in localidades else localidades[0]
    )
    nome_exibicao = {
        "BYD Camacari": "BYD Camaçari",
    }.get(primeira_localidade, primeira_localidade)
    subconjunto = previsoes_teste.loc[
        previsoes_teste["localidade"] == primeira_localidade
    ]
    primeira_origem = subconjunto["origem_utc"].min()
    alvo = (
        subconjunto.loc[subconjunto["origem_utc"] == primeira_origem]
        .sort_values("passo_h")
        .head(configuracao.pred_len)
    )
    serie = next(
        item for item in series if item.localidade == primeira_localidade
    )
    origem_utc = pd.Timestamp(primeira_origem)
    if origem_utc.tzinfo is None:
        origem_utc = origem_utc.tz_localize("UTC")
    posicao = int(serie.timestamp_utc.get_indexer([origem_utc])[0])
    if posicao < configuracao.seq_len:
        raise ValueError("Histórico insuficiente para a figura TimesNet.")
    historico_local = serie.timestamp_local[
        posicao - configuracao.seq_len : posicao
    ]
    historico = serie.ghi[posicao - configuracao.seq_len : posicao]

    caminho.parent.mkdir(parents=True, exist_ok=True)
    figura, eixo = plt.subplots(figsize=(11.2, 4.5))
    eixo.plot(
        historico_local,
        historico,
        color="#E3B341",
        linewidth=1.35,
        label=f"Histórico ({configuracao.seq_len} h)",
    )
    eixo.plot(
        pd.to_datetime(alvo["timestamp_alvo_local_fixo"]),
        alvo["ghi_real_wm2"],
        color="#202124",
        linewidth=1.5,
        label="GHI de referência (NSRDB)",
    )
    eixo.plot(
        pd.to_datetime(alvo["timestamp_alvo_local_fixo"]),
        alvo["previsao_bruta_timesnet_wm2"],
        color="#5B8FF9",
        linewidth=1.0,
        linestyle="--",
        alpha=0.65,
        label="Saída bruta do TimesNet",
    )
    eixo.plot(
        pd.to_datetime(alvo["timestamp_alvo_local_fixo"]),
        alvo["previsao_pos_timesnet_wm2"],
        color="#1F5AA6",
        linewidth=1.7,
        label="Previsão pós-processada do TimesNet",
    )
    eixo.axvline(
        pd.Timestamp(alvo["origem_local_fixa"].iloc[0]),
        color="#A23B72",
        linewidth=1.0,
        linestyle=":",
        label="Origem da previsão",
    )
    sinal_utc = "+" if serie.offset_horas >= 0 else "−"
    deslocamento_utc = f"{sinal_utc}{abs(serie.offset_horas):g}"
    eixo.set(
        title=f"Previsão horária com o TimesNet — {nome_exibicao}",
        xlabel=f"Tempo-padrão local (UTC{deslocamento_utc})",
        ylabel="GHI (W/m²)",
    )
    eixo.set_ylim(bottom=min(-5.0, float(alvo["previsao_bruta_timesnet_wm2"].min())))
    eixo.grid(alpha=0.2)
    eixo.legend(ncol=2, fontsize=8, frameon=False)
    figura.autofmt_xdate()
    figura.tight_layout()
    figura.savefig(caminho, dpi=220, bbox_inches="tight")
    plt.close(figura)


def gerar_figura_comparacao_rmse(
    previsoes_teste: pd.DataFrame,
    configuracao: ConfiguracaoExperimentoHorario,
    caminho: Path,
) -> None:
    """Resume a evolucao do RMSE e a variacao espacial dos modelos.

    O painel esquerdo usa todos os prefixos entre 1 h e ``pred_len``. Para
    manter a mesma ponderacao do artigo, o RMSE e calculado primeiro em cada
    localidade e depois agregado por media macro. O painel direito compara os
    tres modelos aprendidos no horizonte completo.
    """

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colunas_necessarias = {
        "localidade",
        "passo_h",
        "ghi_real_wm2",
        *(f"previsao_pos_{SLUG_MODELOS[modelo]}_wm2" for modelo in MODELOS),
    }
    ausentes = colunas_necessarias - set(previsoes_teste.columns)
    if ausentes:
        raise ValueError(
            "Colunas ausentes para a figura comparativa: "
            + ", ".join(sorted(ausentes))
        )

    dados = previsoes_teste.loc[
        previsoes_teste["passo_h"].between(1, configuracao.pred_len)
    ].copy()
    if dados.empty:
        raise ValueError("Sem previsoes para gerar a figura comparativa.")

    curvas: dict[str, pd.Series] = {}
    rmse_locais: dict[str, pd.Series] = {}
    for modelo in MODELOS:
        coluna = f"previsao_pos_{SLUG_MODELOS[modelo]}_wm2"
        erro_quadratico = (dados["ghi_real_wm2"] - dados[coluna]) ** 2
        por_passo = (
            dados.assign(erro_quadratico=erro_quadratico)
            .groupby(["localidade", "passo_h"], sort=True)["erro_quadratico"]
            .agg(["sum", "count"])
        )
        por_passo["soma_acumulada"] = por_passo.groupby(level=0)["sum"].cumsum()
        por_passo["n_acumulado"] = por_passo.groupby(level=0)["count"].cumsum()
        por_passo["rmse_acumulado"] = np.sqrt(
            por_passo["soma_acumulada"] / por_passo["n_acumulado"]
        )
        curvas[modelo] = por_passo.groupby(level=1)["rmse_acumulado"].mean()
        rmse_locais[modelo] = np.sqrt(
            dados.assign(erro_quadratico=erro_quadratico)
            .groupby("localidade", sort=True)["erro_quadratico"]
            .mean()
        )

    nomes_locais = {
        "BMW San Luis Potosi": "BMW San Luis Potosi",
        "BYD Camacari": "BYD Camacari",
        "Ford Rouge Electric Vehicle Center": "Ford Rouge",
        "GM Factory Zero": "GM Factory Zero",
        "Hyundai Metaplant Georgia": "Hyundai Georgia",
        "Lucid AMP 1 Casa Grande": "Lucid Casa Grande",
        "Rivian Normal": "Rivian Normal",
        "Tesla Fremont Factory": "Tesla Fremont",
        "Tesla Gigafactory Nevada": "Tesla Nevada",
        "Tesla Gigafactory Texas": "Tesla Texas",
    }
    cores = {
        "Persistência": "#7A7A7A",
        "Sazonal ingênuo": "#B5B5B5",
        "XGBoost": "#D55E00",
        "LSTM": "#009E73",
        "TimesNet": "#2864B7",
    }
    estilos = {
        "Persistência": "--",
        "Sazonal ingênuo": ":",
        "XGBoost": "-",
        "LSTM": "-.",
        "TimesNet": "-",
    }
    marcadores = {"XGBoost": "o", "LSTM": "^", "TimesNet": "s"}
    nomes_ascii = {
        "Persistência": "Persistência",
        "Sazonal Ingênuo": "Sazonal ingênuo",
        "XGBoost": "XGBoost",
        "LSTM": "LSTM",
        "TimesNet": "TimesNet",
    }

    caminho.parent.mkdir(parents=True, exist_ok=True)
    figura, (eixo_a, eixo_b) = plt.subplots(
        1,
        2,
        figsize=(12.6, 4.8),
        gridspec_kw={"width_ratios": [1.08, 1.0]},
    )

    ordem_curvas = (
        "Persistência",
        "Sazonal Ingênuo",
        "XGBoost",
        "LSTM",
        "TimesNet",
    )
    for modelo in ordem_curvas:
        rotulo = nomes_ascii[modelo]
        curva = curvas[modelo]
        destaque = modelo == "TimesNet"
        eixo_a.plot(
            curva.index,
            curva.values,
            color=cores[rotulo],
            linestyle=estilos[rotulo],
            linewidth=2.2 if destaque else 1.45,
            label=rotulo,
            zorder=4 if destaque else 2,
        )
        pontos = [
            valor
            for valor in configuracao.horizontes
            if valor in curva.index and valor <= configuracao.pred_len
        ]
        if pontos:
            eixo_a.scatter(
                pontos,
                curva.loc[pontos],
                color=cores[rotulo],
                s=18 if destaque else 11,
                zorder=5,
            )
    eixo_a.set(
        title="(a) Evolução com o horizonte",
        xlabel="Prefixo acumulado da previsão (h)",
        ylabel=r"RMSE macro (W m$^{-2}$)",
        xlim=(1, configuracao.pred_len),
    )
    eixo_a.set_xticks(
        sorted({1, *configuracao.horizontes, configuracao.pred_len})
    )
    eixo_a.grid(axis="both", alpha=0.18)
    eixo_a.legend(
        ncol=2,
        fontsize=8,
        frameon=False,
        loc="upper left",
    )

    aprendidos = ("XGBoost", "TimesNet", "LSTM")
    quadro_local = pd.DataFrame({m: rmse_locais[m] for m in aprendidos})
    quadro_local = quadro_local.sort_values("TimesNet", ascending=True)
    posicoes = np.arange(len(quadro_local))
    deslocamentos = {"XGBoost": -0.18, "TimesNet": 0.0, "LSTM": 0.18}
    for modelo in aprendidos:
        eixo_b.scatter(
            quadro_local[modelo],
            posicoes + deslocamentos[modelo],
            color=cores[modelo],
            marker=marcadores[modelo],
            s=31,
            label=modelo,
            zorder=4,
        )
    for posicao, (_, linha) in enumerate(quadro_local.iterrows()):
        eixo_b.plot(
            [linha.min(), linha.max()],
            [posicao, posicao],
            color="#D6D6D6",
            linewidth=1.0,
            zorder=1,
        )
    eixo_b.set(
        title=f"(b) Modelos aprendidos em {configuracao.pred_len} h",
        xlabel=r"RMSE (W m$^{-2}$)",
        yticks=posicoes,
        yticklabels=[nomes_locais.get(nome, nome) for nome in quadro_local.index],
    )
    eixo_b.grid(axis="x", alpha=0.18)
    eixo_b.legend(ncol=3, fontsize=8, frameon=False, loc="lower right")

    for eixo in (eixo_a, eixo_b):
        eixo.spines["top"].set_visible(False)
        eixo.spines["right"].set_visible(False)
        eixo.tick_params(labelsize=8.5)
        eixo.title.set_fontsize(10)
        eixo.xaxis.label.set_fontsize(9)
        eixo.yaxis.label.set_fontsize(9)

    figura.tight_layout(w_pad=2.0)
    figura.savefig(caminho, dpi=240, bbox_inches="tight")
    plt.close(figura)


def _manifesto(
    pasta_saida: Path,
    configuracao: ConfiguracaoExperimentoHorario,
    epocas_selecionadas: Mapping[str, int],
) -> dict[str, object]:
    import xgboost

    arquivos = sorted(
        caminho
        for caminho in pasta_saida.rglob("*")
        if caminho.is_file() and caminho.name != "manifesto_artefatos.json"
    )
    return {
        "versao_esquema": 1,
        "criado_em_utc": datetime.now(timezone.utc).isoformat(),
        "modo_execucao": configuracao.modo_execucao,
        "resultado_smoke_nao_publicavel": configuracao.modo_execucao == "smoke",
        "semente": int(configuracao.semente),
        "epocas_escolhidas_exclusivamente_na_validacao_2023": dict(
            epocas_selecionadas
        ),
        "xgboost_multi_strategy": "multi_output_tree",
        "politica_borda": (
            "somente_origens_com_72_horas_totalmente_observadas; "
            "sem completar a borda de 2024 com dados de 2025"
        ),
        "ambiente": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "torch": torch.__version__,
            "pvlib": pvlib.__version__,
            "xgboost": xgboost.__version__,
        },
        "arquivos": {
            caminho.relative_to(pasta_saida).as_posix(): {
                "sha256": _sha256(caminho),
                "bytes": caminho.stat().st_size,
            }
            for caminho in arquivos
        },
    }


def executar_experimento(
    pasta_saida: Path | str = PASTA_RESULTADOS / "avaliacao_horaria_timesnet",
    configuracao: ConfiguracaoExperimentoHorario | None = None,
    *,
    pasta_dados: Path | str = PASTA_HORARIA_PADRAO,
    dados: pd.DataFrame | None = None,
    sobrescrever: bool = False,
) -> dict[str, Path]:
    """Executa validação, refit, teste, métricas e persistência dos artefatos."""

    configuracao = configuracao or ConfiguracaoExperimentoHorario()
    saida = Path(pasta_saida)
    if saida.exists() and any(saida.iterdir()) and not sobrescrever:
        raise FileExistsError(
            f"{saida} já contém artefatos; use sobrescrever=True conscientemente."
        )
    saida.mkdir(parents=True, exist_ok=True)
    _salvar_json(saida / "configuracao_execucao.json", asdict(configuracao))
    _salvar_json(
        saida / "status_execucao.json",
        {
            "etapa": "iniciada",
            "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
            "modo_execucao": configuracao.modo_execucao,
            "resultado_smoke_nao_publicavel": (
                configuracao.modo_execucao == "smoke"
            ),
        },
    )

    if dados is None:
        anos = range(configuracao.anos_treino[0], configuracao.ano_teste + 1)
        dados = carregar_dados_horarios(pasta_dados, anos=anos)
    series = preparar_series_localidades(dados, configuracao)
    limite = (
        configuracao.limite_origens_smoke
        if configuracao.modo_execucao == "smoke"
        else None
    )
    treino = construir_janelas_diarias(
        series,
        anos_origem=configuracao.anos_treino,
        seq_len=configuracao.seq_len,
        pred_len=configuracao.pred_len,
        particao="validacao_treino",
        limite_origens_por_localidade=limite,
    )
    validacao = construir_janelas_diarias(
        series,
        anos_origem=(configuracao.ano_validacao,),
        seq_len=configuracao.seq_len,
        pred_len=configuracao.pred_len,
        particao="validacao_2023",
        limite_origens_por_localidade=limite,
    )
    refit = construir_janelas_diarias(
        series,
        anos_origem=(*configuracao.anos_treino, configuracao.ano_validacao),
        seq_len=configuracao.seq_len,
        pred_len=configuracao.pred_len,
        particao="refit_2019_2023",
        limite_origens_por_localidade=limite,
    )
    teste = construir_janelas_diarias(
        series,
        anos_origem=(configuracao.ano_teste,),
        seq_len=configuracao.seq_len,
        pred_len=configuracao.pred_len,
        particao="teste_2024",
        limite_origens_por_localidade=limite,
    )
    _validar_cortes_sem_vazamento(
        treino, validacao, refit, teste, configuracao
    )

    escalas_treino = ajustar_escalas_pre_corte(
        series,
        primeiro_ano=configuracao.anos_treino[0],
        fim_local_exclusivo=f"{configuracao.ano_validacao}-01-01",
        nome_ajuste="treino_para_validacao",
    )
    escalas_refit = ajustar_escalas_pre_corte(
        series,
        primeiro_ano=configuracao.anos_treino[0],
        fim_local_exclusivo=f"{configuracao.ano_teste}-01-01",
        nome_ajuste="refit_para_teste",
    )
    escalas = pd.concat((escalas_treino, escalas_refit), ignore_index=True)
    _salvar_csv(escalas, saida / "escalas_minmax_pre_corte.csv")
    protocolo = _protocolo_por_localidade(
        series=series,
        treino=treino,
        validacao=validacao,
        refit=refit,
        teste=teste,
        escalas_treino=escalas_treino,
        escalas_refit=escalas_refit,
        configuracao=configuracao,
    )
    _salvar_csv(protocolo, saida / "protocolo_temporal.csv")

    previsoes_val, epocas, historico_val = _treinar_e_prever_validacao(
        treino=treino,
        validacao=validacao,
        escalas=escalas_treino,
        series=series,
        configuracao=configuracao,
    )
    tabela_val = montar_tabela_previsoes(
        validacao, previsoes_val, series, configuracao
    )
    metricas_val, macro_val = calcular_metricas_horarias(
        tabela_val, configuracao.horizontes
    )
    _salvar_csv(tabela_val, saida / "previsoes_validacao.csv.gz")
    del previsoes_val, tabela_val
    gc.collect()

    previsoes_teste, historico_refit = _treinar_e_prever_teste(
        refit=refit,
        teste=teste,
        escalas=escalas_refit,
        series=series,
        configuracao=configuracao,
        epocas_selecionadas=epocas,
        pasta_modelos=saida / "modelos",
    )
    tabela_teste = montar_tabela_previsoes(
        teste, previsoes_teste, series, configuracao
    )
    metricas_teste, macro_teste = calcular_metricas_horarias(
        tabela_teste, configuracao.horizontes
    )
    _salvar_csv(tabela_teste, saida / "previsoes_teste.csv.gz")
    metricas_locais = pd.concat((metricas_val, metricas_teste), ignore_index=True)
    metricas_macro = pd.concat((macro_val, macro_teste), ignore_index=True)
    _salvar_csv(metricas_locais, saida / "metricas_por_localidade.csv")
    _salvar_csv(metricas_macro, saida / "metricas_macro.csv")
    historico = pd.DataFrame(historico_val + historico_refit)
    _salvar_csv(historico, saida / "historico_treinamento.csv")
    gerar_figura_timesnet_horaria(
        tabela_teste,
        series,
        configuracao,
        saida / "figuras" / "previsao_horaria_timesnet_72h.png",
    )
    gerar_figura_comparacao_rmse(
        tabela_teste,
        configuracao,
        saida / "figuras" / "comparacao_rmse_modelos.png",
    )

    resumo_final = metricas_macro.loc[
        (metricas_macro["particao"] == "teste_2024")
        & (metricas_macro["escopo"] == "todas_horas")
        & (metricas_macro["versao_previsao"] == "pos_processada")
    ].copy()
    _salvar_json(
        saida / "resumo_execucao.json",
        {
            "modo_execucao": configuracao.modo_execucao,
            "resultado_smoke_nao_publicavel": (
                configuracao.modo_execucao == "smoke"
            ),
            "semente": int(configuracao.semente),
            "modelos": list(MODELOS),
            "epocas_redes_escolhidas_em_2023": dict(epocas),
            "metricas_macro_teste_pos_processadas": resumo_final.to_dict(
                orient="records"
            ),
        },
    )
    _salvar_json(
        saida / "status_execucao.json",
        {
            "etapa": "concluida",
            "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
            "modo_execucao": configuracao.modo_execucao,
            "resultado_smoke_nao_publicavel": (
                configuracao.modo_execucao == "smoke"
            ),
        },
    )
    _salvar_json(
        saida / "manifesto_artefatos.json",
        _manifesto(saida, configuracao, epocas),
    )
    return {
        "pasta_saida": saida,
        "previsoes_teste": saida / "previsoes_teste.csv.gz",
        "metricas_macro": saida / "metricas_macro.csv",
        "figura_timesnet": (
            saida / "figuras" / "previsao_horaria_timesnet_72h.png"
        ),
        "figura_comparacao_rmse": (
            saida / "figuras" / "comparacao_rmse_modelos.png"
        ),
        "manifesto": saida / "manifesto_artefatos.json",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Executa o protocolo horário TimesNet (336 h -> 72 h) nas "
            "localidades da NSRDB."
        )
    )
    parser.add_argument(
        "--dados",
        type=Path,
        default=PASTA_HORARIA_PADRAO,
        help="Pasta dos CSVs horários anuais da NSRDB.",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=PASTA_RESULTADOS / "avaliacao_horaria_timesnet",
    )
    parser.add_argument(
        "--modo",
        choices=("completa", "smoke"),
        default="smoke",
        help="Smoke verifica o pipeline; completa executa o protocolo científico.",
    )
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("--sobrescrever", action="store_true")
    parser.add_argument(
        "--confirmar-execucao-longa",
        action="store_true",
        help="Confirma explicitamente treinamento completo em CPU.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    argumentos = _parser().parse_args(argv)
    if argumentos.modo == "completa" and not argumentos.confirmar_execucao_longa:
        raise SystemExit(
            "A execução completa é longa. Repita com "
            "--confirmar-execucao-longa."
        )
    configuracao = ConfiguracaoExperimentoHorario(
        modo_execucao=argumentos.modo,
        semente=argumentos.semente,
    )
    artefatos = executar_experimento(
        argumentos.saida,
        configuracao,
        pasta_dados=argumentos.dados,
        sobrescrever=argumentos.sobrescrever,
    )
    print(f"Artefatos horários salvos em {artefatos['pasta_saida']}")


__all__ = [
    "ConfiguracaoExperimentoHorario",
    "JanelasHorarias",
    "LSTMEncoderDireto",
    "MODELOS",
    "SerieLocalidade",
    "ajustar_escalas_pre_corte",
    "aplicar_pos_processamento_fisico",
    "calcular_elevacao_solar",
    "calcular_metricas_horarias",
    "construir_janelas_diarias",
    "executar_experimento",
    "gerar_figura_timesnet_horaria",
    "gerar_figura_comparacao_rmse",
    "main",
    "montar_tabela_previsoes",
    "preparar_series_localidades",
    "prever_persistencia_diaria",
    "prever_sazonal_ingenuo_anual",
    "timestamps_alvo",
]


if __name__ == "__main__":
    main()
