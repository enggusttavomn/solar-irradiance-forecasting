"""Contexto geográfico e climático auditável das localidades do estudo.

O módulo usa exclusivamente os GeoTIFFs de Beck et al. (2018) já presentes no
projeto. As classes e a confiança são amostradas nos pontos canônicos de
LOCALIDADES_EV sem interpolação espacial. O raster de 0,5 grau é usado somente
como fundo cartográfico; a classificação tabular sempre vem dos rasters
presentes de 0,008333 grau (resolução nominal de 1 km).
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import md5
from pathlib import Path
import re
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window

from codigo_fonte.localidades_ev import LOCALIDADES_EV, distancia_haversine_km


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
DIRETORIO_KOPPEN_PADRAO = (
    RAIZ_PROJETO / "dados" / "externos" / "koppen_geiger" / "Beck_KG_V1"
)
DIRETORIO_SAIDA_PADRAO = (
    RAIZ_PROJETO / "resultados" / "artigo_revista_unificado"
)
CSV_CONTEXTO_PADRAO = DIRETORIO_SAIDA_PADRAO / "contexto_geografico.csv"
MAPA_PNG_PADRAO = DIRETORIO_SAIDA_PADRAO / "mapa_contexto_geografico.png"
MAPA_PDF_PADRAO = DIRETORIO_SAIDA_PADRAO / "mapa_contexto_geografico.pdf"

NOME_CLASSE_1KM = "Beck_KG_V1_present_0p0083.tif"
NOME_CONFIANCA_1KM = "Beck_KG_V1_present_conf_0p0083.tif"
NOME_FUNDO_05GRAU = "Beck_KG_V1_present_0p5.tif"
NOME_LEGENDA = "legend.txt"

FONTE_AUTORES = (
    "Beck, H. E.; Zimmermann, N. E.; McVicar, T. R.; "
    "Vergopolan, N.; Berg, A.; Wood, E. F."
)
FONTE_TITULO = (
    "Present and future Koppen-Geiger climate classification maps "
    "at 1-km resolution"
)
FONTE_PERIODICO = "Scientific Data"
FONTE_ANO = 2018
FONTE_DOI = "10.1038/sdata.2018.214"
FONTE_URL = f"https://doi.org/{FONTE_DOI}"
VERSAO_PRODUTO = "Beck_KG_V1"
CENARIO_PRODUTO = "present"

_PADRAO_LEGENDA = re.compile(
    r"^\s*(\d+):\s+([A-Za-z]+)\s+(.+?)\s+"
    r"\[(\d+)\s+(\d+)\s+(\d+)\]\s*$"
)


@dataclass(frozen=True)
class ClasseKoppen:
    """Uma entrada auditada da legenda distribuída com os GeoTIFFs."""

    identificador: int
    codigo: str
    descricao_fonte: str
    rgb: tuple[int, int, int]

    @property
    def cor_hex(self) -> str:
        """Retorna a cor da legenda no formato hexadecimal."""

        return "#{:02x}{:02x}{:02x}".format(*self.rgb)


@dataclass(frozen=True)
class ArquivosKoppen:
    """Arquivos locais necessários para a tabela e o mapa."""

    diretorio: Path
    classe_1km: Path
    confianca_1km: Path
    fundo_05grau: Path
    legenda: Path


def resolver_arquivos_koppen(
    diretorio: str | Path = DIRETORIO_KOPPEN_PADRAO,
) -> ArquivosKoppen:
    """Resolve e valida os quatro arquivos locais exigidos pelo pipeline."""

    raiz = Path(diretorio).expanduser().resolve()
    arquivos = ArquivosKoppen(
        diretorio=raiz,
        classe_1km=raiz / NOME_CLASSE_1KM,
        confianca_1km=raiz / NOME_CONFIANCA_1KM,
        fundo_05grau=raiz / NOME_FUNDO_05GRAU,
        legenda=raiz / NOME_LEGENDA,
    )
    ausentes = [
        caminho
        for caminho in (
            arquivos.classe_1km,
            arquivos.confianca_1km,
            arquivos.fundo_05grau,
            arquivos.legenda,
        )
        if not caminho.is_file()
    ]
    if ausentes:
        lista = ", ".join(str(caminho) for caminho in ausentes)
        raise FileNotFoundError(f"Arquivos Köppen--Geiger ausentes: {lista}")
    return arquivos


def carregar_legenda_koppen(caminho: str | Path) -> dict[int, ClasseKoppen]:
    """Lê as 30 classes, descrições e cores do legend.txt local."""

    texto = Path(caminho).read_text(encoding="utf-8")
    classes: dict[int, ClasseKoppen] = {}
    codigos: set[str] = set()
    for linha in texto.splitlines():
        correspondencia = _PADRAO_LEGENDA.match(linha)
        if correspondencia is None:
            continue
        identificador = int(correspondencia.group(1))
        codigo = correspondencia.group(2)
        descricao = correspondencia.group(3).strip()
        rgb = tuple(int(correspondencia.group(i)) for i in range(4, 7))
        if identificador in classes or codigo in codigos:
            raise ValueError("Legenda Köppen--Geiger contém classe duplicada.")
        if any(canal < 0 or canal > 255 for canal in rgb):
            raise ValueError(f"Cor RGB inválida para a classe {codigo}.")
        classes[identificador] = ClasseKoppen(
            identificador=identificador,
            codigo=codigo,
            descricao_fonte=descricao,
            rgb=rgb,
        )
        codigos.add(codigo)

    esperados = set(range(1, 31))
    if set(classes) != esperados:
        faltantes = sorted(esperados.difference(classes))
        raise ValueError(
            "A legenda Köppen--Geiger deve conter as classes 1--30; "
            f"ausentes: {faltantes}."
        )
    return classes


def decompor_codigo_koppen(codigo: str) -> tuple[str, str, str]:
    """Traduz os componentes do código Köppen--Geiger para português."""

    if codigo == "ET":
        return "Polar", "tundra", "não se aplica"
    if codigo == "EF":
        return "Polar", "gelo permanente", "não se aplica"

    principal = {
        "A": "Tropical",
        "B": "Árido",
        "C": "Temperado",
        "D": "Frio/continental",
    }.get(codigo[0])
    if principal is None:
        raise ValueError(f"Código Köppen--Geiger desconhecido: {codigo}")

    if codigo[0] == "A":
        precipitacao = {
            "f": "sem estação seca (floresta tropical)",
            "m": "monções",
            "w": "savana com inverno seco",
        }.get(codigo[1])
        temperatura = "não se aplica"
    elif codigo[0] == "B":
        precipitacao = {"W": "deserto", "S": "estepe"}.get(codigo[1])
        temperatura = {"h": "quente", "k": "frio"}.get(codigo[2])
    else:
        precipitacao = {
            "s": "verão seco",
            "w": "inverno seco",
            "f": "sem estação seca",
        }.get(codigo[1])
        temperatura = {
            "a": "verão quente",
            "b": "verão ameno",
            "c": "verão frio",
            "d": "inverno muito frio",
        }.get(codigo[2])

    if precipitacao is None or temperatura is None:
        raise ValueError(f"Código Köppen--Geiger incompleto ou inválido: {codigo}")
    return principal, precipitacao, temperatura


def md5_arquivo(caminho: str | Path, tamanho_bloco: int = 1024 * 1024) -> str:
    """Calcula MD5 para auditoria de integridade, não para segurança."""

    resumo = md5(usedforsecurity=False)
    with Path(caminho).open("rb") as arquivo:
        while bloco := arquivo.read(tamanho_bloco):
            resumo.update(bloco)
    return resumo.hexdigest()


def _caminho_auditavel(caminho: Path) -> str:
    try:
        return caminho.resolve().relative_to(RAIZ_PROJETO).as_posix()
    except ValueError:
        return caminho.resolve().as_posix()


def _validar_par_rasters(classe, confianca) -> None:
    if classe.crs != rasterio.CRS.from_epsg(4326):
        raise ValueError(f"Raster de classe deve usar EPSG:4326, não {classe.crs}.")
    atributos = ("crs", "transform", "width", "height", "bounds")
    divergentes = [
        atributo
        for atributo in atributos
        if getattr(classe, atributo) != getattr(confianca, atributo)
    ]
    if divergentes:
        raise ValueError(
            "Rasters de classe e confiança não estão alinhados: "
            + ", ".join(divergentes)
        )
    if classe.count != 1 or confianca.count != 1:
        raise ValueError("Os rasters de classe e confiança devem ter uma banda.")


def _amostrar_pixel(dataset, longitude: float, latitude: float):
    limites = dataset.bounds
    if not (
        limites.left <= longitude < limites.right
        and limites.bottom < latitude <= limites.top
    ):
        raise ValueError(
            f"Ponto ({latitude}, {longitude}) fora do raster {dataset.name}."
        )
    linha, coluna = dataset.index(longitude, latitude)
    valor = dataset.read(
        1,
        window=Window(coluna, linha, 1, 1),
        boundless=False,
    )
    if valor.size != 1:
        raise ValueError(f"Não foi possível amostrar {dataset.name}.")
    centro_lon, centro_lat = dataset.xy(linha, coluna, offset="center")
    return int(valor[0, 0]), int(linha), int(coluna), float(centro_lon), float(
        centro_lat
    )


def _validar_localidade(localidade: Mapping[str, object]) -> None:
    obrigatorias = {
        "nome",
        "pais",
        "lat",
        "lon",
        "endereco",
        "fonte_localidade",
        "fonte_coordenadas",
        "osm_elemento",
        "metodo_coordenadas",
    }
    faltantes = sorted(obrigatorias.difference(localidade))
    if faltantes:
        raise ValueError(
            f"Localidade sem campos obrigatórios {faltantes}: {localidade!r}"
        )


def construir_contexto_geografico(
    diretorio_koppen: str | Path = DIRETORIO_KOPPEN_PADRAO,
    localidades: Sequence[Mapping[str, object]] | None = None,
) -> pd.DataFrame:
    """Amostra classe e confiança presentes de 1 km nas localidades."""

    arquivos = resolver_arquivos_koppen(diretorio_koppen)
    classes = carregar_legenda_koppen(arquivos.legenda)
    registros_localidades = list(LOCALIDADES_EV if localidades is None else localidades)
    if not registros_localidades:
        raise ValueError("Ao menos uma localidade é necessária.")

    hashes = {
        "md5_raster_classe_1km": md5_arquivo(arquivos.classe_1km),
        "md5_raster_confianca_1km": md5_arquivo(arquivos.confianca_1km),
        "md5_raster_fundo_05grau": md5_arquivo(arquivos.fundo_05grau),
        "md5_legenda": md5_arquivo(arquivos.legenda),
    }

    linhas: list[dict[str, object]] = []
    with rasterio.open(arquivos.classe_1km) as classe_ds, rasterio.open(
        arquivos.confianca_1km
    ) as confianca_ds:
        _validar_par_rasters(classe_ds, confianca_ds)
        resolucao_lon, resolucao_lat = classe_ds.res
        software_raster = classe_ds.tags().get("TIFFTAG_SOFTWARE", "")

        for ordem, localidade in enumerate(registros_localidades, start=1):
            _validar_localidade(localidade)
            latitude = float(localidade["lat"])
            longitude = float(localidade["lon"])
            (
                classe_id,
                linha_pixel,
                coluna_pixel,
                centro_lon,
                centro_lat,
            ) = _amostrar_pixel(classe_ds, longitude, latitude)
            (
                confianca_pct,
                linha_confianca,
                coluna_confianca,
                _,
                _,
            ) = _amostrar_pixel(confianca_ds, longitude, latitude)
            if (linha_pixel, coluna_pixel) != (
                linha_confianca,
                coluna_confianca,
            ):
                raise ValueError("Classe e confiança foram amostradas em pixels distintos.")
            if classe_id not in classes:
                raise ValueError(
                    f"Classe {classe_id} sem legenda em {localidade['nome']}."
                )
            if not 0 <= confianca_pct <= 100:
                raise ValueError(
                    f"Confiança fora de 0--100 em {localidade['nome']}: "
                    f"{confianca_pct}."
                )

            classe = classes[classe_id]
            principal, precipitacao, temperatura = decompor_codigo_koppen(
                classe.codigo
            )
            descricao_pt = "; ".join(
                parte
                for parte in (principal, precipitacao, temperatura)
                if parte != "não se aplica"
            )
            distancia_centro = distancia_haversine_km(
                latitude,
                longitude,
                centro_lat,
                centro_lon,
            )

            linha = {
                "ordem": ordem,
                "localidade": str(localidade["nome"]),
                "pais": str(localidade["pais"]),
                "latitude": latitude,
                "longitude": longitude,
                "endereco_localidade": str(localidade["endereco"]),
                "fonte_localidade": str(localidade["fonte_localidade"]),
                "fonte_coordenadas": str(localidade["fonte_coordenadas"]),
                "osm_elemento": str(localidade["osm_elemento"]),
                "metodo_coordenadas": str(localidade["metodo_coordenadas"]),
                "classe_id": classe.identificador,
                "classe_codigo": classe.codigo,
                "classe_descricao_fonte": classe.descricao_fonte,
                "classe_descricao_pt": descricao_pt,
                "clima_principal": principal,
                "criterio_precipitacao": precipitacao,
                "criterio_temperatura": temperatura,
                "classe_cor_rgb": ",".join(str(canal) for canal in classe.rgb),
                "classe_cor_hex": classe.cor_hex,
                "confianca_pct": confianca_pct,
                "confianca_interpretacao": (
                    "valor percentual fornecido pelo raster de confiança"
                ),
                "pixel_linha": linha_pixel,
                "pixel_coluna": coluna_pixel,
                "pixel_centro_latitude": centro_lat,
                "pixel_centro_longitude": centro_lon,
                "distancia_ponto_centro_pixel_km": distancia_centro,
                "metodo_amostragem": (
                    "célula raster que contém o ponto WGS84; sem interpolação"
                ),
                "crs": classe_ds.crs.to_string(),
                "resolucao_longitude_graus": float(resolucao_lon),
                "resolucao_latitude_graus": float(resolucao_lat),
                "resolucao_nominal": "1 km",
                "versao_produto": VERSAO_PRODUTO,
                "cenario_produto": CENARIO_PRODUTO,
                "arquivo_raster_classe_1km": _caminho_auditavel(
                    arquivos.classe_1km
                ),
                "arquivo_raster_confianca_1km": _caminho_auditavel(
                    arquivos.confianca_1km
                ),
                "arquivo_raster_fundo_05grau": _caminho_auditavel(
                    arquivos.fundo_05grau
                ),
                "arquivo_legenda": _caminho_auditavel(arquivos.legenda),
                "software_criacao_raster": software_raster,
                "fonte_autores": FONTE_AUTORES,
                "fonte_titulo": FONTE_TITULO,
                "fonte_periodico": FONTE_PERIODICO,
                "fonte_ano": FONTE_ANO,
                "fonte_doi": FONTE_DOI,
                "fonte_url": FONTE_URL,
                **hashes,
            }
            linhas.append(linha)

    tabela = pd.DataFrame(linhas)
    validar_tabela_contexto(tabela)
    return tabela


def validar_tabela_contexto(tabela: pd.DataFrame) -> None:
    """Valida o contrato mínimo do CSV antes da escrita ou plotagem."""

    obrigatorias = {
        "ordem",
        "localidade",
        "pais",
        "latitude",
        "longitude",
        "classe_id",
        "classe_codigo",
        "classe_descricao_fonte",
        "classe_descricao_pt",
        "confianca_pct",
        "fonte_doi",
        "md5_raster_classe_1km",
        "md5_raster_confianca_1km",
        "md5_raster_fundo_05grau",
        "md5_legenda",
    }
    faltantes = sorted(obrigatorias.difference(tabela.columns))
    if faltantes:
        raise ValueError(f"Tabela geográfica sem colunas obrigatórias: {faltantes}")
    if tabela.empty:
        raise ValueError("Tabela geográfica vazia.")
    if tabela["localidade"].duplicated().any():
        raise ValueError("Tabela geográfica contém localidades duplicadas.")
    if tabela["ordem"].duplicated().any():
        raise ValueError("Tabela geográfica contém ordens duplicadas.")
    if not tabela["classe_id"].between(1, 30).all():
        raise ValueError("Tabela geográfica contém classe fora de 1--30.")
    if not tabela["confianca_pct"].between(0, 100).all():
        raise ValueError("Tabela geográfica contém confiança fora de 0--100.")
    for coluna in (
        "md5_raster_classe_1km",
        "md5_raster_confianca_1km",
        "md5_raster_fundo_05grau",
        "md5_legenda",
    ):
        if not tabela[coluna].astype(str).str.fullmatch(r"[0-9a-f]{32}").all():
            raise ValueError(f"Hash MD5 inválido na coluna {coluna}.")


def salvar_contexto_csv(
    tabela: pd.DataFrame,
    caminho: str | Path = CSV_CONTEXTO_PADRAO,
) -> Path:
    """Salva o CSV em UTF-8 com precisão suficiente para auditar os pixels."""

    validar_tabela_contexto(tabela)
    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tabela.sort_values("ordem").to_csv(
        destino,
        index=False,
        encoding="utf-8",
        float_format="%.10f",
        lineterminator="\n",
    )
    return destino


def _desenhar_fundo(ax, raster, cmap, norm) -> None:
    dados = raster.read(1)
    mascarado = np.ma.masked_equal(dados, 0)
    limites = raster.bounds
    ax.set_facecolor("#dceef8")
    ax.imshow(
        mascarado,
        extent=(limites.left, limites.right, limites.bottom, limites.top),
        origin="upper",
        cmap=cmap,
        norm=norm,
        interpolation="nearest",
        rasterized=True,
        zorder=0,
    )


def gerar_mapa_contexto(
    tabela: pd.DataFrame,
    diretorio_koppen: str | Path = DIRETORIO_KOPPEN_PADRAO,
    caminho_png: str | Path = MAPA_PNG_PADRAO,
    caminho_pdf: str | Path = MAPA_PDF_PADRAO,
    dpi: int = 300,
) -> tuple[Path, Path]:
    """Gera mapa das Américas, painel dos EUA e detalhe Ford/GM."""

    if dpi < 72:
        raise ValueError("DPI deve ser pelo menos 72.")
    validar_tabela_contexto(tabela)
    arquivos = resolver_arquivos_koppen(diretorio_koppen)
    classes = carregar_legenda_koppen(arquivos.legenda)

    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch

    cores = ["#dceef8"] + [
        tuple(canal / 255 for canal in classes[i].rgb) for i in range(1, 31)
    ]
    cmap = ListedColormap(cores, name="koppen_geiger_beck_2018")
    cmap.set_bad("#dceef8")
    norm = BoundaryNorm(np.arange(-0.5, 31.5, 1), cmap.N)

    tabela_ordenada = tabela.sort_values("ordem").copy()
    fig = plt.figure(figsize=(10, 6.7))
    grade = fig.add_gridspec(
        2,
        2,
        width_ratios=(2.8, 1.2),
        height_ratios=(1.18, 1.0),
    )
    ax_mundo = fig.add_subplot(grade[:, 0])
    ax_eua = fig.add_subplot(grade[0, 1])
    ax_detroit = fig.add_subplot(grade[1, 1])

    with rasterio.open(arquivos.fundo_05grau) as fundo:
        if fundo.crs != rasterio.CRS.from_epsg(4326):
            raise ValueError("Raster cartográfico de fundo deve usar EPSG:4326.")
        for eixo in (ax_mundo, ax_eua, ax_detroit):
            _desenhar_fundo(eixo, fundo, cmap, norm)

    def configurar(eixo, xlim, ylim, titulo):
        eixo.set_xlim(*xlim)
        eixo.set_ylim(*ylim)
        eixo.set_title(titulo, loc="left", fontsize=12, fontweight="bold")
        eixo.set_xlabel("Longitude (°)", fontsize=10)
        eixo.set_ylabel("Latitude (°)", fontsize=10)
        eixo.grid(
            color="white",
            alpha=0.55,
            linewidth=0.45,
            linestyle=":",
            zorder=1,
        )

    configurar(ax_mundo, (-130, -30), (-35, 55), "(a) Americas context")
    configurar(
        ax_eua,
        (-126, -79),
        (24, 47),
        "(b) Contiguous United States",
    )
    configurar(
        ax_detroit,
        (-83.28, -82.92),
        (42.22, 42.47),
        "(c) Detroit: Ford and GM",
    )

    for _, registro in tabela_ordenada.iterrows():
        ordem = int(registro["ordem"])
        longitude = float(registro["longitude"])
        latitude = float(registro["latitude"])
        classe_id = int(registro["classe_id"])
        cor = classes[classe_id].cor_hex
        ax_mundo.scatter(
            longitude,
            latitude,
            s=95,
            c=cor,
            edgecolors="black",
            linewidths=1.0,
            zorder=4,
        )
        ax_mundo.annotate(
            str(ordem),
            (longitude, latitude),
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
            color="black",
            zorder=5,
        )

    tabela_eua = tabela_ordenada[tabela_ordenada["pais"].eq("EUA")]
    deslocamentos = {
        "Tesla Gigafactory Nevada": (5, 6),
        "Tesla Gigafactory Texas": (5, -12),
        "Hyundai Metaplant Georgia": (-5, -13),
        "Rivian Normal": (-5, 7),
        "Tesla Fremont Factory": (5, -12),
        "Lucid AMP 1 Casa Grande": (5, 6),
        "GM Factory Zero": (6, 8),
        "Ford Rouge Electric Vehicle Center": (6, -13),
    }
    for _, registro in tabela_eua.iterrows():
        nome = str(registro["localidade"])
        longitude = float(registro["longitude"])
        latitude = float(registro["latitude"])
        classe_id = int(registro["classe_id"])
        ax_eua.scatter(
            longitude,
            latitude,
            s=72,
            c=classes[classe_id].cor_hex,
            edgecolors="black",
            linewidths=0.9,
            zorder=4,
        )
        dx, dy = deslocamentos.get(nome, (5, 5))
        ax_eua.annotate(
            str(int(registro["ordem"])),
            (longitude, latitude),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=9,
            fontweight="bold",
            arrowprops={"arrowstyle": "-", "lw": 0.5, "color": "#333333"},
            zorder=5,
        )

    tabela_detroit = tabela_ordenada[
        tabela_ordenada["localidade"].isin(
            ["GM Factory Zero", "Ford Rouge Electric Vehicle Center"]
        )
    ]
    rotulos_detroit = {
        "GM Factory Zero": ("GM Factory Zero", (-8, 8), "right"),
        "Ford Rouge Electric Vehicle Center": (
            "Ford Rouge EV Center",
            (10, -15),
            "left",
        ),
    }
    for _, registro in tabela_detroit.iterrows():
        nome = str(registro["localidade"])
        longitude = float(registro["longitude"])
        latitude = float(registro["latitude"])
        classe_id = int(registro["classe_id"])
        rotulo, deslocamento, alinhamento_horizontal = rotulos_detroit[nome]
        ax_detroit.scatter(
            longitude,
            latitude,
            s=95,
            c=classes[classe_id].cor_hex,
            edgecolors="black",
            linewidths=1.0,
            zorder=4,
        )
        ax_detroit.annotate(
            rotulo,
            (longitude, latitude),
            xytext=deslocamento,
            textcoords="offset points",
            fontsize=9,
            ha=alinhamento_horizontal,
            va="center",
            arrowprops={"arrowstyle": "-", "lw": 0.7, "color": "#333333"},
            zorder=5,
        )

    classes_presentes = sorted(
        {int(valor) for valor in tabela_ordenada["classe_id"]}
    )
    legenda_classes = [
        Patch(
            facecolor=classes[classe_id].cor_hex,
            edgecolor="black",
            label=classes[classe_id].codigo,
        )
        for classe_id in classes_presentes
    ]
    fig.legend(
        handles=legenda_classes,
        title="Köppen–Geiger classes at study sites",
        loc="lower center",
        bbox_to_anchor=(0.5, 0.02),
        ncol=len(legenda_classes),
        fontsize=8.5,
        title_fontsize=8.5,
        columnspacing=1.0,
        handlelength=1.4,
        handletextpad=0.45,
        borderaxespad=0.0,
        frameon=False,
    )
    fig.subplots_adjust(
        left=0.055,
        right=0.98,
        top=0.96,
        bottom=0.14,
        wspace=0.16,
        hspace=0.24,
    )

    destino_png = Path(caminho_png)
    destino_pdf = Path(caminho_pdf)
    destino_png.parent.mkdir(parents=True, exist_ok=True)
    destino_pdf.parent.mkdir(parents=True, exist_ok=True)
    titulo = "Köppen–Geiger climate context of the study locations"
    fig.savefig(
        destino_png,
        dpi=dpi,
        facecolor="white",
        metadata={
            "Title": titulo,
            "Author": "TCC GHI project",
            "Description": (
                f"Original map generated from {VERSAO_PRODUTO}; {FONTE_URL}"
            ),
            "Software": "Matplotlib and Rasterio",
        },
    )
    fig.savefig(
        destino_pdf,
        facecolor="white",
        metadata={
            "Title": titulo,
            "Author": "TCC GHI project",
            "Subject": (
                f"Original map generated from {VERSAO_PRODUTO}; {FONTE_URL}"
            ),
            "Keywords": "Koppen-Geiger, climate, GHI, factories",
            "Creator": "Matplotlib and Rasterio",
            "CreationDate": None,
            "ModDate": None,
        },
    )
    plt.close(fig)

    if not destino_png.is_file() or destino_png.stat().st_size == 0:
        raise RuntimeError("Falha ao gerar o mapa PNG.")
    if not destino_pdf.is_file() or destino_pdf.stat().st_size == 0:
        raise RuntimeError("Falha ao gerar o mapa PDF.")
    return destino_png, destino_pdf


def gerar_artefatos_contexto(
    diretorio_koppen: str | Path = DIRETORIO_KOPPEN_PADRAO,
    caminho_csv: str | Path = CSV_CONTEXTO_PADRAO,
    caminho_png: str | Path = MAPA_PNG_PADRAO,
    caminho_pdf: str | Path = MAPA_PDF_PADRAO,
    dpi: int = 300,
) -> tuple[pd.DataFrame, tuple[Path, Path]]:
    """Executa a tabela auditável e os dois formatos do mapa."""

    tabela = construir_contexto_geografico(diretorio_koppen=diretorio_koppen)
    salvar_contexto_csv(tabela, caminho_csv)
    mapas = gerar_mapa_contexto(
        tabela,
        diretorio_koppen=diretorio_koppen,
        caminho_png=caminho_png,
        caminho_pdf=caminho_pdf,
        dpi=dpi,
    )
    return tabela, mapas


__all__ = [
    "ArquivosKoppen",
    "CSV_CONTEXTO_PADRAO",
    "ClasseKoppen",
    "DIRETORIO_KOPPEN_PADRAO",
    "DIRETORIO_SAIDA_PADRAO",
    "FONTE_DOI",
    "FONTE_TITULO",
    "MAPA_PDF_PADRAO",
    "MAPA_PNG_PADRAO",
    "carregar_legenda_koppen",
    "construir_contexto_geografico",
    "decompor_codigo_koppen",
    "gerar_artefatos_contexto",
    "gerar_mapa_contexto",
    "md5_arquivo",
    "resolver_arquivos_koppen",
    "salvar_contexto_csv",
    "validar_tabela_contexto",
]
