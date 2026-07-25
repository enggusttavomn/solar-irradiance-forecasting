"""Wrappers GluonTS do protocolo mensal global canonico.

Este modulo encapsula :class:`DeepNPTSEstimator` e
:class:`DeepAREstimator`, ambos do backend PyTorch do GluonTS. Ao contrario de
um ajuste independente por localidade, uma unica rede e treinada sobre todas
as series. A identidade da localidade entra como uma categoria estatica. Para
o DeepNPTS, uma subclasse local corrige exclusivamente o registro dos
embeddings no PyTorch; arquitetura, distribuicao e perda RPS permanecem as da
implementacao oficial 0.16.2.

As entradas esperadas sao series ``pandas.Series`` mensais, sem lacunas e ja
normalizadas no intervalo ``[0, 1]``. O modulo nao estima a normalizacao: os
limites devem ser obtidos exclusivamente no conjunto de treino pelo pipeline
chamador e reaplicados nas janelas de validacao/teste.

Exemplo resumido::

    modelo = DeepNPTSGlobalGluonTS(context_length=12, seed=42)
    modelo.ajustar(series_treino)  # mapping com dez localidades
    previsoes = modelo.prever_multiplas_origens(
        series_com_historico,
        origens={nome: ["2024-01", "2024-02"] for nome in series_treino},
        num_samples=500,
    )
    modelo.salvar("resultados/deepnpts_seed_42")

Cada origem designa o ultimo mes observado; como ``prediction_length=1``, o
mes imediatamente seguinte e o previsto. O historico e truncado na origem
antes de chegar ao GluonTS, o que torna o protocolo causal e auditavel.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
import json
from numbers import Integral
from pathlib import Path
import random
import shutil
import tempfile
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


VERSAO_GLUONTS_SUPORTADA = "0.16.2"
FREQUENCIA_MENSAL_GLUONTS = "M"
HORIZONTE_PREVISAO = 1
NOME_ARQUIVO_WRAPPER = "wrapper-gluonts.json"
VERSAO_ESQUEMA_WRAPPER = 1


@dataclass(frozen=True)
class PrevisaoProbabilistica:
    """Amostras de uma previsao de um mes para uma localidade e origem."""

    localidade: str
    origem: pd.Period
    inicio_previsao: pd.Period
    amostras: np.ndarray
    seed: int

    def __post_init__(self) -> None:
        amostras = np.asarray(self.amostras, dtype=float)
        if amostras.ndim == 1:
            amostras = amostras.reshape((-1, 1))
        if amostras.ndim != 2 or amostras.shape[1] != HORIZONTE_PREVISAO:
            raise ValueError(
                "amostras deve ter formato (numero_amostras, prediction_length=1)."
            )
        if len(amostras) == 0 or not np.isfinite(amostras).all():
            raise ValueError("amostras deve ser uma matriz finita e nao vazia.")
        # A dataclass e congelada, mas a conversao garante forma e dtype comuns.
        object.__setattr__(self, "amostras", amostras)

    @property
    def media(self) -> float:
        """Media das amostras preditivas."""

        return float(np.mean(self.amostras[:, 0]))

    @property
    def mediana(self) -> float:
        """Mediana das amostras preditivas."""

        return float(np.median(self.amostras[:, 0]))

    def quantil(self, nivel: float) -> float:
        """Retorna um quantil da distribuicao amostral."""

        if not 0.0 <= nivel <= 1.0:
            raise ValueError("nivel deve pertencer ao intervalo [0, 1].")
        return float(np.quantile(self.amostras[:, 0], nivel))

    def resumo(self, quantis: Sequence[float] = (0.05, 0.5, 0.95)) -> dict[str, Any]:
        """Produz uma linha serializavel para tabelas de avaliacao."""

        linha: dict[str, Any] = {
            "localidade": self.localidade,
            "origem": str(self.origem),
            "inicio_previsao": str(self.inicio_previsao),
            "seed": self.seed,
            "numero_amostras": int(len(self.amostras)),
            "media": self.media,
            "mediana": self.mediana,
        }
        for nivel in quantis:
            if not 0.0 <= nivel <= 1.0:
                raise ValueError("Todos os quantis devem pertencer a [0, 1].")
            linha[f"q{nivel:g}"] = self.quantil(float(nivel))
        return linha


@dataclass(frozen=True)
class _SerieMensalValidada:
    nome: str
    periodos: pd.PeriodIndex
    valores: np.ndarray


@lru_cache(maxsize=1)
def _carregar_api_gluonts() -> SimpleNamespace:
    """Importa a API suportada tardiamente e verifica sua versao.

    Imports tardios mantem os demais modelos do projeto utilizaveis quando o
    extra PyTorch/GluonTS nao estiver instalado. A verificacao exata evita que
    mudancas de API alterem silenciosamente os experimentos publicados.
    """

    try:
        versao_instalada = version("gluonts")
    except PackageNotFoundError as exc:
        raise ImportError(
            "GluonTS nao esta instalado. Instale gluonts==0.16.2 com os extras "
            "PyTorch antes de treinar DeepNPTS ou DeepAR."
        ) from exc
    if versao_instalada != VERSAO_GLUONTS_SUPORTADA:
        raise RuntimeError(
            "Versao do GluonTS nao validada: "
            f"esperada {VERSAO_GLUONTS_SUPORTADA}, encontrada {versao_instalada}."
        )

    try:
        import torch
        from gluonts.dataset.common import ListDataset
        from gluonts.model.predictor import Predictor
        from gluonts.transform.sampler import ExpectedNumInstanceSampler
        from gluonts.torch.model.deepar import DeepAREstimator
        from gluonts.torch.model.deep_npts import (
            DeepNPTSEstimator,
        )
        from codigo_fonte.redes_deepnpts_registradas import (
            DeepNPTSNetworkDiscreteRegistrada,
            DeepNPTSNetworkSmoothRegistrada,
        )
    except ImportError as exc:
        raise ImportError(
            "A instalacao do GluonTS nao possui o backend PyTorch necessario."
        ) from exc

    return SimpleNamespace(
        torch=torch,
        ListDataset=ListDataset,
        Predictor=Predictor,
        ExpectedNumInstanceSampler=ExpectedNumInstanceSampler,
        DeepAREstimator=DeepAREstimator,
        DeepNPTSEstimator=DeepNPTSEstimator,
        DeepNPTSNetworkDiscreteRegistrada=DeepNPTSNetworkDiscreteRegistrada,
        DeepNPTSNetworkSmoothRegistrada=DeepNPTSNetworkSmoothRegistrada,
    )


def _validar_inteiro_positivo(nome: str, valor: int) -> int:
    if isinstance(valor, bool) or not isinstance(valor, Integral) or valor < 1:
        raise ValueError(f"{nome} deve ser um inteiro positivo.")
    return int(valor)


def _validar_seed(seed: int) -> int:
    if (
        isinstance(seed, bool)
        or not isinstance(seed, Integral)
        or not 0 <= seed < 2**32
    ):
        raise ValueError("seed deve ser um inteiro no intervalo [0, 2**32).")
    return int(seed)


def _definir_seed(seed: int, torch: Any) -> None:
    """Semeia Python, NumPy e PyTorch antes de ajuste ou amostragem."""

    _validar_seed(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if hasattr(torch, "cuda") and torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except (AttributeError, RuntimeError):
        pass


def _converter_indice_mensal(indice: pd.Index, nome: str) -> pd.PeriodIndex:
    if isinstance(indice, pd.PeriodIndex):
        periodos = indice.asfreq("M")
    elif isinstance(indice, pd.DatetimeIndex):
        if indice.tz is not None:
            raise ValueError(f"A serie {nome!r} nao pode usar indice com fuso horario.")
        periodos = indice.to_period("M")
    else:
        try:
            periodos = pd.PeriodIndex(indice, freq="M")
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"O indice da serie {nome!r} deve representar meses validos."
            ) from exc

    if periodos.has_duplicates:
        raise ValueError(f"A serie {nome!r} possui mais de uma observacao no mesmo mes.")
    if not periodos.is_monotonic_increasing:
        raise ValueError(f"O indice da serie {nome!r} deve estar em ordem crescente.")
    esperado = pd.period_range(periodos[0], periodos[-1], freq="M")
    if not periodos.equals(esperado):
        raise ValueError(f"A serie {nome!r} possui lacunas mensais.")
    return periodos


def _validar_serie(
    nome: str,
    serie: pd.Series,
    *,
    tamanho_minimo: int,
) -> _SerieMensalValidada:
    if not isinstance(nome, str) or not nome.strip():
        raise ValueError("Cada localidade deve possuir um nome textual nao vazio.")
    if not isinstance(serie, pd.Series):
        raise TypeError(f"A serie da localidade {nome!r} deve ser pandas.Series.")
    if len(serie) < tamanho_minimo:
        raise ValueError(
            f"A serie {nome!r} deve conter pelo menos {tamanho_minimo} meses."
        )

    try:
        valores = serie.to_numpy(dtype=np.float32, copy=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"A serie {nome!r} deve conter apenas valores numericos.") from exc
    if valores.ndim != 1 or not np.isfinite(valores).all():
        raise ValueError(f"A serie {nome!r} deve conter somente valores finitos.")
    if np.any(valores < 0.0) or np.any(valores > 1.0):
        raise ValueError(f"A serie {nome!r} deve estar normalizada em [0, 1].")

    periodos = _converter_indice_mensal(serie.index, nome)
    return _SerieMensalValidada(nome=nome, periodos=periodos, valores=valores)


def _validar_colecao_series(
    series: Mapping[str, pd.Series],
    *,
    tamanho_minimo: int,
    numero_esperado: int | None,
) -> dict[str, _SerieMensalValidada]:
    if not isinstance(series, Mapping) or not series:
        raise ValueError("series deve ser um mapping nao vazio de localidade para Serie.")
    if numero_esperado is not None and len(series) != numero_esperado:
        raise ValueError(
            f"O treino global exige {numero_esperado} localidades; "
            f"foram recebidas {len(series)}."
        )

    nomes = list(series)
    if any(not isinstance(nome, str) for nome in nomes):
        raise ValueError("Os identificadores de localidade devem ser strings.")
    validadas: dict[str, _SerieMensalValidada] = {}
    for nome in sorted(nomes):
        validada = _validar_serie(nome, series[nome], tamanho_minimo=tamanho_minimo)
        validadas[nome] = validada
    return validadas


def construir_dataset_global(
    series: Mapping[str, pd.Series],
    *,
    context_length: int,
    numero_localidades_esperado: int = 10,
) -> tuple[Any, dict[str, int]]:
    """Constroi um ``ListDataset`` global com categoria estatica de localidade.

    A categoria e determinada pela ordem lexicografica dos nomes, garantindo
    que a mesma entrada produza o mesmo mapeamento em diferentes execucoes.
    O retorno contem o dataset e o mapeamento ``localidade -> categoria``.
    """

    context_length = _validar_inteiro_positivo("context_length", context_length)
    numero_localidades_esperado = _validar_inteiro_positivo(
        "numero_localidades_esperado", numero_localidades_esperado
    )
    validadas = _validar_colecao_series(
        series,
        tamanho_minimo=context_length + HORIZONTE_PREVISAO,
        numero_esperado=numero_localidades_esperado,
    )
    categorias = {nome: indice for indice, nome in enumerate(validadas)}
    entradas = [
        {
            "start": validada.periodos[0],
            "target": validada.valores,
            "feat_static_cat": np.asarray([categorias[nome]], dtype=np.int64),
            "item_id": nome,
        }
        for nome, validada in validadas.items()
    ]
    api = _carregar_api_gluonts()
    return api.ListDataset(entradas, freq=FREQUENCIA_MENSAL_GLUONTS), categorias


class _ModeloGlobalGluonTS(ABC):
    """Base comum para um unico predictor global de dez series mensais."""

    nome_modelo: str

    def __init__(
        self,
        *,
        context_length: int = 12,
        seed: int = 42,
        num_samples: int = 500,
        numero_localidades_esperado: int = 10,
        batch_size: int = 32,
        num_batches_per_epoch: int = 50,
        epochs: int = 100,
        learning_rate: float = 1e-3,
        device: str = "cpu",
        cache_data: bool = True,
        diretorio_saida: str | Path | None = None,
    ) -> None:
        self.context_length = _validar_inteiro_positivo(
            "context_length", context_length
        )
        self.seed = _validar_seed(seed)
        self.num_samples = _validar_inteiro_positivo("num_samples", num_samples)
        self.numero_localidades_esperado = _validar_inteiro_positivo(
            "numero_localidades_esperado", numero_localidades_esperado
        )
        self.batch_size = _validar_inteiro_positivo("batch_size", batch_size)
        self.num_batches_per_epoch = _validar_inteiro_positivo(
            "num_batches_per_epoch", num_batches_per_epoch
        )
        self.epochs = _validar_inteiro_positivo("epochs", epochs)
        if not np.isfinite(learning_rate) or learning_rate <= 0:
            raise ValueError("learning_rate deve ser positivo e finito.")
        if not isinstance(device, str) or not device:
            raise ValueError("device deve ser uma string nao vazia.")
        self.learning_rate = float(learning_rate)
        self.device = device
        self.cache_data = bool(cache_data)
        self.diretorio_saida = (
            Path(diretorio_saida) if diretorio_saida is not None else None
        )
        self.diretorio_execucao_: Path | None = None
        self.predictor_: Any | None = None
        self.categorias_localidade_: dict[str, int] = {}

    @property
    def ajustado(self) -> bool:
        return self.predictor_ is not None

    @abstractmethod
    def _criar_estimador(self, api: SimpleNamespace, cardinalidade: int) -> Any:
        """Cria o estimador oficial com os parametros do wrapper."""

    @abstractmethod
    def _configuracao_especifica(self) -> dict[str, Any]:
        """Retorna parametros especificos e serializaveis do modelo."""

    def ajustar(self, series_treino: Mapping[str, pd.Series]) -> "_ModeloGlobalGluonTS":
        """Treina uma unica rede sobre todas as localidades recebidas."""

        dataset, categorias = construir_dataset_global(
            series_treino,
            context_length=self.context_length,
            numero_localidades_esperado=self.numero_localidades_esperado,
        )
        api = _carregar_api_gluonts()
        _definir_seed(self.seed, api.torch)
        estimador = self._criar_estimador(api, cardinalidade=len(categorias))
        predictor = estimador.train(
            training_data=dataset,
            cache_data=self.cache_data,
        )
        if hasattr(predictor, "to"):
            predictor.to(self.device)
        self.predictor_ = predictor
        self.categorias_localidade_ = categorias
        return self

    def _obter_diretorio_execucao(self) -> Path:
        """Reserva uma pasta para logs/checkpoints sem escrever na raiz."""

        if self.diretorio_execucao_ is None:
            if self.diretorio_saida is None:
                self.diretorio_execucao_ = Path(
                    tempfile.mkdtemp(
                        prefix=f"tcc-{self.nome_modelo.lower()}-seed-{self.seed}-"
                    )
                )
            else:
                self.diretorio_saida.mkdir(parents=True, exist_ok=True)
                self.diretorio_execucao_ = self.diretorio_saida
        return self.diretorio_execucao_

    def _normalizar_origens(
        self,
        nomes: Iterable[str],
        origens: Mapping[str, Sequence[Any]] | Sequence[Any],
    ) -> dict[str, list[pd.Period]]:
        nomes = list(nomes)
        if isinstance(origens, Mapping):
            desconhecidas = sorted(set(origens) - set(nomes))
            faltantes = sorted(set(nomes) - set(origens))
            if desconhecidas or faltantes:
                detalhes = []
                if desconhecidas:
                    detalhes.append(f"desconhecidas={desconhecidas}")
                if faltantes:
                    detalhes.append(f"faltantes={faltantes}")
                raise ValueError("Mapa de origens incompativel: " + "; ".join(detalhes))
            por_nome = {nome: origens[nome] for nome in nomes}
        else:
            if isinstance(origens, (str, bytes)):
                raise TypeError("origens deve ser uma sequencia de meses, nao texto isolado.")
            por_nome = {nome: origens for nome in nomes}

        resultado: dict[str, list[pd.Period]] = {}
        for nome, valores in por_nome.items():
            periodos = []
            for valor in valores:
                try:
                    periodo = pd.Period(valor, freq="M")
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Origem mensal invalida para {nome!r}: {valor!r}.") from exc
                periodos.append(periodo)
            if not periodos:
                raise ValueError(f"Informe pelo menos uma origem para {nome!r}.")
            if len(set(periodos)) != len(periodos):
                raise ValueError(f"Ha origens repetidas para {nome!r}.")
            resultado[nome] = periodos
        return resultado

    def prever_multiplas_origens(
        self,
        series: Mapping[str, pd.Series],
        origens: Mapping[str, Sequence[Any]] | Sequence[Any],
        *,
        num_samples: int | None = None,
        seed: int | None = None,
    ) -> list[PrevisaoProbabilistica]:
        """Amostra previsoes causais para varias origens e localidades.

        ``origens`` pode ser uma sequencia comum a todas as series ou um mapa
        com uma sequencia por localidade. Cada entrada e truncada incluindo a
        origem; nenhum valor posterior e enviado ao predictor.
        """

        if self.predictor_ is None:
            raise RuntimeError("O modelo global precisa ser ajustado antes da previsao.")
        amostras_solicitadas = self.num_samples if num_samples is None else num_samples
        amostras_solicitadas = _validar_inteiro_positivo(
            "num_samples", amostras_solicitadas
        )
        seed_previsao = self.seed if seed is None else _validar_seed(seed)

        validadas = _validar_colecao_series(
            series,
            tamanho_minimo=self.context_length,
            numero_esperado=None,
        )
        desconhecidas = sorted(set(validadas) - set(self.categorias_localidade_))
        if desconhecidas:
            raise ValueError(
                "Localidades nao vistas no treino global: " + ", ".join(desconhecidas)
            )
        origens_normalizadas = self._normalizar_origens(validadas, origens)

        entradas = []
        metadados: list[tuple[str, pd.Period]] = []
        for nome in sorted(validadas, key=self.categorias_localidade_.get):
            validada = validadas[nome]
            for origem in origens_normalizadas[nome]:
                posicoes = np.flatnonzero(validada.periodos == origem)
                if len(posicoes) != 1:
                    raise ValueError(
                        f"A origem {origem} nao existe na serie {nome!r}."
                    )
                fim = int(posicoes[0]) + 1
                if fim < self.context_length:
                    raise ValueError(
                        f"A origem {origem} de {nome!r} possui menos que "
                        f"{self.context_length} meses de historico."
                    )
                entradas.append(
                    {
                        "start": validada.periodos[0],
                        "target": validada.valores[:fim],
                        "feat_static_cat": np.asarray(
                            [self.categorias_localidade_[nome]], dtype=np.int64
                        ),
                        "item_id": f"{nome}::{origem}",
                    }
                )
                metadados.append((nome, origem))

        api = _carregar_api_gluonts()
        _definir_seed(seed_previsao, api.torch)
        dataset = api.ListDataset(entradas, freq=FREQUENCIA_MENSAL_GLUONTS)
        forecasts = list(
            self.predictor_.predict(dataset, num_samples=amostras_solicitadas)
        )
        if len(forecasts) != len(metadados):
            raise RuntimeError(
                "O predictor retornou uma quantidade de forecasts diferente "
                "da quantidade de origens solicitadas."
            )

        resultados = []
        for forecast, (nome, origem) in zip(forecasts, metadados):
            valores = getattr(forecast, "samples", None)
            if valores is None:
                raise TypeError(
                    "O predictor nao retornou SampleForecast; previsoes "
                    "probabilisticas exigem o atributo samples."
                )
            resultados.append(
                PrevisaoProbabilistica(
                    localidade=nome,
                    origem=origem,
                    inicio_previsao=origem + HORIZONTE_PREVISAO,
                    amostras=np.asarray(valores, dtype=float),
                    seed=seed_previsao,
                )
            )
        return resultados

    def _configuracao_comum(self) -> dict[str, Any]:
        return {
            "context_length": self.context_length,
            "seed": self.seed,
            "num_samples": self.num_samples,
            "numero_localidades_esperado": self.numero_localidades_esperado,
            "batch_size": self.batch_size,
            "num_batches_per_epoch": self.num_batches_per_epoch,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "device": self.device,
            "cache_data": self.cache_data,
            "diretorio_saida": (
                str(self.diretorio_saida) if self.diretorio_saida is not None else None
            ),
        }

    def salvar(self, destino: str | Path) -> Path:
        """Serializa predictor e metadados de categorias de forma atomica."""

        if self.predictor_ is None:
            raise RuntimeError("Nao ha predictor ajustado para salvar.")
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            raise FileExistsError(
                f"O destino {destino} ja existe; escolha uma nova pasta."
            )

        temporario = Path(
            tempfile.mkdtemp(prefix=f".{destino.name}-", dir=destino.parent)
        )
        try:
            self.predictor_.serialize(temporario)
            metadados = {
                "versao_esquema": VERSAO_ESQUEMA_WRAPPER,
                "versao_gluonts": VERSAO_GLUONTS_SUPORTADA,
                "modelo": self.nome_modelo,
                "frequencia": FREQUENCIA_MENSAL_GLUONTS,
                "prediction_length": HORIZONTE_PREVISAO,
                "categorias_localidade": self.categorias_localidade_,
                "configuracao": {
                    **self._configuracao_comum(),
                    **self._configuracao_especifica(),
                },
            }
            (temporario / NOME_ARQUIVO_WRAPPER).write_text(
                json.dumps(
                    metadados,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
            temporario.rename(destino)
        except Exception:
            shutil.rmtree(temporario, ignore_errors=True)
            raise
        return destino


class DeepNPTSGlobalGluonTS(_ModeloGlobalGluonTS):
    """Wrapper global do ``DeepNPTSEstimator`` do GluonTS 0.16.2.

    A rede conserva o calculo oficial e corrige apenas o registro dos
    embeddings categoricos, necessario para que sejam treinados e persistidos.
    """

    nome_modelo = "DeepNPTS"

    def __init__(
        self,
        *,
        context_length: int = 12,
        seed: int = 42,
        num_samples: int = 500,
        numero_localidades_esperado: int = 10,
        batch_size: int = 32,
        num_batches_per_epoch: int = 100,
        epochs: int = 100,
        learning_rate: float = 1e-5,
        device: str = "cpu",
        cache_data: bool = True,
        diretorio_saida: str | Path | None = None,
        variante: str = "discreta",
        num_hidden_nodes: Sequence[int] | None = None,
        embedding_dimension: int | None = None,
        dropout_rate: float = 0.0,
        batch_norm: bool = False,
    ) -> None:
        super().__init__(
            context_length=context_length,
            seed=seed,
            num_samples=num_samples,
            numero_localidades_esperado=numero_localidades_esperado,
            batch_size=batch_size,
            num_batches_per_epoch=num_batches_per_epoch,
            epochs=epochs,
            learning_rate=learning_rate,
            device=device,
            cache_data=cache_data,
            diretorio_saida=diretorio_saida,
        )
        variante = variante.lower()
        if variante not in {"discreta", "suave"}:
            raise ValueError("variante deve ser 'discreta' ou 'suave'.")
        if num_hidden_nodes is not None:
            num_hidden_nodes = tuple(
                _validar_inteiro_positivo("num_hidden_nodes", no)
                for no in num_hidden_nodes
            )
            if not num_hidden_nodes:
                raise ValueError("num_hidden_nodes nao pode ser vazio.")
        if embedding_dimension is not None:
            embedding_dimension = _validar_inteiro_positivo(
                "embedding_dimension", embedding_dimension
            )
        if not np.isfinite(dropout_rate) or not 0.0 <= dropout_rate < 1.0:
            raise ValueError("dropout_rate deve pertencer a [0, 1).")
        self.variante = variante
        self.num_hidden_nodes = num_hidden_nodes
        self.embedding_dimension = embedding_dimension
        self.dropout_rate = float(dropout_rate)
        self.batch_norm = bool(batch_norm)

    def _criar_estimador(self, api: SimpleNamespace, cardinalidade: int) -> Any:
        rede = (
            api.DeepNPTSNetworkDiscreteRegistrada
            if self.variante == "discreta"
            else api.DeepNPTSNetworkSmoothRegistrada
        )
        return api.DeepNPTSEstimator(
            freq=FREQUENCIA_MENSAL_GLUONTS,
            prediction_length=HORIZONTE_PREVISAO,
            context_length=self.context_length,
            num_hidden_nodes=(
                list(self.num_hidden_nodes) if self.num_hidden_nodes is not None else None
            ),
            batch_norm=self.batch_norm,
            use_feat_static_cat=True,
            cardinality=[cardinalidade],
            embedding_dimension=(
                [self.embedding_dimension]
                if self.embedding_dimension is not None
                else None
            ),
            input_scaling=None,
            dropout_rate=self.dropout_rate,
            network_type=rede,
            epochs=self.epochs,
            lr=self.learning_rate,
            batch_size=self.batch_size,
            num_batches_per_epoch=self.num_batches_per_epoch,
            cache_data=self.cache_data,
        )

    def _configuracao_especifica(self) -> dict[str, Any]:
        return {
            "variante": self.variante,
            "num_hidden_nodes": (
                list(self.num_hidden_nodes) if self.num_hidden_nodes is not None else None
            ),
            "embedding_dimension": self.embedding_dimension,
            "dropout_rate": self.dropout_rate,
            "batch_norm": self.batch_norm,
            "embeddings_pytorch_registrados": True,
        }


class DeepARGlobalGluonTS(_ModeloGlobalGluonTS):
    """Wrapper do ``DeepAREstimator`` global oficial do GluonTS 0.16.2."""

    nome_modelo = "DeepAR"

    def __init__(
        self,
        *,
        context_length: int = 12,
        seed: int = 42,
        num_samples: int = 500,
        numero_localidades_esperado: int = 10,
        batch_size: int = 32,
        num_batches_per_epoch: int = 50,
        epochs: int = 100,
        learning_rate: float = 1e-3,
        device: str = "cpu",
        cache_data: bool = True,
        diretorio_saida: str | Path | None = None,
        num_layers: int = 2,
        hidden_size: int = 40,
        dropout_rate: float = 0.1,
        patience: int = 10,
        embedding_dimension: int | None = None,
        lags_seq: Sequence[int] = tuple(range(1, 13)),
        scaling: bool = False,
        nonnegative_pred_samples: bool = False,
    ) -> None:
        super().__init__(
            context_length=context_length,
            seed=seed,
            num_samples=num_samples,
            numero_localidades_esperado=numero_localidades_esperado,
            batch_size=batch_size,
            num_batches_per_epoch=num_batches_per_epoch,
            epochs=epochs,
            learning_rate=learning_rate,
            device=device,
            cache_data=cache_data,
            diretorio_saida=diretorio_saida,
        )
        self.num_layers = _validar_inteiro_positivo("num_layers", num_layers)
        self.hidden_size = _validar_inteiro_positivo("hidden_size", hidden_size)
        self.patience = _validar_inteiro_positivo("patience", patience)
        if embedding_dimension is not None:
            embedding_dimension = _validar_inteiro_positivo(
                "embedding_dimension", embedding_dimension
            )
        if not np.isfinite(dropout_rate) or not 0.0 <= dropout_rate < 1.0:
            raise ValueError("dropout_rate deve pertencer a [0, 1).")
        lags = tuple(_validar_inteiro_positivo("lags_seq", lag) for lag in lags_seq)
        if not lags or len(set(lags)) != len(lags):
            raise ValueError("lags_seq deve conter defasagens positivas e unicas.")
        self.dropout_rate = float(dropout_rate)
        self.embedding_dimension = embedding_dimension
        self.lags_seq = lags
        self.scaling = bool(scaling)
        self.nonnegative_pred_samples = bool(nonnegative_pred_samples)

    def _criar_estimador(self, api: SimpleNamespace, cardinalidade: int) -> Any:
        return api.DeepAREstimator(
            freq=FREQUENCIA_MENSAL_GLUONTS,
            prediction_length=HORIZONTE_PREVISAO,
            context_length=self.context_length,
            num_layers=self.num_layers,
            hidden_size=self.hidden_size,
            lr=self.learning_rate,
            dropout_rate=self.dropout_rate,
            patience=self.patience,
            num_feat_static_cat=1,
            cardinality=[cardinalidade],
            embedding_dimension=(
                [self.embedding_dimension]
                if self.embedding_dimension is not None
                else None
            ),
            lags_seq=list(self.lags_seq),
            scaling=self.scaling,
            num_parallel_samples=self.num_samples,
            batch_size=self.batch_size,
            num_batches_per_epoch=self.num_batches_per_epoch,
            nonnegative_pred_samples=self.nonnegative_pred_samples,
            # O padrao do DeepAR aceita alvos sem nenhum historico real e os
            # completa por padding. Exigir ``context_length`` meses alinha o
            # primeiro alvo de treino aos demais modelos (jan./2020 quando o
            # historico comeca em jan./2019).
            train_sampler=api.ExpectedNumInstanceSampler(
                num_instances=1.0,
                min_past=self.context_length,
                min_future=HORIZONTE_PREVISAO,
            ),
            trainer_kwargs={
                "max_epochs": self.epochs,
                "default_root_dir": str(self._obter_diretorio_execucao()),
                "deterministic": True,
                "enable_progress_bar": False,
                "enable_model_summary": False,
                "logger": False,
            },
        )

    def _configuracao_especifica(self) -> dict[str, Any]:
        return {
            "num_layers": self.num_layers,
            "hidden_size": self.hidden_size,
            "dropout_rate": self.dropout_rate,
            "patience": self.patience,
            "embedding_dimension": self.embedding_dimension,
            "lags_seq": list(self.lags_seq),
            "scaling": self.scaling,
            "nonnegative_pred_samples": self.nonnegative_pred_samples,
            "amostragem_treino": {
                "classe": "ExpectedNumInstanceSampler",
                "num_instances": 1.0,
                "min_past": self.context_length,
                "min_future": HORIZONTE_PREVISAO,
            },
        }


def carregar_modelo_global_gluonts(
    origem: str | Path,
    *,
    device: str = "cpu",
) -> _ModeloGlobalGluonTS:
    """Restaura predictor, configuracao e mapeamento de localidades."""

    origem = Path(origem)
    arquivo = origem / NOME_ARQUIVO_WRAPPER
    if not arquivo.is_file():
        raise FileNotFoundError(f"Metadados do wrapper inexistentes: {arquivo}")
    metadados = json.loads(arquivo.read_text(encoding="utf-8"))
    if metadados.get("versao_esquema") != VERSAO_ESQUEMA_WRAPPER:
        raise ValueError("Versao de esquema do wrapper nao suportada.")
    if metadados.get("versao_gluonts") != VERSAO_GLUONTS_SUPORTADA:
        raise ValueError("O predictor foi salvo com outra versao do GluonTS.")
    if metadados.get("prediction_length") != HORIZONTE_PREVISAO:
        raise ValueError("O predictor persistido nao possui prediction_length=1.")

    classes = {
        DeepNPTSGlobalGluonTS.nome_modelo: DeepNPTSGlobalGluonTS,
        DeepARGlobalGluonTS.nome_modelo: DeepARGlobalGluonTS,
    }
    nome_modelo = metadados.get("modelo")
    if nome_modelo not in classes:
        raise ValueError(f"Modelo global desconhecido nos metadados: {nome_modelo!r}.")
    configuracao = dict(metadados.get("configuracao", {}))
    if (
        nome_modelo == DeepNPTSGlobalGluonTS.nome_modelo
        and configuracao.get("embeddings_pytorch_registrados") is not True
    ):
        raise ValueError(
            "Predictor DeepNPTS anterior a correcao dos embeddings; "
            "treine novamente com o wrapper atual."
        )
    # Campo informativo derivado de ``context_length`` e ``prediction_length``.
    # Ele permanece no JSON para auditar o protocolo, mas o construtor recria
    # o sampler em ``_criar_estimador`` e nao recebe esse dicionario.
    configuracao.pop("amostragem_treino", None)
    # Marcador de proveniencia da rede DeepNPTS; nao e parametro do construtor.
    configuracao.pop("embeddings_pytorch_registrados", None)
    configuracao["device"] = device
    modelo = classes[nome_modelo](**configuracao)

    categorias = metadados.get("categorias_localidade")
    categorias_validas = (
        isinstance(categorias, dict)
        and categorias
        and all(isinstance(nome, str) and nome.strip() for nome in categorias)
        and all(
            isinstance(valor, Integral) and not isinstance(valor, bool)
            for valor in categorias.values()
        )
        and sorted(int(valor) for valor in categorias.values())
        == list(range(len(categorias)))
    )
    if not categorias_validas:
        raise ValueError("Mapeamento de categorias de localidade invalido.")
    api = _carregar_api_gluonts()
    modelo.predictor_ = api.Predictor.deserialize(origem, device=device)
    modelo.categorias_localidade_ = {
        str(nome): int(categoria) for nome, categoria in categorias.items()
    }
    return modelo


def previsoes_para_dataframe(
    previsoes: Sequence[PrevisaoProbabilistica],
    *,
    quantis: Sequence[float] = (0.05, 0.5, 0.95),
) -> pd.DataFrame:
    """Converte previsoes amostrais em uma tabela compacta de resumo."""

    return pd.DataFrame([previsao.resumo(quantis) for previsao in previsoes])


__all__ = [
    "DeepARGlobalGluonTS",
    "DeepNPTSGlobalGluonTS",
    "PrevisaoProbabilistica",
    "carregar_modelo_global_gluonts",
    "construir_dataset_global",
    "previsoes_para_dataframe",
]
