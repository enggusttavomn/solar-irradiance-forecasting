"""Coleta, valida e treina modelos para todas as localidades do estudo.

O script repete o mesmo pipeline independente em cada fabrica. Ele tambem
aplica validacoes mais rigorosas que o fluxo de serie unica, pois os CSVs desta
pasta sao apresentados como o conjunto oficial e auditavel do trabalho.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import math
import multiprocessing as mp
import os
from pathlib import Path
import traceback
import warnings

import numpy as np
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
# O diretorio historico ``todas_localidades_mensal`` e preservado. A avaliacao
# corrigida fica separada para impedir que tabelas de protocolos diferentes
# sejam combinadas acidentalmente no artigo.
RESULTADOS_MENSAIS_DIR = PASTA_RESULTADOS / "avaliacao_mensal_corrigida"
ANO_INICIAL_DADOS = 2019
ANO_FINAL_DADOS = 2024
COLUNAS_ESTATISTICAS_HORARIAS = [
    "ghi_horario_media",
    "ghi_horario_sigma",
    "ghi_horario_cov",
    "ghi_horario_cov_percentual",
    "ghi_horario_observacoes",
    "ghi_horario_intervalo_mediano_horas",
    "ghi_horario_fonte_estatistica",
]


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


def ler_estatisticas_horarias_localidade(local: dict) -> dict[str, float | str]:
    """Le sigma/media horario salvo na coleta ou marca indisponivel."""
    arquivo = OUTPUT_DIR / f"{nome_arquivo(local['nome'])}.csv"
    base = {
        "Localidade": local["nome"],
        "Pais": local["pais"],
        "ghi_horario_media": float("nan"),
        "ghi_horario_sigma": float("nan"),
        "ghi_horario_cov": float("nan"),
        "ghi_horario_cov_percentual": float("nan"),
        "ghi_horario_observacoes": float("nan"),
        "ghi_horario_intervalo_mediano_horas": float("nan"),
        "ghi_horario_fonte_estatistica": "indisponivel_csv_diario",
    }
    if not arquivo.exists():
        return base

    dados = pd.read_csv(arquivo, nrows=1)
    for coluna in COLUNAS_ESTATISTICAS_HORARIAS:
        if coluna in dados.columns:
            base[coluna] = dados.iloc[0][coluna]
    return base


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


def caminho_resultados_frequencia(frequencia_modelagem: str) -> Path:
    """Retorna a pasta de resultados da escala temporal solicitada."""
    if frequencia_modelagem == "diaria":
        return RESULTADOS_DIR
    if frequencia_modelagem == "mensal":
        return RESULTADOS_MENSAIS_DIR
    raise ValueError("frequencia_modelagem deve ser 'diaria' ou 'mensal'.")


def treinar_localidade(
    local: dict,
    verbose: bool = True,
    forcar_download: bool = False,
    frequencia_modelagem: str = "diaria",
    repeticoes_redes: int = 3,
    seed_base: int = 42,
    gerar_figuras: bool = True,
    reter_modelos: bool = True,
) -> dict:
    """Executa o pipeline completo e independente para uma localidade.

    Args:
        local: Dicionario do cadastro ``LOCALIDADES_EV``.
        verbose: Controla as mensagens detalhadas no terminal.
        forcar_download: Quando verdadeiro, ignora o CSV local.
        frequencia_modelagem: ``diaria`` para prever o dia seguinte ou
            ``mensal`` para prever o mes seguinte.
        repeticoes_redes: Sementes independentes para MLP, RNN e LSTM. As
            previsoes publicadas sao a media do conjunto.
        seed_base: Primeira semente da sequencia reproduzivel.
        gerar_figuras: Desativa apenas figuras por localidade, sem afetar CSVs.
        reter_modelos: Mantem objetos ajustados no retorno. O lote desativa esta
            opcao porque os modelos ja foram salvos e o TensorFlow consumiria
            memoria cumulativa entre localidades.

    Returns:
        Dicionario com metricas, modelos e informacoes da localidade.
    """
    # Importacoes locais reduzem o custo dos modos que apenas validam ou baixam.
    if repeticoes_redes < 1:
        raise ValueError("repeticoes_redes deve ser positivo.")

    from codigo_fonte.avaliacao import calcular_metricas, salvar_previsoes
    from codigo_fonte.avaliacao import desnormalizar_ghi
    from codigo_fonte.baselines import normalizar_previsoes_fisicas, prever_baselines
    from codigo_fonte.features import dividir_treino_teste_temporal
    from codigo_fonte.graficos import salvar_graficos
    from codigo_fonte.modelos import (
        salvar_modelo,
        treinar_lstm,
        treinar_mlp,
        treinar_rnn,
        treinar_vizinhos_historicos,
        treinar_xgboost,
    )
    from codigo_fonte.preprocessamento import preparar_serie_temporal

    nome = local["nome"]
    pais = local["pais"]
    resultados_dir = caminho_resultados_frequencia(frequencia_modelagem)
    resultados_dir.mkdir(parents=True, exist_ok=True)
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"Localidade: {nome} ({pais})")
        print(f"Frequencia: {frequencia_modelagem}")
        print(f"Latitude: {local['lat']}, Longitude: {local['lon']}")
        print(f"{'='*60}")
    
    # Etapa 1: obter somente dados oficiais e validados.
    serie_ghi = carregar_ou_coletar_localidade(local, forcar_download=forcar_download)
    
    # Etapa 2: limpar, transformar e salvar a base de features desta localidade.
    if verbose:
        print("  Preparando serie temporal continua, lags e calendario...")
    sufixo_features = "" if frequencia_modelagem == "diaria" else "_mensal_v2"
    preparation = preparar_serie_temporal(
        serie_ghi,
        output_path=(
            PASTA_DADOS_PROCESSADOS
            / "localidades_ev"
            / f"{nome_arquivo(nome)}_features{sufixo_features}.csv"
        ),
        frequencia_modelagem=frequencia_modelagem,
    )
    dados = preparation.dados_modelagem
    feature_columns = preparation.feature_columns
    
    # Etapa 3: corte cronologico. Os ultimos 20% simulam o futuro nao visto.
    X_train, X_test, y_train, y_test, dados_treino, dados_teste = dividir_treino_teste_temporal(
        dados,
        feature_columns,
        target_column="ghi_alvo",
        train_ratio=0.8,
    )
    # A data associada a cada previsao e a data do alvo t+1.
    datas_teste = pd.to_datetime(dados_teste["data_alvo"])
    
    # Um nome por localidade impede que modelos sejam sobrescritos no lote.
    pasta_modelo_local = PASTA_MODELOS / (
        "localidades"
        if frequencia_modelagem == "diaria"
        else "avaliacao_mensal_corrigida"
    )
    pasta_modelo_local.mkdir(parents=True, exist_ok=True)

    treinadores = {
        "XGBoost": (treinar_xgboost, "xgboost", ".joblib", False),
        "MLP": (treinar_mlp, "mlp", ".joblib", True),
        "RNN": (treinar_rnn, "rnn", ".keras", True),
        "LSTM": (treinar_lstm, "lstm", ".keras", True),
        "VizinhosHistoricos": (
            treinar_vizinhos_historicos,
            "vizinhos_historicos",
            ".joblib",
            False,
        ),
    }
    modelos = {}
    predicoes = {}
    predicoes_repeticoes = []
    for nome_modelo, (treinador, slug, extensao, repetir) in treinadores.items():
        if verbose:
            print(f"  Treinando {nome_modelo}...")
        sementes = list(range(seed_base, seed_base + repeticoes_redes)) if repetir else [seed_base]
        previsoes_semente = []
        modelos_semente = []
        for semente in sementes:
            modelo = treinador(X_train, y_train, random_state=semente)
            if reter_modelos:
                modelos_semente.append(modelo)
            y_pred_semente = (
                pd.Series(modelo.predict(X_test), index=y_test.index)
                .clip(0, 1)
                .reset_index(drop=True)
            )
            previsoes_semente.append(y_pred_semente)
            sufixo_seed = f"_seed{semente}" if repetir else ""
            salvar_modelo(
                modelo,
                pasta_modelo_local
                / f"{slug}_{nome_arquivo(nome)}{sufixo_seed}{extensao}",
            )
            predicoes_repeticoes.append(
                {
                    "Localidade": nome,
                    "Pais": pais,
                    "Modelo": nome_modelo,
                    "Seed": semente,
                    "Predicao_normalizada": y_pred_semente,
                }
            )
        if reter_modelos:
            modelos[nome_modelo] = modelos_semente if repetir else modelos_semente[0]
        predicoes[nome_modelo] = pd.concat(previsoes_semente, axis=1).mean(axis=1)

    # Referencias sazonais sao parte do protocolo, nao um pos-processamento.
    baselines_original = prever_baselines(
        dados_treino,
        dados_teste,
        frequencia=frequencia_modelagem,
    )
    baselines_normalizados = normalizar_previsoes_fisicas(
        baselines_original,
        preparation.quantization_params,
    )
    predicoes.update(baselines_normalizados)

    # Etapa 6: zerar os indices facilita alinhar datas, reais e previsoes.
    y_test_reset = y_test.reset_index(drop=True)
    datas_reset = datas_teste.reset_index(drop=True)
    y_test_original = dados_teste["ghi_alvo_original"].reset_index(drop=True)
    predicoes_original = {
        nome_modelo: desnormalizar_ghi(y_pred, preparation.quantization_params)
        for nome_modelo, y_pred in predicoes.items()
        if nome_modelo not in baselines_original
    }
    predicoes_original.update(
        {
            nome_modelo: pd.Series(valores).reset_index(drop=True)
            for nome_modelo, valores in baselines_original.items()
        }
    )

    # Guarda a dispersao entre sementes sem confundi-la com a metrica do
    # ensemble, que e a previsao principal usada na comparacao entre modelos.
    metricas_repeticoes = []
    for registro in predicoes_repeticoes:
        predicao_wm2 = desnormalizar_ghi(
            registro.pop("Predicao_normalizada"),
            preparation.quantization_params,
        )
        metrica_seed = calcular_metricas(
            y_test_original,
            predicao_wm2,
            registro["Modelo"],
            sufixo="wm2",
        )
        metricas_repeticoes.append({**registro, **metrica_seed})

    # Mantem as metricas normalizadas e acrescenta a escala fisica em W/m2.
    metricas_modelos = {}
    for nome_modelo in predicoes:
        metricas = calcular_metricas(
            y_test_reset,
            predicoes[nome_modelo],
            nome_modelo,
            sufixo="normalizado",
        )
        metricas.update(
            calcular_metricas(
                y_test_original,
                predicoes_original[nome_modelo],
                nome_modelo,
                sufixo="wm2",
            )
        )
        # Adiciona contexto geografico para montar a tabela consolidada depois.
        metricas["Localidade"] = nome
        metricas["Pais"] = pais
        metricas["Lat"] = local["lat"]
        metricas["Lon"] = local["lon"]
        metricas_modelos[nome_modelo] = metricas
    
    # Etapa 7: salvar valores linha a linha para auditoria e graficos.
    pasta_previsoes_local = resultados_dir / "previsoes"
    pasta_previsoes_local.mkdir(parents=True, exist_ok=True)
    salvar_previsoes(
        datas_reset,
        y_test_reset,
        predicoes,
        pasta_previsoes_local / nome_arquivo(nome),
        y_true_original=y_test_original,
        predicoes_original=predicoes_original,
    )
    
    # Etapa 8: produzir figuras nas duas escalas para a mesma localidade.
    if gerar_figuras:
        pasta_figuras_local = resultados_dir / "figuras"
        pasta_figuras_local.mkdir(parents=True, exist_ok=True)
        salvar_graficos(
            datas_reset,
            y_test_reset,
            predicoes,
            pasta_figuras_local / nome_arquivo(nome) / "normalizado",
        )
        salvar_graficos(
            datas_reset,
            y_test_original,
            predicoes_original,
            pasta_figuras_local / nome_arquivo(nome) / "wm2",
            y_label=f"GHI medio {frequencia_modelagem} (W/m2)",
            titulo_sufixo=" - escala real",
        )
    
    if verbose:
        for nome_modelo, metricas in metricas_modelos.items():
            print(f"\n  Metricas {nome_modelo}:")
            print(f"    MAE normalizado: {metricas['MAE_normalizado']:.4f}")
            print(f"    RMSE normalizado: {metricas['RMSE_normalizado']:.4f}")
            print(f"    MAE W/m2: {metricas['MAE_wm2']:.2f}")
            print(f"    RMSE W/m2: {metricas['RMSE_wm2']:.2f}")
            print(f"    nRMSE W/m2: {metricas['nRMSE_percentual_wm2']:.2f}%")
            print(f"    R2 W/m2: {metricas['R2_wm2']:.4f}")

    # Checkpoints tabulares permitem retomar/consolidar um lote interrompido
    # sem repetir modelos ja finalizados.
    pasta_parciais = resultados_dir / "parciais_localidades"
    pasta_parciais.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(metricas_modelos.values()).to_csv(
        pasta_parciais / f"metricas_{nome_arquivo(nome)}.csv",
        index=False,
    )
    pd.DataFrame(metricas_repeticoes).to_csv(
        pasta_parciais / f"seeds_{nome_arquivo(nome)}.csv",
        index=False,
    )
    
    # O retorno alimenta a consolidacao feita por ``main``.
    return {
        "localidade": nome,
        "pais": pais,
        "lat": local["lat"],
        "lon": local["lon"],
        "frequencia_modelagem": frequencia_modelagem,
        "xgboost": metricas_modelos["XGBoost"],
        "mlp": metricas_modelos["MLP"],
        "rnn": metricas_modelos["RNN"],
        "lstm": metricas_modelos["LSTM"],
        "metricas_modelos": metricas_modelos,
        "metricas_repeticoes": metricas_repeticoes,
        "modelos": modelos,
        "dados": dados,
        "y_test": y_test_reset,
        "predicoes": predicoes,
        "y_test_original": y_test_original,
        "predicoes_original": predicoes_original,
        "datas_teste": datas_reset,
        "feature_columns": feature_columns,
        "target_transform": preparation.target_transform,
        "inicio_treino": pd.to_datetime(dados_treino["data_alvo"]).min(),
        "fim_treino": pd.to_datetime(dados_treino["data_alvo"]).max(),
        "inicio_teste": pd.to_datetime(dados_teste["data_alvo"]).min(),
        "fim_teste": pd.to_datetime(dados_teste["data_alvo"]).max(),
        "n_treino": len(dados_treino),
        "n_teste": len(dados_teste),
        "estatisticas_horarias": ler_estatisticas_horarias_localidade(local),
    }


def reconstruir_resultado_localidade(
    local: dict,
    frequencia_modelagem: str = "mensal",
) -> dict:
    """Reconstrui metricas a partir das previsoes salvas e valida o alinhamento."""
    from codigo_fonte.avaliacao import calcular_metricas
    from codigo_fonte.features import dividir_treino_teste_temporal
    from codigo_fonte.preprocessamento import preparar_serie_temporal

    resultados_dir = caminho_resultados_frequencia(frequencia_modelagem)
    slug_local = nome_arquivo(local["nome"])
    arquivo_previsoes = (
        resultados_dir / "previsoes" / slug_local / "previsoes_modelos.csv"
    )
    if not arquivo_previsoes.exists():
        raise FileNotFoundError(f"Previsoes ausentes para {local['nome']}.")
    previsoes = pd.read_csv(arquivo_previsoes, parse_dates=["data"])

    # Refaz apenas o preprocessamento leve para comprovar que datas, valores de
    # referencia, features e corte ainda correspondem ao codigo atual.
    serie = carregar_ou_coletar_localidade(local, forcar_download=False)
    preparation = preparar_serie_temporal(
        serie,
        output_path=None,
        frequencia_modelagem=frequencia_modelagem,
    )
    dados = preparation.dados_modelagem
    _, _, _, _, dados_treino, dados_teste = dividir_treino_teste_temporal(
        dados,
        preparation.feature_columns,
        target_column="ghi_alvo",
        train_ratio=0.8,
    )
    datas_esperadas = pd.to_datetime(dados_teste["data_alvo"]).reset_index(drop=True)
    y_normalizado = dados_teste["ghi_alvo"].reset_index(drop=True)
    y_wm2 = dados_teste["ghi_alvo_original"].reset_index(drop=True)
    if not previsoes["data"].reset_index(drop=True).equals(datas_esperadas):
        raise ValueError(f"Datas salvas divergentes para {local['nome']}.")
    if not np.allclose(previsoes["ghi_real_wm2"], y_wm2, rtol=0, atol=1e-9):
        raise ValueError(f"Valores de referencia divergentes para {local['nome']}.")

    modelos = {
        "XGBoost": "xgboost",
        "MLP": "mlp",
        "RNN": "rnn",
        "LSTM": "lstm",
        "VizinhosHistoricos": "vizinhoshistoricos",
        "Persistencia": "persistencia",
        "SazonalIngenuo": "sazonalingenuo",
        "Climatologia": "climatologia",
    }
    metricas_modelos = {}
    for nome_modelo, slug_modelo in modelos.items():
        coluna_norm = f"ghi_previsto_{slug_modelo}_normalizado"
        coluna_wm2 = f"ghi_previsto_{slug_modelo}_wm2"
        if coluna_norm not in previsoes or coluna_wm2 not in previsoes:
            raise ValueError(f"Previsao de {nome_modelo} ausente para {local['nome']}.")
        metricas = calcular_metricas(
            y_normalizado,
            previsoes[coluna_norm],
            nome_modelo,
            sufixo="normalizado",
        )
        metricas.update(
            calcular_metricas(
                y_wm2,
                previsoes[coluna_wm2],
                nome_modelo,
                sufixo="wm2",
            )
        )
        metricas.update(
            {
                "Localidade": local["nome"],
                "Pais": local["pais"],
                "Lat": local["lat"],
                "Lon": local["lon"],
            }
        )
        metricas_modelos[nome_modelo] = metricas

    arquivo_seeds = resultados_dir / "parciais_localidades" / f"seeds_{slug_local}.csv"
    metricas_repeticoes = (
        pd.read_csv(arquivo_seeds).to_dict("records")
        if arquivo_seeds.exists() and arquivo_seeds.stat().st_size > 1
        else []
    )
    return {
        "localidade": local["nome"],
        "pais": local["pais"],
        "lat": local["lat"],
        "lon": local["lon"],
        "frequencia_modelagem": frequencia_modelagem,
        "metricas_modelos": metricas_modelos,
        "metricas_repeticoes": metricas_repeticoes,
        "feature_columns": preparation.feature_columns,
        "target_transform": preparation.target_transform,
        "inicio_treino": pd.to_datetime(dados_treino["data_alvo"]).min(),
        "fim_treino": pd.to_datetime(dados_treino["data_alvo"]).max(),
        "inicio_teste": pd.to_datetime(dados_teste["data_alvo"]).min(),
        "fim_teste": pd.to_datetime(dados_teste["data_alvo"]).max(),
        "n_treino": len(dados_treino),
        "n_teste": len(dados_teste),
        "estatisticas_horarias": ler_estatisticas_horarias_localidade(local),
    }


def consolidar_resultados(resultados: list[dict], resultados_dir: Path) -> pd.DataFrame:
    """Salva as tabelas consolidadas para uma escala temporal de modelagem."""
    from codigo_fonte.avaliacao import (
        comparar_mae_com_referencia,
        resumir_metricas_por_modelo,
    )

    # Consolida uma linha por par localidade/modelo.
    print("\n" + "="*60)
    print("TABELA COMPARATIVA FINAL")
    print("="*60)

    metricas_geral = []
    for res in resultados:
        if "erro" not in res:
            for nome_modelo, metricas in res["metricas_modelos"].items():
                metricas_geral.append({
                    "Localidade": res["localidade"],
                    "Pais": res["pais"],
                    "Frequencia": res["frequencia_modelagem"],
                    "Modelo": nome_modelo,
                    **{
                        chave: valor
                        for chave, valor in metricas.items()
                        if chave != "Modelo"
                        and chave not in {"Localidade", "Pais", "Lat", "Lon"}
                    },
                })

    df_metricas = pd.DataFrame(metricas_geral)
    df_metricas = df_metricas.sort_values(["Localidade", "MAE_wm2", "Modelo"])
    df_metricas.to_csv(resultados_dir / "metricas_geral.csv", index=False)

    # Media e intervalo entre localidades: unidade de repeticao do estudo.
    df_resumo_modelos = resumir_metricas_por_modelo(df_metricas, "MAE_wm2")
    df_resumo_modelos.to_csv(
        resultados_dir / "resumo_modelos_mae.csv",
        index=False,
    )
    if "Climatologia" in set(df_metricas["Modelo"]):
        df_comparacao = comparar_mae_com_referencia(df_metricas, "Climatologia")
        df_comparacao.to_csv(
            resultados_dir / "comparacao_climatologia.csv",
            index=False,
        )

    # Resultados de cada seed ficam separados do ensemble para quantificar
    # sensibilidade a inicializacao sem inflar artificialmente a amostra.
    metricas_repeticoes = [
        linha
        for res in resultados
        if "erro" not in res
        for linha in res.get("metricas_repeticoes", [])
    ]
    df_repeticoes = pd.DataFrame(metricas_repeticoes)
    if not df_repeticoes.empty:
        df_repeticoes.to_csv(
            resultados_dir / "metricas_por_seed.csv",
            index=False,
        )
        resumo_seeds = (
            df_repeticoes.groupby(["Localidade", "Pais", "Modelo"], as_index=False)
            .agg(
                N_seeds=("Seed", "nunique"),
                MAE_wm2_media_seeds=("MAE_wm2", "mean"),
                MAE_wm2_desvio_seeds=("MAE_wm2", "std"),
                RMSE_wm2_media_seeds=("RMSE_wm2", "mean"),
                RMSE_wm2_desvio_seeds=("RMSE_wm2", "std"),
            )
        )
        resumo_seeds.to_csv(
            resultados_dir / "variabilidade_sementes.csv",
            index=False,
        )

    divisoes = pd.DataFrame(
        [
            {
                "Localidade": res["localidade"],
                "Frequencia": res["frequencia_modelagem"],
                "Inicio_treino": res["inicio_treino"],
                "Fim_treino": res["fim_treino"],
                "N_treino": res["n_treino"],
                "Inicio_teste": res["inicio_teste"],
                "Fim_teste": res["fim_teste"],
                "N_teste": res["n_teste"],
                "Horizonte_passos": 1,
                "Modo": "walk_forward_modelo_fixo_com_observacao_t",
                "Transformacao_alvo": res["target_transform"],
                "Features": ";".join(res["feature_columns"]),
                "Status_inferencia": "retrospectiva_exploratoria",
            }
            for res in resultados
            if "erro" not in res
        ]
    )
    divisoes.to_csv(resultados_dir / "protocolo_temporal.csv", index=False)

    print("\nTabela de metricas (todas as localidades):")
    print(df_metricas.to_string(index=False))

    # Esta tabela larga facilita comparar todos os modelos na mesma linha.
    resumo = []
    estatisticas_horarias = []
    for res in resultados:
        if "erro" not in res:
            linha_resumo = {
                "Localidade": res["localidade"],
                "Pais": res["pais"],
                "Frequencia": res["frequencia_modelagem"],
                "Lat": res["lat"],
                "Lon": res["lon"],
            }
            for nome_modelo, metricas in res["metricas_modelos"].items():
                linha_resumo.update({
                    f"{nome_modelo}_MAE_normalizado": metricas["MAE_normalizado"],
                    f"{nome_modelo}_RMSE_normalizado": metricas["RMSE_normalizado"],
                    f"{nome_modelo}_MAE_wm2": metricas["MAE_wm2"],
                    f"{nome_modelo}_RMSE_wm2": metricas["RMSE_wm2"],
                    f"{nome_modelo}_nRMSE_percentual_wm2": metricas["nRMSE_percentual_wm2"],
                    f"{nome_modelo}_R2_wm2": metricas["R2_wm2"],
                })
            # MAE em W/m2 e a metrica primaria declarada antes da comparacao.
            linha_resumo["Melhor_Modelo_MAE"] = min(
                res["metricas_modelos"].items(),
                key=lambda item: item[1]["MAE_wm2"],
            )[0]
            resumo.append(linha_resumo)
            estatisticas_horarias.append(res["estatisticas_horarias"])

    df_resumo = pd.DataFrame(resumo)
    df_resumo.to_csv(resultados_dir / "resumo_localidades.csv", index=False)
    df_estatisticas_horarias = pd.DataFrame(estatisticas_horarias)
    df_estatisticas_horarias.to_csv(
        resultados_dir / "estatisticas_horarias.csv",
        index=False,
    )

    print("\n" + "="*60)
    print("RESUMO POR LOCALIDADE")
    print("="*60)
    print(df_resumo.to_string(index=False))
    print("\nEstatisticas horarias de GHI:")
    print(df_estatisticas_horarias.to_string(index=False))

    print("\n[OK] Pipeline finalizado!")
    print(f"[INFO] Resultados salvos em: {resultados_dir.absolute()}")
    print(f"[INFO] Metricas gerais: {resultados_dir / 'metricas_geral.csv'}")
    print(f"[INFO] Resumo: {resultados_dir / 'resumo_localidades.csv'}")
    print(f"[INFO] Comparacao com climatologia: {resultados_dir / 'comparacao_climatologia.csv'}")
    print(f"[INFO] Protocolo temporal: {resultados_dir / 'protocolo_temporal.csv'}")
    print(f"[INFO] Estatisticas horarias: {resultados_dir / 'estatisticas_horarias.csv'}")
    return df_resumo


def _reduzir_resultado_para_consolidacao(resultado: dict) -> dict:
    """Remove objetos grandes que nao sao usados depois de salvar cada local."""
    chaves = {
        "localidade",
        "pais",
        "lat",
        "lon",
        "frequencia_modelagem",
        "metricas_modelos",
        "metricas_repeticoes",
        "feature_columns",
        "target_transform",
        "inicio_treino",
        "fim_treino",
        "inicio_teste",
        "fim_teste",
        "n_treino",
        "n_teste",
        "estatisticas_horarias",
    }
    return {chave: valor for chave, valor in resultado.items() if chave in chaves}


def _worker_treinar_localidade(conexao, kwargs: dict) -> None:
    """Executa uma localidade em processo descartavel e devolve dados pequenos."""
    try:
        resultado = treinar_localidade(**kwargs, reter_modelos=False)
        conexao.send(("ok", _reduzir_resultado_para_consolidacao(resultado)))
    except BaseException as exc:  # a falha precisa atravessar a fronteira do processo
        conexao.send(
            (
                "erro",
                {
                    "mensagem": str(exc),
                    "tipo": type(exc).__name__,
                    "traceback": traceback.format_exc(),
                },
            )
        )
    finally:
        conexao.close()


def salvar_manifesto_execucao(
    frequencia_modelagem: str,
    repeticoes_redes: int,
    seed_base: int,
) -> None:
    """Registra entradas, codigo, ambiente e protocolo do lote consolidado."""
    from codigo_fonte.reprodutibilidade import salvar_manifesto

    resultados_dir = caminho_resultados_frequencia(frequencia_modelagem)
    arquivos_entrada = [
        OUTPUT_DIR / f"{nome_arquivo(local['nome'])}.csv" for local in LOCALIDADES
    ]
    arquivos_entrada.extend(
        [
            Path(__file__),
            Path(__file__).resolve().parent / "reavaliar_modelos_salvos.py",
            Path(__file__).resolve().parent / "requirements.txt",
            Path(__file__).resolve().parent / "codigo_fonte" / "preprocessamento.py",
            Path(__file__).resolve().parent / "codigo_fonte" / "features.py",
            Path(__file__).resolve().parent / "codigo_fonte" / "modelos.py",
            Path(__file__).resolve().parent / "codigo_fonte" / "avaliacao.py",
            Path(__file__).resolve().parent / "codigo_fonte" / "baselines.py",
        ]
    )
    salvar_manifesto(
        resultados_dir / "manifesto_execucao.json",
        arquivos_entrada=arquivos_entrada,
        configuracao={
            "frequencia": frequencia_modelagem,
            "train_ratio": 0.8,
            "horizonte_passos": 1,
            "modo_previsao": "walk_forward_modelo_fixo_com_observacao_t",
            "repeticoes_redes": repeticoes_redes,
            "seed_base": seed_base,
            "metrica_primaria": "MAE_wm2",
            "referencia_primaria": "Climatologia",
            "quantizacao_modelagem": False,
            "status_inferencia": "retrospectiva_exploratoria",
        },
        seed=seed_base,
        raiz_projeto=Path(__file__).resolve().parent,
        metadados={
            "observacao": (
                "A janela de 2024 ja foi inspecionada durante o desenvolvimento; "
                "os resultados nao constituem confirmacao prospectiva independente."
            )
        },
    )


def executar_lote_modelagem(
    frequencia_modelagem: str,
    verbose: bool = True,
    forcar_download: bool = False,
    repeticoes_redes: int = 5,
    seed_base: int = 42,
    gerar_figuras: bool = True,
    isolar_localidades: bool = True,
) -> list[dict]:
    """Executa treinamento e consolidacao de uma escala temporal."""
    resultados_dir = caminho_resultados_frequencia(frequencia_modelagem)
    resultados_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "="*60)
    print(f"ESCALA DE MODELAGEM: {frequencia_modelagem.upper()}")
    print("="*60)

    resultados = []
    for local in LOCALIDADES:
        try:
            parametros = {
                "local": local,
                "verbose": verbose,
                "forcar_download": forcar_download,
                "frequencia_modelagem": frequencia_modelagem,
                "repeticoes_redes": repeticoes_redes,
                "seed_base": seed_base,
                "gerar_figuras": gerar_figuras,
            }
            if isolar_localidades:
                contexto = mp.get_context("spawn")
                conexao_pai, conexao_filho = contexto.Pipe(duplex=False)
                processo = contexto.Process(
                    target=_worker_treinar_localidade,
                    args=(conexao_filho, parametros),
                    name=f"ghi-{nome_arquivo(local['nome'])}",
                )
                processo.start()
                conexao_filho.close()
                try:
                    status, payload = conexao_pai.recv()
                except EOFError as exc:
                    processo.join()
                    raise RuntimeError(
                        f"Subprocesso terminou sem resultado (exit code {processo.exitcode})."
                    ) from exc
                finally:
                    conexao_pai.close()
                processo.join()
                if status == "erro":
                    raise RuntimeError(
                        f"{payload['tipo']}: {payload['mensagem']}\n{payload['traceback']}"
                    )
                if processo.exitcode != 0:
                    raise RuntimeError(
                        f"Subprocesso terminou com exit code {processo.exitcode}."
                    )
                resultado = payload
            else:
                resultado = _reduzir_resultado_para_consolidacao(
                    treinar_localidade(**parametros, reter_modelos=False)
                )
            resultados.append(resultado)
            gc.collect()
        except Exception as e:
            # Registra a falha para apresentar todas as localidades problematicas.
            print(f"  ERRO ao processar {local['nome']}: {e}")
            resultados.append({
                "localidade": local["nome"],
                "pais": local["pais"],
                "lat": local["lat"],
                "lon": local["lon"],
                "frequencia_modelagem": frequencia_modelagem,
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

    consolidar_resultados(resultados, resultados_dir)

    salvar_manifesto_execucao(frequencia_modelagem, repeticoes_redes, seed_base)
    return resultados


def main():
    """Interpreta o modo solicitado e coordena as dez localidades."""
    # As opcoes permitem separar validacao, coleta e treinamento.
    parser = argparse.ArgumentParser(
        description=(
            "Avalia baselines, XGBoost, MLP, RNN, LSTM e vizinhos historicos "
            "para previsao de GHI em todas as localidades."
        )
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
    parser.add_argument(
        "--frequencia",
        choices=["diaria", "mensal", "ambas"],
        default="diaria",
        help="Escala temporal da modelagem. Use 'ambas' para rodar diaria e mensal.",
    )
    parser.add_argument(
        "--repeticoes-redes",
        type=int,
        default=3,
        help="Numero de sementes para MLP, RNN e LSTM (padrao: 5).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semente inicial reproduzivel (padrao: 42).",
    )
    parser.add_argument(
        "--sem-figuras",
        action="store_true",
        help="Nao gera o grande conjunto de figuras por localidade.",
    )
    parser.add_argument(
        "--somente-consolidar",
        action="store_true",
        help=(
            "Revalida e consolida previsoes existentes sem treinar novamente; "
            "util para retomar um lote interrompido."
        ),
    )
    args = parser.parse_args()
    if args.repeticoes_redes < 1:
        parser.error("--repeticoes-redes deve ser positivo")

    from codigo_fonte.reprodutibilidade import definir_seed_global

    definir_seed_global(args.seed, configurar_tensorflow=False)
    
    # Prepara a estrutura antes de qualquer modo de execucao.
    criar_pastas()
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTADOS_MENSAIS_DIR.mkdir(parents=True, exist_ok=True)
    
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
    
    # Os CSVs usados no experimento ficam registrados apos uma execucao valida.
    gerar_manifesto_dados()
    print(f"\n[OK] Manifesto SHA-256 atualizado em: {MANIFESTO_DADOS}")

    frequencias = ["diaria", "mensal"] if args.frequencia == "ambas" else [args.frequencia]
    resultados_por_frequencia = {}
    for frequencia_modelagem in frequencias:
        if args.somente_consolidar:
            resultados = [
                reconstruir_resultado_localidade(local, frequencia_modelagem)
                for local in LOCALIDADES
            ]
            consolidar_resultados(
                resultados,
                caminho_resultados_frequencia(frequencia_modelagem),
            )
            salvar_manifesto_execucao(
                frequencia_modelagem,
                args.repeticoes_redes,
                args.seed,
            )
            resultados_por_frequencia[frequencia_modelagem] = resultados
        else:
            resultados_por_frequencia[frequencia_modelagem] = executar_lote_modelagem(
                frequencia_modelagem,
                verbose=args.verbose,
                forcar_download=args.forcar_download,
                repeticoes_redes=args.repeticoes_redes,
                seed_base=args.seed,
                gerar_figuras=not args.sem_figuras,
            )
    
    return resultados_por_frequencia


# Evita iniciar a coleta ou o treinamento quando o modulo e importado em testes.
if __name__ == "__main__":
    main()
