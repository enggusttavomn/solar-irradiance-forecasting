"""Contratos mínimos dos artigos IEEE horário e BTSym'26 mensal."""

from __future__ import annotations

from pathlib import Path
import re


RAIZ = Path(__file__).resolve().parents[1]
ARTIGOS = (
    RAIZ / "overlief" / "IEEE" / "artigo.tex",
    RAIZ / "overlief" / "BTSym26" / "main.tex",
)


def test_ieee_declara_resultado_horario_timesnet_e_limitacoes() -> None:
    texto = ARTIGOS[0].read_text(encoding="utf-8")
    assert "TimesNet" in texto
    assert "XGBoost" not in texto
    assert "101,04" in texto
    assert "104,68" in texto
    assert "quatro métodos" in texto.lower()
    assert "redução" in texto.lower()
    assert "uma única semente" in texto.lower()
    assert "clipping" in texto.lower()
    assert "elevação solar" in texto.lower()
    assert "retrospectiv" in texto.lower()
    assert "climatologia" not in texto.lower()
    assert "DeepNPTS" not in texto
    assert "PENDENTE_" not in texto
    assert not re.search(r"@@[A-Z0-9_-]+@@", texto)


def test_btsym_preserva_resultado_mensal_dilatedrnn() -> None:
    texto = ARTIGOS[1].read_text(encoding="utf-8")
    assert "DilatedRNN" in texto
    assert "13.42" in texto
    assert "16.20" in texto
    assert "first among five" in texto
    assert "two simple baselines and two other learned models" in texto
    assert "led at only four locations" in texto
    assert "XGBoost" not in texto
    assert "tab:monthly" not in texto
    assert "Monthly MAE" not in texto
    assert "climatology" not in texto.lower()
    assert "lstm" not in texto.lower()
    assert not re.search(r"\bRNN\b", texto)
    assert "retrospectiv" in texto.lower()
    assert "TimesNet" not in texto
    assert "DeepNPTS" not in texto
    assert "MCSM" not in texto
    assert not re.search(r"@@[A-Z0-9_-]+@@", texto)


def test_agradecimentos_respeitam_o_destino_de_cada_artigo() -> None:
    ieee = ARTIGOS[0].read_text(encoding="utf-8")
    btsym = ARTIGOS[1].read_text(encoding="utf-8")

    assert "FAPEMIG" not in ieee
    assert "FAPEMIG (grant OET-00243-26)" in btsym


def test_artigos_usam_somente_as_figuras_oficiais() -> None:
    esperadas_por_artigo = {
        ARTIGOS[0]: {
            "comparacao_rmse_modelos.png",
            "previsao_horaria_timesnet_72h.png",
        },
        ARTIGOS[1]: {
            "dilatedrnn_forecast_byd_camacari.png",
        },
    }
    for caminho in ARTIGOS:
        texto = caminho.read_text(encoding="utf-8")
        usadas = {
            Path(nome).name
            for nome in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", texto)
        }
        assert usadas == esperadas_por_artigo[caminho]


def test_cada_artigo_mantem_somente_suas_figuras() -> None:
    pastas = {
        ARTIGOS[0]: RAIZ / "overlief" / "IEEE" / "figuras",
        ARTIGOS[1]: RAIZ / "overlief" / "BTSym26" / "figures",
    }
    esperadas = {
        ARTIGOS[0]: {
            "comparacao_rmse_modelos.png",
            "previsao_horaria_timesnet_72h.png",
        },
        ARTIGOS[1]: {
            "dilatedrnn_forecast_byd_camacari.png",
        },
    }
    for artigo, pasta in pastas.items():
        texto = artigo.read_text(encoding="utf-8")
        caminho_figuras = r"\graphicspath{{figuras/}}" if artigo == ARTIGOS[0] else r"\graphicspath{{figures/}}"
        assert caminho_figuras in texto
        assert pasta.is_dir()
        arquivos = {item.name for item in pasta.iterdir() if item.is_file()}
        assert arquivos == esperadas[artigo]
    # A pasta compartilhada pertence a um manuscrito MCSM legado ainda
    # versionado. Os dois artigos oficiais acima permanecem isolados nas
    # respectivas pastas, independentemente da presenca desse legado.


def test_chaves_de_citacao_estao_definidas_em_cada_artigo() -> None:
    for caminho in ARTIGOS:
        texto = caminho.read_text(encoding="utf-8")
        citadas: set[str] = set()
        for grupo in re.findall(r"\\cite[pt]?\{([^}]+)\}", texto):
            citadas.update(chave.strip() for chave in grupo.split(","))
        definidas = set(re.findall(r"\\bibitem(?:\[[^]]*\])?\{([^}]+)\}", texto))
        assert citadas
        assert citadas <= definidas
