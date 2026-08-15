"""Redes recorrentes do protocolo mensal global canonico.

RNN e LSTM recebem uma sequencia de meses consecutivos. Atributos derivados,
calendario e identificacao da localidade entram por um ramo auxiliar, nunca
como falsos passos recorrentes. A mesma interface tambem aceita a DilatedRNN
implementada por conexoes recorrentes de salto em :mod:`codigo_fonte.dilated_rnn`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import tempfile

import numpy as np


@dataclass(frozen=True)
class TreinoRedeGlobal:
    """Modelo ajustado e quantidade de epocas escolhida na validacao temporal."""

    modelo: object
    epocas: int
    melhor_val_loss: float


def _tensorflow():
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    # O protocolo de referencia e explicitamente CPU para reduzir variacao
    # entre maquinas. O valor nao fica dependente do ambiente do chamador.
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache-tcc")
    try:
        import tensorflow as tf
    except ImportError as exc:
        raise ImportError("TensorFlow e necessario para RNN, LSTM e DilatedRNN.") from exc
    try:
        tf.config.set_visible_devices([], "GPU")
    except (RuntimeError, ValueError):
        # Uma importacao anterior pode ter inicializado os dispositivos. Nesse
        # caso, CUDA_VISIBLE_DEVICES ainda protege novas execucoes do processo.
        pass
    return tf


def construir_rede_global(
    tipo: str,
    *,
    contexto: int,
    n_auxiliares: int,
    unidades: int = 16,
    unidades_densas: int = 16,
    taxa_aprendizado: float = 1e-3,
):
    """Constroi RNN, LSTM ou DilatedRNN para previsao global pontual."""

    if contexto < 1 or n_auxiliares < 1:
        raise ValueError("contexto e n_auxiliares devem ser positivos.")
    if unidades < 1 or unidades_densas < 1:
        raise ValueError("As quantidades de unidades devem ser positivas.")
    if not np.isfinite(taxa_aprendizado) or taxa_aprendizado <= 0:
        raise ValueError("taxa_aprendizado deve ser positiva e finita.")
    tf = _tensorflow()
    tipo = tipo.upper()
    entrada_sequencia = tf.keras.layers.Input(
        shape=(contexto, 1), name="sequencia_ghi"
    )
    entrada_auxiliar = tf.keras.layers.Input(
        shape=(n_auxiliares,), name="covariaveis"
    )
    if tipo == "RNN":
        representacao = tf.keras.layers.SimpleRNN(
            unidades, activation="tanh", name="simple_rnn"
        )(entrada_sequencia)
    elif tipo == "LSTM":
        representacao = tf.keras.layers.LSTM(
            unidades, activation="tanh", name="lstm"
        )(entrada_sequencia)
    elif tipo == "DILATEDRNN":
        from codigo_fonte.dilated_rnn import DilatedSimpleRNNCell

        representacao = entrada_sequencia
        for indice, dilatacao in enumerate((1, 2, 4)):
            representacao = tf.keras.layers.RNN(
                DilatedSimpleRNNCell(
                    units=unidades,
                    dilation=dilatacao,
                    name=f"dilated_cell_{indice + 1}",
                ),
                return_sequences=indice < 2,
                name=f"dilated_rnn_s{dilatacao}",
            )(representacao)
    else:
        raise ValueError("tipo deve ser RNN, LSTM ou DilatedRNN.")

    combinado = tf.keras.layers.Concatenate(name="fusao")(
        [representacao, entrada_auxiliar]
    )
    x = tf.keras.layers.Dense(
        unidades_densas, activation="relu", name="densa"
    )(combinado)
    # Uma saida linear preserva extrapolacoes. A conversao final para W/m2
    # aplica somente o piso fisico zero, sem winsorizar no intervalo do treino.
    saida = tf.keras.layers.Dense(1, activation="linear", name="previsao")(x)
    modelo = tf.keras.Model([entrada_sequencia, entrada_auxiliar], saida, name=tipo)
    modelo.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=taxa_aprendizado),
        loss="mse",
        metrics=[tf.keras.metrics.MeanAbsoluteError(name="mae")],
    )
    return modelo


def treinar_rede_global_com_validacao_temporal(
    tipo: str,
    sequencia_treino: np.ndarray,
    auxiliares_treino: np.ndarray,
    y_treino: np.ndarray,
    sequencia_validacao: np.ndarray,
    auxiliares_validacao: np.ndarray,
    y_validacao: np.ndarray,
    *,
    seed: int,
    max_epocas: int = 300,
    paciencia: int = 30,
    lote: int = 32,
    unidades: int = 16,
    unidades_densas: int = 16,
    taxa_aprendizado: float = 1e-3,
    verbose: int = 0,
    sequencia_refit: np.ndarray | None = None,
    auxiliares_refit: np.ndarray | None = None,
    y_refit: np.ndarray | None = None,
) -> TreinoRedeGlobal:
    """Seleciona epocas em 2023 e reajusta a rede em todo o treino.

    O conjunto de teste nunca participa da parada antecipada. Depois de obter a
    melhor epoca na janela de validacao cronologica, a rede e reinicializada e
    treinada em todos os exemplos de treino pelo numero selecionado de epocas.
    """

    if not 0 <= seed < 2**32:
        raise ValueError("seed deve pertencer ao intervalo [0, 2**32).")
    if max_epocas < 1 or paciencia < 1 or lote < 1:
        raise ValueError("max_epocas, paciencia e lote devem ser positivos.")

    def validar_bloco(
        nome: str,
        sequencias: np.ndarray,
        auxiliares: np.ndarray,
        alvos: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        seq = np.asarray(sequencias, dtype=np.float32)
        aux = np.asarray(auxiliares, dtype=np.float32)
        y = np.asarray(alvos, dtype=np.float32).reshape(-1)
        if seq.ndim != 3 or seq.shape[2] != 1:
            raise ValueError(f"{nome}: sequencias deve ter forma (n, contexto, 1).")
        if aux.ndim != 2 or len(seq) == 0 or len(seq) != len(aux) or len(seq) != len(y):
            raise ValueError(f"{nome}: sequencias, auxiliares e alvos devem se alinhar.")
        if not all(np.isfinite(valores).all() for valores in (seq, aux, y)):
            raise ValueError(f"{nome}: todas as entradas devem ser finitas.")
        return seq, aux, y

    sequencia_treino, auxiliares_treino, y_treino = validar_bloco(
        "ajuste", sequencia_treino, auxiliares_treino, y_treino
    )
    sequencia_validacao, auxiliares_validacao, y_validacao = validar_bloco(
        "validacao", sequencia_validacao, auxiliares_validacao, y_validacao
    )
    if sequencia_treino.shape[1:] != sequencia_validacao.shape[1:]:
        raise ValueError("A sequencia de validacao difere da sequencia de ajuste.")
    if auxiliares_treino.shape[1] != auxiliares_validacao.shape[1]:
        raise ValueError("As covariaveis de validacao diferem das de ajuste.")

    opcionais = (sequencia_refit, auxiliares_refit, y_refit)
    if any(valor is not None for valor in opcionais) and not all(
        valor is not None for valor in opcionais
    ):
        raise ValueError("Informe conjuntamente sequencia_refit, auxiliares_refit e y_refit.")

    tf = _tensorflow()
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(seed)
    try:
        tf.config.experimental.enable_op_determinism()
    except (AttributeError, RuntimeError):
        pass

    kwargs_modelo = {
        "contexto": int(sequencia_treino.shape[1]),
        "n_auxiliares": int(auxiliares_treino.shape[1]),
        "unidades": unidades,
        "unidades_densas": unidades_densas,
        "taxa_aprendizado": taxa_aprendizado,
    }
    seletor = construir_rede_global(tipo, **kwargs_modelo)
    historico = seletor.fit(
        [sequencia_treino, auxiliares_treino],
        y_treino,
        validation_data=(
            [sequencia_validacao, auxiliares_validacao],
            y_validacao,
        ),
        epochs=max_epocas,
        batch_size=lote,
        shuffle=False,
        callbacks=[
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=paciencia,
                restore_best_weights=True,
            )
        ],
        verbose=verbose,
    )
    perdas = np.asarray(historico.history["val_loss"], dtype=float)
    if perdas.size == 0 or not np.isfinite(perdas).any():
        raise RuntimeError("A validacao temporal nao produziu perda finita.")
    melhor_indice = int(np.nanargmin(perdas))
    epocas = melhor_indice + 1
    melhor_perda = float(perdas[melhor_indice])

    # Repetir a semente faz o modelo final partir da mesma inicializacao que o
    # seletor. As matrizes opcionais de refit podem ter sido recalculadas com a
    # transformacao ajustada em todo o treino.
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(seed)
    modelo = construir_rede_global(tipo, **kwargs_modelo)
    if sequencia_refit is None:
        seq_total = np.concatenate([sequencia_treino, sequencia_validacao], axis=0)
        aux_total = np.concatenate([auxiliares_treino, auxiliares_validacao], axis=0)
        y_total = np.concatenate([y_treino, y_validacao], axis=0)
    else:
        seq_total, aux_total, y_total = validar_bloco(
            "refit", sequencia_refit, auxiliares_refit, y_refit
        )
        if seq_total.shape[1:] != sequencia_treino.shape[1:]:
            raise ValueError("A sequencia de refit difere da usada na selecao.")
        if aux_total.shape[1] != auxiliares_treino.shape[1]:
            raise ValueError("As covariaveis de refit diferem das usadas na selecao.")
    modelo.fit(
        [seq_total, aux_total],
        y_total,
        epochs=epocas,
        batch_size=lote,
        shuffle=False,
        verbose=verbose,
    )
    return TreinoRedeGlobal(modelo=modelo, epocas=epocas, melhor_val_loss=melhor_perda)


def prever_rede_global(
    modelo,
    sequencias: np.ndarray,
    auxiliares: np.ndarray,
) -> np.ndarray:
    """Produz previsoes pontuais normalizadas."""

    return np.asarray(
        modelo.predict([sequencias, auxiliares], verbose=0), dtype=float
    ).reshape(-1)


def salvar_rede_global(modelo, caminho: str | Path) -> None:
    """Salva um arquivo Keras por substituicao atomica."""

    caminho = Path(caminho)
    if caminho.suffix != ".keras":
        raise ValueError("Redes globais devem ser salvas com extensao .keras.")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{caminho.stem}-",
        suffix=".keras",
        dir=caminho.parent,
        delete=False,
    ) as arquivo:
        temporario = Path(arquivo.name)
    temporario.unlink(missing_ok=True)
    try:
        modelo.save(temporario)
        temporario.replace(caminho)
    finally:
        temporario.unlink(missing_ok=True)


__all__ = [
    "TreinoRedeGlobal",
    "construir_rede_global",
    "prever_rede_global",
    "salvar_rede_global",
    "treinar_rede_global_com_validacao_temporal",
]
