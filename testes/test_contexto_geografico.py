"""Testes do contexto geográfico e climático das fábricas EV."""

from __future__ import annotations

from pathlib import Path

import matplotlib.image as mpimg
import pandas as pd
import pytest

from codigo_fonte.contexto_geografico import (
    DIRETORIO_KOPPEN_PADRAO,
    FONTE_DOI,
    carregar_legenda_koppen,
    construir_contexto_geografico,
    decompor_codigo_koppen,
    gerar_mapa_contexto,
    salvar_contexto_csv,
    validar_tabela_contexto,
)
from codigo_fonte.localidades_ev import LOCALIDADES_EV
from gerar_contexto_geografico import main


CLASSES_ESPERADAS = {
    "BYD Camacari": ("Af", 100),
    "Tesla Gigafactory Nevada": ("BWk", 100),
    "Tesla Gigafactory Texas": ("Cfa", 100),
    "Hyundai Metaplant Georgia": ("Cfa", 100),
    "Rivian Normal": ("Dfa", 100),
    "Tesla Fremont Factory": ("Csb", 100),
    "Lucid AMP 1 Casa Grande": ("BWh", 100),
    "GM Factory Zero": ("Dfa", 100),
    "Ford Rouge Electric Vehicle Center": ("Dfa", 100),
    "BMW San Luis Potosi": ("BSh", 50),
}

HASHES_ESPERADOS = {
    "md5_raster_classe_1km": "fe8f23532bfb59231a072398f0d9a7cb",
    "md5_raster_confianca_1km": "a87f331e406e4ef02114e1350eb2dd01",
    "md5_raster_fundo_05grau": "78d09475fa4b0dbb004b6178cba47b4a",
    "md5_legenda": "f0632ca1b3b475d3de5a143c4ee1928f",
}


@pytest.fixture(scope="module")
def tabela_real() -> pd.DataFrame:
    """Amostra os ativos reais uma vez para os testes de integração."""

    return construir_contexto_geografico()


def test_legenda_local_tem_30_classes_descricoes_e_cores() -> None:
    legenda = carregar_legenda_koppen(DIRETORIO_KOPPEN_PADRAO / "legend.txt")

    assert list(legenda) == list(range(1, 31))
    assert legenda[1].codigo == "Af"
    assert legenda[1].descricao_fonte == "Tropical, rainforest"
    assert legenda[1].rgb == (0, 0, 255)
    assert legenda[1].cor_hex == "#0000ff"
    assert legenda[30].codigo == "EF"
    assert legenda[30].descricao_fonte == "Polar, frost"


@pytest.mark.parametrize(
    "codigo,esperado",
    [
        ("Af", ("Tropical", "sem estação seca (floresta tropical)", "não se aplica")),
        ("BWk", ("Árido", "deserto", "frio")),
        ("Cfa", ("Temperado", "sem estação seca", "verão quente")),
        ("Dfa", ("Frio/continental", "sem estação seca", "verão quente")),
        ("EF", ("Polar", "gelo permanente", "não se aplica")),
    ],
)
def test_decomposicao_koppen_em_portugues(codigo, esperado) -> None:
    assert decompor_codigo_koppen(codigo) == esperado


def test_amostragem_real_preserva_ordem_classes_confianca_e_fonte(
    tabela_real: pd.DataFrame,
) -> None:
    assert tabela_real["localidade"].tolist() == [
        localidade["nome"] for localidade in LOCALIDADES_EV
    ]
    observado = {
        linha.localidade: (linha.classe_codigo, linha.confianca_pct)
        for linha in tabela_real.itertuples()
    }
    assert observado == CLASSES_ESPERADAS
    assert tabela_real["fonte_doi"].eq(FONTE_DOI).all()
    assert tabela_real["crs"].eq("EPSG:4326").all()
    assert tabela_real["cenario_produto"].eq("present").all()
    assert tabela_real["resolucao_nominal"].eq("1 km").all()
    assert tabela_real["resolucao_longitude_graus"].to_numpy() == pytest.approx(
        [1 / 120] * len(tabela_real)
    )
    assert tabela_real["distancia_ponto_centro_pixel_km"].max() < 0.8


def test_amostragem_real_registra_md5_de_todas_as_fontes(
    tabela_real: pd.DataFrame,
) -> None:
    for coluna, hash_esperado in HASHES_ESPERADOS.items():
        assert tabela_real[coluna].nunique() == 1
        assert tabela_real[coluna].iat[0] == hash_esperado


def test_csv_e_auditavel_em_utf8(
    tabela_real: pd.DataFrame,
    tmp_path: Path,
) -> None:
    destino = salvar_contexto_csv(tabela_real, tmp_path / "contexto.csv")

    bruto = destino.read_bytes()
    recarregada = pd.read_csv(destino)
    assert not bruto.startswith(b"\xef\xbb\xbf")
    assert bruto.endswith(b"\n")
    assert len(recarregada) == len(LOCALIDADES_EV)
    assert set(HASHES_ESPERADOS).issubset(recarregada.columns)
    assert recarregada.loc[
        recarregada["localidade"].eq("BMW San Luis Potosi"),
        "confianca_pct",
    ].iat[0] == 50


def test_cli_sem_mapa_gera_somente_csv(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv = tmp_path / "saida.csv"
    png = tmp_path / "nao_deve_existir.png"
    pdf = tmp_path / "nao_deve_existir.pdf"

    codigo = main(
        [
            "--diretorio-koppen",
            str(DIRETORIO_KOPPEN_PADRAO),
            "--csv",
            str(csv),
            "--mapa-png",
            str(png),
            "--mapa-pdf",
            str(pdf),
            "--sem-mapa",
        ]
    )

    saida = capsys.readouterr().out
    assert codigo == 0
    assert csv.is_file()
    assert not png.exists()
    assert not pdf.exists()
    assert "Localidades: 10" in saida
    assert "Mapas: não gerados" in saida


def test_mapa_original_e_gerado_em_png_e_pdf(
    tabela_real: pd.DataFrame,
    tmp_path: Path,
) -> None:
    png, pdf = gerar_mapa_contexto(
        tabela_real,
        caminho_png=tmp_path / "mapa.png",
        caminho_pdf=tmp_path / "mapa.pdf",
        dpi=90,
    )

    assert png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert pdf.read_bytes().startswith(b"%PDF-")
    assert png.stat().st_size > 50_000
    assert pdf.stat().st_size > 20_000
    imagem = mpimg.imread(png)
    assert imagem.shape[:2] == (810, 1440)


def test_validacao_rejeita_localidade_duplicada(
    tabela_real: pd.DataFrame,
) -> None:
    invalida = pd.concat([tabela_real, tabela_real.iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="localidades duplicadas"):
        validar_tabela_contexto(invalida)
