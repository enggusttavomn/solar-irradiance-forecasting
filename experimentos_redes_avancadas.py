"""Experimentos LEGADOS com candidatos avancados de serie temporal.

Este script nao altera a avaliacao mensal corrigida. Sua rodada historica nao
usa o protocolo publicavel atual e NAO PODE ser citada no TCC, em artigo ou em
congresso. Uma nova execucao exige a flag explicita de aceite e grava resultados
em uma pasta separada:

    resultados/experimentos_redes_avancadas/

Modelos avaliados:
- DilatedRNN: rede recorrente multiescala com subamostragens dilatadas.
- DeepAR_exp: aproximacao probabilistica autoregressiva com LSTM e perda
  Gaussiana; nao e a implementacao canonica.
- VizinhosHistoricos_aprox: suavizador nao parametrico por vizinhos historicos
  ponderados por similaridade e recencia; nao e DeepNPTS.

O pipeline opcional com DeepAR e DeepNPTS canonicos do GluonTS esta em outro
modulo e ainda nao possui resultados completos validados para publicacao.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from codigo_fonte.avaliacao import calcular_metricas, desnormalizar_ghi, salvar_previsoes
from codigo_fonte.configuracao import PASTA_DADOS_BRUTOS, PASTA_RESULTADOS
from codigo_fonte.features import dividir_treino_teste_temporal
from codigo_fonte.localidades_ev import LOCALIDADES_EV
from codigo_fonte.preprocessamento import preparar_serie_temporal


RESULTADOS_EXPERIMENTOS = PASTA_RESULTADOS / "experimentos_redes_avancadas"
FREQUENCIAS_VALIDAS = {"diaria", "mensal"}
AVISO_LEGADO = (
    "Experimento legado e nao comparavel ao resultado publicavel. "
    "E proibido usar suas saidas no TCC, em artigo ou em congresso."
)


def nome_arquivo(local: str) -> str:
    """Converte o nome legivel da localidade para o padrao dos CSVs."""
    return local.lower().replace(" ", "_").replace("-", "_")


def carregar_csv_localidade(local: dict) -> pd.DataFrame:
    """Carrega o CSV bruto oficial de uma localidade."""
    caminho = PASTA_DADOS_BRUTOS / "localidades_ev" / f"{nome_arquivo(local['nome'])}.csv"
    if not caminho.exists():
        raise FileNotFoundError(f"CSV bruto nao encontrado: {caminho}")
    return pd.read_csv(caminho)


def tensorflow():
    """Importa TensorFlow apenas quando um modelo Keras for treinado."""
    try:
        import tensorflow as tf
    except ImportError as exc:
        raise ImportError(
            "TensorFlow nao esta instalado neste ambiente. Instale as dependencias "
            "com `pip install -r requirements.txt` para rodar DilatedRNN e DeepAR."
        ) from exc
    return tf


class KerasExperimentalRegressor:
    """Base pequena para modelos Keras usados so nos experimentos."""

    nome_modelo = "KerasExperimental"

    def __init__(
        self,
        units: int = 32,
        dense_units: int = 16,
        epochs: int = 80,
        batch_size: int = 32,
        learning_rate: float = 0.001,
        validation_split: float = 0.15,
        random_state: int = 42,
        verbose: int = 0,
    ) -> None:
        self.units = units
        self.dense_units = dense_units
        self.epochs = epochs
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.validation_split = validation_split
        self.random_state = random_state
        self.verbose = verbose
        self.model_ = None
        self.n_features_in_: int | None = None

    @staticmethod
    def _reshape(X: pd.DataFrame | np.ndarray) -> np.ndarray:
        valores = np.asarray(X, dtype=np.float32)
        if valores.ndim != 2:
            raise ValueError("A entrada deve ser uma matriz 2D.")
        return valores.reshape((valores.shape[0], valores.shape[1], 1))

    def _build_model(self, tf, n_features: int):
        raise NotImplementedError

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series) -> "KerasExperimentalRegressor":
        tf = tensorflow()
        tf.keras.utils.set_random_seed(self.random_state)
        X_seq = self._reshape(X_train)
        y_array = np.asarray(y_train, dtype=np.float32)
        self.n_features_in_ = X_seq.shape[1]
        self.model_ = self._build_model(tf, self.n_features_in_)

        callbacks = []
        if len(X_seq) >= 50 and self.validation_split > 0:
            callbacks.append(
                tf.keras.callbacks.EarlyStopping(
                    monitor="val_loss",
                    patience=10,
                    restore_best_weights=True,
                )
            )

        self.model_.fit(
            X_seq,
            y_array,
            epochs=self.epochs,
            batch_size=self.batch_size,
            validation_split=self.validation_split if callbacks else 0.0,
            shuffle=False,
            callbacks=callbacks,
            verbose=self.verbose,
        )
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        if self.model_ is None:
            raise RuntimeError("O modelo precisa ser treinado antes da previsao.")
        pred = self.model_.predict(self._reshape(X_test), verbose=0)
        return np.asarray(pred).reshape((len(X_test), -1))[:, 0]


class DilatedRNNRegressor(KerasExperimentalRegressor):
    """RNN multiescala com entradas dilatadas por fatores 1, 2 e 4."""

    nome_modelo = "DilatedRNN"

    def _build_model(self, tf, n_features: int):
        entrada = tf.keras.layers.Input(shape=(n_features, 1))
        ramos = []
        for fator in (1, 2, 4):
            ramo = tf.keras.layers.Lambda(lambda x, f=fator: x[:, ::f, :])(entrada)
            ramo = tf.keras.layers.SimpleRNN(self.units, activation="tanh")(ramo)
            ramos.append(ramo)
        x = tf.keras.layers.Concatenate()(ramos) if len(ramos) > 1 else ramos[0]
        x = tf.keras.layers.Dense(self.dense_units, activation="relu")(x)
        saida = tf.keras.layers.Dense(1, activation="sigmoid")(x)
        model = tf.keras.Model(entrada, saida)
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=self.learning_rate),
            loss="mse",
        )
        return model


class DeepARExperimentalRegressor(KerasExperimentalRegressor):
    """Aproximacao DeepAR: LSTM probabilistica com media e desvio previstos."""

    nome_modelo = "DeepAR_exp"

    def _build_model(self, tf, n_features: int):
        entrada = tf.keras.layers.Input(shape=(n_features, 1))
        x = tf.keras.layers.LSTM(self.units, activation="tanh")(entrada)
        x = tf.keras.layers.Dense(self.dense_units, activation="relu")(x)
        saida = tf.keras.layers.Dense(2)(x)

        def gaussian_nll(y_true, y_pred):
            media = tf.keras.activations.sigmoid(y_pred[:, :1])
            sigma = tf.nn.softplus(y_pred[:, 1:]) + 1e-4
            y_true = tf.reshape(y_true, (-1, 1))
            return tf.reduce_mean(
                0.5 * tf.math.log(tf.square(sigma))
                + 0.5 * tf.square((y_true - media) / sigma)
            )

        model = tf.keras.Model(entrada, saida)
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=self.learning_rate),
            loss=gaussian_nll,
        )
        return model

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        if self.model_ is None:
            raise RuntimeError("O modelo precisa ser treinado antes da previsao.")
        pred = self.model_.predict(self._reshape(X_test), verbose=0)
        return 1 / (1 + np.exp(-pred[:, 0]))


class VizinhosHistoricosApproxRegressor:
    """Suavizador por vizinhos historicos para teste exploratorio.

    A previsao e uma media ponderada dos alvos historicos. Os pesos combinam
    similaridade entre o vetor de features atual e exemplos de treino com um
    fator de recencia. O modelo nao usa TensorFlow e serve como referencia
    experimental de baixo custo. Ele nao implementa DeepNPTS.
    """

    nome_modelo = "VizinhosHistoricos_aprox"

    def __init__(self, k: int = 80, temperature: float = 0.08, recency_decay: float = 0.995):
        self.k = k
        self.temperature = temperature
        self.recency_decay = recency_decay
        self.X_train_: np.ndarray | None = None
        self.y_train_: np.ndarray | None = None
        self.recency_weights_: np.ndarray | None = None

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
    ) -> "VizinhosHistoricosApproxRegressor":
        self.X_train_ = np.asarray(X_train, dtype=np.float32)
        self.y_train_ = np.asarray(y_train, dtype=np.float32)
        n = len(self.y_train_)
        idade = np.arange(n - 1, -1, -1, dtype=np.float32)
        self.recency_weights_ = np.power(self.recency_decay, idade)
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        if self.X_train_ is None or self.y_train_ is None or self.recency_weights_ is None:
            raise RuntimeError("O modelo precisa ser treinado antes da previsao.")

        X_test_array = np.asarray(X_test, dtype=np.float32)
        previsoes = []
        for linha in X_test_array:
            distancias = np.linalg.norm(self.X_train_ - linha, axis=1)
            k = min(self.k, len(distancias))
            vizinhos = np.argpartition(distancias, k - 1)[:k]
            pesos = np.exp(-distancias[vizinhos] / self.temperature)
            pesos = pesos * self.recency_weights_[vizinhos]
            if np.isclose(pesos.sum(), 0.0):
                previsoes.append(float(np.mean(self.y_train_[vizinhos])))
            else:
                previsoes.append(float(np.average(self.y_train_[vizinhos], weights=pesos)))
        return np.asarray(previsoes, dtype=np.float32)


@dataclass
class ResultadoExperimento:
    metricas: dict[str, float | str]
    predicao_normalizada: pd.Series
    predicao_wm2: pd.Series


def criar_modelos_experimentais() -> dict[str, object]:
    """Instancia modelos candidatos para uma rodada independente."""
    return {
        "DilatedRNN": DilatedRNNRegressor(),
        "DeepAR_exp": DeepARExperimentalRegressor(),
        "VizinhosHistoricos_aprox": VizinhosHistoricosApproxRegressor(),
    }


def preparar_base_experimento(local: dict, frequencia: str):
    """Prepara X/y/datas usando exatamente o mesmo contrato do pipeline oficial."""
    serie = carregar_csv_localidade(local)
    preparation = preparar_serie_temporal(
        serie,
        output_path=None,
        frequencia_modelagem=frequencia,
    )
    dados = preparation.dados_modelagem
    X_train, X_test, y_train, y_test, _, dados_teste = dividir_treino_teste_temporal(
        dados,
        preparation.feature_columns,
        target_column="ghi_alvo",
        train_ratio=0.8,
    )
    return preparation, X_train, X_test, y_train, y_test, dados_teste


def avaliar_modelo_experimental(
    nome_modelo: str,
    modelo,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    y_test_original: pd.Series,
    normalization_params: dict[str, float],
) -> ResultadoExperimento:
    """Treina, preve e calcula metricas de um modelo experimental."""
    modelo.fit(X_train, y_train)
    y_pred = pd.Series(modelo.predict(X_test), index=y_test.index).clip(0, 1).reset_index(drop=True)
    y_pred_original = desnormalizar_ghi(y_pred, normalization_params)
    metricas = calcular_metricas(
        y_test.reset_index(drop=True),
        y_pred,
        nome_modelo,
        sufixo="normalizado",
    )
    metricas.update(
        calcular_metricas(
            y_test_original.reset_index(drop=True),
            y_pred_original,
            nome_modelo,
            sufixo="wm2",
        )
    )
    metricas["MAE"] = metricas["MAE_normalizado"]
    metricas["MSE"] = metricas["MSE_normalizado"]
    metricas["RMSE"] = metricas["RMSE_normalizado"]
    metricas["R2"] = metricas["R2_normalizado"]
    return ResultadoExperimento(metricas, y_pred, y_pred_original)


def carregar_metricas_referencia(frequencia: str) -> pd.DataFrame:
    """Le apenas a avaliacao mensal corrigida, quando houver comparacao.

    Nao existe uma referencia diaria com o mesmo nivel de auditoria; portanto,
    experimentos diarios nao recebem uma tabela rotulada como comparacao
    oficial. Mesmo no caso mensal, a tabela e somente diagnostica e nao autoriza
    combinar protocolos em publicacoes.
    """
    if frequencia not in FREQUENCIAS_VALIDAS:
        raise ValueError("frequencia deve ser 'diaria' ou 'mensal'.")
    if frequencia == "diaria":
        return pd.DataFrame()
    caminho = PASTA_RESULTADOS / "avaliacao_mensal_corrigida" / "metricas_geral.csv"
    if not caminho.exists():
        return pd.DataFrame()
    return pd.read_csv(caminho)


def rodar_experimentos(
    frequencias: Iterable[str],
    localidades: Iterable[dict],
    continuar_em_erro: bool = True,
    aceitar_experimento_legado: bool = False,
) -> pd.DataFrame:
    """Executa modelos legados somente depois de um aceite explicito."""
    if not aceitar_experimento_legado:
        raise RuntimeError(
            f"{AVISO_LEGADO} Informe aceitar_experimento_legado=True "
            "conscientemente."
        )
    RESULTADOS_EXPERIMENTOS.mkdir(parents=True, exist_ok=True)
    (RESULTADOS_EXPERIMENTOS / "AVISO_NAO_PUBLICAR.txt").write_text(
        f"{AVISO_LEGADO}\n",
        encoding="utf-8",
    )
    print(f"AVISO: {AVISO_LEGADO}")
    registros_metricas = []
    registros_status = []

    for frequencia in frequencias:
        if frequencia not in FREQUENCIAS_VALIDAS:
            raise ValueError("frequencia deve ser 'diaria' ou 'mensal'.")
        pasta_freq = RESULTADOS_EXPERIMENTOS / frequencia
        pasta_freq.mkdir(parents=True, exist_ok=True)

        for local in localidades:
            nome_local = local["nome"]
            print(f"\n[{frequencia}] {nome_local}")
            preparation, X_train, X_test, y_train, y_test, dados_teste = preparar_base_experimento(
                local,
                frequencia,
            )
            datas_teste = pd.to_datetime(dados_teste["data_alvo"]).reset_index(drop=True)
            y_test_original = dados_teste["ghi_alvo_original"].reset_index(drop=True)
            predicoes = {}
            predicoes_original = {}

            for nome_modelo, modelo in criar_modelos_experimentais().items():
                print(f"  Treinando {nome_modelo}...")
                try:
                    resultado = avaliar_modelo_experimental(
                        nome_modelo,
                        modelo,
                        X_train,
                        X_test,
                        y_train,
                        y_test,
                        y_test_original,
                        preparation.normalization_params,
                    )
                except Exception as exc:
                    registros_status.append(
                        {
                            "Frequencia": frequencia,
                            "Localidade": nome_local,
                            "Modelo": nome_modelo,
                            "Status": "erro",
                            "Mensagem": str(exc),
                        }
                    )
                    print(f"    [ERRO] {exc}")
                    if continuar_em_erro:
                        continue
                    raise

                metricas = dict(resultado.metricas)
                metricas["Frequencia"] = frequencia
                metricas["Localidade"] = nome_local
                metricas["Pais"] = local["pais"]
                metricas["Lat"] = local["lat"]
                metricas["Lon"] = local["lon"]
                registros_metricas.append(metricas)
                registros_status.append(
                    {
                        "Frequencia": frequencia,
                        "Localidade": nome_local,
                        "Modelo": nome_modelo,
                        "Status": "ok",
                        "Mensagem": "",
                    }
                )
                predicoes[nome_modelo] = resultado.predicao_normalizada
                predicoes_original[nome_modelo] = resultado.predicao_wm2

            if predicoes:
                salvar_previsoes(
                    datas_teste,
                    y_test.reset_index(drop=True),
                    predicoes,
                    pasta_freq / "previsoes" / nome_arquivo(nome_local),
                    y_true_original=y_test_original,
                    predicoes_original=predicoes_original,
                )

        df_metricas = pd.DataFrame(registros_metricas)
        if not df_metricas.empty:
            df_freq = df_metricas[df_metricas["Frequencia"] == frequencia]
            df_freq.to_csv(pasta_freq / "metricas_experimentos.csv", index=False)

            referencia = carregar_metricas_referencia(frequencia)
            if not referencia.empty:
                referencia = referencia.copy()
                referencia = referencia[
                    referencia["Localidade"].isin(df_freq["Localidade"].unique())
                ]
                referencia["Frequencia"] = frequencia
                referencia["Origem"] = "avaliacao_mensal_corrigida"
                df_comp = df_freq.copy()
                df_comp["Origem"] = "experimento_legado"
                colunas_comuns = [
                    col for col in df_comp.columns if col in referencia.columns
                ]
                pd.concat(
                    [referencia[colunas_comuns], df_comp[colunas_comuns]],
                    ignore_index=True,
                ).to_csv(
                    pasta_freq / "comparacao_com_avaliacao_mensal_corrigida.csv",
                    index=False,
                )

    df_status = pd.DataFrame(registros_status)
    if not df_status.empty:
        df_status.to_csv(RESULTADOS_EXPERIMENTOS / "status_execucao.csv", index=False)

    df_metricas = pd.DataFrame(registros_metricas)
    if not df_metricas.empty:
        df_metricas.to_csv(RESULTADOS_EXPERIMENTOS / "metricas_experimentos_todas.csv", index=False)
    return df_metricas


def selecionar_localidades(nomes: list[str] | None) -> list[dict]:
    """Filtra localidades por nome; sem filtro, usa todas."""
    if not nomes:
        return LOCALIDADES_EV
    nomes_normalizados = {nome.casefold() for nome in nomes}
    selecionadas = [local for local in LOCALIDADES_EV if local["nome"].casefold() in nomes_normalizados]
    faltantes = sorted(nomes_normalizados - {local["nome"].casefold() for local in selecionadas})
    if faltantes:
        raise ValueError(f"Localidades nao encontradas: {', '.join(faltantes)}")
    return selecionadas


def main() -> pd.DataFrame:
    parser = argparse.ArgumentParser(
        description=(
            "Roda experimento LEGADO com DilatedRNN, DeepAR experimental e "
            "VizinhosHistoricos_aprox. Suas saidas nao podem ser publicadas."
        ),
        epilog=AVISO_LEGADO,
    )
    parser.add_argument(
        "--aceitar-experimento-legado",
        action="store_true",
        help=(
            "Confirma que a rodada e apenas diagnostica e que seus resultados "
            "nao serao usados em TCC, artigo ou congresso."
        ),
    )
    parser.add_argument(
        "--frequencia",
        choices=["diaria", "mensal", "ambas"],
        default="diaria",
        help="Escala temporal testada.",
    )
    parser.add_argument(
        "--localidade",
        action="append",
        help=(
            "Nome exato de uma localidade. Pode ser informado mais de uma vez. "
            "Sem este argumento, roda todas."
        ),
    )
    parser.add_argument(
        "--parar-em-erro",
        action="store_true",
        help="Interrompe a execucao no primeiro erro de modelo.",
    )
    args = parser.parse_args()
    if not args.aceitar_experimento_legado:
        parser.error(
            "a execucao foi bloqueada: informe --aceitar-experimento-legado "
            "depois de ler o aviso de nao publicacao"
        )

    frequencias = ["diaria", "mensal"] if args.frequencia == "ambas" else [args.frequencia]
    localidades = selecionar_localidades(args.localidade)
    return rodar_experimentos(
        frequencias=frequencias,
        localidades=localidades,
        continuar_em_erro=not args.parar_em_erro,
        aceitar_experimento_legado=True,
    )


if __name__ == "__main__":
    main()
