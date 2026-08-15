"""Testes dos wrappers globais oficiais do GluonTS.

Os testes usuais usam dublês leves para verificar contrato, causalidade e
parametros sem treinar redes. Um smoke test real pode ser ativado com
``EXECUTAR_SMOKE_GLUONTS=1 pytest testes/test_modelos_gluonts.py -k smoke``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import codigo_fonte.modelos_globais_gluonts as globais


class _CudaFalso:
    @staticmethod
    def is_available() -> bool:
        return False


class _TorchFalso:
    cuda = _CudaFalso()
    seeds: list[int] = []

    @classmethod
    def manual_seed(cls, seed: int) -> None:
        cls.seeds.append(seed)

    @staticmethod
    def use_deterministic_algorithms(*args, **kwargs) -> None:
        del args, kwargs


class _ListDatasetFalso(list):
    def __init__(self, entradas, freq: str) -> None:
        super().__init__(entradas)
        self.freq = freq


class _ForecastFalso:
    def __init__(self, amostras: np.ndarray) -> None:
        self.samples = amostras


class _PredictorFalso:
    desserializado: "_PredictorFalso | None" = None

    def __init__(self) -> None:
        self.device = None
        self.dataset_previsao = None
        self.num_samples = None

    def to(self, device: str) -> "_PredictorFalso":
        self.device = device
        return self

    def predict(self, dataset, num_samples: int):
        self.dataset_previsao = dataset
        self.num_samples = num_samples
        for indice, _ in enumerate(dataset):
            yield _ForecastFalso(
                np.full((num_samples, 1), fill_value=indice / 10.0, dtype=float)
            )

    def serialize(self, path: Path) -> None:
        (path / "predictor-falso.txt").write_text("ok\n", encoding="utf-8")

    @classmethod
    def deserialize(cls, path: Path, device: str = "cpu") -> "_PredictorFalso":
        assert (path / "predictor-falso.txt").is_file()
        predictor = cls().to(device)
        cls.desserializado = predictor
        return predictor


class _EstimadorFalso:
    instancias: list["_EstimadorFalso"] = []

    def __init__(self, **parametros) -> None:
        self.parametros = parametros
        self.chamadas_treino = 0
        self.training_data = None
        self.cache_data = None
        self.predictor = _PredictorFalso()
        type(self).instancias.append(self)

    def train(self, training_data, cache_data: bool):
        self.chamadas_treino += 1
        self.training_data = training_data
        self.cache_data = cache_data
        return self.predictor


class _DeepNPTSEstimadorFalso(_EstimadorFalso):
    instancias: list[_EstimadorFalso] = []


class _DeepAREstimadorFalso(_EstimadorFalso):
    instancias: list[_EstimadorFalso] = []


class _ExpectedNumInstanceSamplerFalso:
    def __init__(self, *, num_instances, min_past, min_future) -> None:
        self.num_instances = num_instances
        self.min_past = min_past
        self.min_future = min_future


@pytest.fixture
def api_falsa(monkeypatch):
    _DeepNPTSEstimadorFalso.instancias.clear()
    _DeepAREstimadorFalso.instancias.clear()
    _TorchFalso.seeds.clear()
    api = SimpleNamespace(
        torch=_TorchFalso,
        ListDataset=_ListDatasetFalso,
        Predictor=_PredictorFalso,
        DeepAREstimator=_DeepAREstimadorFalso,
        DeepNPTSEstimator=_DeepNPTSEstimadorFalso,
        DeepNPTSNetworkDiscreteRegistrada=type("RedeDiscretaFalsa", (), {}),
        DeepNPTSNetworkSmoothRegistrada=type("RedeSuaveFalsa", (), {}),
        ExpectedNumInstanceSampler=_ExpectedNumInstanceSamplerFalso,
    )
    monkeypatch.setattr(globais, "_carregar_api_gluonts", lambda: api)
    return api


def _series_mensais(numero: int = 2, periodos: int = 24):
    indice = pd.period_range("2020-01", periods=periodos, freq="M")
    return {
        f"localidade_{i:02d}": pd.Series(
            np.linspace(0.05 + i / 100, 0.85 + i / 100, periodos),
            index=indice,
        )
        for i in range(numero)
    }


def test_dataset_global_usa_uma_categoria_estatica_por_localidade(api_falsa) -> None:
    series = _series_mensais(2)

    dataset, categorias = globais.construir_dataset_global(
        series,
        context_length=6,
        numero_localidades_esperado=2,
    )

    assert dataset.freq == "M"
    assert categorias == {"localidade_00": 0, "localidade_01": 1}
    assert len(dataset) == 2
    assert dataset[0]["item_id"] == "localidade_00"
    assert dataset[0]["start"] == pd.Period("2020-01", freq="M")
    assert dataset[0]["target"].dtype == np.float32
    assert dataset[0]["feat_static_cat"].tolist() == [0]
    assert dataset[1]["feat_static_cat"].tolist() == [1]


def test_dataset_exige_dez_localidades_por_padrao(api_falsa) -> None:
    with pytest.raises(ValueError, match="exige 10 localidades"):
        globais.construir_dataset_global(_series_mensais(2), context_length=6)


@pytest.mark.parametrize(
    "mutacao,mensagem",
    [
        (lambda s: s.mask(s.index == s.index[0], 1.1), "normalizada"),
        (lambda s: s.drop(s.index[5]), "lacunas mensais"),
        (lambda s: s.iloc[::-1], "ordem crescente"),
    ],
)
def test_dataset_rejeita_serie_invalida(api_falsa, mutacao, mensagem: str) -> None:
    series = _series_mensais(2)
    series["localidade_00"] = mutacao(series["localidade_00"])

    with pytest.raises(ValueError, match=mensagem):
        globais.construir_dataset_global(
            series,
            context_length=6,
            numero_localidades_esperado=2,
        )


def test_deepnpts_e_treinado_uma_vez_globalmente_com_categoria(api_falsa) -> None:
    modelo = globais.DeepNPTSGlobalGluonTS(
        context_length=6,
        numero_localidades_esperado=2,
        seed=43,
        epochs=2,
        num_batches_per_epoch=3,
        num_samples=20,
        variante="suave",
        num_hidden_nodes=(7, 5),
        embedding_dimension=2,
    )

    retorno = modelo.ajustar(_series_mensais(2))

    assert retorno is modelo
    assert modelo.ajustado
    assert _TorchFalso.seeds == [43]
    assert len(_DeepNPTSEstimadorFalso.instancias) == 1
    estimador = _DeepNPTSEstimadorFalso.instancias[0]
    assert estimador.chamadas_treino == 1
    assert len(estimador.training_data) == 2
    assert estimador.parametros["prediction_length"] == 1
    assert estimador.parametros["context_length"] == 6
    assert estimador.parametros["use_feat_static_cat"] is True
    assert estimador.parametros["cardinality"] == [2]
    assert estimador.parametros["embedding_dimension"] == [2]
    assert (
        estimador.parametros["network_type"]
        is api_falsa.DeepNPTSNetworkSmoothRegistrada
    )
    assert estimador.parametros["input_scaling"] is None
    assert modelo.predictor_.device == "cpu"


def test_deepar_e_global_probabilistico_e_configura_seed(
    api_falsa, tmp_path: Path
) -> None:
    diretorio_saida = tmp_path / "deep_ar_seed_44"
    modelo = globais.DeepARGlobalGluonTS(
        context_length=8,
        numero_localidades_esperado=2,
        seed=44,
        num_samples=30,
        epochs=2,
        num_batches_per_epoch=3,
        lags_seq=(1, 2, 12),
        scaling=False,
        diretorio_saida=diretorio_saida,
    ).ajustar(_series_mensais(2))

    assert modelo.ajustado
    assert _TorchFalso.seeds == [44]
    assert len(_DeepAREstimadorFalso.instancias) == 1
    estimador = _DeepAREstimadorFalso.instancias[0]
    assert estimador.chamadas_treino == 1
    assert estimador.parametros["prediction_length"] == 1
    assert estimador.parametros["num_feat_static_cat"] == 1
    assert estimador.parametros["cardinality"] == [2]
    assert estimador.parametros["num_parallel_samples"] == 30
    assert estimador.parametros["lags_seq"] == [1, 2, 12]
    assert estimador.parametros["train_sampler"].min_past == 8
    assert estimador.parametros["train_sampler"].min_future == 1
    assert estimador.parametros["scaling"] is False
    sampler = estimador.parametros["train_sampler"]
    assert isinstance(sampler, _ExpectedNumInstanceSamplerFalso)
    assert sampler.num_instances == pytest.approx(1.0)
    assert sampler.min_past == 8
    assert sampler.min_future == 1
    assert estimador.parametros["trainer_kwargs"]["deterministic"] is True
    assert estimador.parametros["trainer_kwargs"]["max_epochs"] == 2
    assert estimador.parametros["trainer_kwargs"]["default_root_dir"] == str(
        diretorio_saida
    )


def test_deepar_persiste_protocolo_do_sampler_de_treino(
    api_falsa, tmp_path: Path
) -> None:
    modelo = globais.DeepARGlobalGluonTS(
        context_length=8,
        numero_localidades_esperado=2,
        epochs=1,
        num_batches_per_epoch=1,
    ).ajustar(_series_mensais(2))
    destino = modelo.salvar(tmp_path / "deepar_com_sampler")

    metadados = json.loads(
        (destino / globais.NOME_ARQUIVO_WRAPPER).read_text(encoding="utf-8")
    )
    protocolo = metadados["configuracao"]["amostragem_treino"]

    assert protocolo == {
        "classe": "ExpectedNumInstanceSampler",
        "num_instances": 1.0,
        "min_past": 8,
        "min_future": 1,
    }
    restaurado = globais.carregar_modelo_global_gluonts(destino)
    assert isinstance(restaurado, globais.DeepARGlobalGluonTS)


def test_loader_rejeita_deepnpts_anterior_ao_registro_dos_embeddings(
    api_falsa, tmp_path: Path
) -> None:
    modelo = globais.DeepNPTSGlobalGluonTS(
        context_length=6,
        numero_localidades_esperado=2,
        epochs=1,
        num_batches_per_epoch=1,
    ).ajustar(_series_mensais(2))
    destino = modelo.salvar(tmp_path / "deepnpts_antigo")
    arquivo = destino / globais.NOME_ARQUIVO_WRAPPER
    metadados = json.loads(arquivo.read_text(encoding="utf-8"))
    metadados["configuracao"].pop("embeddings_pytorch_registrados")
    arquivo.write_text(json.dumps(metadados), encoding="utf-8")

    with pytest.raises(ValueError, match="anterior a correcao"):
        globais.carregar_modelo_global_gluonts(destino)


def test_multiplas_origens_truncam_historico_e_preservam_amostras(api_falsa) -> None:
    series = _series_mensais(2)
    modelo = globais.DeepNPTSGlobalGluonTS(
        context_length=6,
        numero_localidades_esperado=2,
        seed=42,
        epochs=1,
        num_batches_per_epoch=1,
    ).ajustar(series)

    previsoes = modelo.prever_multiplas_origens(
        series,
        origens={
            "localidade_00": ["2021-06", "2021-08"],
            "localidade_01": ["2021-07"],
        },
        num_samples=17,
        seed=99,
    )

    assert _TorchFalso.seeds == [42, 99]
    assert len(previsoes) == 3
    assert [p.localidade for p in previsoes] == [
        "localidade_00",
        "localidade_00",
        "localidade_01",
    ]
    assert previsoes[0].origem == pd.Period("2021-06", freq="M")
    assert previsoes[0].inicio_previsao == pd.Period("2021-07", freq="M")
    assert previsoes[0].amostras.shape == (17, 1)
    assert previsoes[1].media == pytest.approx(0.1)

    entradas = modelo.predictor_.dataset_previsao
    assert [len(entrada["target"]) for entrada in entradas] == [18, 20, 19]
    assert entradas[0]["target"][-1] == pytest.approx(
        series["localidade_00"].loc["2021-06"]
    )
    assert entradas[0]["feat_static_cat"].tolist() == [0]
    assert entradas[2]["feat_static_cat"].tolist() == [1]
    assert modelo.predictor_.num_samples == 17


def test_previsao_rejeita_origem_sem_contexto_e_localidade_nova(api_falsa) -> None:
    series = _series_mensais(2)
    modelo = globais.DeepARGlobalGluonTS(
        context_length=6,
        numero_localidades_esperado=2,
        epochs=1,
        num_batches_per_epoch=1,
    ).ajustar(series)

    with pytest.raises(ValueError, match="menos que 6 meses"):
        modelo.prever_multiplas_origens(series, ["2020-03"])

    series_nova = {"nova": series["localidade_00"]}
    with pytest.raises(ValueError, match="nao vistas no treino"):
        modelo.prever_multiplas_origens(series_nova, ["2021-06"])


def test_previsao_probabilistica_resume_media_mediana_e_quantis() -> None:
    previsao = globais.PrevisaoProbabilistica(
        localidade="L",
        origem=pd.Period("2024-01", freq="M"),
        inicio_previsao=pd.Period("2024-02", freq="M"),
        amostras=np.array([0.1, 0.3, 0.5]),
        seed=42,
    )

    assert previsao.amostras.shape == (3, 1)
    assert previsao.media == pytest.approx(0.3)
    assert previsao.mediana == pytest.approx(0.3)
    assert previsao.quantil(0.5) == pytest.approx(0.3)
    tabela = globais.previsoes_para_dataframe([previsao], quantis=(0.1, 0.9))
    assert tabela.loc[0, "numero_amostras"] == 3
    assert {"q0.1", "q0.9"}.issubset(tabela.columns)


def test_rede_deepnpts_registra_e_restaura_embeddings() -> None:
    torch = pytest.importorskip("torch")
    pytest.importorskip("gluonts")
    from codigo_fonte.redes_deepnpts_registradas import (
        DeepNPTSNetworkDiscreteRegistrada,
    )

    parametros = {
        "context_length": 4,
        "num_hidden_nodes": [4],
        "cardinality": [2],
        "embedding_dimension": [2],
        "num_time_features": 3,
    }
    rede = DeepNPTSNetworkDiscreteRegistrada(**parametros)
    chaves = set(rede.state_dict())

    assert "embedder.embedders.0.weight" in chaves
    assert any(
        parametro is rede.embedder.embedders[0].weight
        for parametro in rede.parameters()
    )

    estado = {chave: valor.detach().clone() for chave, valor in rede.state_dict().items()}
    restaurada = DeepNPTSNetworkDiscreteRegistrada(**parametros)
    restaurada.load_state_dict(estado)

    assert torch.equal(
        rede.embedder.embedders[0].weight,
        restaurada.embedder.embedders[0].weight,
    )


@pytest.mark.parametrize(
    "classe",
    [globais.DeepNPTSGlobalGluonTS, globais.DeepARGlobalGluonTS],
)
def test_predictor_e_mapeamento_sao_persistidos_e_restaurados(
    api_falsa, tmp_path: Path, classe
) -> None:
    modelo = classe(
        context_length=6,
        numero_localidades_esperado=2,
        epochs=1,
        num_batches_per_epoch=1,
        num_samples=11,
    ).ajustar(_series_mensais(2))
    destino = tmp_path / classe.__name__

    assert modelo.salvar(destino) == destino
    assert (destino / "predictor-falso.txt").is_file()
    restaurado = globais.carregar_modelo_global_gluonts(destino, device="cpu")

    assert isinstance(restaurado, classe)
    assert restaurado.ajustado
    assert restaurado.context_length == 6
    assert restaurado.num_samples == 11
    assert restaurado.categorias_localidade_ == modelo.categorias_localidade_
    assert restaurado.predictor_ is _PredictorFalso.desserializado
    with pytest.raises(FileExistsError):
        modelo.salvar(destino)


@pytest.mark.skipif(
    os.environ.get("EXECUTAR_SMOKE_GLUONTS") != "1",
    reason="Smoke real opt-in; defina EXECUTAR_SMOKE_GLUONTS=1.",
)
@pytest.mark.parametrize(
    "modelo",
    [
        globais.DeepNPTSGlobalGluonTS(
            context_length=4,
            num_samples=5,
            batch_size=5,
            epochs=1,
            num_batches_per_epoch=1,
            num_hidden_nodes=(4,),
        ),
        globais.DeepARGlobalGluonTS(
            context_length=4,
            num_samples=5,
            batch_size=5,
            epochs=1,
            num_batches_per_epoch=1,
            num_layers=1,
            hidden_size=4,
            dropout_rate=0.0,
            patience=1,
            lags_seq=(1, 2, 3),
        ),
    ],
)
def test_smoke_treino_e_previsao_com_gluonts_real(modelo) -> None:
    series = _series_mensais(10, periodos=18)

    modelo.ajustar(series)
    previsoes = modelo.prever_multiplas_origens(series, ["2021-06"], num_samples=5)

    assert len(previsoes) == 10
    assert all(previsao.amostras.shape == (5, 1) for previsao in previsoes)
