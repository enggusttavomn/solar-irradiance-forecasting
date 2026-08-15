"""Testes de aceitação dos artefatos mensais usados nos artigos."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import r2_score


RAIZ = Path(__file__).resolve().parents[1]
BASE = RAIZ / "resultados" / "avaliacao_mensal_corrigida"
if not BASE.is_dir():
    pytest.skip(
        "Artefatos mensais não estão presentes nesta cópia do repositório.",
        allow_module_level=True,
    )

MODELOS = {
    "XGBoost": "xgboost",
    "MLP": "mlp",
    "RNN": "rnn",
    "LSTM": "lstm",
    "VizinhosHistoricos": "vizinhoshistoricos",
    "Persistencia": "persistencia",
    "SazonalIngenuo": "sazonalingenuo",
    "Climatologia": "climatologia",
}


def _arquivos_previsao() -> list[Path]:
    return sorted((BASE / "previsoes").glob("*/previsoes_modelos.csv"))


def test_previsoes_publicaveis_cobrem_dez_localidades_e_2024() -> None:
    arquivos = _arquivos_previsao()
    assert len(arquivos) == 10
    for arquivo in arquivos:
        dados = pd.read_csv(arquivo, parse_dates=["data"])
        assert len(dados) == 12
        assert dados["data"].dt.strftime("%Y-%m").tolist() == [
            f"2024-{mes:02d}" for mes in range(1, 13)
        ]
        colunas_fisicas = ["ghi_real_wm2"] + [
            f"ghi_previsto_{slug}_wm2" for slug in MODELOS.values()
        ]
        assert set(colunas_fisicas).issubset(dados.columns)
        assert np.isfinite(dados[colunas_fisicas].to_numpy(dtype=float)).all()


def test_features_publicaveis_usam_v2_continua_e_doze_lags() -> None:
    pasta = RAIZ / "dados" / "processados" / "localidades_ev"
    arquivos = sorted(pasta.glob("*_features_mensal_v2.csv"))
    assert len(arquivos) == 10

    lags_esperados = {f"ghi_t-{lag}" for lag in range(1, 13)}
    for arquivo in arquivos:
        dados = pd.read_csv(arquivo, parse_dates=["data", "data_alvo"])
        assert len(dados) == 60
        assert set(dados.columns).intersection(lags_esperados) == lags_esperados
        assert {"mes_alvo_sin", "mes_alvo_cos", "ghi_alvo"}.issubset(dados.columns)
        assert dados["data_alvo"].dt.strftime("%Y-%m").tolist() == [
            f"{ano}-{mes:02d}"
            for ano in range(2020, 2025)
            for mes in range(1, 13)
        ]
        # O alvo oficial e continuo; a coluna discretizada existe so para
        # auditoria do pipeline anterior e nao coincide com ele.
        assert dados["ghi_alvo"].nunique() > 20
        assert not np.allclose(
            dados["ghi_alvo"],
            dados["ghi_alvo_quantizado"] / 127.0,
            rtol=0,
            atol=1e-12,
        )


def test_metricas_fisicas_recalculam_exatamente_das_previsoes() -> None:
    publicadas = pd.read_csv(BASE / "metricas_geral.csv").set_index(
        ["Localidade", "Modelo"]
    )
    assert len(publicadas) == 80
    assert not {"MAE", "MSE", "RMSE", "R2"}.intersection(publicadas.columns)

    slugs_localidades = {
        arquivo.parent.name: localidade
        for localidade in publicadas.index.get_level_values("Localidade").unique()
        for arquivo in _arquivos_previsao()
        if arquivo.parent.name
        == localidade.lower().replace(" ", "_").replace("-", "_")
    }
    assert len(slugs_localidades) == 10

    for arquivo in _arquivos_previsao():
        dados = pd.read_csv(arquivo)
        localidade = slugs_localidades[arquivo.parent.name]
        real = dados["ghi_real_wm2"].to_numpy(dtype=float)
        for modelo, slug in MODELOS.items():
            previsto = dados[f"ghi_previsto_{slug}_wm2"].to_numpy(dtype=float)
            erro = real - previsto
            esperado = publicadas.loc[(localidade, modelo)]
            assert np.mean(np.abs(erro)) == pytest.approx(esperado["MAE_wm2"], abs=1e-10)
            assert np.mean(erro**2) == pytest.approx(esperado["MSE_wm2"], abs=1e-8)
            assert np.sqrt(np.mean(erro**2)) == pytest.approx(
                esperado["RMSE_wm2"], abs=1e-10
            )
            assert r2_score(real, previsto) == pytest.approx(
                esperado["R2_wm2"], abs=1e-12
            )

    tabela = publicadas.reset_index()
    vencedores = (
        tabela.sort_values(["Localidade", "MAE_wm2", "Modelo"])
        .groupby("Localidade", sort=False)
        .first()["Modelo"]
        .value_counts()
        .to_dict()
    )
    assert vencedores == {
        "MLP": 4,
        "Climatologia": 3,
        "XGBoost": 2,
        "VizinhosHistoricos": 1,
    }


def test_baselines_publicadas_sao_causais_e_derivadas_dos_csvs_diarios() -> None:
    pasta_brutos = RAIZ / "dados" / "brutos" / "localidades_ev"
    for arquivo in _arquivos_previsao():
        previsoes = pd.read_csv(arquivo, parse_dates=["data"]).set_index("data")
        bruto = pd.read_csv(
            pasta_brutos / f"{arquivo.parent.name}.csv",
            usecols=["data", "ghi"],
            parse_dates=["data"],
        )
        mensal = bruto.set_index("data")["ghi"].resample("ME").mean()
        teste = mensal.loc["2024-01-01":"2024-12-31"]
        persistencia = mensal.shift(1).loc[teste.index]
        sazonal = mensal.shift(12).loc[teste.index]
        climatologia = pd.Series(
            [
                mensal.loc[
                    (mensal.index.year >= 2020)
                    & (mensal.index.year <= 2023)
                    & (mensal.index.month == data.month)
                ].mean()
                for data in teste.index
            ],
            index=teste.index,
        )
        assert np.allclose(previsoes["ghi_real_wm2"], teste, rtol=0, atol=1e-10)
        assert np.allclose(
            previsoes["ghi_previsto_persistencia_wm2"],
            persistencia,
            rtol=0,
            atol=1e-10,
        )
        assert np.allclose(
            previsoes["ghi_previsto_sazonalingenuo_wm2"],
            sazonal,
            rtol=0,
            atol=1e-10,
        )
        assert np.allclose(
            previsoes["ghi_previsto_climatologia_wm2"],
            climatologia,
            rtol=0,
            atol=1e-10,
        )


def test_protocolo_e_repeticoes_correspondem_ao_texto_publicado() -> None:
    protocolo = pd.read_csv(BASE / "protocolo_temporal.csv")
    assert len(protocolo) == 10
    assert set(protocolo["N_treino"]) == {48}
    assert set(protocolo["N_teste"]) == {12}
    assert set(protocolo["Horizonte_passos"]) == {1}
    assert set(protocolo["Transformacao_alvo"]) == {"continuo_minmax"}
    assert set(protocolo["Status_inferencia"]) == {"retrospectiva_exploratoria"}
    assert protocolo["Features"].str.count("ghi_t-").eq(12).all()

    seeds = pd.read_csv(BASE / "metricas_por_seed.csv")
    contagens = seeds.groupby(["Localidade", "Modelo"])["Seed"].nunique()
    assert set(contagens.xs("MLP", level="Modelo")) == {3}
    assert set(contagens.xs("RNN", level="Modelo")) == {3}
    assert set(contagens.xs("LSTM", level="Modelo")) == {3}
    assert set(contagens.xs("XGBoost", level="Modelo")) == {1}
    assert set(contagens.xs("VizinhosHistoricos", level="Modelo")) == {1}

    comparacao = pd.read_csv(BASE / "comparacao_climatologia.csv").set_index("Modelo")
    assert comparacao.loc["MLP", "Diferenca_MAE_wm2"] == pytest.approx(
        0.7604191270, abs=1e-9
    )
    assert comparacao.loc["MLP", "Wilcoxon_p_Holm"] == pytest.approx(0.4921875)
    assert comparacao.loc["VizinhosHistoricos", "Diferenca_MAE_wm2"] == pytest.approx(
        3.422948, abs=1e-6
    )
    assert comparacao.loc["VizinhosHistoricos", "IC95_inferior"] == pytest.approx(
        1.753405, abs=1e-6
    )
    assert comparacao.loc["VizinhosHistoricos", "IC95_superior"] == pytest.approx(
        5.083148, abs=1e-6
    )
    assert comparacao.loc["VizinhosHistoricos", "Wilcoxon_p_Holm"] == pytest.approx(
        0.0234375
    )


def test_todos_os_modelos_e_metadados_das_seeds_foram_persistidos() -> None:
    pasta = RAIZ / "resultados" / "modelos" / "avaliacao_mensal_corrigida"
    arquivos = list(pasta.iterdir())
    assert sum(caminho.suffix == ".joblib" for caminho in arquivos) == 50
    assert sum(caminho.suffix == ".keras" for caminho in arquivos) == 60
    assert sum(caminho.name.endswith(".metadata.json") for caminho in arquivos) == 60

    for arquivo_previsao in _arquivos_previsao():
        slug = arquivo_previsao.parent.name
        assert (pasta / f"xgboost_{slug}.joblib").is_file()
        assert (pasta / f"vizinhos_historicos_{slug}.joblib").is_file()
        for seed in (42, 43, 44):
            assert (pasta / f"mlp_{slug}_seed{seed}.joblib").is_file()
            for rede in ("rnn", "lstm"):
                keras = pasta / f"{rede}_{slug}_seed{seed}.keras"
                assert keras.is_file()
                assert keras.with_suffix(".metadata.json").is_file()


def test_reavaliacao_dos_modelos_salvos_reconstroi_os_ensembles() -> None:
    pasta_seeds = BASE / "previsoes_seeds"
    assert len(list(pasta_seeds.glob("*/*.csv"))) == 110
    modelos = {
        "xgboost": ("xgboost", (42,)),
        "mlp": ("mlp", (42, 43, 44)),
        "rnn": ("rnn", (42, 43, 44)),
        "lstm": ("lstm", (42, 43, 44)),
        "vizinhoshistoricos": ("vizinhos_historicos", (42,)),
    }
    for arquivo_principal in _arquivos_previsao():
        slug_local = arquivo_principal.parent.name
        principal = pd.read_csv(arquivo_principal)
        for slug_coluna, (slug_arquivo, sementes) in modelos.items():
            previsoes = []
            for seed in sementes:
                arquivo_seed = (
                    pasta_seeds
                    / slug_local
                    / f"previsoes_{slug_arquivo}_seed{seed}.csv"
                )
                assert arquivo_seed.is_file()
                dados_seed = pd.read_csv(arquivo_seed)
                assert len(dados_seed) == 12
                previsoes.append(
                    dados_seed["ghi_previsto_normalizado"].to_numpy(dtype=float)
                )
            ensemble = np.mean(np.vstack(previsoes), axis=0)
            publicado = principal[
                f"ghi_previsto_{slug_coluna}_normalizado"
            ].to_numpy(dtype=float)
            assert np.allclose(ensemble, publicado, rtol=0, atol=2e-6)


def test_manifesto_referencia_os_bytes_atuais() -> None:
    manifesto = json.loads((BASE / "manifesto_execucao.json").read_text(encoding="utf-8"))
    config = manifesto["configuracao"]
    assert config["frequencia"] == "mensal"
    assert config["repeticoes_redes"] == 3
    assert config["quantizacao_modelagem"] is False
    assert config["metrica_primaria"] == "MAE_wm2"
    assert config["referencia_primaria"] == "Climatologia"

    for registro in manifesto["arquivos_entrada"]:
        caminho = RAIZ / registro["caminho"]
        assert caminho.is_file(), registro["caminho"]
        digest = hashlib.sha256(caminho.read_bytes()).hexdigest()
        assert digest == registro["sha256"], registro["caminho"]
