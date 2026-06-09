"""Script para treinar e avaliar modelos de previsao de GHI em todas as 10 localidades de fabricas de EVs."""

from __future__ import annotations

import argparse
import hashlib
import math
import os
from pathlib import Path
import warnings

import pandas as pd

from codigo_fonte.configuracao import (
    PASTA_DADOS_BRUTOS,
    PASTA_DADOS_PROCESSADOS,
    PASTA_MODELOS,
    PASTA_RESULTADOS,
)
from codigo_fonte.localidades_ev import LOCALIDADES_EV, distancia_haversine_km
from codigo_fonte.utilitarios import criar_pastas

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault(
    "MPLCONFIGDIR",
    str((Path(__file__).resolve().parent / ".matplotlib-cache").resolve()),
)

warnings.filterwarnings('ignore')


LOCALIDADES = LOCALIDADES_EV

OUTPUT_DIR = PASTA_DADOS_BRUTOS / "localidades_ev"
MANIFESTO_DADOS = OUTPUT_DIR / "manifesto_nsrdb.csv"
RESULTADOS_DIR = PASTA_RESULTADOS / "todas_localidades"
ANO_INICIAL_DADOS = 2019
ANO_FINAL_DADOS = 2024


def nome_arquivo(local: str) -> str:
    """Gera nome de arquivo seguro a partir do nome da localidade."""
    return local.lower().replace(" ", "_").replace("-", "_")


def calcular_sha256(arquivo: Path) -> str:
    """Calcula o hash SHA-256 de um arquivo sem carrega-lo inteiro na memoria."""
    digest = hashlib.sha256()
    with arquivo.open("rb") as stream:
        for bloco in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def gerar_manifesto_dados() -> pd.DataFrame:
    """Registra integridade e metadados essenciais dos CSVs oficiais."""
    registros = []
    for local in LOCALIDADES:
        arquivo = OUTPUT_DIR / f"{nome_arquivo(local['nome'])}.csv"
        valido, motivo = validar_csv_nrel_localidade(arquivo, local)
        if not valido:
            raise RuntimeError(
                f"Nao foi possivel gerar manifesto para {local['nome']}: {motivo}"
            )

        dados = pd.read_csv(arquivo)
        primeira = dados.iloc[0]
        registros.append(
            {
                "arquivo": arquivo.name,
                "localidade": local["nome"],
                "sha256": calcular_sha256(arquivo),
                "registros": len(dados),
                "inicio": dados["data"].min(),
                "fim": dados["data"].max(),
                "lat": primeira["lat"],
                "lon": primeira["lon"],
                "lat_grade_nsrdb": primeira["lat_grade_nsrdb"],
                "lon_grade_nsrdb": primeira["lon_grade_nsrdb"],
                "site_id_nsrdb": primeira["site_id_nsrdb"],
                "fonte_dados": primeira["fonte_dados"],
                "produto_dados": primeira["produto_dados"],
                "versao_dados": primeira["versao_dados"],
                "data_coleta_utc": primeira["data_coleta_utc"],
            }
        )

    manifesto = pd.DataFrame(registros)
    manifesto.to_csv(MANIFESTO_DADOS, index=False, lineterminator="\n")
    return manifesto


def validar_csv_nrel_localidade(arquivo: Path, local: dict) -> tuple[bool, str]:
    """Valida conteudo, cobertura e proveniencia do CSV NSRDB."""
    from codigo_fonte.preprocessamento import (
        NSRDB_API_URL,
        NSRDB_DAILY_AGGREGATION,
        NSRDB_GHI_UNIT,
        NSRDB_PRODUCT,
        NSRDB_SOURCE,
    )

    if not arquivo.exists():
        return False, "arquivo nao existe"

    try:
        dados = pd.read_csv(arquivo)
    except Exception as exc:
        return False, f"nao foi possivel ler o CSV: {exc}"

    colunas_obrigatorias = {
        "data",
        "ghi",
        "localidade",
        "pais",
        "lat",
        "lon",
        "endereco_localidade",
        "fonte_localidade",
        "fonte_coordenadas",
        "metodo_coordenadas",
        "osm_elemento",
        "ano",
        "fonte_dados",
        "produto_dados",
        "versao_dados",
        "endpoint_api",
        "intervalo_minutos",
        "agregacao",
        "unidade_ghi",
        "lat_grade_nsrdb",
        "lon_grade_nsrdb",
        "site_id_nsrdb",
        "source_nsrdb",
        "timezone_nsrdb",
        "elevacao_grade_m",
        "ghi_unidade_api",
        "data_coleta_utc",
    }
    faltantes = sorted(colunas_obrigatorias - set(dados.columns))
    if faltantes:
        return False, f"colunas de proveniencia ausentes: {', '.join(faltantes)}"

    localidades = dados["localidade"].dropna().astype(str).unique().tolist()
    if any(valor.startswith("lat_") and "_lon_" in valor for valor in localidades):
        return False, "campo localidade indica geracao sintetica por latitude/longitude"

    if set(localidades) != {local["nome"]}:
        return False, f"localidade no CSV nao corresponde a {local['nome']}"

    paises = dados["pais"].dropna().astype(str).unique().tolist()
    if set(paises) != {local["pais"]}:
        return False, f"pais no CSV nao corresponde a {local['pais']}"

    metadados_esperados = {
        "fonte_dados": NSRDB_SOURCE,
        "produto_dados": NSRDB_PRODUCT,
        "endpoint_api": NSRDB_API_URL,
        "intervalo_minutos": 60,
        "agregacao": NSRDB_DAILY_AGGREGATION,
        "unidade_ghi": NSRDB_GHI_UNIT,
    }
    for coluna, esperado in metadados_esperados.items():
        encontrados = set(dados[coluna].dropna().unique().tolist())
        if encontrados != {esperado}:
            return False, f"{coluna} deve ser {esperado}"

    if dados["versao_dados"].isna().any():
        return False, "versao_dados nao pode ser vazia"

    datas = pd.to_datetime(dados["data"], errors="coerce")
    if datas.isna().any():
        return False, "ha datas invalidas"
    if datas.duplicated().any():
        return False, "ha datas duplicadas"

    datas_esperadas = pd.date_range(
        f"{ANO_INICIAL_DADOS}-01-01",
        f"{ANO_FINAL_DADOS}-12-31",
        freq="D",
    )
    if len(datas) != len(datas_esperadas) or not datas.sort_values().reset_index(
        drop=True
    ).equals(pd.Series(datas_esperadas)):
        return False, (
            f"cobertura diaria deve ser completa de {ANO_INICIAL_DADOS}-01-01 "
            f"a {ANO_FINAL_DADOS}-12-31"
        )

    anos = pd.to_numeric(dados["ano"], errors="coerce")
    if anos.isna().any() or not (
        anos.astype(int).to_numpy() == datas.dt.year.to_numpy()
    ).all():
        return False, "coluna ano nao corresponde as datas"

    ghi = pd.to_numeric(dados["ghi"], errors="coerce")
    if ghi.isna().any() or not ghi.between(0, 500).all():
        return False, "GHI diario deve estar entre 0 e 500 W/m2"

    latitudes = pd.to_numeric(dados["lat"], errors="coerce")
    longitudes = pd.to_numeric(dados["lon"], errors="coerce")
    if latitudes.isna().any() or not all(
        math.isclose(value, local["lat"], abs_tol=1e-6) for value in latitudes.unique()
    ):
        return False, "latitude no CSV nao corresponde a localidade"
    if longitudes.isna().any() or not all(
        math.isclose(value, local["lon"], abs_tol=1e-6) for value in longitudes.unique()
    ):
        return False, "longitude no CSV nao corresponde a localidade"

    metadados_localidade = {
        "endereco_localidade": local["endereco"],
        "fonte_localidade": local["fonte_localidade"],
        "fonte_coordenadas": local["fonte_coordenadas"],
        "metodo_coordenadas": local["metodo_coordenadas"],
        "osm_elemento": local["osm_elemento"],
    }
    for coluna, esperado in metadados_localidade.items():
        encontrados = set(dados[coluna].dropna().astype(str).unique().tolist())
        if encontrados != {esperado}:
            return False, f"{coluna} nao corresponde ao cadastro auditavel"

    lat_grade = pd.to_numeric(dados["lat_grade_nsrdb"], errors="coerce")
    lon_grade = pd.to_numeric(dados["lon_grade_nsrdb"], errors="coerce")
    if lat_grade.isna().any() or lon_grade.isna().any():
        return False, "coordenadas da grade NSRDB ausentes"
    if len(lat_grade.unique()) != 1 or len(lon_grade.unique()) != 1:
        return False, "o ponto da grade NSRDB mudou dentro do mesmo CSV"

    distancia_grade = distancia_haversine_km(
        local["lat"],
        local["lon"],
        float(lat_grade.iloc[0]),
        float(lon_grade.iloc[0]),
    )
    if distancia_grade > 5:
        return False, f"ponto NSRDB esta distante demais da fabrica: {distancia_grade:.2f} km"

    if dados["site_id_nsrdb"].isna().any() or dados["source_nsrdb"].isna().any():
        return False, "identificacao do ponto NSRDB ausente"
    unidades_api = set(
        dados["ghi_unidade_api"].dropna().astype(str).str.lower().unique().tolist()
    )
    if unidades_api != {"w/m2"}:
        return False, "unidade GHI retornada pela API deve ser w/m2"
    if dados["data_coleta_utc"].isna().any():
        return False, "data de coleta da API ausente"

    return True, "CSV validado como NLR/NSRDB"


def coletar_localidade_nrel(local: dict, arquivo: Path) -> pd.DataFrame:
    """Coleta dados oficiais NLR/NSRDB e valida o arquivo salvo."""
    from codigo_fonte.preprocessamento import coletar_ghi_nrel

    print(f"  Coletando dados de {local['nome']} da API NLR/NSRDB...")
    df = coletar_ghi_nrel(
        lat=local["lat"],
        lon=local["lon"],
        city=local["nome"],
        pais=local["pais"],
        endereco=local["endereco"],
        fonte_localidade=local["fonte_localidade"],
        fonte_coordenadas=local["fonte_coordenadas"],
        metodo_coordenadas=local["metodo_coordenadas"],
        osm_elemento=local["osm_elemento"],
        start_year=ANO_INICIAL_DADOS,
        end_year=ANO_FINAL_DADOS,
        inter=60,
        output_path=arquivo,
    )

    valido, motivo = validar_csv_nrel_localidade(arquivo, local)
    if not valido:
        raise RuntimeError(f"Arquivo coletado nao passou na validacao de origem: {motivo}")

    print(f"  Dados NLR/NSRDB salvos e validados em: {arquivo}")
    return df


def carregar_ou_coletar_localidade(local: dict, forcar_download: bool = False) -> pd.DataFrame:
    """Carrega dados NLR/NSRDB locais ou coleta novamente pela API."""
    from codigo_fonte.preprocessamento import carregar_serie_ghi

    nome = local["nome"]
    arquivo = OUTPUT_DIR / f"{nome_arquivo(nome)}.csv"

    if arquivo.exists() and not forcar_download:
        valido, motivo = validar_csv_nrel_localidade(arquivo, local)
        if not valido:
            print(f"  CSV local invalido para {nome}: {motivo}")
            print("  Recoletando pela API NLR/NSRDB para evitar uso de dados sinteticos.")
            return coletar_localidade_nrel(local, arquivo)

        print(f"  Carregando CSV NLR/NSRDB validado de {nome}...")
        return carregar_serie_ghi(arquivo)

    if forcar_download and arquivo.exists():
        print(f"  Download forcado para {nome}; o CSV local sera substituido apos coleta valida.")

    try:
        return coletar_localidade_nrel(local, arquivo)
    except Exception as exc:
        raise RuntimeError(
            "Falha ao coletar dados reais da API NLR/NSRDB. "
            "O pipeline foi interrompido porque dados sinteticos nao sao mais aceitos."
        ) from exc


def treinar_localidade(local: dict, verbose: bool = True, forcar_download: bool = False) -> dict:
    """
    Executa o pipeline completo para uma localidade.
    
    Returns:
        Dicionario com metricas, modelos e informacoes da localidade.
    """
    from codigo_fonte.avaliacao import calcular_metricas, salvar_previsoes
    from codigo_fonte.features import dividir_treino_teste_temporal
    from codigo_fonte.graficos import salvar_graficos
    from codigo_fonte.modelos import salvar_modelo, treinar_mlp, treinar_xgboost
    from codigo_fonte.preprocessamento import preparar_serie_temporal

    nome = local["nome"]
    pais = local["pais"]
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"Localidade: {nome} ({pais})")
        print(f"Latitude: {local['lat']}, Longitude: {local['lon']}")
        print(f"{'='*60}")
    
    # Carregar ou coletar dados
    serie_ghi = carregar_ou_coletar_localidade(local, forcar_download=forcar_download)
    
    # Preparar serie temporal (quantizacao, normalizacao, features)
    if verbose:
        print("  Preparando serie temporal (quantizacao 128 niveis, features)...")
    preparation = preparar_serie_temporal(
        serie_ghi,
        output_path=(
            PASTA_DADOS_PROCESSADOS
            / "localidades_ev"
            / f"{nome_arquivo(nome)}_features.csv"
        ),
    )
    dados = preparation.dados_modelagem
    feature_columns = preparation.feature_columns
    
    # Divisao treino/teste
    X_train, X_test, y_train, y_test, _, dados_teste = dividir_treino_teste_temporal(
        dados,
        feature_columns,
        target_column="ghi_alvo",
        train_ratio=0.8,
    )
    datas_teste = pd.to_datetime(dados_teste["data_alvo"])
    
    # Treinar XGBoost
    if verbose:
        print("  Treinando XGBoost...")
    xgb_model = treinar_xgboost(X_train, y_train)
    pred_xgb = pd.Series(xgb_model.predict(X_test), index=y_test.index).clip(0, 1)
    
    # Salvar modelo XGBoost
    pasta_modelo_local = PASTA_MODELOS / "localidades"
    pasta_modelo_local.mkdir(parents=True, exist_ok=True)
    salvar_modelo(xgb_model, pasta_modelo_local / f"xgboost_{nome_arquivo(nome)}.joblib")
    
    # Treinar MLP
    if verbose:
        print("  Treinando MLP...")
    mlp_model = treinar_mlp(X_train, y_train)
    pred_mlp = pd.Series(mlp_model.predict(X_test), index=y_test.index).clip(0, 1)
    
    # Salvar modelo MLP
    salvar_modelo(mlp_model, pasta_modelo_local / f"mlp_{nome_arquivo(nome)}.joblib")
    
    # Calcular metricas
    predicoes = {
        "XGBoost": pred_xgb.reset_index(drop=True),
        "MLP": pred_mlp.reset_index(drop=True),
    }
    y_test_reset = y_test.reset_index(drop=True)
    datas_reset = datas_teste.reset_index(drop=True)
    
    metricas_xgb = calcular_metricas(y_test_reset, predicoes["XGBoost"], "XGBoost")
    metricas_mlp = calcular_metricas(y_test_reset, predicoes["MLP"], "MLP")
    
    # Adicionar informacoes da localidade
    metricas_xgb["Localidade"] = nome
    metricas_xgb["Pais"] = pais
    metricas_xgb["Lat"] = local["lat"]
    metricas_xgb["Lon"] = local["lon"]
    
    metricas_mlp["Localidade"] = nome
    metricas_mlp["Pais"] = pais
    metricas_mlp["Lat"] = local["lat"]
    metricas_mlp["Lon"] = local["lon"]
    
    # Salvar previsoes
    pasta_previsoes_local = RESULTADOS_DIR / "previsoes"
    pasta_previsoes_local.mkdir(parents=True, exist_ok=True)
    salvar_previsoes(datas_reset, y_test_reset, predicoes, pasta_previsoes_local / nome_arquivo(nome))
    
    # Salvar graficos
    pasta_figuras_local = RESULTADOS_DIR / "figuras"
    pasta_figuras_local.mkdir(parents=True, exist_ok=True)
    salvar_graficos(datas_reset, y_test_reset, predicoes, pasta_figuras_local / nome_arquivo(nome))
    
    if verbose:
        print(f"\n  Metricas XGBoost:")
        print(f"    MAE: {metricas_xgb['MAE']:.4f}")
        print(f"    RMSE: {metricas_xgb['RMSE']:.4f}")
        print(f"    R2: {metricas_xgb['R2']:.4f}")
        print(f"\n  Metricas MLP:")
        print(f"    MAE: {metricas_mlp['MAE']:.4f}")
        print(f"    RMSE: {metricas_mlp['RMSE']:.4f}")
        print(f"    R2: {metricas_mlp['R2']:.4f}")
    
    return {
        "localidade": nome,
        "pais": pais,
        "lat": local["lat"],
        "lon": local["lon"],
        "xgboost": metricas_xgb,
        "mlp": metricas_mlp,
        "dados": dados,
        "y_test": y_test_reset,
        "y_pred_xgb": predicoes["XGBoost"],
        "y_pred_mlp": predicoes["MLP"],
        "datas_teste": datas_reset,
    }


def main():
    """Executa o pipeline completo para todas as 10 localidades."""
    parser = argparse.ArgumentParser(
        description="Treina XGBoost e MLP para previsao diaria de GHI em todas as localidades."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=True,
        help="Mostrar saida detalhada durante o processamento.",
    )
    parser.add_argument(
        "--forcar-download",
        action="store_true",
        help="Ignora CSVs locais e baixa novamente todos os dados pela API NLR/NSRDB.",
    )
    parser.add_argument(
        "--validar-dados",
        action="store_true",
        help="Apenas valida a origem dos CSVs locais, sem treinar os modelos.",
    )
    parser.add_argument(
        "--somente-download",
        action="store_true",
        help="Baixa e valida os CSVs das localidades sem treinar os modelos.",
    )
    args = parser.parse_args()
    
    criar_pastas()
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    
    print("="*60)
    print("TREINAMENTO DE MODELOS PARA TODAS AS LOCALIDADES")
    print("="*60)
    print(f"\nTotal de localidades: {len(LOCALIDADES)}")
    print("\nLocalidades:")
    for i, local in enumerate(LOCALIDADES, 1):
        print(f"  {i}. {local['nome']} ({local['pais']})")

    if args.validar_dados:
        print("\nValidando CSVs locais em dados/brutos/localidades_ev/...")
        invalidos = []
        manifesto = (
            pd.read_csv(MANIFESTO_DADOS)
            if MANIFESTO_DADOS.exists()
            else pd.DataFrame()
        )
        colunas_manifesto_validas = {"arquivo", "sha256"}.issubset(manifesto.columns)
        for local in LOCALIDADES:
            arquivo = OUTPUT_DIR / f"{nome_arquivo(local['nome'])}.csv"
            valido, motivo = validar_csv_nrel_localidade(arquivo, local)
            if not colunas_manifesto_validas:
                valido = False
                motivo = "manifesto SHA-256 ausente ou com colunas invalidas"
            else:
                registro_manifesto = manifesto.loc[
                    manifesto["arquivo"] == arquivo.name
                ]
                if len(registro_manifesto) != 1:
                    valido = False
                    motivo = "arquivo ausente ou duplicado no manifesto SHA-256"
                elif registro_manifesto.iloc[0]["sha256"] != calcular_sha256(arquivo):
                    valido = False
                    motivo = "hash SHA-256 diverge do manifesto"
            status = "OK" if valido else "INVALIDO"
            print(f"  [{status}] {local['nome']}: {motivo}")
            if not valido:
                invalidos.append((local["nome"], motivo))

        if invalidos:
            raise SystemExit(
                "\nValidacao falhou: ha CSVs locais sem proveniencia NLR/NSRDB valida. "
                "Execute `python treinar_todas_localidades.py --forcar-download` "
                "para baixar novamente pela API."
            )

        print("\n[OK] Todos os CSVs locais foram validados como NLR/NSRDB.")
        return []

    if args.somente_download:
        print("\nBaixando e validando CSVs oficiais sem treinar os modelos...")
        for local in LOCALIDADES:
            arquivo = OUTPUT_DIR / f"{nome_arquivo(local['nome'])}.csv"
            if args.forcar_download:
                coletar_localidade_nrel(local, arquivo)
            else:
                carregar_ou_coletar_localidade(local)

        gerar_manifesto_dados()
        print(f"  Manifesto SHA-256 salvo em: {MANIFESTO_DADOS}")
        print("\n[OK] Download e validacao das 10 localidades concluidos.")
        return []
    
    resultados = []
    
    for local in LOCALIDADES:
        try:
            resultado = treinar_localidade(
                local,
                verbose=args.verbose,
                forcar_download=args.forcar_download,
            )
            resultados.append(resultado)
        except Exception as e:
            print(f"  ERRO ao processar {local['nome']}: {e}")
            resultados.append({
                "localidade": local["nome"],
                "pais": local["pais"],
                "lat": local["lat"],
                "lon": local["lon"],
                "erro": str(e),
            })

    erros = [res for res in resultados if "erro" in res]
    if erros:
        print("\n" + "="*60)
        print("EXECUCAO INTERROMPIDA")
        print("="*60)
        print("Uma ou mais localidades falharam. Nenhuma tabela final sera gerada.")
        for erro in erros:
            print(f"  - {erro['localidade']}: {erro['erro']}")
        raise SystemExit(
            "Corrija a coleta NLR/NSRDB antes de regenerar metricas, notebooks ou relatorios."
        )

    gerar_manifesto_dados()
    print(f"\n[OK] Manifesto SHA-256 atualizado em: {MANIFESTO_DADOS}")
    
    # Gerar tabela comparativa final
    print("\n" + "="*60)
    print("TABELA COMPARATIVA FINAL")
    print("="*60)
    
    metricas_geral = []
    for res in resultados:
        if "erro" not in res:
            metricas_geral.append({
                "Localidade": res["localidade"],
                "Pais": res["pais"],
                "Modelo": "XGBoost",
                "MAE": res["xgboost"]["MAE"],
                "MSE": res["xgboost"]["MSE"],
                "RMSE": res["xgboost"]["RMSE"],
                "R2": res["xgboost"]["R2"],
            })
            metricas_geral.append({
                "Localidade": res["localidade"],
                "Pais": res["pais"],
                "Modelo": "MLP",
                "MAE": res["mlp"]["MAE"],
                "MSE": res["mlp"]["MSE"],
                "RMSE": res["mlp"]["RMSE"],
                "R2": res["mlp"]["R2"],
            })
    
    df_metricas = pd.DataFrame(metricas_geral)
    
    # Salvar tabela comparativa
    df_metricas.to_csv(RESULTADOS_DIR / "metricas_geral.csv", index=False)
    
    print("\nTabela de metricas (todas as localidades):")
    print(df_metricas.to_string(index=False))
    
    # Salvar resumo por localidade
    resumo = []
    for res in resultados:
        if "erro" not in res:
            resumo.append({
                "Localidade": res["localidade"],
                "Pais": res["pais"],
                "Lat": res["lat"],
                "Lon": res["lon"],
                "XGBoost_MAE": res["xgboost"]["MAE"],
                "XGBoost_RMSE": res["xgboost"]["RMSE"],
                "XGBoost_R2": res["xgboost"]["R2"],
                "MLP_MAE": res["mlp"]["MAE"],
                "MLP_RMSE": res["mlp"]["RMSE"],
                "MLP_R2": res["mlp"]["R2"],
                "Melhor_Modelo": "XGBoost" if res["xgboost"]["R2"] > res["mlp"]["R2"] else "MLP",
            })
    
    df_resumo = pd.DataFrame(resumo)
    df_resumo.to_csv(RESULTADOS_DIR / "resumo_localidades.csv", index=False)
    
    print("\n" + "="*60)
    print("RESUMO POR LOCALIDADE")
    print("="*60)
    print(df_resumo.to_string(index=False))
    
    print("\n[OK] Pipeline finalizado!")
    print(f"[INFO] Resultados salvos em: {RESULTADOS_DIR.absolute()}")
    print(f"[INFO] Metricas gerais: {RESULTADOS_DIR / 'metricas_geral.csv'}")
    print(f"[INFO] Resumo: {RESULTADOS_DIR / 'resumo_localidades.csv'}")
    
    return resultados


if __name__ == "__main__":
    main()
