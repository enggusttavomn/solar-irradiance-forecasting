"""Executavel do pipeline para uma unica serie de GHI.

Este arquivo apenas coordena funcoes dos modulos de ``codigo_fonte``. A ordem
e: carregar, preparar, dividir, treinar, avaliar e salvar. Manter os calculos
nos modulos evita que o script e os notebooks implementem regras diferentes.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pandas as pd

from codigo_fonte.avaliacao import (
    calcular_metricas,
    desnormalizar_ghi,
    salvar_metricas,
    salvar_previsoes,
)
from codigo_fonte.configuracao import PASTA_FIGURAS, PASTA_METRICAS, PASTA_MODELOS
from codigo_fonte.features import dividir_treino_teste_temporal
from codigo_fonte.graficos import salvar_graficos
from codigo_fonte.modelos import salvar_modelo, treinar_mlp, treinar_xgboost
from codigo_fonte.preprocessamento import carregar_serie_ghi, preparar_serie_temporal
from codigo_fonte.utilitarios import criar_pastas


# Mantem a saida do terminal concentrada nas etapas e metricas do experimento.
warnings.filterwarnings("ignore")


def executar_pipeline(data_path: str | Path | None = None, gerar_graficos: bool = True) -> dict[str, object]:
    """Executa todas as etapas para um arquivo ou serie localizada automaticamente.

    Args:
        data_path: Arquivo de entrada. Se for ``None``, procura nas pastas padrao.
        gerar_graficos: Permite desativar as figuras em execucoes mais rapidas.

    Returns:
        Dicionario com metricas, base preparada, previsoes e modelos ajustados.
    """
    # Garante que todas as pastas de saida existam antes de salvar artefatos.
    criar_pastas()

    print("=" * 60)
    print("TREINAMENTO PRINCIPAL - PREVISAO DIARIA DE GHI")
    print("=" * 60)

    print("\n[1/5] Carregando serie de GHI...")
    # A funcao de carga tambem limpa e converte a entrada para frequencia diaria.
    serie_ghi = carregar_serie_ghi(data_path)
    print(f"      Observacoes carregadas: {len(serie_ghi)}")

    print("[2/5] Preparando features temporais...")
    # Quantiza, normaliza, cria as sete features e alinha o alvo de t+1.
    preparation = preparar_serie_temporal(serie_ghi)
    dados = preparation.dados_modelagem
    feature_columns = preparation.feature_columns

    # O corte e cronologico. O DataFrame de treino completo nao e usado aqui,
    # por isso sua posicao na tupla e recebida por ``_``.
    X_train, X_test, y_train, y_test, _, dados_teste = dividir_treino_teste_temporal(
        dados,
        feature_columns,
        target_column="ghi_alvo",
        train_ratio=0.8,
    )
    # Os graficos e CSVs devem usar a data prevista, nao a data das features.
    datas_teste = pd.to_datetime(dados_teste["data_alvo"]).reset_index(drop=True)
    y_test_reset = y_test.reset_index(drop=True)

    print("[3/5] Treinando modelos...")
    # Ambos recebem exatamente X_train e y_train, tornando a comparacao justa.
    xgb_model = treinar_xgboost(X_train, y_train)
    mlp_model = treinar_mlp(X_train, y_train)

    # Alguns regressores podem extrapolar. O ``clip`` respeita a escala [0, 1].
    predicoes = {
        "XGBoost": pd.Series(xgb_model.predict(X_test), index=y_test.index).clip(0, 1).reset_index(drop=True),
        "MLP": pd.Series(mlp_model.predict(X_test), index=y_test.index).clip(0, 1).reset_index(drop=True),
    }
    y_test_original = dados_teste["ghi_alvo_original"].reset_index(drop=True)
    predicoes_original = {
        nome_modelo: desnormalizar_ghi(y_pred, preparation.quantization_params)
        for nome_modelo, y_pred in predicoes.items()
    }

    print("[4/5] Salvando modelos, metricas e previsoes...")
    # Modelos e resultados sao salvos antes dos graficos, que podem ser omitidos.
    salvar_modelo(xgb_model, PASTA_MODELOS / "xgboost_ghi.joblib")
    salvar_modelo(mlp_model, PASTA_MODELOS / "mlp_ghi.joblib")

    # A mesma funcao de metricas e aplicada aos dois vetores de previsao.
    metricas = []
    for nome_modelo in ("XGBoost", "MLP"):
        metricas_modelo = calcular_metricas(
            y_test_reset,
            predicoes[nome_modelo],
            nome_modelo,
            sufixo="normalizado",
        )
        metricas_modelo.update(
            calcular_metricas(
                y_test_original,
                predicoes_original[nome_modelo],
                nome_modelo,
                sufixo="wm2",
            )
        )
        metricas_modelo["MAE"] = metricas_modelo["MAE_normalizado"]
        metricas_modelo["MSE"] = metricas_modelo["MSE_normalizado"]
        metricas_modelo["RMSE"] = metricas_modelo["RMSE_normalizado"]
        metricas_modelo["R2"] = metricas_modelo["R2_normalizado"]
        metricas.append(metricas_modelo)
    df_metricas = salvar_metricas(metricas, PASTA_METRICAS / "metricas_modelos.csv")
    salvar_previsoes(
        datas_teste,
        y_test_reset,
        predicoes,
        PASTA_METRICAS,
        y_true_original=y_test_original,
        predicoes_original=predicoes_original,
    )

    # A flag existe para ambientes sem interface grafica ou execucoes de teste.
    if gerar_graficos:
        print("[5/5] Gerando graficos...")
        salvar_graficos(datas_teste, y_test_reset, predicoes, PASTA_FIGURAS / "normalizado")
        salvar_graficos(
            datas_teste,
            y_test_original,
            predicoes_original,
            PASTA_FIGURAS / "wm2",
            y_label="GHI medio diario (W/m2)",
            titulo_sufixo=" - escala real",
        )
    else:
        print("[5/5] Geracao de graficos ignorada.")

    print("\nMetricas:")
    print(df_metricas.to_string(index=False))
    print("\n[OK] Pipeline finalizado.")

    # O retorno facilita reutilizar o pipeline a partir de outro modulo Python.
    return {
        "metricas": df_metricas,
        "dados_modelagem": dados,
        "predicoes": predicoes,
        "modelos": {"XGBoost": xgb_model, "MLP": mlp_model},
    }


def main() -> dict[str, object]:
    """Le argumentos da linha de comando e chama o pipeline."""
    # ``argparse`` gera automaticamente a ajuda exibida com ``--help``.
    parser = argparse.ArgumentParser(description="Treina XGBoost e MLP para previsao diaria de GHI.")
    parser.add_argument(
        "--data-path",
        type=Path,
        default=None,
        help="Caminho opcional para CSV, Excel ou Parquet com colunas de data e GHI.",
    )
    parser.add_argument(
        "--sem-graficos",
        action="store_true",
        help="Executa o treino sem gerar figuras PNG.",
    )
    args = parser.parse_args()
    return executar_pipeline(args.data_path, gerar_graficos=not args.sem_graficos)


# Este bloco so executa quando o arquivo e chamado diretamente. Em importacoes,
# as funcoes ficam disponiveis sem iniciar um treinamento automaticamente.
if __name__ == "__main__":
    main()
