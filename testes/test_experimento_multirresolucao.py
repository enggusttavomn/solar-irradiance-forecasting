"""Testes do protocolo pareado multirresolucao."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

import codigo_fonte.experimento_multirresolucao as multires
from codigo_fonte.experimento_horario_timesnet import JanelasHorarias
from codigo_fonte.experimento_multirresolucao import (
    ConfiguracaoMultirresolucao,
    Estimativa,
    IntervaloParticao,
    SerieResolucao,
    TAREFA_HORARIA_EXTENSAO,
    TAREFAS_CANONICAS,
    ajustar_escalas_pre_corte,
    agregar_series_mensais,
    anexar_dilated_a_previsoes_oficiais,
    calcular_metricas_estimativas,
    carregar_series_diarias,
    construir_contrato,
    construir_janelas,
    criar_modelo_neural,
    executar_avaliacao_multirresolucao,
    prever_climatologia,
    prever_sazonal_anual,
    salvar_csv_atomico,
    salvar_joblib_atomico,
    salvar_json_atomico,
    salvar_npz_atomico,
    salvar_torch_atomico,
    sha256_arquivo,
    validar_ou_criar_contrato,
)


def _serie_sintetica_diaria(tmp_path: Path) -> SerieResolucao:
    datas = pd.date_range("2019-01-01", "2024-12-31", freq="D")
    valores = (
        100.0
        + 10.0 * np.sin(2 * np.pi * datas.dayofyear.to_numpy() / 365.25)
        + (datas.year.to_numpy() - 2019)
    ).astype(np.float32)
    fonte = tmp_path / "serie.csv"
    fonte.write_text("fonte de teste\n", encoding="utf-8")
    return SerieResolucao(
        localidade="Fabrica Teste",
        localidade_id=0,
        pais="Teste",
        datas=datas,
        ghi=valores,
        frequencia="D",
        caminho_fonte=fonte,
    )


def test_especificacoes_canonicas_e_contagens_reais() -> None:
    series_diarias, _ = carregar_series_diarias()
    assert len(series_diarias) == 10
    mensal = agregar_series_mensais(series_diarias)
    esperadas = {
        "daily_30": (1067, 336, 1432, 337),
        "monthly_1": (36, 12, 48, 12),
        "monthly_6": (31, 7, 43, 7),
    }
    for nome, contagens in esperadas.items():
        tarefa = TAREFAS_CANONICAS[nome]
        series = series_diarias if tarefa.resolucao == "diaria" else mensal
        observadas = []
        for particao in ("ajuste", "validacao", "refit", "teste"):
            janelas = construir_janelas(
                series[:1],
                seq_len=tarefa.seq_len,
                pred_len=tarefa.pred_len,
                intervalo=getattr(tarefa, particao),
                particao=particao,
            )
            observadas.append(len(janelas.x_bruto))
            assert pd.Timestamp(janelas.datas_alvo.max()) <= pd.Timestamp(
                getattr(tarefa, particao).fim_alvo
            )
        assert tuple(observadas) == contagens


def test_escala_pre_corte_nao_muda_com_futuro(tmp_path: Path) -> None:
    serie = _serie_sintetica_diaria(tmp_path)
    alterados = serie.ghi.copy()
    alterados[serie.datas >= "2023-01-01"] += 10000.0
    serie_alterada = replace(serie, ghi=alterados)
    escala_original = ajustar_escalas_pre_corte(
        [serie],
        fim_exclusivo="2023-01-01",
        nome_ajuste="selecao",
    )
    escala_alterada = ajustar_escalas_pre_corte(
        [serie_alterada],
        fim_exclusivo="2023-01-01",
        nome_ajuste="selecao",
    )
    pd.testing.assert_frame_equal(escala_original, escala_alterada)


def test_baselines_sao_causais_e_tratam_29_fevereiro(tmp_path: Path) -> None:
    serie = _serie_sintetica_diaria(tmp_path)
    intervalo = IntervaloParticao("2024-02-20", "2024-02-20", "2024-03-20", 1)
    janelas = construir_janelas(
        [serie],
        seq_len=365,
        pred_len=30,
        intervalo=intervalo,
        particao="teste",
    )
    sazonal = prever_sazonal_anual(janelas, [serie])
    indice_29 = list(pd.to_datetime(janelas.datas_alvo[0])).index(pd.Timestamp("2024-02-29"))
    esperado = serie.ghi[serie.datas.get_loc(pd.Timestamp("2023-02-28"))]
    assert sazonal[0, indice_29] == pytest.approx(float(esperado))
    clima_original = prever_climatologia(
        janelas,
        [serie],
        fim_ajuste_exclusivo="2024-01-01",
    )
    futuro = serie.ghi.copy()
    futuro[serie.datas >= "2024-01-01"] += 5000.0
    clima_futuro = prever_climatologia(
        janelas,
        [replace(serie, ghi=futuro)],
        fim_ajuste_exclusivo="2024-01-01",
    )
    np.testing.assert_allclose(clima_original, clima_futuro)


@pytest.mark.parametrize("nome", ["LSTM", "TimesNet", "DilatedRNN"])
def test_redes_compartilham_forma_de_entrada_e_saida(nome: str) -> None:
    tarefa = TAREFAS_CANONICAS["monthly_6"]
    config = ConfiguracaoMultirresolucao(modo_execucao="smoke")
    modelo = criar_modelo_neural(
        nome,
        tarefa=tarefa,
        configuracao=config,
        num_localidades=2,
        semente=11,
    )
    saida = modelo(torch.rand(3, 12), torch.tensor([0, 1, 0]))
    assert saida.shape == (3, 6)
    assert torch.isfinite(saida).all()


def test_metricas_separam_prefixo_e_lead_exato() -> None:
    tarefa = TAREFAS_CANONICAS["monthly_6"]
    y = np.arange(1, 13, dtype=np.float32).reshape(2, 6)
    janelas = construir_janelas(
        [
            SerieResolucao(
                localidade="A",
                localidade_id=0,
                pais="X",
                datas=pd.date_range("2019-01-31", periods=30, freq="ME"),
                ghi=np.arange(30, dtype=np.float32),
                frequencia="ME",
                caminho_fonte=Path("sintetica.csv"),
            )
        ],
        seq_len=12,
        pred_len=6,
        intervalo=IntervaloParticao("2020-01-31", "2020-02-29", "2020-07-31", 2),
        particao="teste",
    )
    janelas = replace(janelas, y_bruto=y)
    previsto = y.copy()
    previsto[:, 5] += 6
    local, macro = calcular_metricas_estimativas(
        tarefa=tarefa,
        particao="teste",
        janelas=janelas,
        estimativas=[Estimativa("TimesNet", "ensemble", None, previsto, previsto)],
    )
    lead_3 = local.query("horizonte == 3 and tipo_horizonte == 'lead_exato'")
    lead_6 = local.query("horizonte == 6 and tipo_horizonte == 'lead_exato'")
    cumulativo_6 = macro.query("horizonte == 6 and tipo_horizonte == 'cumulativo'")
    assert lead_3["MAE_wm2"].iloc[0] == 0
    assert lead_6["MAE_wm2"].iloc[0] == 6
    assert cumulativo_6["MAE_wm2"].iloc[0] == 1


def test_retomada_exige_contrato_exato(tmp_path: Path) -> None:
    entrada = tmp_path / "entrada.csv"
    entrada.write_text("data,ghi\n2024-01-01,1\n", encoding="utf-8")
    tarefa = TAREFAS_CANONICAS["monthly_1"]
    config = ConfiguracaoMultirresolucao(modo_execucao="smoke")
    contrato = construir_contrato(
        tarefa=tarefa,
        configuracao=config,
        arquivos_entrada=[entrada],
    )
    saida = tmp_path / "saida"
    saida.mkdir()
    orfao = saida / ".contrato_execucao.json.0123456789abcdef0123456789abcdef.tmp"
    orfao.write_text("interrompido", encoding="utf-8")
    validar_ou_criar_contrato(saida, contrato, retomar=True)
    assert not orfao.exists()
    validar_ou_criar_contrato(saida, contrato, retomar=True)
    divergente = construir_contrato(
        tarefa=tarefa,
        configuracao=replace(config, sementes=(23,)),
        arquivos_entrada=[entrada],
    )
    with pytest.raises(RuntimeError, match="outro contrato"):
        validar_ou_criar_contrato(saida, divergente, retomar=True)


def test_todas_gravacoes_atomicas_usam_retry_e_fallback_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simula WinError 32 em todo os.replace e exercita ambos os fallbacks."""

    existente = tmp_path / "existente.json"
    salvar_json_atomico({"versao": 1}, existente)
    chamadas = 0

    def bloqueado(*_args: object, **_kwargs: object) -> None:
        nonlocal chamadas
        chamadas += 1
        erro = PermissionError(13, "arquivo em uso pelo indexador")
        erro.winerror = 32  # type: ignore[attr-defined]
        raise erro

    monkeypatch.setattr(multires, "ATRASOS_SUBSTITUICAO_ATOMICA_S", (0.0, 0.0))
    monkeypatch.setattr(multires.os, "replace", bloqueado)
    salvar_json_atomico({"versao": 2}, existente)
    quadro = pd.DataFrame({"a": [1, 2]})
    caminho_csv = tmp_path / "quadro.csv"
    caminho_npz = tmp_path / "matrizes.npz"
    caminho_torch = tmp_path / "modelo.pt"
    caminho_joblib = tmp_path / "objeto.joblib"
    salvar_csv_atomico(quadro, caminho_csv)
    salvar_npz_atomico(caminho_npz, x=np.asarray([1, 2, 3]))
    salvar_torch_atomico({"x": torch.tensor([4.0])}, caminho_torch)
    salvar_joblib_atomico({"chave": [5, 6]}, caminho_joblib)
    assert json.loads(existente.read_text("utf-8")) == {"versao": 2}
    pd.testing.assert_frame_equal(pd.read_csv(caminho_csv), quadro)
    with np.load(caminho_npz) as conteudo:
        np.testing.assert_array_equal(conteudo["x"], [1, 2, 3])
    assert torch.load(caminho_torch, weights_only=True)["x"].item() == 4
    assert multires.joblib.load(caminho_joblib) == {"chave": [5, 6]}
    assert chamadas >= 10
    assert not list(tmp_path.rglob(".*.tmp"))


def test_alinhamento_horario_nao_altera_fonte(tmp_path: Path) -> None:
    origens_utc = pd.DatetimeIndex(
        ["2024-01-01 03:00:00+00:00", "2024-01-02 03:00:00+00:00"]
    )
    janelas = JanelasHorarias(
        x_bruto=np.ones((2, 2), dtype=np.float32),
        y_bruto=np.asarray([[1, 2], [3, 4]], dtype=np.float32),
        localidade_id=np.zeros(2, dtype=np.int64),
        localidade=np.asarray(["A", "A"], dtype=object),
        origem_utc=origens_utc,
        origem_local=pd.DatetimeIndex(["2024-01-01", "2024-01-02"]),
        seq_len=2,
        pred_len=2,
        particao="teste",
    )
    linhas = []
    for i, origem in enumerate(origens_utc):
        for passo in (1, 2):
            linhas.append(
                {
                    "particao": "teste",
                    "semente": 42,
                    "localidade": "A",
                    "localidade_id": 0,
                    "origem_utc": origem,
                    "timestamp_alvo_utc": origem + pd.Timedelta(hours=passo - 1),
                    "passo_h": passo,
                    "ghi_real_wm2": float(janelas.y_bruto[i, passo - 1]),
                    "previsao_pos_timesnet_wm2": 1.0,
                }
            )
    fonte = tmp_path / "oficial.csv.gz"
    pd.DataFrame(linhas).to_csv(fonte, index=False, compression="gzip")
    hash_antes = sha256_arquivo(fonte)
    combinado = anexar_dilated_a_previsoes_oficiais(
        caminho_oficial=fonte,
        janelas=janelas,
        previsao_bruta=np.zeros((2, 2)),
        previsao_pos=np.zeros((2, 2)),
    )
    assert sha256_arquivo(fonte) == hash_antes
    assert "previsao_pos_dilatedrnn_wm2" in combinado
    assert len(combinado) == 4


def test_smoke_mensal_produz_sete_modelos_e_retomada(tmp_path: Path) -> None:
    pytest.importorskip("xgboost")
    config = ConfiguracaoMultirresolucao(modo_execucao="smoke")
    resumos = executar_avaliacao_multirresolucao(
        tarefas="monthly_1",
        configuracao=config,
        pasta_saida=tmp_path,
    )
    pasta = tmp_path / "monthly_1"
    assert resumos[0]["etapa"] == "concluida"
    assert resumos[0]["resultado_smoke_nao_publicavel"] is True
    metricas = pd.read_csv(pasta / "metricas_macro.csv")
    assert set(metricas["modelo"]) == {
        "Persistencia",
        "Sazonal ingenuo",
        "Climatologia",
        "XGBoost",
        "LSTM",
        "TimesNet",
        "DilatedRNN",
    }
    previsoes = pd.read_csv(pasta / "previsoes_teste.csv.gz")
    assert "previsao_pos_timesnet_ensemble_wm2" in previsoes
    assert "previsao_pos_dilatedrnn_ensemble_wm2" in previsoes
    caches = sorted((pasta / "cache").glob("*.npz"))
    assert len(caches) == 4
    mtimes = {p.name: p.stat().st_mtime_ns for p in caches}
    executar_avaliacao_multirresolucao(
        tarefas="monthly_1",
        configuracao=config,
        pasta_saida=tmp_path,
        retomar=True,
    )
    assert {p.name: p.stat().st_mtime_ns for p in caches} == mtimes
    manifesto = json.loads((pasta / "manifesto_artefatos.json").read_text("utf-8"))
    assert manifesto["N_arquivos"] >= 20


def test_contrato_horario_registra_seed42_e_dimensoes() -> None:
    assert TAREFA_HORARIA_EXTENSAO.seq_len == 336
    assert TAREFA_HORARIA_EXTENSAO.pred_len == 72
    assert TAREFA_HORARIA_EXTENSAO.horizontes == (24, 48, 72)
