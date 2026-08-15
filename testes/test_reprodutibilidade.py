"""Testes dos hashes, sementes e manifestos de execucao cientifica."""

from __future__ import annotations

import hashlib
import json
import random

import numpy as np
import pytest

from codigo_fonte.reprodutibilidade import (
    DEPENDENCIAS_CIENTIFICAS,
    construir_manifesto,
    definir_seed_global,
    json_canonico,
    salvar_manifesto,
    sha256_arquivo,
    sha256_configuracao,
)


def test_json_canonico_independe_da_ordem_das_chaves() -> None:
    primeiro = {"b": [2, 1], "a": {"y": 2, "x": 1}}
    segundo = {"a": {"x": 1, "y": 2}, "b": [2, 1]}

    assert json_canonico(primeiro) == json_canonico(segundo)
    assert sha256_configuracao(primeiro) == sha256_configuracao(segundo)


def test_sha256_arquivo_confere_com_hash_conhecido(tmp_path) -> None:
    arquivo = tmp_path / "entrada.csv"
    conteudo = b"data,ghi\n2024-01-01,100\n"
    arquivo.write_bytes(conteudo)

    assert sha256_arquivo(arquivo) == hashlib.sha256(conteudo).hexdigest()


def test_seed_global_reproduz_python_e_numpy() -> None:
    definir_seed_global(
        123,
        configurar_tensorflow=False,
        configurar_pytorch=False,
    )
    primeira = (random.random(), np.random.random())
    definir_seed_global(
        123,
        configurar_tensorflow=False,
        configurar_pytorch=False,
    )
    segunda = (random.random(), np.random.random())

    assert primeira == pytest.approx(segunda)


def test_seed_global_reproduz_pytorch_quando_solicitado() -> None:
    torch = pytest.importorskip("torch")

    estado = definir_seed_global(
        321,
        configurar_tensorflow=False,
        configurar_pytorch=True,
        operacoes_pytorch_deterministicas=False,
    )
    primeira = torch.rand(4)
    definir_seed_global(
        321,
        configurar_tensorflow=False,
        configurar_pytorch=True,
        operacoes_pytorch_deterministicas=False,
    )
    segunda = torch.rand(4)

    assert estado["pytorch"] is True
    assert estado["pytorch_deterministico"] is False
    assert torch.equal(primeira, segunda)


def test_manifesto_padrao_inclui_dependencias_do_experimento_canonico() -> None:
    esperadas = {
        "numpy",
        "pandas",
        "scipy",
        "matplotlib",
        "joblib",
        "scikit-learn",
        "xgboost",
        "tensorflow",
        "keras",
        "torch",
        "gluonts",
        "lightning",
        "pytorch-lightning",
    }

    assert esperadas <= DEPENDENCIAS_CIENTIFICAS.keys()
    manifesto = construir_manifesto()
    assert esperadas <= manifesto["ambiente"]["dependencias"].keys()


def test_manifesto_registra_configuracao_ambiente_e_entrada(tmp_path) -> None:
    entrada = tmp_path / "dados.csv"
    entrada.write_text("ghi\n100\n", encoding="utf-8")
    configuracao = {"frequencia": "mensal", "horizonte": 1}

    manifesto = construir_manifesto(
        arquivos_entrada=[entrada],
        configuracao=configuracao,
        seed=42,
        raiz_projeto=tmp_path,
        dependencias={"pytest": "pytest"},
    )

    assert manifesto["configuracao"] == configuracao
    assert manifesto["configuracao_sha256"] == sha256_configuracao(configuracao)
    assert manifesto["arquivos_entrada"][0]["caminho"] == "dados.csv"
    assert manifesto["arquivos_entrada"][0]["sha256"] == sha256_arquivo(entrada)
    assert manifesto["ambiente"]["dependencias"]["pytest"]


def test_salvar_manifesto_produz_json_valido_sem_temporario_residual(tmp_path) -> None:
    destino = tmp_path / "artefatos" / "manifesto.json"

    salvo = salvar_manifesto(
        destino,
        configuracao={"lags": (1, 2, 3)},
        dependencias={},
    )

    assert json.loads(destino.read_text(encoding="utf-8")) == salvo
    assert not (destino.parent / ".manifesto.json.tmp").exists()
