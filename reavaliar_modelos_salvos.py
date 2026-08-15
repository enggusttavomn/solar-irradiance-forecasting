"""Reavalia cada seed persistida e comprova o ensemble mensal publicado.

O treinamento em lote salva os modelos antes da consolidacao. Este utilitario
permite reconstruir ``metricas_por_seed.csv`` sem treinar novamente e isola
cada localidade em um subprocesso para liberar a memoria nativa do TensorFlow.
"""

from __future__ import annotations

import argparse
import gc
import json
import multiprocessing as mp
import os
from pathlib import Path
import traceback

import joblib
import numpy as np
import pandas as pd

from codigo_fonte.avaliacao import calcular_metricas, desnormalizar_ghi
from codigo_fonte.configuracao import PASTA_MODELOS
from codigo_fonte.features import dividir_treino_teste_temporal
from codigo_fonte.preprocessamento import preparar_serie_temporal
from treinar_todas_localidades import (
    LOCALIDADES,
    carregar_ou_coletar_localidade,
    caminho_resultados_frequencia,
    consolidar_resultados,
    nome_arquivo,
    reconstruir_resultado_localidade,
    salvar_manifesto_execucao,
)


def _carregar_keras_e_prever(caminho: Path, X_test: pd.DataFrame) -> np.ndarray:
    import tensorflow as tf

    tf.keras.backend.clear_session()
    metadados = json.loads(caminho.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    colunas = metadados["sequence_columns"]
    if not colunas or not set(colunas).issubset(X_test.columns):
        raise ValueError(f"Metadados de sequencia invalidos em {caminho.name}.")
    valores = X_test[colunas].to_numpy(dtype=np.float32).reshape(len(X_test), len(colunas), 1)
    modelo = tf.keras.models.load_model(caminho, compile=False)
    previsao = np.asarray(modelo.predict(valores, verbose=0)).ravel()
    del modelo
    tf.keras.backend.clear_session()
    gc.collect()
    return previsao


def reavaliar_localidade(local: dict, repeticoes: int, seed_base: int) -> dict:
    """Reproduz previsoes das seeds e grava checkpoints tabulares auditaveis."""
    frequencia = "mensal"
    resultados_dir = caminho_resultados_frequencia(frequencia)
    slug_local = nome_arquivo(local["nome"])
    serie = carregar_ou_coletar_localidade(local, forcar_download=False)
    preparation = preparar_serie_temporal(
        serie,
        output_path=None,
        frequencia_modelagem=frequencia,
    )
    dados = preparation.dados_modelagem
    X_train, X_test, _, _, _, dados_teste = dividir_treino_teste_temporal(
        dados,
        preparation.feature_columns,
        target_column="ghi_alvo",
        train_ratio=0.8,
    )
    del X_train
    datas = pd.to_datetime(dados_teste["data_alvo"]).reset_index(drop=True)
    y_wm2 = dados_teste["ghi_alvo_original"].reset_index(drop=True)
    pasta_modelos = PASTA_MODELOS / "avaliacao_mensal_corrigida"
    pasta_previsoes = resultados_dir / "previsoes_seeds" / slug_local
    pasta_previsoes.mkdir(parents=True, exist_ok=True)

    especificacoes = [
        ("XGBoost", "xgboost", ".joblib", [seed_base], False),
        ("MLP", "mlp", ".joblib", range(seed_base, seed_base + repeticoes), True),
        ("RNN", "rnn", ".keras", range(seed_base, seed_base + repeticoes), True),
        ("LSTM", "lstm", ".keras", range(seed_base, seed_base + repeticoes), True),
        ("VizinhosHistoricos", "vizinhos_historicos", ".joblib", [seed_base], False),
    ]
    registros = []
    previsoes_por_modelo: dict[str, list[np.ndarray]] = {}
    for nome_modelo, slug_modelo, extensao, sementes, usa_seed_nome in especificacoes:
        previsoes_por_modelo[nome_modelo] = []
        for seed in sementes:
            sufixo_seed = f"_seed{seed}" if usa_seed_nome else ""
            caminho = pasta_modelos / f"{slug_modelo}_{slug_local}{sufixo_seed}{extensao}"
            if not caminho.exists():
                raise FileNotFoundError(f"Modelo salvo ausente: {caminho}")
            if extensao == ".keras":
                previsao_norm = _carregar_keras_e_prever(caminho, X_test)
            else:
                modelo = joblib.load(caminho)
                previsao_norm = np.asarray(modelo.predict(X_test)).ravel()
                del modelo
            previsao_norm = np.clip(previsao_norm, 0, 1)
            previsoes_por_modelo[nome_modelo].append(previsao_norm)
            previsao_wm2 = desnormalizar_ghi(
                previsao_norm,
                preparation.quantization_params,
            )
            metricas = calcular_metricas(
                y_wm2,
                previsao_wm2,
                nome_modelo,
                sufixo="wm2",
            )
            registros.append(
                {
                    "Localidade": local["nome"],
                    "Pais": local["pais"],
                    "Modelo": nome_modelo,
                    "Seed": seed,
                    **metricas,
                }
            )
            pd.DataFrame(
                {
                    "data": datas,
                    "ghi_real_wm2": y_wm2,
                    "ghi_previsto_normalizado": previsao_norm,
                    "ghi_previsto_wm2": previsao_wm2,
                }
            ).to_csv(
                pasta_previsoes / f"previsoes_{slug_modelo}_seed{seed}.csv",
                index=False,
            )

    # A media das seeds deve reproduzir a coluna principal ja publicada.
    consolidadas = pd.read_csv(
        resultados_dir / "previsoes" / slug_local / "previsoes_modelos.csv"
    )
    slugs_colunas = {
        "XGBoost": "xgboost",
        "MLP": "mlp",
        "RNN": "rnn",
        "LSTM": "lstm",
        "VizinhosHistoricos": "vizinhoshistoricos",
    }
    maiores_diferencas = {}
    for nome_modelo, previsoes in previsoes_por_modelo.items():
        ensemble = np.mean(np.vstack(previsoes), axis=0)
        esperado = consolidadas[
            f"ghi_previsto_{slugs_colunas[nome_modelo]}_normalizado"
        ].to_numpy()
        maior_diferenca = float(np.max(np.abs(ensemble - esperado)))
        if maior_diferenca > 2e-6:
            raise ValueError(
                f"Ensemble salvo de {nome_modelo} diverge por {maior_diferenca:.3g}."
            )
        maiores_diferencas[nome_modelo] = maior_diferenca

    pasta_parciais = resultados_dir / "parciais_localidades"
    pasta_parciais.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(registros).to_csv(
        pasta_parciais / f"seeds_{slug_local}.csv",
        index=False,
    )
    return {
        "localidade": local["nome"],
        "registros": len(registros),
        "maiores_diferencas_ensemble": maiores_diferencas,
    }


def _worker(conexao, local: dict, repeticoes: int, seed_base: int) -> None:
    try:
        conexao.send(("ok", reavaliar_localidade(local, repeticoes, seed_base)))
    except BaseException as exc:
        conexao.send(
            (
                "erro",
                {
                    "tipo": type(exc).__name__,
                    "mensagem": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )
        )
    finally:
        conexao.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeticoes", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.repeticoes < 1:
        parser.error("--repeticoes deve ser positivo")

    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    contexto = mp.get_context("spawn")
    for local in LOCALIDADES:
        pai, filho = contexto.Pipe(duplex=False)
        processo = contexto.Process(
            target=_worker,
            args=(filho, local, args.repeticoes, args.seed),
            name=f"auditoria-{nome_arquivo(local['nome'])}",
        )
        processo.start()
        filho.close()
        try:
            status, payload = pai.recv()
        except EOFError as exc:
            processo.join()
            raise RuntimeError(
                f"Auditoria de {local['nome']} terminou sem resposta: {processo.exitcode}."
            ) from exc
        finally:
            pai.close()
        processo.join()
        if status != "ok" or processo.exitcode != 0:
            raise RuntimeError(f"Falha em {local['nome']}: {payload}")
        print(f"[OK] {local['nome']}: {payload['maiores_diferencas_ensemble']}")

    resultados = [reconstruir_resultado_localidade(local, "mensal") for local in LOCALIDADES]
    consolidar_resultados(resultados, caminho_resultados_frequencia("mensal"))
    salvar_manifesto_execucao("mensal", args.repeticoes, args.seed)


if __name__ == "__main__":
    main()
