"""Contexto meteorologico diario independente para a analise de erros.

Os modelos de previsao usam somente o historico causal de GHI e a identidade
da localidade. Este modulo consulta separadamente a API NASA POWER para
caracterizar, depois da previsao, dias de chuva ou nebulosidade elevada. Assim,
uma baixa irradiancia nunca e usada como prova circular de chuva.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from codigo_fonte.localidades_ev import LOCALIDADES_EV


POWER_DAILY_ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETROS_POWER = (
    "PRECTOTCORR",
    "CLOUD_AMT",
    "ALLSKY_SFC_SW_DWN",
    "CLRSKY_SFC_SW_DWN",
)
LIMIAR_CHUVA_MM_DIA = 1.0
LIMIAR_MUITO_NUBLADO_PERCENTUAL = 80.0
VALOR_AUSENTE_POWER = -999.0


def _data_power(valor: str | date | pd.Timestamp) -> str:
    convertido = pd.Timestamp(valor)
    if convertido.tz is not None:
        convertido = convertido.tz_localize(None)
    return convertido.strftime("%Y%m%d")


def construir_url_power(
    *,
    latitude: float,
    longitude: float,
    inicio: str | date | pd.Timestamp,
    fim: str | date | pd.Timestamp,
) -> str:
    """Constroi uma consulta diaria em tempo solar local e formato JSON."""

    inicio_power = _data_power(inicio)
    fim_power = _data_power(fim)
    if inicio_power > fim_power:
        raise ValueError("A data inicial deve ser anterior ou igual a final.")
    if not -90 <= float(latitude) <= 90 or not -180 <= float(longitude) <= 180:
        raise ValueError("Latitude ou longitude fora dos limites geograficos.")
    consulta = urlencode(
        {
            "parameters": ",".join(PARAMETROS_POWER),
            "community": "RE",
            "longitude": f"{float(longitude):.7f}",
            "latitude": f"{float(latitude):.7f}",
            "start": inicio_power,
            "end": fim_power,
            "format": "JSON",
            "time-standard": "LST",
        }
    )
    return f"{POWER_DAILY_ENDPOINT}?{consulta}"


def _serie_parametro(
    parametros: Mapping[str, Mapping[str, object]], nome: str
) -> pd.Series:
    if nome not in parametros or not isinstance(parametros[nome], Mapping):
        raise ValueError(f"Parametro {nome} ausente na resposta NASA POWER.")
    serie = pd.Series(parametros[nome], dtype="object")
    serie.index = pd.to_datetime(serie.index, format="%Y%m%d", errors="raise")
    serie = pd.to_numeric(serie, errors="coerce").astype(float)
    return serie.mask(np.isclose(serie, VALOR_AUSENTE_POWER))


def interpretar_resposta_power(
    resposta: Mapping[str, object],
    *,
    localidade: str,
    latitude: float,
    longitude: float,
) -> pd.DataFrame:
    """Converte uma resposta POWER em tabela diaria auditavel."""

    propriedades = resposta.get("properties")
    if not isinstance(propriedades, Mapping):
        raise ValueError("Resposta NASA POWER sem objeto properties.")
    parametros = propriedades.get("parameter")
    if not isinstance(parametros, Mapping):
        raise ValueError("Resposta NASA POWER sem series em properties.parameter.")

    series = {nome: _serie_parametro(parametros, nome) for nome in PARAMETROS_POWER}
    indice = series[PARAMETROS_POWER[0]].index
    if any(not serie.index.equals(indice) for serie in series.values()):
        raise ValueError("Parametros NASA POWER possuem grades de datas distintas.")
    quadro = pd.DataFrame(
        {
            "data_local": indice,
            "localidade": localidade,
            "latitude_fabrica": float(latitude),
            "longitude_fabrica": float(longitude),
            "precipitacao_corrigida_mm_dia": series["PRECTOTCORR"].to_numpy(),
            "nebulosidade_percentual": series["CLOUD_AMT"].to_numpy(),
            "irradiacao_all_sky_kwh_m2_dia": series[
                "ALLSKY_SFC_SW_DWN"
            ].to_numpy(),
            "irradiacao_clear_sky_kwh_m2_dia": series[
                "CLRSKY_SFC_SW_DWN"
            ].to_numpy(),
        }
    )
    denominador = quadro["irradiacao_clear_sky_kwh_m2_dia"].where(
        quadro["irradiacao_clear_sky_kwh_m2_dia"] > 0
    )
    quadro["indice_all_sky_clear_sky"] = (
        quadro["irradiacao_all_sky_kwh_m2_dia"] / denominador
    )
    quadro["chuva_relevante"] = (
        quadro["precipitacao_corrigida_mm_dia"] >= LIMIAR_CHUVA_MM_DIA
    )
    quadro["muito_nublado"] = (
        quadro["nebulosidade_percentual"] >= LIMIAR_MUITO_NUBLADO_PERCENTUAL
    )
    quadro["condicao_adversa_independente"] = (
        quadro["chuva_relevante"] | quadro["muito_nublado"]
    )
    quadro["fonte_contexto"] = "NASA POWER Daily API"
    quadro["time_standard"] = "LST"
    return quadro.sort_values("data_local", ignore_index=True)


def baixar_json_power(url: str, *, timeout: float = 60.0) -> dict[str, object]:
    """Baixa uma resposta JSON com identificacao explicita do cliente."""

    requisicao = Request(url, headers={"User-Agent": "GHI-journal-study/1.0"})
    with urlopen(requisicao, timeout=timeout) as resposta:  # noqa: S310
        conteudo = resposta.read()
    resultado = json.loads(conteudo.decode("utf-8"))
    if not isinstance(resultado, dict):
        raise ValueError("A API NASA POWER nao retornou um objeto JSON.")
    return resultado


def _gravar_json_cache(caminho: Path, resposta: Mapping[str, object]) -> None:
    """Grava o cache e tolera bloqueios transitorios de indexadores no Windows."""

    conteudo = json.dumps(resposta, ensure_ascii=False, sort_keys=True)
    temporario = caminho.with_suffix(".json.tmp")
    temporario.write_text(conteudo, encoding="utf-8")
    for tentativa in range(6):
        try:
            os.replace(temporario, caminho)
            return
        except PermissionError:
            if tentativa == 5:
                # O JSON da API e pequeno e seu SHA-256 e registrado. Este
                # fallback continua recuperavel: uma interrupcao produz JSON
                # invalido, que pode ser substituido com ``--atualizar``.
                caminho.write_text(conteudo, encoding="utf-8")
                try:
                    temporario.unlink()
                except PermissionError:
                    pass
                return
            time.sleep(0.25 * (tentativa + 1))


def _slug(nome: str) -> str:
    import unicodedata

    ascii_nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return "_".join(ascii_nome.lower().replace("-", " ").split())


def coletar_contexto_meteorologico(
    *,
    inicio: str | date | pd.Timestamp,
    fim: str | date | pd.Timestamp,
    pasta_cache: str | Path,
    localidades: Sequence[Mapping[str, object]] = LOCALIDADES_EV,
    atualizar: bool = False,
    baixar: Callable[[str], Mapping[str, object]] | None = None,
    espera_entre_consultas_s: float = 0.25,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    """Consulta ou reutiliza o cache JSON para todas as localidades."""

    pasta = Path(pasta_cache)
    pasta.mkdir(parents=True, exist_ok=True)
    baixar_efetivo = baixar or baixar_json_power
    tabelas: list[pd.DataFrame] = []
    proveniencia: list[dict[str, object]] = []
    for indice, cadastro in enumerate(localidades):
        nome = str(cadastro["nome"])
        latitude = float(cadastro["lat"])
        longitude = float(cadastro["lon"])
        url = construir_url_power(
            latitude=latitude,
            longitude=longitude,
            inicio=inicio,
            fim=fim,
        )
        caminho = pasta / (
            f"{_slug(nome)}_{_data_power(inicio)}_{_data_power(fim)}.json"
        )
        origem = "cache"
        if atualizar or not caminho.exists():
            resposta = dict(baixar_efetivo(url))
            _gravar_json_cache(caminho, resposta)

            origem = "api"
            if indice + 1 < len(localidades) and espera_entre_consultas_s > 0:
                time.sleep(float(espera_entre_consultas_s))
        else:
            resposta = json.loads(caminho.read_text(encoding="utf-8"))
        bruto = caminho.read_bytes()
        tabela = interpretar_resposta_power(
            resposta,
            localidade=nome,
            latitude=latitude,
            longitude=longitude,
        )
        tabelas.append(tabela)
        proveniencia.append(
            {
                "localidade": nome,
                "url": url,
                "arquivo_cache": caminho.as_posix(),
                "sha256": hashlib.sha256(bruto).hexdigest(),
                "origem_execucao": origem,
                "linhas": int(len(tabela)),
            }
        )
    combinado = pd.concat(tabelas, ignore_index=True)
    combinado = combinado.sort_values(["localidade", "data_local"], ignore_index=True)
    return combinado, proveniencia


__all__ = [
    "LIMIAR_CHUVA_MM_DIA",
    "LIMIAR_MUITO_NUBLADO_PERCENTUAL",
    "PARAMETROS_POWER",
    "POWER_DAILY_ENDPOINT",
    "baixar_json_power",
    "coletar_contexto_meteorologico",
    "construir_url_power",
    "interpretar_resposta_power",
]
