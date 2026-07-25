"""Orquestracao auditavel do protocolo mensal global canonico.

Uma execucao marcada como ``completa`` fornece a fonte numerica dos artigos;
execucoes ``smoke`` verificam somente o caminho de codigo e nunca constituem
evidencia cientifica. A execucao pode ser retomada por artefato de
modelo/semente sem recalcular treinamentos ja persistidos.

Todos os modelos usam as mesmas dez series, as mesmas origens de previsao e
um horizonte de um mes. DeepAR usa o estimador oficial global do GluonTS, e o
DeepNPTS usa esse estimador com uma correcao restrita ao registro dos
embeddings no PyTorch; RNN, LSTM e DilatedRNN recebem sequencias cronologicas;
XGBoost e MLP usam a representacao tabular equivalente. O teste de 2024 e
retrospectivo, com origem deslizante e sem reajuste dos modelos.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import platform
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Iterable

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache-tcc")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import joblib
import numpy as np
import pandas as pd

from codigo_fonte.avaliacao import (
    calcular_metricas,
    calcular_metricas_probabilisticas,
    comparar_mae_com_referencia,
    resumir_metricas_por_modelo,
)
from codigo_fonte.configuracao import PASTA_DADOS_BRUTOS, PROJECT_ROOT
from codigo_fonte.dados_mensais_globais import (
    BaseMensalGlobal,
    auditar_arquivos_diarios,
    carregar_base_mensal_global,
    matrizes_keras,
    nome_arquivo,
)
from codigo_fonte.localidades_ev import LOCALIDADES_EV
from codigo_fonte.modelos_globais_gluonts import (
    DeepARGlobalGluonTS,
    DeepNPTSGlobalGluonTS,
    carregar_modelo_global_gluonts,
)
from codigo_fonte.modelos_neurais_globais import (
    prever_rede_global,
    salvar_rede_global,
    treinar_rede_global_com_validacao_temporal,
)
from codigo_fonte.modelos_tabulares_globais import (
    prever_baselines_mensais,
    salvar_modelo_joblib,
    treinar_mlp_global,
    treinar_xgboost_global,
)
from codigo_fonte.reprodutibilidade import (
    salvar_json,
    salvar_manifesto,
    sha256_arquivo,
    versoes_dependencias,
)


MODELOS_PROBABILISTICOS = ("DeepAR", "DeepNPTS")
SEMENTES_PADRAO = (11, 23, 42, 67, 89)
ARQUIVOS_CODIGO_PROTOCOLO = (
    "codigo_fonte/avaliacao.py",
    "codigo_fonte/dados_mensais_globais.py",
    "codigo_fonte/dilated_rnn.py",
    "codigo_fonte/experimento_mensal_canonico.py",
    "codigo_fonte/figuras_experimento_canonico.py",
    "codigo_fonte/modelos_globais_gluonts.py",
    "codigo_fonte/redes_deepnpts_registradas.py",
    "codigo_fonte/modelos_neurais_globais.py",
    "codigo_fonte/modelos_tabulares_globais.py",
    "codigo_fonte/reprodutibilidade.py",
    "executar_avaliacao_mensal_canonica.py",
    "gerar_figuras_avaliacao_canonica.py",
)


@dataclass(frozen=True)
class ConfiguracaoExperimento:
    """Hiperparametros e identificacao do protocolo canonico."""

    contexto: int = 12
    train_ratio: float = 0.8
    niveis_quantizacao: int = 128
    inicio_validacao: str = "2023-01-01"
    sementes: tuple[int, ...] = SEMENTES_PADRAO
    amostras_probabilisticas_por_semente: int = 500
    max_epocas_keras: int = 300
    paciencia_keras: int = 30
    epocas_deepnpts: int = 100
    lotes_por_epoca_deepnpts: int = 100
    epocas_deepar: int = 100
    lotes_por_epoca_deepar: int = 50
    nivel_intervalo: float = 0.90
    modo_execucao: str = "completa"

    def __post_init__(self) -> None:
        if self.modo_execucao not in {"completa", "smoke"}:
            raise ValueError("modo_execucao deve ser 'completa' ou 'smoke'.")
        if self.contexto < 12:
            raise ValueError("contexto deve ser pelo menos 12.")
        if not 0 < self.train_ratio < 1:
            raise ValueError("train_ratio deve estar entre zero e um.")
        if self.niveis_quantizacao < 2:
            raise ValueError("niveis_quantizacao deve ser pelo menos dois.")
        if not self.sementes or len(set(self.sementes)) != len(self.sementes):
            raise ValueError("sementes deve conter valores unicos.")
        if any(
            isinstance(seed, bool)
            or not isinstance(seed, (int, np.integer))
            or not 0 <= int(seed) < 2**32
            for seed in self.sementes
        ):
            raise ValueError("sementes devem ser inteiros em [0, 2**32).")
        positivos = {
            "amostras_probabilisticas_por_semente": self.amostras_probabilisticas_por_semente,
            "max_epocas_keras": self.max_epocas_keras,
            "paciencia_keras": self.paciencia_keras,
            "epocas_deepnpts": self.epocas_deepnpts,
            "lotes_por_epoca_deepnpts": self.lotes_por_epoca_deepnpts,
            "epocas_deepar": self.epocas_deepar,
            "lotes_por_epoca_deepar": self.lotes_por_epoca_deepar,
        }
        for nome, valor in positivos.items():
            if isinstance(valor, bool) or not isinstance(valor, (int, np.integer)) or valor < 1:
                raise ValueError(f"{nome} deve ser um inteiro positivo.")
        inicio = pd.Timestamp(self.inicio_validacao)
        if inicio.tz is not None:
            raise ValueError("inicio_validacao nao pode possuir fuso horario.")
        if not 0 < self.nivel_intervalo < 1:
            raise ValueError("nivel_intervalo deve estar entre zero e um.")


def _arquivos_entrada_protocolo() -> list[Path]:
    arquivos = [PROJECT_ROOT / "requirements.txt"]
    arquivos.extend(
        PASTA_DADOS_BRUTOS / "localidades_ev" / f"{nome_arquivo(item['nome'])}.csv"
        for item in LOCALIDADES_EV
    )
    arquivos.extend(PROJECT_ROOT / caminho for caminho in ARQUIVOS_CODIGO_PROTOCOLO)
    return arquivos


def _contrato_retomada(
    configuracao: dict[str, object],
    arquivos_entrada: Iterable[Path],
) -> dict[str, object]:
    """Vincula artefatos retomados à configuração, entradas e ambiente."""

    hashes = {}
    for caminho in arquivos_entrada:
        resolvido = caminho.resolve()
        try:
            chave = resolvido.relative_to(PROJECT_ROOT.resolve()).as_posix()
        except ValueError:
            chave = resolvido.as_posix()
        hashes[chave] = sha256_arquivo(resolvido)
    return {
        "versao_esquema": 1,
        "configuracao": configuracao,
        "sha256_entradas": dict(sorted(hashes.items())),
        "versoes_dependencias": versoes_dependencias(),
    }


def _salvar_status(saida: Path, etapa: str, detalhes: dict | None = None) -> None:
    contexto = {
        "protocolo_canonico": True,
        "fonte_artigos_atuais": False,
        **(detalhes or {}),
    }
    salvar_json(
        {
            "etapa": etapa,
            "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
            "detalhes": contexto,
        },
        saida / "status_execucao.json",
    )


def _inverter_por_linha(
    dados: pd.DataFrame,
    valores_normalizados: Iterable[float],
) -> np.ndarray:
    valores = np.asarray(valores_normalizados, dtype=float).reshape(-1)
    if len(valores) != len(dados):
        raise ValueError("Uma previsao normalizada e necessaria por linha.")
    minimo = dados["minimo_treino"].to_numpy(dtype=float)
    maximo = dados["maximo_treino"].to_numpy(dtype=float)
    invertidos = valores * (maximo - minimo) + minimo
    return np.maximum(invertidos, 0.0)


def _series_gluonts(
    base: BaseMensalGlobal,
) -> tuple[dict[str, pd.Series], dict[str, pd.Series], dict[str, list[pd.Period]]]:
    treino: dict[str, pd.Series] = {}
    historico: dict[str, pd.Series] = {}
    origens: dict[str, list[pd.Period]] = {}
    for serie in base.series:
        indice = serie.datas.to_period("M")
        treino[serie.localidade] = pd.Series(
            serie.ghi_modelo[: serie.indice_corte_alvo],
            index=indice[: serie.indice_corte_alvo],
            dtype=float,
        )
        historico[serie.localidade] = pd.Series(
            serie.ghi_modelo,
            index=indice,
            dtype=float,
        )
        alvos = base.teste.loc[
            base.teste["localidade_id"] == serie.localidade_id, "data_alvo"
        ]
        origens[serie.localidade] = [
            pd.Period(data, freq="M") - 1 for data in pd.to_datetime(alvos)
        ]
    return treino, historico, origens


def _mapear_amostras_gluonts(
    base: BaseMensalGlobal,
    previsoes,
) -> np.ndarray:
    """Alinha a ordem localidade-origem do GluonTS a data-localidade da tabela."""

    if not previsoes:
        raise ValueError("O GluonTS nao retornou previsoes.")
    por_chave = {}
    for previsao in previsoes:
        chave = (previsao.localidade, previsao.inicio_previsao)
        if chave in por_chave:
            raise ValueError(f"Previsao GluonTS duplicada para {chave}.")
        por_chave[chave] = np.asarray(previsao.amostras[:, 0], dtype=float)
    n_amostras = len(previsoes[0].amostras)
    if n_amostras < 2:
        raise ValueError("Sao necessarias pelo menos duas amostras probabilisticas.")
    resultado = np.empty((len(base.teste), n_amostras), dtype=float)
    series_por_id = {serie.localidade_id: serie for serie in base.series}
    for posicao, (_, linha) in enumerate(base.teste.iterrows()):
        serie = series_por_id[int(linha["localidade_id"])]
        chave = (serie.localidade, pd.Period(linha["data_alvo"], freq="M"))
        if chave not in por_chave:
            raise ValueError(f"Previsao GluonTS ausente para {chave}.")
        normalizadas = por_chave[chave]
        if normalizadas.shape != (n_amostras,) or not np.isfinite(normalizadas).all():
            raise ValueError(f"Amostras GluonTS invalidas para {chave}.")
        resultado[posicao] = serie.inverter(normalizadas)
    if len(por_chave) != len(base.teste):
        raise ValueError("O GluonTS retornou chaves extras ou cobertura incompleta.")
    return resultado


def _linha_metricas(
    localidade: str,
    modelo: str,
    seed: int,
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> dict[str, object]:
    metricas = calcular_metricas(y_true, y_pred, modelo)
    return {
        "Localidade": localidade,
        "Modelo": modelo,
        "seed": seed,
        "N_teste": len(y_true),
        "MAE_wm2": float(metricas["MAE"]),
        "MSE_wm4": float(metricas["MSE"]),
        "RMSE_wm2": float(metricas["RMSE"]),
        "R2": float(metricas["R2"]),
        "nRMSE_percentual": float(metricas["nRMSE_percentual"]),
    }


def _avaliar_previsao(
    base: BaseMensalGlobal,
    modelo: str,
    seed: int,
    previsao: np.ndarray,
) -> list[dict[str, object]]:
    previsao = np.asarray(previsao, dtype=float).reshape(-1)
    teste = base.teste.reset_index(drop=True)
    if previsao.shape != (len(teste),) or not np.isfinite(previsao).all():
        raise ValueError(f"Previsao principal invalida para {modelo}.")
    linhas = []
    for localidade, grupo in teste.groupby("Localidade", sort=True):
        posicoes = grupo.index.to_numpy()
        linhas.append(
            _linha_metricas(
                localidade,
                modelo,
                seed,
                grupo["y_wm2"].to_numpy(dtype=float),
                previsao[posicoes],
            )
        )
    return linhas


def _resumo_modelos(
    metricas_por_seed: pd.DataFrame,
    metricas_principais: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Resume o ensemble principal e separa sua variacao entre sementes.

    As metricas centrais sao recalculadas sobre a previsao consolidada, nunca
    obtidas pela media de metricas de previsoes diferentes. O desvio entre
    sementes permanece uma informacao de robustez separada.
    """

    colunas_metricas = [
        "MAE_wm2",
        "MSE_wm4",
        "RMSE_wm2",
        "R2",
        "nRMSE_percentual",
    ]
    obrigatorias_seed = {"Localidade", "Modelo", "seed", *colunas_metricas}
    faltantes = sorted(obrigatorias_seed - set(metricas_por_seed.columns))
    if faltantes:
        raise ValueError(f"Colunas ausentes nas metricas por seed: {', '.join(faltantes)}")
    if metricas_principais is None:
        metricas_principais = (
            metricas_por_seed.groupby(["Localidade", "Modelo"], as_index=False)[
                colunas_metricas
            ].mean()
        )
    obrigatorias_principais = {"Localidade", "Modelo", *colunas_metricas}
    faltantes = sorted(obrigatorias_principais - set(metricas_principais.columns))
    if faltantes:
        raise ValueError(f"Colunas ausentes nas metricas principais: {', '.join(faltantes)}")
    if metricas_principais.duplicated(["Localidade", "Modelo"]).any():
        raise ValueError("Metricas principais duplicadas por localidade e modelo.")

    por_seed = (
        metricas_por_seed.groupby(["Modelo", "seed"], as_index=False)[
            ["MAE_wm2", "MSE_wm4", "RMSE_wm2", "R2", "nRMSE_percentual"]
        ]
        .mean()
        .rename(columns={"MAE_wm2": "MAE_macro_wm2"})
    )
    linhas = []
    for modelo, grupo_principal in metricas_principais.groupby("Modelo", sort=False):
        grupo_seed = por_seed.loc[por_seed["Modelo"] == modelo]
        if grupo_seed.empty:
            raise ValueError(f"Nao ha metricas por seed para {modelo}.")
        linhas.append(
            {
                "Modelo": modelo,
                "N_localidades": int(grupo_principal["Localidade"].nunique()),
                "N_sementes": len(grupo_seed),
                "MAE_media_wm2": float(grupo_principal["MAE_wm2"].mean()),
                "MAE_dp_sementes_wm2": (
                    float(grupo_seed["MAE_macro_wm2"].std(ddof=1))
                    if len(grupo_seed) > 1
                    else 0.0
                ),
                "MSE_media_wm4": float(grupo_principal["MSE_wm4"].mean()),
                "RMSE_media_wm2": float(grupo_principal["RMSE_wm2"].mean()),
                "R2_medio": float(grupo_principal["R2"].mean()),
                "nRMSE_medio_percentual": float(
                    grupo_principal["nRMSE_percentual"].mean()
                ),
            }
        )
    return pd.DataFrame(linhas).sort_values("MAE_media_wm2", ignore_index=True)


def _hardware() -> dict[str, object]:
    memoria_kib = None
    caminho_memoria = Path("/proc/meminfo")
    if caminho_memoria.is_file():
        primeira = caminho_memoria.read_text(encoding="utf-8").splitlines()[0]
        memoria_kib = int(primeira.split()[1])
    return {
        "sistema": platform.system(),
        "kernel": platform.release(),
        "arquitetura": platform.machine(),
        "processador": platform.processor(),
        "cpus_logicas": os.cpu_count(),
        "memoria_total_gib": (
            round(memoria_kib / 1024**2, 3) if memoria_kib is not None else None
        ),
        "gpu": "nenhuma; execucao forcada em CPU",
    }


def _registrar_falha(func):
    """Registra uma excecao inclusive durante uma retomada."""

    @wraps(func)
    def protegido(saida, *args, **kwargs):
        pasta = Path(saida)
        try:
            return func(saida, *args, **kwargs)
        except Exception as exc:
            if pasta.is_dir():
                try:
                    _salvar_status(
                        pasta,
                        "falhou",
                        {
                            "tipo_erro": type(exc).__name__,
                            "mensagem": str(exc),
                            "retomavel": True,
                        },
                    )
                except Exception:
                    pass
            raise

    return protegido


@_registrar_falha
def executar_experimento(
    saida: str | Path,
    configuracao: ConfiguracaoExperimento | None = None,
    *,
    retomar: bool = False,
) -> Path:
    """Executa ou retoma o protocolo canônico em uma pasta controlada.

    Somente uma execucao ``completa`` cujo ``status_execucao.json`` esteja em
    ``concluido`` pode alimentar os artigos. Em uma retomada, a configuracao e
    conferida e cada artefato de modelo ja persistido e carregado para refazer
    as previsoes e a consolidacao de maneira deterministica.
    """

    config = configuracao or ConfiguracaoExperimento()
    saida = Path(saida)
    havia_artefatos_anteriores = saida.is_dir() and any(saida.iterdir())
    if saida.exists() and not saida.is_dir():
        raise NotADirectoryError(f"O caminho de saida existe e nao e uma pasta: {saida}")
    if saida.exists() and any(saida.iterdir()) and not retomar:
        raise FileExistsError(
            f"A pasta {saida} ja contem arquivos; use --retomar ou uma nova pasta."
        )
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "modelos").mkdir(exist_ok=True)
    (saida / "logs_treinamento").mkdir(exist_ok=True)
    arquivo_configuracao = saida / "configuracao_execucao.json"
    arquivo_contrato = saida / "contrato_retomada.json"
    configuracao_atual = asdict(config)
    configuracao_atual["sementes"] = list(config.sementes)
    retomada_sem_contrato_anterior = (
        retomar and havia_artefatos_anteriores and not arquivo_configuracao.is_file()
    )
    if retomar and arquivo_configuracao.is_file():
        configuracao_anterior = json.loads(
            arquivo_configuracao.read_text(encoding="utf-8")
        )
        if configuracao_anterior != configuracao_atual:
            raise ValueError(
                "A configuracao da retomada difere da execucao existente. "
                "Use exatamente os mesmos argumentos ou outra pasta de saida."
            )
    arquivos_entrada = _arquivos_entrada_protocolo()
    contrato_atual = _contrato_retomada(configuracao_atual, arquivos_entrada)
    contrato_adotado_em_retomada = (
        retomar and havia_artefatos_anteriores and not arquivo_contrato.is_file()
    )
    if retomar and arquivo_contrato.is_file():
        contrato_anterior = json.loads(arquivo_contrato.read_text(encoding="utf-8"))
        if contrato_anterior != contrato_atual:
            raise ValueError(
                "Dados, codigo ou dependencias mudaram desde o inicio da execucao; "
                "os modelos existentes nao podem ser retomados nesta pasta."
            )
    salvar_json(configuracao_atual, arquivo_configuracao)
    salvar_json(contrato_atual, arquivo_contrato)
    _salvar_status(
        saida,
        "carregando_dados",
        {
            "execucao_retomada": retomar,
            "retomada_sem_contrato_anterior": retomada_sem_contrato_anterior,
            "contrato_adotado_em_retomada": contrato_adotado_em_retomada,
        },
    )

    base = carregar_base_mensal_global(
        contexto=config.contexto,
        train_ratio=config.train_ratio,
        niveis_quantizacao=config.niveis_quantizacao,
    )
    # Base exclusiva para selecao: seus limites numericos terminam antes da
    # validacao. A base final acima pode usar todo o treino de 2020--2023.
    base_selecao = carregar_base_mensal_global(
        contexto=config.contexto,
        train_ratio=config.train_ratio,
        niveis_quantizacao=config.niveis_quantizacao,
        limite_ajuste_transformacao=config.inicio_validacao,
    )
    if not base.janelas[["Localidade", "data_alvo", "particao"]].equals(
        base_selecao.janelas[["Localidade", "data_alvo", "particao"]]
    ):
        raise RuntimeError("As bases de selecao e refit perderam o alinhamento temporal.")
    auditoria = auditar_arquivos_diarios()
    auditoria.to_csv(saida / "auditoria_dados.csv", index=False)
    teste = base.teste.reset_index(drop=True)
    y_teste = teste["y_wm2"].to_numpy(dtype=float)
    previsoes_por_modelo_seed: dict[str, dict[int, np.ndarray]] = {}
    metricas: list[dict[str, object]] = []
    hiperparametros_executados: list[dict[str, object]] = []

    def registrar(modelo: str, seed: int, valores: np.ndarray) -> None:
        arr = np.asarray(valores, dtype=float).reshape(-1)
        if arr.shape != (len(teste),) or not np.isfinite(arr).all():
            raise ValueError(f"Previsao invalida produzida por {modelo}, seed {seed}.")
        previsoes_por_modelo_seed.setdefault(modelo, {})[seed] = arr
        metricas.extend(_avaliar_previsao(base, modelo, seed, arr))

    _salvar_status(saida, "baselines_e_tabulares")
    baselines = prever_baselines_mensais(base)
    nomes_baselines = {
        "Persistencia": "Persistencia",
        "SazonalIngenuo": "Sazonal ingenuo",
        "Climatologia": "Climatologia",
    }
    for nome_codigo, valores in baselines.items():
        registrar(nomes_baselines[nome_codigo], -1, valores)

    for seed in config.sementes:
        caminho_modelo = saida / "modelos" / f"xgboost_global_seed_{seed}.joblib"
        if retomar and caminho_modelo.is_file():
            modelo_xgb = joblib.load(caminho_modelo)
            parametros_xgb = modelo_xgb.get_params()
            if int(parametros_xgb.get("random_state", -1)) != seed:
                raise ValueError(f"XGBoost retomado nao corresponde a seed {seed}.")
            n_estimators = int(parametros_xgb["n_estimators"])
            retomado = True
        else:
            xgb = treinar_xgboost_global(
                base_selecao.treino,
                base.colunas_tabulares,
                seed=seed,
                inicio_validacao=config.inicio_validacao,
                treino_refit=base.treino,
            )
            modelo_xgb = xgb.modelo
            n_estimators = int(xgb.n_estimators)
            salvar_modelo_joblib(modelo_xgb, caminho_modelo)
            retomado = False
        pred_xgb_norm = modelo_xgb.predict(teste.loc[:, base.colunas_tabulares])
        registrar("XGBoost", seed, _inverter_por_linha(teste, pred_xgb_norm))
        hiperparametros_executados.append(
            {
                "Modelo": "XGBoost",
                "seed": seed,
                "n_estimators": n_estimators,
                "retomado": retomado,
            }
        )
        del modelo_xgb

    for seed in config.sementes:
        caminho_modelo = saida / "modelos" / f"mlp_global_seed_{seed}.joblib"
        if retomar and caminho_modelo.is_file():
            mlp = joblib.load(caminho_modelo)
            parametros_mlp = mlp.get_params()
            if int(parametros_mlp.get("mlpregressor__random_state", -1)) != seed:
                raise ValueError(f"MLP retomada nao corresponde a seed {seed}.")
            retomado = True
        else:
            mlp = treinar_mlp_global(base.treino, base.colunas_tabulares, seed=seed)
            salvar_modelo_joblib(mlp, caminho_modelo)
            retomado = False
        pred_norm = mlp.predict(teste.loc[:, base.colunas_tabulares])
        registrar("MLP", seed, _inverter_por_linha(teste, pred_norm))
        hiperparametros_executados.append(
            {
                "Modelo": "MLP",
                "seed": seed,
                "iteracoes_efetivas": int(
                    mlp.named_steps["mlpregressor"].n_iter_
                ),
                "retomado": retomado,
            }
        )
        del mlp

    _salvar_status(saida, "redes_recorrentes")
    datas_treino = pd.to_datetime(base_selecao.treino["data_alvo"])
    mascara_validacao = datas_treino >= pd.Timestamp(config.inicio_validacao)
    if not mascara_validacao.any() or mascara_validacao.all():
        raise ValueError("A janela de validacao Keras precisa dividir o treino.")
    frame_ajuste = base_selecao.treino.loc[~mascara_validacao]
    frame_validacao = base_selecao.treino.loc[mascara_validacao]
    seq_ajuste, aux_ajuste, y_ajuste = matrizes_keras(frame_ajuste, base_selecao)
    seq_valid, aux_valid, y_valid = matrizes_keras(frame_validacao, base_selecao)
    seq_refit, aux_refit, y_refit = matrizes_keras(base.treino, base)
    seq_teste, aux_teste, _ = matrizes_keras(teste, base)
    for tipo, nome_modelo in (
        ("RNN", "RNN"),
        ("LSTM", "LSTM"),
        ("DilatedRNN", "DilatedRNN"),
    ):
        for seed in config.sementes:
            caminho_modelo = (
                saida / "modelos" / f"{nome_modelo.lower()}_global_seed_{seed}.keras"
            )
            if retomar and caminho_modelo.is_file():
                import tensorflow as tf

                # O import registra a celula serializavel antes de restaurar
                # uma DilatedRNN; para RNN/LSTM ele e inofensivo.
                from codigo_fonte.dilated_rnn import DilatedSimpleRNNCell  # noqa: F401

                modelo_rede = tf.keras.models.load_model(caminho_modelo)
                if modelo_rede.name.upper() != tipo.upper():
                    raise ValueError(
                        f"Rede retomada em {caminho_modelo.name} e "
                        f"{modelo_rede.name!r}, nao {tipo!r}."
                    )
                lotes_refit = int(np.ceil(len(seq_refit) / 32))
                iteracoes = int(modelo_rede.optimizer.iterations.numpy())
                epocas_selecionadas = (
                    iteracoes // lotes_refit
                    if lotes_refit and iteracoes % lotes_refit == 0
                    else None
                )
                melhor_val_loss = None
                retomado = True
            else:
                resultado = treinar_rede_global_com_validacao_temporal(
                    tipo,
                    seq_ajuste,
                    aux_ajuste,
                    y_ajuste,
                    seq_valid,
                    aux_valid,
                    y_valid,
                    seed=seed,
                    max_epocas=config.max_epocas_keras,
                    paciencia=config.paciencia_keras,
                    lote=32,
                    unidades=16,
                    unidades_densas=16,
                    taxa_aprendizado=1e-3,
                    sequencia_refit=seq_refit,
                    auxiliares_refit=aux_refit,
                    y_refit=y_refit,
                )
                modelo_rede = resultado.modelo
                epocas_selecionadas = int(resultado.epocas)
                melhor_val_loss = float(resultado.melhor_val_loss)
                salvar_rede_global(modelo_rede, caminho_modelo)
                retomado = False
                del resultado
            pred_norm = prever_rede_global(modelo_rede, seq_teste, aux_teste)
            registrar(nome_modelo, seed, _inverter_por_linha(teste, pred_norm))
            hiperparametros_executados.append(
                {
                    "Modelo": nome_modelo,
                    "seed": seed,
                    "epocas_selecionadas": epocas_selecionadas,
                    "melhor_val_loss": melhor_val_loss,
                    "retomado": retomado,
                }
            )
            _salvar_status(
                saida,
                "redes_recorrentes",
                {"ultimo_modelo_concluido": nome_modelo, "seed": seed},
            )
            del modelo_rede
            try:
                tf.keras.backend.clear_session()
            except NameError:
                pass
            gc.collect()

    # Libera os grafos Keras antes de carregar as duas redes PyTorch.
    try:
        import tensorflow as tf

        tf.keras.backend.clear_session()
    except ImportError:
        pass
    gc.collect()

    _salvar_status(saida, "modelos_probabilisticos_globais")
    series_treino, series_historico, origens = _series_gluonts(base)
    amostras_probabilisticas: dict[str, list[np.ndarray]] = {
        nome: [] for nome in MODELOS_PROBABILISTICOS
    }
    metricas_probabilisticas: list[dict[str, object]] = []
    for nome_modelo, classe in (
        ("DeepNPTS", DeepNPTSGlobalGluonTS),
        ("DeepAR", DeepARGlobalGluonTS),
    ):
        for seed in config.sementes:
            pasta_log = saida / "logs_treinamento" / f"{nome_modelo.lower()}_seed_{seed}"
            kwargs = {
                "context_length": config.contexto,
                "seed": seed,
                "num_samples": config.amostras_probabilisticas_por_semente,
                "numero_localidades_esperado": len(base.series),
                "batch_size": 32,
                "device": "cpu",
                "diretorio_saida": pasta_log,
            }
            if nome_modelo == "DeepNPTS":
                kwargs.update(
                    {
                        "epochs": config.epocas_deepnpts,
                        "num_batches_per_epoch": config.lotes_por_epoca_deepnpts,
                        "learning_rate": 1e-5,
                        "variante": "discreta",
                    }
                )
            else:
                kwargs.update(
                    {
                        "epochs": config.epocas_deepar,
                        "num_batches_per_epoch": config.lotes_por_epoca_deepar,
                        "learning_rate": 1e-3,
                        "num_layers": 2,
                        "hidden_size": 40,
                        "dropout_rate": 0.1,
                        "lags_seq": tuple(range(1, 13)),
                        "scaling": False,
                        # A escala normalizada pode extrapolar abaixo de zero;
                        # o piso fisico e aplicado somente depois da inversao.
                        "nonnegative_pred_samples": False,
                    }
                )
            caminho_modelo = (
                saida / "modelos" / f"{nome_modelo.lower()}_global_seed_{seed}"
            )
            if retomar and caminho_modelo.is_dir():
                modelo = carregar_modelo_global_gluonts(caminho_modelo, device="cpu")
                if modelo.nome_modelo != nome_modelo or modelo.seed != seed:
                    raise ValueError(
                        f"Predictor retomado nao corresponde a {nome_modelo}, seed {seed}."
                    )
                retomado = True
            else:
                modelo = classe(**kwargs).ajustar(series_treino)
                # A serializacao precede a amostragem: se a execucao for
                # interrompida durante as 120 origens, o treino permanece.
                modelo.salvar(caminho_modelo)
                retomado = False
            previsoes = modelo.prever_multiplas_origens(
                series_historico,
                origens,
                num_samples=config.amostras_probabilisticas_por_semente,
                seed=seed,
            )
            amostras_wm2 = _mapear_amostras_gluonts(base, previsoes)
            amostras_probabilisticas[nome_modelo].append(amostras_wm2)
            ponto = np.median(amostras_wm2, axis=1)
            registrar(nome_modelo, seed, ponto)
            for localidade, grupo in teste.groupby("Localidade", sort=True):
                posicoes = grupo.index.to_numpy()
                probabilisticas = calcular_metricas_probabilisticas(
                    grupo["y_wm2"].to_numpy(dtype=float),
                    amostras_wm2[posicoes],
                    nome_modelo,
                    nivel_intervalo=config.nivel_intervalo,
                )
                metricas_probabilisticas.append(
                    {
                        "Localidade": localidade,
                        "Modelo": nome_modelo,
                        "seed": seed,
                        **{k: v for k, v in probabilisticas.items() if k != "Modelo"},
                    }
                )
            hiperparametros_executados.append(
                {
                    "Modelo": nome_modelo,
                    "seed": seed,
                    "epocas": kwargs["epochs"],
                    "lotes_por_epoca": kwargs["num_batches_per_epoch"],
                    "amostras": config.amostras_probabilisticas_por_semente,
                    "retomado": retomado,
                }
            )
            _salvar_status(
                saida,
                "modelos_probabilisticos_globais",
                {"ultimo_modelo_concluido": nome_modelo, "seed": seed},
            )
            del modelo, previsoes
            gc.collect()

    if _contrato_retomada(configuracao_atual, arquivos_entrada) != contrato_atual:
        raise RuntimeError(
            "Dados, codigo ou dependencias mudaram durante os treinamentos; "
            "a consolidacao foi interrompida."
        )
    _salvar_status(saida, "consolidando_resultados")
    metricas_seed_df = pd.DataFrame(metricas)
    metricas_seed_df.to_csv(saida / "metricas_por_localidade_seed.csv", index=False)

    # Primeiro constroi a previsao realmente adotada por cada modelo. Redes
    # pontuais usam a media das sementes; modelos probabilisticos usam a
    # mediana da mistura de todas as amostras. As metricas principais abaixo
    # sao recalculadas nessas previsoes, nao promediadas entre seeds.
    consolidado = teste[
        ["data_alvo", "Localidade", "localidade_id", "y_wm2"]
    ].copy()
    for modelo, por_seed in previsoes_por_modelo_seed.items():
        matriz = np.stack([por_seed[seed] for seed in sorted(por_seed)], axis=1)
        consolidado[modelo] = matriz.mean(axis=1)
    arrays_npz: dict[str, np.ndarray] = {}
    for modelo, blocos in amostras_probabilisticas.items():
        if not blocos:
            raise RuntimeError(f"Nenhuma amostra probabilistica produzida por {modelo}.")
        combinadas = np.concatenate(blocos, axis=1)
        if combinadas.shape[0] != len(teste) or not np.isfinite(combinadas).all():
            raise ValueError(f"Amostras probabilisticas consolidadas invalidas para {modelo}.")
        consolidado[modelo] = np.median(combinadas, axis=1)
        arrays_npz[f"{modelo}_amostras_wm2"] = combinadas
    consolidado.to_csv(saida / "previsoes_consolidadas.csv", index=False)
    np.savez_compressed(saida / "amostras_probabilisticas.npz", **arrays_npz)

    metricas_principais = []
    for modelo in previsoes_por_modelo_seed:
        metricas_principais.extend(
            _avaliar_previsao(
                base,
                modelo,
                -2,
                consolidado[modelo].to_numpy(dtype=float),
            )
        )
    metricas_localidade = pd.DataFrame(metricas_principais).drop(columns="seed")
    metricas_localidade.to_csv(saida / "metricas_por_localidade.csv", index=False)
    resumo = _resumo_modelos(metricas_seed_df, metricas_localidade)
    resumo.to_csv(saida / "metricas_medias_modelos.csv", index=False)
    resumir_metricas_por_modelo(metricas_localidade).to_csv(
        saida / "intervalos_bootstrap_mae.csv", index=False
    )
    comparar_mae_com_referencia(metricas_localidade, referencia="Climatologia").to_csv(
        saida / "comparacoes_mae_climatologia.csv", index=False
    )

    probabilisticas_seed_df = pd.DataFrame(metricas_probabilisticas)
    probabilisticas_seed_df.to_csv(
        saida / "metricas_probabilisticas_por_localidade_seed.csv", index=False
    )
    metricas_probabilisticas_principais = []
    for modelo in MODELOS_PROBABILISTICOS:
        amostras_modelo = arrays_npz[f"{modelo}_amostras_wm2"]
        for localidade, grupo in teste.groupby("Localidade", sort=True):
            posicoes = grupo.index.to_numpy()
            valores = calcular_metricas_probabilisticas(
                grupo["y_wm2"].to_numpy(dtype=float),
                amostras_modelo[posicoes],
                modelo,
                nivel_intervalo=config.nivel_intervalo,
            )
            metricas_probabilisticas_principais.append(
                {"Localidade": localidade, **valores}
            )
    probabilisticas_df = pd.DataFrame(metricas_probabilisticas_principais)
    probabilisticas_df.to_csv(
        saida / "metricas_probabilisticas_por_localidade.csv", index=False
    )
    probabilisticas_resumo = probabilisticas_df.groupby("Modelo", as_index=False).agg(
        N_localidades=("Localidade", "nunique"),
        CRPS_medio_wm2=("CRPS_wm2", "mean"),
        CRPS_dp_localidades_wm2=("CRPS_wm2", "std"),
        PICP_medio_percentual=("PICP_percentual", "mean"),
        MPIW_medio_wm2=("MPIW_wm2", "mean"),
    )
    probabilisticas_resumo.to_csv(
        saida / "metricas_probabilisticas_medias.csv", index=False
    )

    linhas_longas = []
    for modelo, por_seed in previsoes_por_modelo_seed.items():
        for seed, valores in por_seed.items():
            for posicao, valor in enumerate(valores):
                linhas_longas.append(
                    {
                        "data_alvo": teste.loc[posicao, "data_alvo"],
                        "Localidade": teste.loc[posicao, "Localidade"],
                        "Modelo": modelo,
                        "seed": seed,
                        "y_wm2": y_teste[posicao],
                        "y_pred_wm2": valor,
                    }
                )
    pd.DataFrame(linhas_longas).to_csv(
        saida / "previsoes_por_modelo_seed.csv", index=False
    )
    pd.DataFrame(hiperparametros_executados).to_csv(
        saida / "hiperparametros_executados.csv", index=False
    )
    vencedores = (
        metricas_localidade.sort_values(["Localidade", "MAE_wm2"])
        .groupby("Localidade", as_index=False)
        .first()
    )
    vencedores.to_csv(saida / "vencedores_por_localidade.csv", index=False)

    from codigo_fonte.figuras_experimento_canonico import (
        figura_deepnpts_vs_melhor_concorrente,
        figura_intervalo_deepnpts,
        figura_ranking_mae,
        figura_serie_previsoes,
    )

    pasta_figuras = saida / "figuras"
    figura_ranking_mae(resumo, pasta_figuras / "mae_medio_modelos")
    figura_deepnpts_vs_melhor_concorrente(
        metricas_localidade,
        pasta_figuras / "mae_deepnpts_por_localidade",
    )
    localidade_exemplo = "BYD Camacari"
    melhor_comparacao = (
        metricas_localidade.loc[
            (metricas_localidade["Localidade"] == localidade_exemplo)
            & (metricas_localidade["Modelo"] != "DeepNPTS")
        ]
        .sort_values("MAE_wm2")
        .iloc[0]["Modelo"]
    )
    figura_serie_previsoes(
        consolidado,
        localidade_exemplo,
        str(melhor_comparacao),
        pasta_figuras / "previsao_mensal_byd_camacari",
    )
    figura_intervalo_deepnpts(
        consolidado,
        arrays_npz["DeepNPTS_amostras_wm2"],
        localidade_exemplo,
        pasta_figuras / "intervalo_deepnpts_byd_camacari",
    )

    if _contrato_retomada(configuracao_atual, arquivos_entrada) != contrato_atual:
        raise RuntimeError(
            "Dados, codigo ou dependencias mudaram antes do manifesto final."
        )
    salvar_manifesto(
        saida / "manifesto_execucao.json",
        arquivos_entrada=arquivos_entrada,
        configuracao=asdict(config),
        seed=config.sementes[0],
        raiz_projeto=PROJECT_ROOT,
        metadados={
            "hardware": _hardware(),
            "natureza_teste": "retrospectivo_exploratorio",
            "frequencia": "mensal",
            "horizonte_meses": 1,
            "origens_teste": 12,
            "localidades": len(base.series),
            "previsao_pontual_probabilistica": "mediana_das_amostras",
            "previsao_principal_redes": "ensemble_media_sementes",
            "metricas_principais": "recalculadas_na_previsao_consolidada",
            "ajuste_transformacao_selecao": "somente_antes_da_validacao",
            "protocolo_canonico": True,
            "fonte_artigos_atuais": config.modo_execucao == "completa",
            "modo_execucao": config.modo_execucao,
            "execucao_retomada": retomar,
            "retomada_sem_contrato_anterior": retomada_sem_contrato_anterior,
            "contrato_adotado_em_retomada": contrato_adotado_em_retomada,
        },
    )
    _salvar_status(
        saida,
        "concluido",
        {
            "modelo_menor_macro_mae": resumo.iloc[0]["Modelo"],
            "mae_macro_wm2": float(resumo.iloc[0]["MAE_media_wm2"]),
            "fonte_artigos_atuais": config.modo_execucao == "completa",
            "modo_execucao": config.modo_execucao,
            "execucao_retomada": retomar,
        },
    )
    return saida


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Executa ou retoma o protocolo mensal global canonico usado nos artigos."
        ),
        epilog=(
            "A execucao e longa. Resultados smoke validam apenas o codigo; "
            "nao os use como resultado cientifico."
        ),
    )
    parser.add_argument(
        "--confirmar-execucao-longa",
        action="store_true",
        help="Confirma conscientemente o treinamento completo e demorado.",
    )
    parser.add_argument(
        "--retomar",
        action="store_true",
        help="Reutiliza artefatos completos de modelo/semente na pasta de saida.",
    )
    parser.add_argument(
        "--modo",
        choices=("completa", "smoke"),
        default="completa",
        help="Marca explicitamente se a saida e completa ou apenas smoke.",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("resultados/avaliacao_mensal_canonica"),
    )
    parser.add_argument(
        "--sementes",
        default=",".join(map(str, SEMENTES_PADRAO)),
        help="Lista de inteiros separada por virgulas.",
    )
    parser.add_argument("--amostras", type=int, default=500)
    parser.add_argument("--epocas-keras", type=int, default=300)
    parser.add_argument("--epocas-deepnpts", type=int, default=100)
    parser.add_argument("--lotes-deepnpts", type=int, default=100)
    parser.add_argument("--epocas-deepar", type=int, default=100)
    parser.add_argument("--lotes-deepar", type=int, default=50)
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    if not args.confirmar_execucao_longa:
        parser.error(
            "o protocolo canonico nao inicia sem --confirmar-execucao-longa"
        )
    try:
        sementes = tuple(
            int(valor.strip())
            for valor in args.sementes.split(",")
            if valor.strip()
        )
    except ValueError as exc:
        parser.error(f"--sementes deve conter apenas inteiros: {exc}")
    config = ConfiguracaoExperimento(
        modo_execucao=args.modo,
        sementes=sementes,
        amostras_probabilisticas_por_semente=args.amostras,
        max_epocas_keras=args.epocas_keras,
        epocas_deepnpts=args.epocas_deepnpts,
        lotes_por_epoca_deepnpts=args.lotes_deepnpts,
        epocas_deepar=args.epocas_deepar,
        lotes_por_epoca_deepar=args.lotes_deepar,
    )
    destino = executar_experimento(args.saida, config, retomar=args.retomar)
    print(json.dumps({"saida": str(destino), "status": "concluido"}))


if __name__ == "__main__":
    main()
