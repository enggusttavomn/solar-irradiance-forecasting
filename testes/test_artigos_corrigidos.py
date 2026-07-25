"""Contratos mínimos entre os artigos e a avaliação mensal canônica."""

from __future__ import annotations

from pathlib import Path
import re


RAIZ = Path(__file__).resolve().parents[1]
ARTIGOS = (
    RAIZ / "overlief" / "IEEE" / "artigo.tex",
    RAIZ / "overlief" / "MCSM" / "artigo_mcsm.tex",
)


def test_artigos_declaram_o_resultado_corrigido_e_suas_limitacoes() -> None:
    for caminho in ARTIGOS:
        texto = caminho.read_text(encoding="utf-8")
        assert "climatologia" in texto.lower()
        assert "12,07" in texto
        assert "12,22" in texto
        assert "17,70" in texto
        assert (
            "9º lugar entre 10 métodos" in texto
            or "9ª entre 10 métodos" in texto
        )
        assert "9,22" in texto
        assert "retrospectiv" in texto.lower()
        assert "exploratóri" in texto.lower()
        assert "GluonTS 0.16.2" in texto
        assert "embeddings" in texto
        assert "superioridade universal" in texto
        assert "12,96" not in texto
        assert not re.search(r"@@[A-Z0-9_-]+@@", texto)


def test_agradecimentos_respeitam_o_destino_de_cada_artigo() -> None:
    ieee = ARTIGOS[0].read_text(encoding="utf-8")
    mcsm = ARTIGOS[1].read_text(encoding="utf-8")

    assert "FAPEMIG" not in ieee
    assert "FAPEMIG (grant n OET-00243-26)" in mcsm


def test_artigos_usam_somente_as_figuras_oficiais() -> None:
    esperadas_por_artigo = {
        ARTIGOS[0]: {
            "previsao_mensal_byd_camacari.png",
            "intervalo_deepnpts_byd_camacari.png",
        },
        ARTIGOS[1]: {
            "banner_iii_mcsm.png",
            "previsao_mensal_byd_camacari.png",
            "intervalo_deepnpts_byd_camacari.png",
        },
    }
    for caminho in ARTIGOS:
        texto = caminho.read_text(encoding="utf-8")
        usadas = {
            Path(nome).name
            for nome in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", texto)
        }
        assert usadas == esperadas_por_artigo[caminho]


def test_chaves_de_citacao_estao_definidas_em_cada_artigo() -> None:
    for caminho in ARTIGOS:
        texto = caminho.read_text(encoding="utf-8")
        citadas: set[str] = set()
        for grupo in re.findall(r"\\cite[pt]?\{([^}]+)\}", texto):
            citadas.update(chave.strip() for chave in grupo.split(","))
        definidas = set(re.findall(r"\\bibitem(?:\[[^]]*\])?\{([^}]+)\}", texto))
        assert citadas
        assert citadas <= definidas
