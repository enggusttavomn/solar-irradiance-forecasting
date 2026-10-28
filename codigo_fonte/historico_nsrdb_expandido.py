"""Historico NSRDB 1998--2022 isolado, rastreavel e retomavel.

Consulta somente os blocos HDF5 dos dez pontos ja cadastrados. Os arquivos
originais de 2019--2024 sao referencias verificadas, nunca sobrescritos.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import fsspec
import h5py
import numpy as np
import pandas as pd
import requests

from codigo_fonte.dados_horarios_nsrdb import NSRDB_S3_BASE, carregar_registro_pontos

RAIZ = Path(__file__).resolve().parents[1]
PASTA_ATUAL = RAIZ / "dados/brutos/localidades_ev_horario"
PASTA_HISTORICO = RAIZ / "dados/brutos/localidades_ev_horario_1998_2022"
PASTA_DIARIA = RAIZ / "dados/brutos/localidades_ev_1998_2022"
PASTA_MENSAL = RAIZ / "dados/brutos/localidades_ev_mensal_1998_2022"
PASTA_RELATORIO = RAIZ / "relatorios/quantizacao_todos_modelos_20260929/historico"
ANOS = tuple(range(1998, 2023))
COLUNAS_META = ["site_id_nsrdb", "localidade", "lat_grade_nsrdb", "lon_grade_nsrdb", "timezone_nsrdb"]


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def serializar_tempo_ns(indice: pd.DatetimeIndex) -> np.ndarray:
    if indice.tz is None:
        raise ValueError("Indice temporal precisa informar o fuso horario.")
    return indice.tz_convert("UTC").as_unit("ns").asi8


def sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def salvar_json(valor: object, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".tmp")
    temporario.write_text(json.dumps(valor, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporario.replace(destino)


def _relativo(caminho: Path) -> str:
    return caminho.resolve().relative_to(RAIZ).as_posix()


def verificar_cobertura_remota(ano: int) -> dict:
    url = f"{NSRDB_S3_BASE}/nsrdb_{ano}.h5"
    with requests.Session() as sessao:
        resposta = sessao.head(url, timeout=45)
        resposta.raise_for_status()
        cab = dict(resposta.headers)
        with sessao.get(url, headers={"Range": "bytes=0-7"}, timeout=45, stream=True) as resposta:
            if resposta.status_code != 206 or resposta.raw.read(9) != b"\x89HDF\r\n\x1a\n":
                raise ValueError(f"Fonte {ano} nao respondeu um intervalo HDF5 valido.")
    return {"ano": ano, "url": url, "bytes_arquivo_remoto": int(cab["Content-Length"]),
            "etag": cab.get("ETag"), "last_modified": cab.get("Last-Modified"),
            "range_status": 206, "range_bytes_transferidos": 8, "verificado_em_utc": agora()}


def verificar_ano_horario(dados: pd.DataFrame, ano: int, registro: pd.DataFrame) -> dict:
    ids = set(registro.site_id_nsrdb.astype(int))
    if set(dados.site_id_nsrdb.astype(int)) != ids:
        raise ValueError(f"{ano}: pontos de grade divergentes.")
    tempos = pd.to_datetime(dados.timestamp_utc, utc=True, errors="raise")
    grade = pd.date_range(f"{ano}-01-01", f"{ano+1}-01-01", freq="h", inclusive="left", tz="UTC")
    if not np.isfinite(dados.ghi).all() or (dados.ghi < 0).any():
        raise ValueError(f"{ano}: GHI invalida.")
    for linha in registro.itertuples(index=False):
        parte = dados.loc[dados.site_id_nsrdb == linha.site_id_nsrdb]
        indice = pd.DatetimeIndex(tempos.loc[parte.index]).sort_values()
        if not indice.equals(grade):
            raise ValueError(f"{ano}: grade horaria incompleta/duplicada no ponto {linha.site_id_nsrdb}.")
        for coluna in COLUNAS_META[1:]:
            encontrados = parte[coluna].unique()
            esperado = getattr(linha, coluna)
            if len(encontrados) != 1 or encontrados[0] != esperado:
                raise ValueError(f"{ano}: metadado {coluna} divergente para {linha.site_id_nsrdb}.")
    return {"ano": ano, "horas_por_localidade": len(grade), "localidades": len(ids),
            "linhas": len(dados), "ghi_min_wm2": float(dados.ghi.min()),
            "ghi_max_wm2": float(dados.ghi.max()), "inicio_utc": grade[0].isoformat(),
            "fim_utc": grade[-1].isoformat(), "grade_continua": True, "sem_imputacao": True}


def extrair_ano(ano: int, registro: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    inicio = time.perf_counter()
    registro = carregar_registro_pontos() if registro is None else registro
    ids = registro.site_id_nsrdb.astype(int).to_numpy()
    if len(ids) != 10 or (np.diff(ids) <= 0).any():
        raise ValueError("Esperava os dez IDs distintos em ordem crescente.")
    url = f"{NSRDB_S3_BASE}/nsrdb_{ano}.h5"
    with fsspec.open(url, mode="rb", block_size=64 * 1024, cache_type="bytes") as remoto:
        with h5py.File(remoto, "r") as arquivo:
            if not {"meta", "ghi", "time_index"}.issubset(arquivo.keys()):
                raise ValueError("HDF5 incompleto.")
            dados_ghi = arquivo["ghi"]
            escala = float(dados_ghi.attrs.get("scale_factor", 1.0))
            if escala != 1.0:
                raise ValueError(f"Escala GHI inesperada: {escala}; requer revisao explicita.")
            grade_esperada = pd.date_range(f"{ano}-01-01", f"{ano+1}-01-01", freq="30min", inclusive="left", tz="UTC")
            indice = pd.to_datetime(arquivo["time_index"][:].astype(str), utc=True)
            if not indice.equals(grade_esperada):
                raise ValueError(f"{ano}: indice de 30 minutos divergente do ano civil UTC.")
            meta = arquivo["meta"][ids]
            for i, id_ponto in enumerate(ids):
                for chave, coluna in [("latitude", "lat_grade_nsrdb"), ("longitude", "lon_grade_nsrdb"), ("timezone", "timezone_nsrdb")]:
                    if not np.isclose(float(meta[i][chave]), float(registro.iloc[i][coluna]), atol=0.00001, rtol=0):
                        raise ValueError(f"{ano}: {chave} divergente no ponto {id_ponto}.")
            matriz = np.asarray(dados_ghi[:, ids], dtype=np.float32)
            detalhes = {"ghi_shape_remoto": list(dados_ghi.shape), "ghi_chunks": list(dados_ghi.chunks) if dados_ghi.chunks else None,
                        "ghi_dtype": str(dados_ghi.dtype), "ghi_scale_factor": escala,
                        "amostras_30min_por_localidade": len(indice), "grade_geografica_validada": True,
                        "leitura": "HTTP Range com cache em memoria; sem arquivo HDF5 anual local"}
        detalhes["bytes_blocos_requisitados"] = int(getattr(remoto.cache, "total_requested_bytes", 0))
        detalhes["cache_misses"] = int(getattr(remoto.cache, "miss_count", 0))
    if not np.isfinite(matriz).all() or (matriz < 0).any():
        raise ValueError("Valores invalidos na fonte de 30 minutos.")
    pasta_amostras = PASTA_HISTORICO / "amostras_30min"
    pasta_amostras.mkdir(parents=True, exist_ok=True)
    caminho_amostras = pasta_amostras / f"nsrdb_ghi_30min_{ano}.npz"
    if caminho_amostras.exists():
        with np.load(caminho_amostras, allow_pickle=False) as cache:
            if not np.array_equal(cache["ghi"], matriz) or not np.array_equal(cache["site_ids"], ids):
                raise ValueError(f"Fonte 30min divergiu do cache em {ano}.")
    else:
        temporario_amostras = caminho_amostras.with_suffix(".npz.tmp")
        with temporario_amostras.open("wb") as arquivo_amostras:
            np.savez_compressed(arquivo_amostras, ghi=matriz, site_ids=ids,
                                timestamp_ns=serializar_tempo_ns(indice), ano=np.asarray(ano),
                                timestamp_unit=np.asarray("ns"))
        temporario_amostras.replace(caminho_amostras)
    detalhes["amostras_30min"] = {"arquivo": _relativo(caminho_amostras), "sha256": sha256(caminho_amostras),
                                 "bytes": caminho_amostras.stat().st_size}
    matriz_horaria = matriz.reshape(-1, 2, len(ids)).mean(axis=1)
    tabela = pd.DataFrame(matriz_horaria, index=indice[::2], columns=ids)
    longo = tabela.rename_axis("timestamp_utc").reset_index().melt(id_vars="timestamp_utc", var_name="site_id_nsrdb", value_name="ghi")
    longo["site_id_nsrdb"] = longo.site_id_nsrdb.astype(int)
    longo = longo.merge(registro[COLUNAS_META], on="site_id_nsrdb", validate="many_to_one")
    longo["ano"] = ano
    longo["fonte_dados"] = "NLR/NSRDB"
    longo["produto_dados"] = "GOES Aggregated PSM v4"
    longo["versao_dados"] = "4.0.0"
    longo["resolucao_origem_minutos"] = 30
    longo["agregacao"] = "media_horaria"
    longo["unidade_ghi"] = "W/m2"
    longo["url_hdf5"] = url
    longo = longo.sort_values(["localidade", "timestamp_utc"]).reset_index(drop=True)
    detalhes.update(verificar_ano_horario(longo, ano, registro))
    detalhes["segundos_extracao_validacao"] = time.perf_counter() - inicio
    return longo, detalhes


def _caminho_ano(ano: int) -> Path:
    pasta = PASTA_ATUAL if ano >= 2019 else PASTA_HISTORICO
    return pasta / f"nsrdb_ghi_horaria_{ano}.csv.gz"


def coletar(anos: tuple[int, ...] = ANOS) -> dict:
    PASTA_HISTORICO.mkdir(parents=True, exist_ok=True)
    registro = carregar_registro_pontos()
    manifesto_caminho = PASTA_HISTORICO / "manifesto_historico.json"
    manifesto = json.loads(manifesto_caminho.read_text(encoding="utf-8")) if manifesto_caminho.exists() else {
        "versao_esquema": 1, "inicio_em_utc": agora(), "produto": "GOES Aggregated PSM v4", "versao": "4.0.0",
        "anos_objetivo": list(ANOS), "arquivos": {}, "registro": registro.to_dict(orient="records"),
        "documentacao_oficial": "https://developer.nlr.gov/docs/solar/nsrdb/nsrdb-GOES-aggregated-v4-0-0-download/",
        "sem_imputacao": True}
    antigo = json.loads((PASTA_ATUAL / "manifesto_horario.json").read_text(encoding="utf-8"))
    for ano in anos:
        chave = str(ano)
        caminho = _caminho_ano(ano)
        if ano >= 2019:
            hash_esperado = antigo["arquivos"][caminho.name]["sha256"]
            if sha256(caminho) != hash_esperado:
                raise ValueError(f"Hash do arquivo original {ano} divergiu.")
            quadro = pd.read_csv(caminho)
            detalhe = verificar_ano_horario(quadro, ano, registro)
            detalhe["origem"] = "referencia_original_sem_copia"
        elif chave in manifesto["arquivos"]:
            entrada = manifesto["arquivos"][chave]
            if not caminho.exists() or sha256(caminho) != entrada["sha256"]:
                raise ValueError(f"Cache de {ano} ausente ou modificado; nao sera reutilizado.")
            quadro = pd.read_csv(caminho)
            verificar_ano_horario(quadro, ano, registro)
            detalhe = dict(entrada)
            print(json.dumps({"ano": ano, "status": "cache_verificado"}), flush=True)
        else:
            if caminho.exists():
                raise ValueError(f"Arquivo {caminho} existe sem manifesto verificavel.")
            print(json.dumps({"ano": ano, "status": "extraindo"}), flush=True)
            quadro, detalhe = extrair_ano(ano, registro)
            temporario = caminho.with_suffix(".gz.tmp")
            quadro.to_csv(temporario, index=False, date_format="%Y-%m-%dT%H:%M:%SZ", compression={"method": "gzip", "mtime": 0}, lineterminator="\n")
            temporario.replace(caminho)
            detalhe["origem"] = "extracao_range_hdf5"
        caminho_amostras = PASTA_HISTORICO / "amostras_30min" / f"nsrdb_ghi_30min_{ano}.npz"
        if not caminho_amostras.exists():
            _, detalhes_amostras = extrair_ano(ano, registro)
            detalhe["extracao_amostras_30min"] = detalhes_amostras
        if "amostras_30min" in detalhe and sha256(caminho_amostras) != detalhe["amostras_30min"]["sha256"]:
            raise ValueError(f"Hash do cache 30min {ano} divergiu.")
        with np.load(caminho_amostras, allow_pickle=False) as amostras:
            ids_brutos = amostras["site_ids"]
            grade_bruta = pd.to_datetime(amostras["timestamp_ns"], utc=True)
            grade_30min = pd.date_range(f"{ano}-01-01", f"{ano+1}-01-01", freq="30min", inclusive="left", tz="UTC").as_unit("ns")
            if not np.array_equal(ids_brutos, registro.site_id_nsrdb.to_numpy()) or not grade_bruta.equals(grade_30min):
                raise ValueError(f"Grade do cache 30min {ano} divergiu.")
            matriz = amostras["ghi"]
            if matriz.shape != (len(grade_30min), len(registro)) or not np.isfinite(matriz).all() or (matriz < 0).any():
                raise ValueError(f"Matriz 30min invalida em {ano}.")
            esperado = matriz.reshape(-1, 2, len(registro)).mean(axis=1)
        tabela = quadro.pivot(index="timestamp_utc", columns="site_id_nsrdb", values="ghi").sort_index()
        if not np.array_equal(tabela[ids_brutos].to_numpy(), esperado):
            raise ValueError(f"Agregacao 30min divergiu do horario em {ano}.")
        detalhe["amostras_30min"] = {"arquivo": _relativo(caminho_amostras), "sha256": sha256(caminho_amostras),
                                      "bytes": caminho_amostras.stat().st_size, "reproduz_horario": True}
        detalhe.update({"arquivo": _relativo(caminho), "sha256": sha256(caminho), "bytes": caminho.stat().st_size})
        manifesto["arquivos"][chave] = detalhe
        manifesto["atualizado_em_utc"] = agora()
        manifesto["completo"] = set(manifesto["arquivos"]) == set(map(str, ANOS))
        salvar_json(manifesto, manifesto_caminho)
        print(json.dumps({"ano": ano, "status": "validado", "bytes": detalhe["bytes"], "segundos": detalhe.get("segundos_extracao_validacao")}), flush=True)
    return manifesto


def carregar_historico_horario(anos: tuple[int, ...] = ANOS) -> pd.DataFrame:
    manifesto = json.loads((PASTA_HISTORICO / "manifesto_historico.json").read_text(encoding="utf-8"))
    registro = carregar_registro_pontos()
    quadros = []
    for ano in anos:
        detalhe = manifesto["arquivos"][str(ano)]
        caminho = RAIZ / detalhe["arquivo"]
        if sha256(caminho) != detalhe["sha256"]:
            raise ValueError(f"Hash divergente em {ano}.")
        quadro = pd.read_csv(caminho)
        verificar_ano_horario(quadro, ano, registro)
        quadro["timestamp_utc"] = pd.to_datetime(quadro.timestamp_utc, utc=True)
        quadros.append(quadro)
    return pd.concat(quadros, ignore_index=True).sort_values(["localidade", "timestamp_utc"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acao", choices=["cobertura", "coletar"])
    parser.add_argument("--anos", type=int, nargs="+", default=list(ANOS))
    args = parser.parse_args()
    if args.acao == "cobertura":
        with ThreadPoolExecutor(max_workers=4) as pool:
            cobertura = list(pool.map(verificar_cobertura_remota, args.anos))
        salvar_json({"verificado_em_utc": agora(), "anos": cobertura, "todos_disponiveis": True}, PASTA_RELATORIO / "cobertura_remota.json")
        print(json.dumps({"anos_disponiveis": len(cobertura), "bytes_remotos_nao_baixados": sum(x["bytes_arquivo_remoto"] for x in cobertura)}), flush=True)
    elif args.acao == "coletar":
        coletar(tuple(args.anos))


if __name__ == "__main__":
    main()
