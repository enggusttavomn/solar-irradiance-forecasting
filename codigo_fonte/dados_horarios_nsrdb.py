"""Extração auditável de GHI horário dos HDF5 públicos da NSRDB.

Os CSVs históricos do projeto preservam somente médias diárias. Este módulo
recupera, para os mesmos pontos de grade, os dados de 30 minutos publicados no
bucket público da NSRDB e os agrega em médias horárias. A leitura usa requisições
por intervalo: somente os blocos HDF5 necessários às dez localidades são
transferidos, não o arquivo anual completo.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import fsspec
import h5py
import numpy as np
import pandas as pd

from codigo_fonte.configuracao import PASTA_DADOS_BRUTOS


NSRDB_S3_BASE = (
    "https://nrel-pds-nsrdb.s3.us-west-2.amazonaws.com/"
    "GOES/aggregated/v4.0.0"
)
PASTA_HORARIA_PADRAO = PASTA_DADOS_BRUTOS / "localidades_ev_horario"
COLUNAS_REGISTRO = (
    "localidade",
    "site_id_nsrdb",
    "lat_grade_nsrdb",
    "lon_grade_nsrdb",
    "timezone_nsrdb",
)


def _sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def carregar_registro_pontos(
    pasta_diaria: Path | str | None = None,
) -> pd.DataFrame:
    """Lê os identificadores de grade já auditados nos CSVs diários."""

    pasta = (
        Path(pasta_diaria)
        if pasta_diaria is not None
        else PASTA_DADOS_BRUTOS / "localidades_ev"
    )
    registros: list[dict[str, object]] = []
    for caminho in sorted(pasta.glob("*.csv")):
        if caminho.name == "manifesto_nsrdb.csv":
            continue
        cabecalho = pd.read_csv(caminho, nrows=1)
        ausentes = sorted(set(COLUNAS_REGISTRO) - set(cabecalho.columns))
        if ausentes:
            raise ValueError(f"{caminho} não contém as colunas {ausentes}.")
        linha = cabecalho.loc[0, list(COLUNAS_REGISTRO)].to_dict()
        linha["arquivo_diario"] = caminho.name
        registros.append(linha)

    registro = pd.DataFrame(registros)
    if registro.empty:
        raise FileNotFoundError(f"Nenhum CSV diário foi encontrado em {pasta}.")
    registro["site_id_nsrdb"] = registro["site_id_nsrdb"].astype(int)
    if registro["site_id_nsrdb"].duplicated().any():
        raise ValueError("Os identificadores site_id_nsrdb devem ser únicos.")
    return registro.sort_values("site_id_nsrdb").reset_index(drop=True)


def _decodificar_meta(valor: object) -> object:
    if isinstance(valor, (bytes, np.bytes_)):
        return valor.decode("utf-8")
    if isinstance(valor, np.generic):
        return valor.item()
    return valor


def extrair_ano_horario(
    ano: int,
    registro: pd.DataFrame | None = None,
    block_size: int = 512 * 1024,
) -> pd.DataFrame:
    """Extrai e agrega um ano para as localidades cadastradas.

    O índice temporal do HDF5 está em UTC e possui resolução de 30 minutos.
    Duas amostras consecutivas são promediadas para obter GHI média horária em
    W/m². A posição de cada coluna espacial é o ``site_id_nsrdb`` preservado
    nos arquivos diários do projeto.
    """

    if not 1998 <= int(ano) <= 2100:
        raise ValueError("ano fora do intervalo suportado.")
    if block_size < 64 * 1024:
        raise ValueError("block_size deve ser pelo menos 64 KiB.")
    registro = carregar_registro_pontos() if registro is None else registro.copy()
    ids = registro["site_id_nsrdb"].astype(int).to_numpy()
    if len(ids) == 0 or np.any(np.diff(ids) <= 0):
        raise ValueError("O registro deve conter site_id_nsrdb únicos e ordenados.")

    url = f"{NSRDB_S3_BASE}/nsrdb_{int(ano)}.h5"
    with fsspec.open(
        url,
        mode="rb",
        block_size=block_size,
        cache_type="blockcache",
    ) as remoto:
        with h5py.File(remoto, mode="r") as h5:
            obrigatorios = {"time_index", "meta", "ghi"}
            ausentes = obrigatorios - set(h5.keys())
            if ausentes:
                raise ValueError(f"HDF5 {ano} sem conjuntos {sorted(ausentes)}.")

            tempo = pd.to_datetime(
                h5["time_index"][:].astype(str),
                utc=True,
                errors="raise",
            )
            meta = h5["meta"][ids]
            ghi = np.asarray(h5["ghi"][:, ids], dtype=np.float32)
            escala = float(h5["ghi"].attrs.get("scale_factor", 1.0))
            ghi *= escala

    if len(tempo) != len(ghi):
        raise ValueError("Índice temporal e matriz de GHI possuem tamanhos distintos.")
    if not tempo.is_monotonic_increasing or tempo.has_duplicates:
        raise ValueError("O índice temporal da NSRDB deve ser crescente e único.")
    deltas = pd.Series(tempo[1:] - tempo[:-1])
    if deltas.empty or not (deltas == pd.Timedelta(minutes=30)).all():
        raise ValueError("Esperava-se resolução contínua de 30 minutos no HDF5.")
    if not np.isfinite(ghi).all() or (ghi < 0).any():
        raise ValueError("A matriz de GHI contém valores inválidos.")

    for posicao, linha in enumerate(meta):
        lat = float(linha["latitude"])
        lon = float(linha["longitude"])
        esperado = registro.iloc[posicao]
        if not np.isclose(lat, float(esperado["lat_grade_nsrdb"]), atol=0.011):
            raise ValueError(f"Latitude divergente no site {ids[posicao]}.")
        if not np.isclose(lon, float(esperado["lon_grade_nsrdb"]), atol=0.011):
            raise ValueError(f"Longitude divergente no site {ids[posicao]}.")

    tabela_30min = pd.DataFrame(ghi, index=tempo, columns=ids)
    tabela_horaria = tabela_30min.resample("1h").mean()
    esperado_horas = 8784 if pd.Timestamp(f"{ano}-12-31").is_leap_year else 8760
    if len(tabela_horaria) != esperado_horas or tabela_horaria.isna().any().any():
        raise ValueError(
            f"Cobertura horária incompleta em {ano}: "
            f"{len(tabela_horaria)} de {esperado_horas} horas."
        )

    longo = (
        tabela_horaria.rename_axis("timestamp_utc")
        .reset_index()
        .melt(
            id_vars="timestamp_utc",
            var_name="site_id_nsrdb",
            value_name="ghi",
        )
    )
    longo["site_id_nsrdb"] = longo["site_id_nsrdb"].astype(int)
    colunas_meta = registro[
        [
            "site_id_nsrdb",
            "localidade",
            "lat_grade_nsrdb",
            "lon_grade_nsrdb",
            "timezone_nsrdb",
        ]
    ]
    longo = longo.merge(colunas_meta, on="site_id_nsrdb", validate="many_to_one")
    longo["ano"] = int(ano)
    longo["fonte_dados"] = "NLR/NSRDB"
    longo["produto_dados"] = "GOES Aggregated PSM v4"
    longo["versao_dados"] = "4.0.0"
    longo["resolucao_origem_minutos"] = 30
    longo["agregacao"] = "media_horaria"
    longo["unidade_ghi"] = "W/m2"
    longo["url_hdf5"] = url
    return longo.sort_values(["localidade", "timestamp_utc"]).reset_index(drop=True)


def salvar_ano_horario(
    ano: int,
    saida: Path | str | None = None,
    sobrescrever: bool = False,
    registro: pd.DataFrame | None = None,
) -> Path:
    """Extrai um ano e o salva como CSV gzip reproduzível."""

    destino = (
        Path(saida)
        if saida is not None
        else PASTA_HORARIA_PADRAO / f"nsrdb_ghi_horaria_{int(ano)}.csv.gz"
    )
    if destino.exists() and not sobrescrever:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    dados = extrair_ano_horario(ano, registro=registro)
    temporario = destino.with_suffix(destino.suffix + ".tmp")
    dados.to_csv(
        temporario,
        index=False,
        date_format="%Y-%m-%dT%H:%M:%SZ",
        compression={"method": "gzip", "mtime": 0},
        lineterminator="\n",
    )
    temporario.replace(destino)
    return destino


def coletar_periodo_horario(
    anos: Iterable[int] = range(2019, 2025),
    pasta_saida: Path | str = PASTA_HORARIA_PADRAO,
    sobrescrever: bool = False,
) -> list[Path]:
    """Extrai vários anos com retomada por arquivo anual e grava manifesto."""

    anos_ordenados = sorted({int(ano) for ano in anos})
    if not anos_ordenados:
        raise ValueError("Informe pelo menos um ano.")
    pasta = Path(pasta_saida)
    pasta.mkdir(parents=True, exist_ok=True)
    registro = carregar_registro_pontos()
    caminhos = [
        salvar_ano_horario(
            ano,
            pasta / f"nsrdb_ghi_horaria_{ano}.csv.gz",
            sobrescrever=sobrescrever,
            registro=registro,
        )
        for ano in anos_ordenados
    ]

    manifesto = {
        "versao_esquema": 1,
        "criado_em_utc": datetime.now(timezone.utc).isoformat(),
        "fonte": "NLR/NSRDB public S3",
        "produto": "GOES Aggregated PSM v4",
        "versao": "4.0.0",
        "resolucao_origem_minutos": 30,
        "agregacao_modelagem": "media_horaria",
        "anos": anos_ordenados,
        "localidades": int(len(registro)),
        "arquivos": {
            caminho.name: {"sha256": _sha256(caminho), "bytes": caminho.stat().st_size}
            for caminho in caminhos
        },
    }
    destino_manifesto = pasta / "manifesto_horario.json"
    temporario = destino_manifesto.with_suffix(".json.tmp")
    temporario.write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporario.replace(destino_manifesto)
    return caminhos


def carregar_dados_horarios(
    pasta: Path | str = PASTA_HORARIA_PADRAO,
    anos: Iterable[int] = range(2019, 2025),
) -> pd.DataFrame:
    """Carrega os arquivos anuais coletados e valida sua continuidade."""

    pasta = Path(pasta)
    quadros = []
    for ano in sorted({int(valor) for valor in anos}):
        caminho = pasta / f"nsrdb_ghi_horaria_{ano}.csv.gz"
        if not caminho.exists():
            raise FileNotFoundError(
                f"Dados horários ausentes para {ano}: execute a coleta em {caminho}."
            )
        quadro = pd.read_csv(caminho, parse_dates=["timestamp_utc"])
        quadros.append(quadro)
    dados = pd.concat(quadros, ignore_index=True)
    dados["timestamp_utc"] = pd.to_datetime(
        dados["timestamp_utc"], utc=True, errors="raise"
    )
    dados["ghi"] = pd.to_numeric(dados["ghi"], errors="raise")

    for localidade, grupo in dados.groupby("localidade", sort=True):
        grupo = grupo.sort_values("timestamp_utc")
        if grupo["timestamp_utc"].duplicated().any():
            raise ValueError(f"Datas duplicadas em {localidade}.")
        deltas = grupo["timestamp_utc"].diff().dropna()
        if not (deltas == pd.Timedelta(hours=1)).all():
            raise ValueError(f"Cobertura horária descontínua em {localidade}.")
        if not np.isfinite(grupo["ghi"]).all() or (grupo["ghi"] < 0).any():
            raise ValueError(f"GHI inválida em {localidade}.")
    return dados.sort_values(["localidade", "timestamp_utc"]).reset_index(drop=True)


__all__ = [
    "NSRDB_S3_BASE",
    "PASTA_HORARIA_PADRAO",
    "carregar_dados_horarios",
    "carregar_registro_pontos",
    "coletar_periodo_horario",
    "extrair_ano_horario",
    "salvar_ano_horario",
]
