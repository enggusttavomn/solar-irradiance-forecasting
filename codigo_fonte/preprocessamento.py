"""Coleta e preparacao da serie diaria de GHI.

Este modulo cobre a parte anterior ao treinamento:

1. identifica e le dados tabulares;
2. coleta GHI oficial quando necessario;
3. limpa e agrega a serie em frequencia diaria;
4. ajusta quantizacao e normalizacao sem usar estatisticas do teste;
5. chama a criacao das features e devolve a base pronta.
"""

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


# Nomes aceitos para identificar automaticamente a coluna temporal.
DATE_CANDIDATES = (
    "data",
    "date",
    "datetime",
    "timestamp",
    "time",
    "ds",
)

# Nomes comuns para a coluna de Irradiancia Global Horizontal.
GHI_CANDIDATES = (
    "ghi",
    "global_horizontal_irradiance",
    "global horizontal irradiance",
    "irradiancia_global_horizontal",
    "irradiancia global horizontal",
    "global_horizontal",
)

# Constantes de proveniencia. Alem de configurar a coleta, elas sao gravadas
# nos CSVs e verificadas posteriormente pelo validador das localidades.
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
    """Agrupa todas as saidas necessarias depois do pre-processamento.

    Attributes:
        dados_modelagem: Tabela com features e alvos alinhados.
        feature_columns: Nomes das colunas fornecidas aos modelos.
        train_size: Quantidade de exemplos destinada ao treino.
        quantization_params: Limites usados para converter GHI em 128 niveis.
        normalization_params: Limites usados para mapear os niveis para [0, 1].
    """

    dados_modelagem: pd.DataFrame
    feature_columns: list[str]
    train_size: int
    quantization_params: dict[str, float]
    normalization_params: dict[str, float]


def _normalizar_nome_coluna(column: str) -> str:
    """Uniformiza um nome somente para comparacao durante a deteccao."""
    return str(column).strip().lower().replace("-", "_")


def detectar_colunas(df: pd.DataFrame) -> tuple[str | None, str]:
    """Detecta automaticamente a coluna de data e a coluna de GHI.

    Args:
        df: DataFrame carregado a partir de arquivo ou API.

    Returns:
        Uma tupla com o nome da coluna de data, que pode ser ``None`` se o
        indice ja for datetime, e o nome da coluna de GHI.
    """
    # O dicionario liga o nome simplificado ao nome original do DataFrame.
    normalized = {_normalizar_nome_coluna(col): col for col in df.columns}

    # A ordem dos candidatos define a prioridade quando mais de um nome existe.
    date_col = None
    for candidate in DATE_CANDIDATES:
        if candidate in normalized:
            date_col = normalized[candidate]
            break

    # Primeiro procura correspondencia exata com os nomes conhecidos.
    ghi_col = None
    for candidate in GHI_CANDIDATES:
        if candidate in normalized:
            ghi_col = normalized[candidate]
            break

    # Segundo nivel: aceita qualquer coluna cujo nome contenha a sigla GHI.
    if ghi_col is None:
        for normalized_name, original_name in normalized.items():
            if "ghi" in normalized_name:
                ghi_col = original_name
                break

    # Ultimo recurso: uma unica coluna numerica provavelmente representa GHI.
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
    # Trabalhar em copia impede alteracoes inesperadas no objeto do chamador.
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
    # A sequencia abaixo elimina registros impossiveis e estabelece a ordem
    # temporal exigida pelos lags, pelas janelas e pela divisao treino/teste.
    cleaned = cleaned.dropna(subset=["data", "ghi"]).sort_values("data")
    cleaned = cleaned[cleaned["ghi"] >= 0]
    cleaned = cleaned.drop_duplicates(subset=["data"], keep="last")
    cleaned = cleaned.reset_index(drop=True)

    if cleaned.empty:
        raise ValueError("A serie de GHI ficou vazia apos a limpeza dos dados.")

    # Todo o restante do projeto opera com exatamente uma observacao por dia.
    return garantir_resolucao_diaria(cleaned)


def garantir_resolucao_diaria(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega a serie para resolucao diaria usando media diaria de GHI.

    Args:
        df: DataFrame limpo com colunas ``data`` e ``ghi``.

    Returns:
        DataFrame diario com colunas ``data`` e ``ghi``.
    """
    # ``resample("D")`` cria grupos por dia. A media e apropriada aqui porque
    # o projeto modela irradiancia media em W/m2, nao energia acumulada.
    diario = (
        df.set_index("data")[["ghi"]]
        .resample("D")
        .mean()
        .dropna(subset=["ghi"])
        .reset_index()
    )
    return diario


def calcular_estatisticas_ghi_horario(df: pd.DataFrame) -> dict[str, float | str]:
    """Calcula media, sigma e COV do GHI horario antes da agregacao diaria."""
    date_col, ghi_col = detectar_colunas(df)
    if date_col is None:
        if isinstance(df.index, pd.DatetimeIndex):
            datas = pd.Series(df.index, index=df.index)
        else:
            raise ValueError("Nao foi encontrada coluna de data para estatisticas horarias.")
    else:
        datas = pd.to_datetime(df[date_col], errors="coerce")

    ghi = pd.to_numeric(df[ghi_col], errors="coerce")
    valido = datas.notna() & ghi.notna() & (ghi >= 0)
    datas_validas = datas.loc[valido].sort_values()
    ghi_valido = ghi.loc[datas_validas.index].astype(float)

    if ghi_valido.empty:
        return {
            "ghi_horario_media": float("nan"),
            "ghi_horario_sigma": float("nan"),
            "ghi_horario_cov": float("nan"),
            "ghi_horario_cov_percentual": float("nan"),
            "ghi_horario_observacoes": 0.0,
            "ghi_horario_fonte_estatistica": "indisponivel",
        }

    deltas = datas_validas.diff().dropna()
    intervalo_mediano_horas = deltas.median() / pd.Timedelta(hours=1) if not deltas.empty else float("nan")
    fonte = "horaria" if pd.notna(intervalo_mediano_horas) and intervalo_mediano_horas <= 1.5 else "nao_horaria"

    media = float(ghi_valido.mean())
    sigma = float(ghi_valido.std(ddof=0))
    cov = float("nan") if np.isclose(media, 0.0) else sigma / media
    return {
        "ghi_horario_media": media,
        "ghi_horario_sigma": sigma,
        "ghi_horario_cov": cov,
        "ghi_horario_cov_percentual": cov * 100 if not np.isnan(cov) else float("nan"),
        "ghi_horario_observacoes": float(len(ghi_valido)),
        "ghi_horario_intervalo_mediano_horas": float(intervalo_mediano_horas),
        "ghi_horario_fonte_estatistica": fonte,
    }


def _read_data_file(path: Path) -> pd.DataFrame:
    """Escolhe o leitor do pandas de acordo com a extensao do arquivo."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Formato de arquivo nao suportado: {path}")


def validar_proveniencia_localidades_ev(df: pd.DataFrame, path: Path) -> None:
    """Aplica uma verificacao basica aos arquivos da pasta oficial.

    Esta funcao protege o fluxo de uma unica serie. A validacao completa de
    cobertura, coordenadas e hash fica em ``treinar_todas_localidades.py``.
    Arquivos fora da pasta ``localidades_ev`` podem ser bases fornecidas pelo
    usuario e, por isso, nao precisam conter os metadados oficiais.
    """
    # A regra especial e aplicada somente aos CSVs oficiais das dez fabricas.
    if "localidades_ev" not in [part.lower() for part in path.parts]:
        return

    # Sem estes campos nao e possivel demonstrar a origem do arquivo.
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

    # Versoes antigas sinteticas usavam a coordenada como nome da localidade.
    localidades = df["localidade"].dropna().astype(str).unique().tolist()
    if any(valor.startswith("lat_") and "_lon_" in valor for valor in localidades):
        raise ValueError(
            "CSV em dados/brutos/localidades_ev parece sintetico "
            "(campo localidade no formato lat_*_lon_*). "
            "Execute treinar_todas_localidades.py --forcar-download."
        )

    # Todos os registros do arquivo devem declarar a mesma fonte oficial.
    fontes = set(df["fonte_dados"].dropna().astype(str).unique().tolist())
    if fontes != {NSRDB_SOURCE}:
        raise ValueError(
            f"CSV em dados/brutos/localidades_ev deve ter fonte_dados={NSRDB_SOURCE}. "
            "Execute treinar_todas_localidades.py --forcar-download."
        )


def encontrar_arquivo_ghi() -> Path | None:
    """Delega a busca automatica ao utilitario compartilhado."""
    return localizar_arquivo_dados()


@lru_cache(maxsize=32)
def consultar_anos_disponiveis_nsrdb(
    lat: float,
    lon: float,
    api_key: str,
    timeout: int = 60,
) -> tuple[int, ...]:
    """Consulta os anos publicados para o GOES Aggregated PSM v4.

    O cache evita repetir a mesma requisicao durante uma unica execucao quando
    latitude, longitude e chave sao iguais.
    """
    # Importacao local: ``requests`` so e necessario quando ha consulta remota.
    import requests

    # A API de consulta recebe a coordenada em WKT no formato POINT(lon lat).
    response = requests.get(
        NSRDB_DATA_QUERY_URL,
        params={
            "api_key": api_key,
            "wkt": f"POINT({lon:.4f} {lat:.4f})",
        },
        timeout=timeout,
    )
    # Converte erros HTTP em excecoes antes de tentar interpretar o JSON.
    response.raise_for_status()
    payload = response.json()

    if payload.get("errors"):
        raise RuntimeError(
            "A consulta de disponibilidade do NSRDB retornou erros: "
            + "; ".join(map(str, payload["errors"]))
        )

    # Uma coordenada pode listar varios produtos; selecionamos o usado no TCC.
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

    Notes:
        A API entrega valores no intervalo solicitado, normalmente uma hora.
        O projeto calcula a media das observacoes de cada dia e mantem a unidade
        W/m2. Isso nao e uma integracao de energia em Wh/m2.
    """
    # ``load_dotenv`` permite manter as credenciais fora do codigo-fonte.
    load_dotenv()
    api_key = os.getenv("NREL_API_KEY")
    email = os.getenv("NREL_EMAIL")

    if not api_key or not email:
        raise RuntimeError(
            "Nenhum arquivo de dados foi encontrado e as variaveis NREL_API_KEY "
            "e NREL_EMAIL nao estao configuradas no .env."
        )

    # Dependencias de rede sao importadas apenas quando a coleta sera realizada.
    try:
        import pvlib
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "Nenhum arquivo de dados foi encontrado. Instale pvlib para coletar "
            "dados automaticamente pela API NLR."
        ) from exc

    # Antes de baixar, confirma que todos os anos realmente foram publicados.
    # Isso evita preencher silenciosamente anos indisponiveis.
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

    # Cada ano e coletado separadamente porque este e o contrato da API.
    frames = []
    metadata_by_year = []
    hourly_frames = []
    for index, year in enumerate(anos_solicitados):
        # Faz ate tres tentativas para tolerar falhas transitorias de rede.
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
                # Espera 1 segundo e depois 2 segundos entre as tentativas.
                time.sleep(2 ** attempt)

        # Reduz as observacoes horarias a uma media por dia. Horas noturnas
        # tambem fazem parte da media diaria de 24 horas.
        hourly_frames.append(df_year[["ghi"]])
        daily = df_year[["ghi"]].resample("D").mean()
        # Remove apenas a informacao de fuso, preservando o horario local usado
        # pela consulta (``utc=False``).
        if daily.index.tz is not None:
            daily.index = daily.index.tz_localize(None)
        daily.index.name = "data"
        frames.append(daily)
        metadata_by_year.append(metadata)
        # Pequena pausa reduz o risco de exceder limites de requisicao da API.
        if index < len(anos_solicitados) - 1:
            time.sleep(1.1)

    # Une todos os anos, limpa novamente e garante uma serie diaria ordenada.
    ghi_daily = pd.concat(frames).reset_index()
    estatisticas_horarias = calcular_estatisticas_ghi_horario(pd.concat(hourly_frames))
    ghi_daily = limpar_serie_ghi(ghi_daily)

    # Bloco de identificacao geografica da localidade.
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

    # Bloco de proveniencia da consulta e da unidade dos dados.
    ghi_daily["fonte_dados"] = NSRDB_SOURCE
    ghi_daily["produto_dados"] = NSRDB_PRODUCT
    # Pode haver mais de uma versao entre os anos; o CSV registra todas sem
    # duplicatas e em ordem estavel.
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
    # Metadados do ponto da grade efetivamente retornado pelo NSRDB. Eles podem
    # diferir levemente da coordenada exata da fabrica.
    ghi_daily["lat_grade_nsrdb"] = metadata_by_year[0].get("latitude")
    ghi_daily["lon_grade_nsrdb"] = metadata_by_year[0].get("longitude")
    ghi_daily["site_id_nsrdb"] = metadata_by_year[0].get("Location ID")
    ghi_daily["source_nsrdb"] = metadata_by_year[0].get("Source")
    ghi_daily["timezone_nsrdb"] = metadata_by_year[0].get("Time Zone")
    ghi_daily["elevacao_grade_m"] = metadata_by_year[0].get("altitude")
    ghi_daily["ghi_unidade_api"] = metadata_by_year[0].get("GHI Units")
    for coluna, valor in estatisticas_horarias.items():
        ghi_daily[coluna] = valor
    # Data em UTC permite saber quando o arquivo foi obtido.
    ghi_daily["data_coleta_utc"] = datetime.now(timezone.utc).isoformat()

    # Escrita atomica: primeiro grava um temporario e somente depois substitui
    # o destino. Assim, uma interrupcao nao deixa um CSV final pela metade.
    if output_path is None:
        output_path = PASTA_DADOS_BRUTOS / "ghi_diario.csv"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    ghi_daily.to_csv(temporary_path, index=False, lineterminator="\n")
    temporary_path.replace(output_path)
    return ghi_daily


def carregar_serie_ghi(data_path: str | Path | None = None) -> pd.DataFrame:
    """Carrega a serie diaria de GHI a partir de arquivo ou, se necessario, da API.

    Args:
        data_path: Caminho opcional para um arquivo CSV, Excel ou Parquet.

    Returns:
        DataFrame limpo e ordenado com colunas ``data`` e ``ghi``.
    """
    # Prioridade 1: caminho explicitamente informado pelo usuario.
    if data_path is not None:
        path = Path(data_path)
        df = _read_data_file(path)
        validar_proveniencia_localidades_ev(df, path)
        return limpar_serie_ghi(df)

    # Prioridade 2: procura automatica nas pastas padrao.
    found_path = encontrar_arquivo_ghi()
    if found_path is not None:
        df = _read_data_file(found_path)
        validar_proveniencia_localidades_ev(df, found_path)
        return limpar_serie_ghi(df)

    # Prioridade 3: coleta remota usando as credenciais do arquivo .env.
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

    Notes:
        Valores abaixo ou acima da faixa de ajuste sao limitados aos niveis
        extremos. Isso e importante quando a faixa foi aprendida no treino e o
        teste apresenta um valor mais extremo.
    """
    # Converte qualquer vetor aceito para uma Serie float com o mesmo indice.
    series = pd.Series(valores, copy=True).astype(float)
    min_value = float(series.min() if minimo is None else minimo)
    max_value = float(series.max() if maximo is None else maximo)

    # Uma serie constante causaria divisao por zero; nesse caso usa o nivel 0.
    if np.isclose(max_value, min_value):
        quantized = pd.Series(np.zeros(len(series), dtype=int), index=series.index)
    else:
        # Primeiro leva para [0, 1], depois para [0, n_niveis-1] e arredonda.
        scaled = (series - min_value) / (max_value - min_value)
        quantized = np.rint(scaled.clip(0, 1) * (n_niveis - 1)).astype(int)
        quantized = pd.Series(quantized, index=series.index)

    # Os parametros precisam acompanhar o modelo para transformar novos dados.
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
    # A formula e (x - minimo) / (maximo - minimo).
    series = pd.Series(valores, copy=True).astype(float)
    min_value = float(series.min() if minimo is None else minimo)
    max_value = float(series.max() if maximo is None else maximo)

    # Evita divisao por zero quando todos os valores sao iguais.
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

    Notes:
        A quantizacao e ajustada antes da criacao definitiva das features, mas
        o corte bruto e calculado para corresponder ao mesmo conjunto de alvos
        que sera usado no treino depois das janelas.
    """
    # Validacoes antecipadas produzem mensagens claras antes de iniciar calculos.
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio deve estar entre 0 e 1.")
    if any(lag < 1 for lag in lags):
        raise ValueError("Todos os lags devem ser maiores ou iguais a 1.")
    if any(janela < 1 for janela in moving_windows):
        raise ValueError("Todas as janelas moveis devem ser maiores ou iguais a 1.")

    # Etapa 1: contrato comum com duas colunas, ordem cronologica e escala diaria.
    serie = limpar_serie_ghi(df)

    # Uma janela de N dias perde N-1 linhas no inicio. Um lag chamado t-k usa
    # ``shift(k-1)`` porque os nomes sao relativos ao alvo do dia seguinte.
    historico_necessario = max(
        [lag - 1 for lag in lags] + [janela - 1 for janela in moving_windows],
        default=0,
    )
    # O ``-1`` adicional representa a ultima data, que nao possui alvo t+1.
    quantidade_modelagem = len(serie) - historico_necessario - 1
    train_size = int(quantidade_modelagem * train_ratio)
    if train_size <= 0 or train_size >= quantidade_modelagem:
        raise ValueError(
            "A serie nao tem observacoes suficientes para criar treino e teste "
            "apos lags e medias moveis."
        )

    # Reconverte o tamanho da base modelada para o tamanho equivalente na serie
    # bruta, incluindo o historico inicial e o ultimo alvo do treino.
    raw_train_size = historico_necessario + train_size + 1

    # A quantizacao e a normalizacao usam parametros ajustados somente no trecho
    # de treino, evitando que estatisticas do futuro vazem para o conjunto teste.
    # ``loc`` inclui as duas pontas; por isso o limite termina em size - 1.
    train_ghi = serie.loc[: raw_train_size - 1, "ghi"]
    ghi_quantizado, quantization_params = quantizar_ghi(
        serie["ghi"],
        n_niveis=n_niveis,
        minimo=float(train_ghi.min()),
        maximo=float(train_ghi.max()),
        return_params=True,
    )
    # Como a entrada da normalizacao ja esta em 0..127, seus limites sao fixos.
    ghi_normalizado, normalization_params = normalizar_minmax(
        ghi_quantizado,
        minimo=0,
        maximo=n_niveis - 1,
        return_params=True,
    )

    # Etapa 2: anexa as duas representacoes transformadas a serie original.
    dados = serie.copy()
    dados["ghi_quantizado"] = ghi_quantizado.astype(int)
    dados["ghi_normalizado"] = ghi_normalizado.astype(float)

    # Etapa 3: cria lags, medias moveis e o alvo do dia seguinte.
    dados_modelagem, feature_columns = criar_features_temporais(
        dados,
        lags=lags,
        moving_windows=moving_windows,
    )
    # Recalcula sobre o tamanho real como verificacao final do corte.
    train_size = int(len(dados_modelagem) * train_ratio)

    # Salvar e opcional para permitir testes e uso puramente em memoria.
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
