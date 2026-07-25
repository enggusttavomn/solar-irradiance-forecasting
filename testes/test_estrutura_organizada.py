"""Contratos da camada publica reorganizada do projeto."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from codigo_fonte.modelos.probabilisticos import DeepAR, DeepNPTS
from codigo_fonte.modelos.referencias_simples.climatologia import prever as climatologia
from codigo_fonte.modelos.referencias_simples.persistencia import prever as persistencia
from codigo_fonte.modelos.referencias_simples.sazonal_ingenuo import prever as sazonal
from codigo_fonte.modelos_tabulares_globais import prever_baselines_mensais
from codigo_fonte.preparacao.base_mensal import carregar_base_mensal


RAIZ = Path(__file__).resolve().parents[1]


def test_cada_modelo_possui_modulo_publico_proprio() -> None:
    esperados = {
        "modelos/referencias_simples/persistencia.py",
        "modelos/referencias_simples/sazonal_ingenuo.py",
        "modelos/referencias_simples/climatologia.py",
        "modelos/tabulares/xgboost.py",
        "modelos/tabulares/mlp.py",
        "modelos/recorrentes/rnn.py",
        "modelos/recorrentes/lstm.py",
        "modelos/recorrentes/dilated_rnn.py",
        "modelos/probabilisticos/deepar.py",
        "modelos/probabilisticos/deepnpts.py",
    }
    encontrados = {
        str(caminho.relative_to(RAIZ / "codigo_fonte"))
        for caminho in (RAIZ / "codigo_fonte" / "modelos").rglob("*.py")
        if caminho.name != "__init__.py"
    }
    assert esperados <= encontrados


def test_referencias_publicas_reproduzem_motor_canonico() -> None:
    base = carregar_base_mensal()
    canonicas = prever_baselines_mensais(base)
    np.testing.assert_allclose(persistencia(base), canonicas["Persistencia"])
    np.testing.assert_allclose(sazonal(base), canonicas["SazonalIngenuo"])
    np.testing.assert_allclose(climatologia(base), canonicas["Climatologia"])


def test_classes_probabilisticas_publicas_correspondem_aos_modelos() -> None:
    assert DeepAR.nome_modelo == "DeepAR"
    assert DeepNPTS.nome_modelo == "DeepNPTS"


def test_site_incorpora_grade_canonica_completa() -> None:
    pagina = (RAIZ / "site" / "resultados.html").read_text(encoding="utf-8")
    inicio = pagina.index('<script id="project-data" type="application/json">')
    inicio = pagina.index(">", inicio) + 1
    fim = pagina.index("</script>", inicio)
    dados = json.loads(pagina[inicio:fim])
    assert len(dados["metricasLocais"]) == 100
    assert len(dados["ranking"]) == 10
    assert len(dados["auditoria"]) == 10


def test_site_possui_quatro_paginas_com_navegacao_horizontal() -> None:
    paginas = {
        "index.html": "HOME",
        "data.html": "DATA",
        "modelos.html": "ML MODELS",
        "resultados.html": "RESULTADOS",
    }
    for arquivo, item_ativo in paginas.items():
        texto = (RAIZ / "site" / arquivo).read_text(encoding="utf-8")
        assert 'class="topbar"' in texto
        assert 'class="nav-links"' in texto
        assert f'>{item_ativo}</a>' in texto
        assert texto.count('aria-current="page"') == 1


def test_indice_de_artigos_aponta_para_os_manuscritos_reais() -> None:
    assert (RAIZ / "artigos" / "ieee" / "artigo.tex").is_file()
    assert (RAIZ / "artigos" / "mcsm" / "artigo_mcsm.tex").is_file()
