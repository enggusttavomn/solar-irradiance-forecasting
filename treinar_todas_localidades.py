"""Coleta, valida e treina modelos para todas as localidades do estudo.

O script repete o mesmo pipeline independente em cada fabrica. Ele tambem
aplica validacoes mais rigorosas que o fluxo de serie unica, pois os CSVs desta
pasta sao apresentados como o conjunto oficial e auditavel do trabalho.
"""

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

# O backend ``Agg`` gera PNG sem precisar abrir uma janela grafica.
os.environ.setdefault("MPLBACKEND", "Agg")
# Um cache dentro do projeto evita erro quando a configuracao global e somente leitura.
os.environ.setdefault(
    "MPLCONFIGDIR",
    str((Path(__file__).resolve().parent / ".matplotlib-cache").resolve()),
)

# Reduz ruido no terminal durante o processamento em lote.
warnings.filterwarnings('ignore')


# Alias curto usado ao longo do script. A fonte real e o cadastro centralizado.
LOCALIDADES = LOCALIDADES_EV

OUTPUT_DIR = PASTA_DADOS_BRUTOS / "localidades_ev"
MANIFESTO_DADOS = OUTPUT_DIR / "manifesto_nsrdb.csv"
RESULTADOS_DIR = PASTA_RESULTADOS / "todas_localidades"
ANO_INICIAL_DADOS = 2019
ANO_FINAL_DADOS = 2024


def nome_arquivo(local: str) -> str:
    """Converte o nome legivel em um nome simples usado nos caminhos."""
    return local.lower().replace(" ", "_").replace("-", "_")


def calcular_sha256(arquivo: Path) -> str:
    """Calcula o hash SHA-256 sem carregar o arquivo inteiro na memoria."""
    digest = hashlib.sha256()
    with arquivo.open("rb") as stream:
        # Le em blocos de 1 MiB para funcionar tambem com arquivos grandes.
        for bloco in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def gerar_manifesto_dados() -> pd.DataFrame:
    """Registra integridade e metadados essenciais dos CSVs oficiais.

    O hash permite detectar qualquer alteracao de conteudo depois da coleta.
    Antes de registrar um arquivo, a funcao executa a validacao completa.
    """
    registros = []
    for local in LOCALIDADES:
        # A convencao de nomes liga cada cadastro ao seu CSV correspondente.
        arquivo = OUTPUT_DIR / f"{nome_arquivo(local['nome'])}.csv"
        valido, motivo = validar_csv_nrel_localidade(arquivo, local)
        if not valido:
            raise RuntimeError(
                f"Nao foi possivel gerar manifesto para {local['nome']}: {motivo}"
            )

        # Os metadados sao constantes dentro do CSV; basta ler a primeira linha.
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

    # ``lineterminator`` fixo ajuda a manter hashes estaveis entre plataformas.
    manifesto = pd.DataFrame(registros)
    manifesto.to_csv(MANIFESTO_DADOS, index=False, lineterminator="\n")
    return manifesto


def validar_csv_nrel_localidade(arquivo: Path, local: dict) -> tuple[bool, str]:
    """Valida conteudo, cobertura e proveniencia de um CSV NSRDB.

    Returns:
        Tupla ``(valido, motivo)``. O motivo e adequado para exibicao no
        terminal e permite identificar exatamente qual regra falhou.

    Notes:
        A funcao retorna na primeira falha. Isso deixa a mensagem objetiva e
        evita executar verificacoes dependentes de colunas que podem nao existir.
    """
    # Importacao local evita criar dependencia circular durante a carga do modulo.
    from codigo_fonte.preprocessamento import (
        NSRDB_API_URL,
        NSRDB_DAILY_AGGREGATION,
        NSRDB_GHI_UNIT,
        NSRDB_PRODUCT,
        NSRDB_SOURCE,
    )

    # Etapa 1: existencia e leitura do arquivo.
    if not arquivo.exists():
        return False, "arquivo nao existe"

    try:
        dados = pd.read_csv(arquivo)
    except Exception as exc:
        return False, f"nao foi possivel ler o CSV: {exc}"

    # Etapa 2: esquema minimo necessario para reproduzir e auditar a coleta.
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

    # Etapa 3: identidade da localidade. O padrao lat_*_lon_* denuncia arquivos
    # sinteticos antigos que nao podem fazer parte do conjunto oficial.
    localidades = dados["localidade"].dropna().astype(str).unique().tolist()
    if any(valor.startswith("lat_") and "_lon_" in valor for valor in localidades):
        return False, "campo localidade indica geracao sintetica por latitude/longitude"

    if set(localidades) != {local["nome"]}:
        return False, f"localidade no CSV nao corresponde a {local['nome']}"

    # Nome e pais devem ser constantes e iguais ao cadastro central.
    paises = dados["pais"].dropna().astype(str).unique().tolist()
    if set(paises) != {local["pais"]}:
        return False, f"pais no CSV nao corresponde a {local['pais']}"

    # Etapa 4: contrato da fonte. Qualquer mudanca de produto, intervalo ou
    # unidade precisa ser tratada explicitamente antes de aceitar os dados.
    metadados_esperados = {
        "fonte_dados": NSRDB_SOURCE,
        "produto_dados": NSRDB_PRODUCT,
        "endpoint_api": NSRDB_API_URL,
        "intervalo_minutos": 60,
        "agregacao": NSRDB_DAILY_AGGREGATION,
        "unidade_ghi": NSRDB_GHI_UNIT,
    }
    for coluna, esperado in metadados_esperados.items():
        # ``set`` confirma ao mesmo tempo o valor e sua constancia no arquivo.
        encontrados = set(dados[coluna].dropna().unique().tolist())
        if encontrados != {esperado}:
            return False, f"{coluna} deve ser {esperado}"

    if dados["versao_dados"].isna().any():
        return False, "versao_dados nao pode ser vazia"

    # Etapa 5: qualidade e cobertura temporal.
    datas = pd.to_datetime(dados["data"], errors="coerce")
    if datas.isna().any():
        return False, "ha datas invalidas"
    if datas.duplicated().any():
        return False, "ha datas duplicadas"

    # Gera a grade diaria completa, incluindo 29 de fevereiro dos anos bissextos.
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

    # A coluna auxiliar ``ano`` deve concordar com a data de cada linha.
    anos = pd.to_numeric(dados["ano"], errors="coerce")
    if anos.isna().any() or not (
        anos.astype(int).to_numpy() == datas.dt.year.to_numpy()
    ).all():
        return False, "coluna ano nao corresponde as datas"

    # Etapa 6: valores fisicamente plausiveis para a media diaria em W/m2.
    ghi = pd.to_numeric(dados["ghi"], errors="coerce")
    if ghi.isna().any() or not ghi.between(0, 500).all():
        return False, "GHI diario deve estar entre 0 e 500 W/m2"

    # Etapa 7: coordenadas exatas do cadastro da fabrica.
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

    # Etapa 8: fontes geograficas e institucionais usadas na auditoria.
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

    # Etapa 9: ponto da grade efetivamente usado pela base solar.
    lat_grade = pd.to_numeric(dados["lat_grade_nsrdb"], errors="coerce")
    lon_grade = pd.to_numeric(dados["lon_grade_nsrdb"], errors="coerce")
    if lat_grade.isna().any() or lon_grade.isna().any():
        return False, "coordenadas da grade NSRDB ausentes"
    if len(lat_grade.unique()) != 1 or len(lon_grade.unique()) != 1:
        return False, "o ponto da grade NSRDB mudou dentro do mesmo CSV"

    # O NSRDB usa uma grade; por isso o ponto pode nao coincidir exatamente com
    # a fabrica, mas deve permanecer dentro do limite metodologico de 5 km.
    distancia_grade = distancia_haversine_km(
        local["lat"],
        local["lon"],
        float(lat_grade.iloc[0]),
        float(lon_grade.iloc[0]),
    )
    if distancia_grade > 5:
        return False, f"ponto NSRDB esta distante demais da fabrica: {distancia_grade:.2f} km"

    # Etapa 10: metadados finais retornados diretamente pela API.
    if dados["site_id_nsrdb"].isna().any() or dados["source_nsrdb"].isna().any():
        return False, "identificacao do ponto NSRDB ausente"
    unidades_api = set(
        dados["ghi_unidade_api"].dropna().astype(str).str.lower().unique().tolist()
    )
    if unidades_api != {"w/m2"}:
        return False, "unidade GHI retornada pela API deve ser w/m2"
    if dados["data_coleta_utc"].isna().any():
        return False, "data de coleta da API ausente"

    # Chegar ate aqui significa que todas as verificacoes foram satisfeitas.
    return True, "CSV validado como NLR/NSRDB"


def coletar_localidade_nrel(local: dict, arquivo: Path) -> pd.DataFrame:
    """Coleta uma localidade e so retorna depois de validar o CSV salvo."""
    from codigo_fonte.preprocessamento import coletar_ghi_nrel

    print(f"  Coletando dados de {local['nome']} da API NLR/NSRDB...")
    # Todos os metadados do cadastro sao repassados para serem gravados no CSV.
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

    # A validacao apos a escrita confirma que o resultado atende ao contrato.
    valido, motivo = validar_csv_nrel_localidade(arquivo, local)
    if not valido:
        raise RuntimeError(f"Arquivo coletado nao passou na validacao de origem: {motivo}")

    print(f"  Dados NLR/NSRDB salvos e validados em: {arquivo}")
    return df


def carregar_ou_coletar_localidade(local: dict, forcar_download: bool = False) -> pd.DataFrame:
    """Escolhe entre reutilizar um CSV valido e realizar nova coleta."""
    from codigo_fonte.preprocessamento import carregar_serie_ghi

    nome = local["nome"]
    arquivo = OUTPUT_DIR / f"{nome_arquivo(nome)}.csv"

    # Reutiliza somente arquivos que passam por todas as verificacoes.
    if arquivo.exists() and not forcar_download:
        valido, motivo = validar_csv_nrel_localidade(arquivo, local)
        if not valido:
            print(f"  CSV local invalido para {nome}: {motivo}")
            print("  Recoletando pela API NLR/NSRDB para evitar uso de dados sinteticos.")
            # Um arquivo invalido nunca e usado como fallback silencioso.
            return coletar_localidade_nrel(local, arquivo)

        print(f"  Carregando CSV NLR/NSRDB validado de {nome}...")
        return carregar_serie_ghi(arquivo)

    if forcar_download and arquivo.exists():
        print(f"  Download forcado para {nome}; o CSV local sera substituido apos coleta valida.")

    # Sem arquivo reutilizavel, a unica fonte aceita e a API oficial.
    try:
        return coletar_localidade_nrel(local, arquivo)
    except Exception as exc:
        raise RuntimeError(
            "Falha ao coletar dados reais da API NLR/NSRDB. "
            "O pipeline foi interrompido porque dados sinteticos nao sao mais aceitos."
        ) from exc


def treinar_localidade(local: dict, verbose: bool = True, forcar_download: bool = False) -> dict:
    """Executa o pipeline completo e independente para uma localidade.

    Args:
        local: Dicionario do cadastro ``LOCALIDADES_EV``.
        verbose: Controla as mensagens detalhadas no terminal.
        forcar_download: Quando verdadeiro, ignora o CSV local.

    Returns:
        Dicionario com metricas, modelos e informacoes da localidade.
    """
    # Importacoes locais reduzem o custo dos modos que apenas validam ou baixam.
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
    
    # Etapa 1: obter somente dados oficiais e validados.
    serie_ghi = carregar_ou_coletar_localidade(local, forcar_download=forcar_download)
    
    # Etapa 2: limpar, transformar e salvar a base de features desta localidade.
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
    
    # Etapa 3: corte cronologico. Os ultimos 20% simulam o futuro nao visto.
    X_train, X_test, y_train, y_test, _, dados_teste = dividir_treino_teste_temporal(
        dados,
        feature_columns,
        target_column="ghi_alvo",
        train_ratio=0.8,
    )
    # A data associada a cada previsao e a data do alvo t+1.
    datas_teste = pd.to_datetime(dados_teste["data_alvo"])
    
    # Etapa 4: treinar e prever com XGBoost.
    if verbose:
        print("  Treinando XGBoost...")
    xgb_model = treinar_xgboost(X_train, y_train)
    # Limita a saida ao dominio da variavel normalizada.
    pred_xgb = pd.Series(xgb_model.predict(X_test), index=y_test.index).clip(0, 1)
    
    # Um nome por localidade impede que modelos sejam sobrescritos no lote.
    pasta_modelo_local = PASTA_MODELOS / "localidades"
    pasta_modelo_local.mkdir(parents=True, exist_ok=True)
    salvar_modelo(xgb_model, pasta_modelo_local / f"xgboost_{nome_arquivo(nome)}.joblib")
    
    # Etapa 5: treinar e prever com a MLP usando a mesma divisao.
    if verbose:
        print("  Treinando MLP...")
    mlp_model = treinar_mlp(X_train, y_train)
    pred_mlp = pd.Series(mlp_model.predict(X_test), index=y_test.index).clip(0, 1)
    
    # O formato joblib permite recarregar o estimador ajustado.
    salvar_modelo(mlp_model, pasta_modelo_local / f"mlp_{nome_arquivo(nome)}.joblib")
    
    # Etapa 6: zerar os indices facilita alinhar datas, reais e previsoes.
    predicoes = {
        "XGBoost": pred_xgb.reset_index(drop=True),
        "MLP": pred_mlp.reset_index(drop=True),
    }
    y_test_reset = y_test.reset_index(drop=True)
    datas_reset = datas_teste.reset_index(drop=True)
    
    # As metricas sao calculadas sobre a mesma escala [0, 1].
    metricas_xgb = calcular_metricas(y_test_reset, predicoes["XGBoost"], "XGBoost")
    metricas_mlp = calcular_metricas(y_test_reset, predicoes["MLP"], "MLP")
    
    # Adiciona contexto geografico para montar a tabela consolidada depois.
    metricas_xgb["Localidade"] = nome
    metricas_xgb["Pais"] = pais
    metricas_xgb["Lat"] = local["lat"]
    metricas_xgb["Lon"] = local["lon"]
    
    metricas_mlp["Localidade"] = nome
    metricas_mlp["Pais"] = pais
    metricas_mlp["Lat"] = local["lat"]
    metricas_mlp["Lon"] = local["lon"]
    
    # Etapa 7: salvar valores linha a linha para auditoria e graficos.
    pasta_previsoes_local = RESULTADOS_DIR / "previsoes"
    pasta_previsoes_local.mkdir(parents=True, exist_ok=True)
    salvar_previsoes(datas_reset, y_test_reset, predicoes, pasta_previsoes_local / nome_arquivo(nome))
    
    # Etapa 8: produzir as cinco figuras padrao desta localidade.
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
    
    # O retorno alimenta a consolidacao feita por ``main``.
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
    """Interpreta o modo solicitado e coordena as dez localidades."""
    # As opcoes permitem separar validacao, coleta e treinamento.
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
    
    # Prepara a estrutura antes de qualquer modo de execucao.
    criar_pastas()
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    
    print("="*60)
    print("TREINAMENTO DE MODELOS PARA TODAS AS LOCALIDADES")
    print("="*60)
    print(f"\nTotal de localidades: {len(LOCALIDADES)}")
    print("\nLocalidades:")
    for i, local in enumerate(LOCALIDADES, 1):
        print(f"  {i}. {local['nome']} ({local['pais']})")

    # Modo de auditoria: nao coleta e nao treina.
    if args.validar_dados:
        print("\nValidando CSVs locais em dados/brutos/localidades_ev/...")
        invalidos = []
        # O conteudo do CSV e validado junto com o hash registrado no manifesto.
        manifesto = (
            pd.read_csv(MANIFESTO_DADOS)
            if MANIFESTO_DADOS.exists()
            else pd.DataFrame()
        )
        colunas_manifesto_validas = {"arquivo", "sha256"}.issubset(manifesto.columns)
        for local in LOCALIDADES:
            arquivo = OUTPUT_DIR / f"{nome_arquivo(local['nome'])}.csv"
            valido, motivo = validar_csv_nrel_localidade(arquivo, local)
            # A integridade so pode ser confirmada com arquivo e hash unicos.
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

    # Modo de coleta: atualiza os CSVs e o manifesto, sem treinar modelos.
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
    
    # Modo padrao: executa o pipeline completo em sequencia para cada local.
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
            # Registra a falha para apresentar todas as localidades problematicas.
            print(f"  ERRO ao processar {local['nome']}: {e}")
            resultados.append({
                "localidade": local["nome"],
                "pais": local["pais"],
                "lat": local["lat"],
                "lon": local["lon"],
                "erro": str(e),
            })

    # Nao gera tabelas parciais, pois elas poderiam parecer um resultado completo.
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

    # Os CSVs usados no experimento ficam registrados apos uma execucao valida.
    gerar_manifesto_dados()
    print(f"\n[OK] Manifesto SHA-256 atualizado em: {MANIFESTO_DADOS}")
    
    # Consolida duas linhas por localidade: uma para cada modelo.
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
    
    # Esta tabela longa e adequada para filtros e graficos por modelo.
    df_metricas.to_csv(RESULTADOS_DIR / "metricas_geral.csv", index=False)
    
    print("\nTabela de metricas (todas as localidades):")
    print(df_metricas.to_string(index=False))
    
    # Esta tabela larga facilita comparar os dois modelos na mesma linha.
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
                # O vencedor do resumo e definido pelo maior R2.
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


# Evita iniciar a coleta ou o treinamento quando o modulo e importado em testes.
if __name__ == "__main__":
    main()
