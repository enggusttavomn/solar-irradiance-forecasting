"""Leitura, limpeza, quantizacao e normalizacao da serie diaria de GHI."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from codigo_fonte.configuracao import PASTA_DADOS_BRUTOS, PASTA_DADOS_PROCESSADOS
from codigo_fonte.features import criar_features_temporais
from codigo_fonte.utilitarios import localizar_arquivo_dados


DATE_CANDIDATES = (
    "data",
    "date",
    "datetime",
    "timestamp",
    "time",
    "ds",
)

GHI_CANDIDATES = (
    "ghi",
    "global_horizontal_irradiance",
    "global horizontal irradiance",
    "irradiancia_global_horizontal",
    "irradiancia global horizontal",
    "global_horizontal",
)

NSRDB_API_URL = (
    "https://developer.nlr.gov/api/nsrdb/v2/solar/"
    "nsrdb-GOES-aggregated-v4-0-0-download.csv"
)
NSRDB_DATA_QUERY_URL = "https://developer.nlr.gov/api/solar/nsrdb_data_query.json"
NSRDB_DATASET = "nsrdb-GOES-aggregated-v4-0-0"
NSRDB_PRODUCT = "GOES Aggregated PSM v4"
NSRDB_SOURCE = "NLR/NSRDB"
NSRDB_GHI_UNIT = "W/m2"
NSRDB_DAILY_AGGREGATION = "media_diaria"


@dataclass
class PreparationResult:
    """Resultado completo da preparacao da serie temporal."""

    dados_modelagem: pd.DataFrame
    feature_columns: list[str]
    train_size: int
    quantization_params: dict[str, float]
    normalization_params: dict[str, float]


def _normalizar_nome_coluna(column: str) -> str:
    return str(column).strip().lower().replace("-", "_")


def detectar_colunas(df: pd.DataFrame) -> tuple[str | None, str]:
    """Detecta automaticamente a coluna de data e a coluna de GHI.

    Args:
        df: DataFrame carregado a partir de arquivo ou API.

    Returns:
        Uma tupla com o nome da coluna de data, que pode ser ``None`` se o
        indice ja for datetime, e o nome da coluna de GHI.
    """
    normalized = {_normalizar_nome_coluna(col): col for col in df.columns}

    date_col = None
    for candidate in DATE_CANDIDATES:
        if candidate in normalized:
            date_col = normalized[candidate]
            break

    ghi_col = None
    for candidate in GHI_CANDIDATES:
        if candidate in normalized:
            ghi_col = normalized[candidate]
            break

    if ghi_col is None:
        for normalized_name, original_name in normalized.items():
            if "ghi" in normalized_name:
                ghi_col = original_name
                break

    if ghi_col is None:
        numeric_columns = df.select_dtypes(include="number").columns.tolist()
        if len(numeric_columns) == 1:
            ghi_col = numeric_columns[0]

    if ghi_col is None:
        raise ValueError(
            "Nao foi possivel detectar a coluna de GHI. Use uma coluna chamada "
            "'ghi' ou informe uma serie com apenas uma coluna numerica."
        )

    return date_col, ghi_col


def limpar_serie_ghi(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza a serie para duas colunas: ``data`` e ``ghi``.

    Args:
        df: Dados brutos com uma coluna de data e uma coluna de irradiancia GHI.

    Returns:
        DataFrame ordenado cronologicamente, sem valores ausentes em ``ghi``.
    """
    df = df.copy()
    date_col, ghi_col = detectar_colunas(df)

    # Tratamento da coluna de data: aceita coluna explicita ou indice datetime.
    if date_col is None:
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index().rename(columns={df.index.name or "index": "data"})
            date_col = "data"
        else:
            raise ValueError(
                "Nao foi encontrada coluna de data. Use nomes como data, date, "
                "datetime, timestamp ou ds."
            )

    # Tratamento da coluna de GHI: converte para numero, remove invalidos e
    # descarta irradiancia negativa, que nao tem interpretacao fisica para GHI.
    cleaned = pd.DataFrame(
        {
            "data": pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.tz_convert(None),
            "ghi": pd.to_numeric(df[ghi_col], errors="coerce"),
        }
    )
    cleaned = cleaned.dropna(subset=["data", "ghi"]).sort_values("data")
    cleaned = cleaned[cleaned["ghi"] >= 0]
    cleaned = cleaned.drop_duplicates(subset=["data"], keep="last")
    cleaned = cleaned.reset_index(drop=True)

    if cleaned.empty:
        raise ValueError("A serie de GHI ficou vazia apos a limpeza dos dados.")

    return garantir_resolucao_diaria(cleaned)


def garantir_resolucao_diaria(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega a serie para resolucao diaria usando media diaria de GHI.

    Args:
        df: DataFrame limpo com colunas ``data`` e ``ghi``.

    Returns:
        DataFrame diario com colunas ``data`` e ``ghi``.
    """
    diario = (
        df.set_index("data")[["ghi"]]
        .resample("D")
        .mean()
        .dropna(subset=["ghi"])
        .reset_index()
    )
    return diario


def _read_data_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Formato de arquivo nao suportado: {path}")


def validar_proveniencia_localidades_ev(df: pd.DataFrame, path: Path) -> None:
    """Impede uso de CSVs sinteticos na pasta oficial das localidades EV."""
    if "localidades_ev" not in [part.lower() for part in path.parts]:
        return

    colunas_obrigatorias = {
        "localidade",
        "pais",
        "fonte_dados",
        "produto_dados",
        "endpoint_api",
        "intervalo_minutos",
        "agregacao",
        "unidade_ghi",
    }
    faltantes = sorted(colunas_obrigatorias - set(df.columns))
    if faltantes:
        raise ValueError(
            "CSV em dados/brutos/localidades_ev sem proveniencia NLR/NSRDB "
            f"validavel. Colunas ausentes: {', '.join(faltantes)}."
        )

    localidades = df["localidade"].dropna().astype(str).unique().tolist()
    if any(valor.startswith("lat_") and "_lon_" in valor for valor in localidades):
        raise ValueError(
            "CSV em dados/brutos/localidades_ev parece sintetico "
            "(campo localidade no formato lat_*_lon_*). "
            "Execute treinar_todas_localidades.py --forcar-download."
        )

    fontes = set(df["fonte_dados"].dropna().astype(str).unique().tolist())
    if fontes != {NSRDB_SOURCE}:
        raise ValueError(
            f"CSV em dados/brutos/localidades_ev deve ter fonte_dados={NSRDB_SOURCE}. "
            "Execute treinar_todas_localidades.py --forcar-download."
        )


def encontrar_arquivo_ghi() -> Path | None:
    """Procura um arquivo tabular de GHI nas pastas de dados do projeto."""
    return localizar_arquivo_dados()


@lru_cache(maxsize=32)
def consultar_anos_disponiveis_nsrdb(
    lat: float,
    lon: float,
    api_key: str,
    timeout: int = 60,
) -> tuple[int, ...]:
    """Consulta os anos publicados para o GOES Aggregated PSM v4."""
    import requests

    response = requests.get(
        NSRDB_DATA_QUERY_URL,
        params={
            "api_key": api_key,
            "wkt": f"POINT({lon:.4f} {lat:.4f})",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()

    if payload.get("errors"):
        raise RuntimeError(
            "A consulta de disponibilidade do NSRDB retornou erros: "
            + "; ".join(map(str, payload["errors"]))
        )

    for dataset in payload.get("outputs", []):
        if dataset.get("name") == NSRDB_DATASET:
            years = sorted(
                int(year)
                for year in dataset.get("availableYears", [])
                if str(year).isdigit()
            )
            if years:
                return tuple(years)

    raise RuntimeError(
        "O produto GOES Aggregated PSM v4 nao esta disponivel para as coordenadas "
        f"({lat}, {lon})."
    )


def coletar_ghi_nrel(
    lat: float = 25.7617,
    lon: float = -80.1918,
    start_year: int = 2019,
    end_year: int = 2024,
    inter: int = 60,
    city: str = "Miami",
    pais: str | None = None,
    endereco: str | None = None,
    fonte_localidade: str | None = None,
    fonte_coordenadas: str | None = None,
    metodo_coordenadas: str | None = None,
    osm_elemento: str | None = None,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """Coleta dados diarios de GHI na API NSRDB/NLR usando pvlib.

    Args:
        lat: Latitude do local de coleta.
        lon: Longitude do local de coleta.
        start_year: Primeiro ano da serie.
        end_year: Ultimo ano da serie.
        inter: Intervalo temporal da API, em minutos.
        city: Nome usado para documentar o arquivo gerado.
        pais: Pais da localidade, quando disponivel.
        endereco: Endereco usado para identificar a fabrica.
        fonte_localidade: Pagina oficial que confirma a fabrica.
        fonte_coordenadas: Fonte geografica reproduzivel das coordenadas.
        metodo_coordenadas: Descricao do metodo de obtencao das coordenadas.
        osm_elemento: Identificador do elemento OpenStreetMap.
        output_path: Caminho opcional para salvar o CSV bruto diario.

    Returns:
        DataFrame diario com ``data``, ``ghi`` e metadados da localidade.
    """
    load_dotenv()
    api_key = os.getenv("NREL_API_KEY")
    email = os.getenv("NREL_EMAIL")

    if not api_key or not email:
        raise RuntimeError(
            "Nenhum arquivo de dados foi encontrado e as variaveis NREL_API_KEY "
            "e NREL_EMAIL nao estao configuradas no .env."
        )

    try:
        import pvlib
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "Nenhum arquivo de dados foi encontrado. Instale pvlib para coletar "
            "dados automaticamente pela API NLR."
        ) from exc

    anos_solicitados = list(range(start_year, end_year + 1))
    anos_disponiveis = consultar_anos_disponiveis_nsrdb(
        round(lat, 4),
        round(lon, 4),
        api_key,
    )
    anos_indisponiveis = sorted(set(anos_solicitados) - set(anos_disponiveis))
    if anos_indisponiveis:
        raise ValueError(
            "Os anos solicitados ainda nao estao publicados no "
            f"{NSRDB_PRODUCT}: {anos_indisponiveis}. "
            f"Ultimo ano disponivel para esta coordenada: {max(anos_disponiveis)}."
        )

    frames = []
    metadata_by_year = []
    for index, year in enumerate(anos_solicitados):
        for attempt in range(3):
            try:
                df_year, metadata = pvlib.iotools.get_nsrdb_psm4_aggregated(
                    lat,
                    lon,
                    api_key,
                    email,
                    year=str(year),
                    time_step=inter,
                    parameters=("ghi",),
                    leap_day=True,
                    utc=False,
                    url=NSRDB_API_URL,
                    timeout=120,
                )
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

        daily = df_year[["ghi"]].resample("D").mean()
        if daily.index.tz is not None:
            daily.index = daily.index.tz_localize(None)
        daily.index.name = "data"
        frames.append(daily)
        metadata_by_year.append(metadata)
        if index < len(anos_solicitados) - 1:
            time.sleep(1.1)

    ghi_daily = pd.concat(frames).reset_index()
    ghi_daily = limpar_serie_ghi(ghi_daily)
    ghi_daily["localidade"] = city
    if pais is not None:
        ghi_daily["pais"] = pais
    ghi_daily["lat"] = lat
    ghi_daily["lon"] = lon
    ghi_daily["endereco_localidade"] = endereco
    ghi_daily["fonte_localidade"] = fonte_localidade
    ghi_daily["fonte_coordenadas"] = fonte_coordenadas
    ghi_daily["metodo_coordenadas"] = metodo_coordenadas
    ghi_daily["osm_elemento"] = osm_elemento
    ghi_daily["ano"] = pd.to_datetime(ghi_daily["data"]).dt.year
    ghi_daily["fonte_dados"] = NSRDB_SOURCE
    ghi_daily["produto_dados"] = NSRDB_PRODUCT
    ghi_daily["versao_dados"] = ";".join(
        sorted(
            {
                str(metadata.get("Version", "desconhecida"))
                for metadata in metadata_by_year
            }
        )
    )
    ghi_daily["endpoint_api"] = NSRDB_API_URL
    ghi_daily["intervalo_minutos"] = inter
    ghi_daily["agregacao"] = NSRDB_DAILY_AGGREGATION
    ghi_daily["unidade_ghi"] = NSRDB_GHI_UNIT
    ghi_daily["lat_grade_nsrdb"] = metadata_by_year[0].get("latitude")
    ghi_daily["lon_grade_nsrdb"] = metadata_by_year[0].get("longitude")
    ghi_daily["site_id_nsrdb"] = metadata_by_year[0].get("Location ID")
    ghi_daily["source_nsrdb"] = metadata_by_year[0].get("Source")
    ghi_daily["timezone_nsrdb"] = metadata_by_year[0].get("Time Zone")
    ghi_daily["elevacao_grade_m"] = metadata_by_year[0].get("altitude")
    ghi_daily["ghi_unidade_api"] = metadata_by_year[0].get("GHI Units")
    ghi_daily["data_coleta_utc"] = datetime.now(timezone.utc).isoformat()

    if output_path is None:
        output_path = PASTA_DADOS_BRUTOS / "ghi_diario.csv"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    ghi_daily.to_csv(temporary_path, index=False)
    temporary_path.replace(output_path)
    return ghi_daily


def carregar_serie_ghi(data_path: str | Path | None = None) -> pd.DataFrame:
    """Carrega a serie diaria de GHI a partir de arquivo ou, se necessario, da API.

    Args:
        data_path: Caminho opcional para um arquivo CSV, Excel ou Parquet.

    Returns:
        DataFrame limpo e ordenado com colunas ``data`` e ``ghi``.
    """
    if data_path is not None:
        path = Path(data_path)
        df = _read_data_file(path)
        validar_proveniencia_localidades_ev(df, path)
        return limpar_serie_ghi(df)

    found_path = encontrar_arquivo_ghi()
    if found_path is not None:
        df = _read_data_file(found_path)
        validar_proveniencia_localidades_ev(df, found_path)
        return limpar_serie_ghi(df)

    # Fallback funcional para o estado atual do projeto: os notebooks usam NSRDB,
    # mas ainda nao havia CSV diario salvo no workspace.
    try:
        return limpar_serie_ghi(coletar_ghi_nrel())
    except Exception as exc:
        raise RuntimeError(
            "Nao foi encontrado arquivo local de GHI diario em dados/brutos/ "
            "ou dados/processados/. Insira um CSV com colunas de data e GHI "
            "ou configure NREL_API_KEY e NREL_EMAIL no .env para coletar pela API."
        ) from exc


def quantizar_ghi(
    valores: pd.Series | np.ndarray | Iterable[float],
    n_niveis: int = 128,
    minimo: float | None = None,
    maximo: float | None = None,
    return_params: bool = False,
) -> pd.Series | tuple[pd.Series, dict[str, float]]:
    """Quantiza valores continuos de GHI em niveis inteiros de 0 a 127.

    Args:
        valores: Serie ou vetor com valores continuos de GHI.
        n_niveis: Quantidade de niveis discretos. O padrao e 128.
        minimo: Valor minimo usado na escala. Se ``None``, usa o minimo dos dados.
        maximo: Valor maximo usado na escala. Se ``None``, usa o maximo dos dados.
        return_params: Quando ``True``, retorna tambem os parametros da escala.

    Returns:
        Serie quantizada e, opcionalmente, um dicionario com minimo, maximo e
        numero de niveis.
    """
    series = pd.Series(valores, copy=True).astype(float)
    min_value = float(series.min() if minimo is None else minimo)
    max_value = float(series.max() if maximo is None else maximo)

    if np.isclose(max_value, min_value):
        quantized = pd.Series(np.zeros(len(series), dtype=int), index=series.index)
    else:
        scaled = (series - min_value) / (max_value - min_value)
        quantized = np.rint(scaled.clip(0, 1) * (n_niveis - 1)).astype(int)
        quantized = pd.Series(quantized, index=series.index)

    params = {"min": min_value, "max": max_value, "n_niveis": float(n_niveis)}
    if return_params:
        return quantized, params
    return quantized


def normalizar_minmax(
    valores: pd.Series | np.ndarray | Iterable[float],
    minimo: float | None = None,
    maximo: float | None = None,
    return_params: bool = False,
) -> pd.Series | tuple[pd.Series, dict[str, float]]:
    """Normaliza uma serie pelo metodo Min-Max para o intervalo entre 0 e 1.

    Args:
        valores: Serie ou vetor numerico.
        minimo: Valor minimo usado na normalizacao. Se ``None``, usa o minimo.
        maximo: Valor maximo usado na normalizacao. Se ``None``, usa o maximo.
        return_params: Quando ``True``, retorna tambem os parametros da escala.

    Returns:
        Serie normalizada e, opcionalmente, um dicionario com minimo e maximo.
    """
    series = pd.Series(valores, copy=True).astype(float)
    min_value = float(series.min() if minimo is None else minimo)
    max_value = float(series.max() if maximo is None else maximo)

    if np.isclose(max_value, min_value):
        normalized = pd.Series(np.zeros(len(series), dtype=float), index=series.index)
    else:
        normalized = ((series - min_value) / (max_value - min_value)).clip(0, 1)

    params = {"min": min_value, "max": max_value}
    if return_params:
        return normalized, params
    return normalized


def preparar_serie_temporal(
    df: pd.DataFrame,
    lags: tuple[int, ...] = (1, 2, 3, 7),
    moving_windows: tuple[int, ...] = (3, 7, 30),
    n_niveis: int = 128,
    train_ratio: float = 0.8,
    output_path: str | Path | None = PASTA_DADOS_PROCESSADOS / "ghi_features.csv",
) -> PreparationResult:
    """Prepara a base supervisionada para previsao do GHI do dia seguinte.

    Args:
        df: Serie bruta contendo data e GHI.
        lags: Defasagens temporais usadas como features.
        moving_windows: Janelas das medias moveis usadas como features.
        n_niveis: Quantidade de niveis da quantizacao.
        train_ratio: Proporcao cronologica inicial usada para treino.
        output_path: Arquivo opcional para salvar as features. Use ``None``
            para preparar os dados sem escrever no disco.

    Returns:
        Objeto ``PreparationResult`` com a base de modelagem, colunas de
        entrada, tamanho do treino e parametros de transformacao.
    """
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio deve estar entre 0 e 1.")

    serie = limpar_serie_ghi(df)
    raw_train_size = max(1, int(len(serie) * train_ratio))

    # A quantizacao e a normalizacao usam parametros ajustados somente no trecho
    # de treino, evitando que estatisticas do futuro vazem para o conjunto teste.
    train_ghi = serie.loc[: raw_train_size - 1, "ghi"]
    ghi_quantizado, quantization_params = quantizar_ghi(
        serie["ghi"],
        n_niveis=n_niveis,
        minimo=float(train_ghi.min()),
        maximo=float(train_ghi.max()),
        return_params=True,
    )
    ghi_normalizado, normalization_params = normalizar_minmax(
        ghi_quantizado,
        minimo=0,
        maximo=n_niveis - 1,
        return_params=True,
    )

    dados = serie.copy()
    dados["ghi_quantizado"] = ghi_quantizado.astype(int)
    dados["ghi_normalizado"] = ghi_normalizado.astype(float)

    dados_modelagem, feature_columns = criar_features_temporais(
        dados,
        lags=lags,
        moving_windows=moving_windows,
    )
    train_size = int(len(dados_modelagem) * train_ratio)

    if train_size == 0 or train_size == len(dados_modelagem):
        raise ValueError(
            "A serie nao tem observacoes suficientes para criar treino e teste "
            "apos lags e medias moveis."
        )

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        dados_modelagem.to_csv(output_path, index=False)

    return PreparationResult(
        dados_modelagem=dados_modelagem,
        feature_columns=feature_columns,
        train_size=train_size,
        quantization_params=quantization_params,
        normalization_params=normalization_params,
    )
