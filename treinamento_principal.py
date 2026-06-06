"""Pipeline principal para treinar XGBoost e MLP em uma unica serie de GHI."""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pandas as pd

from codigo_fonte.avaliacao import calcular_metricas, salvar_metricas, salvar_previsoes
from codigo_fonte.configuracao import PASTA_FIGURAS, PASTA_METRICAS, PASTA_MODELOS
from codigo_fonte.features import dividir_treino_teste_temporal
from codigo_fonte.graficos import salvar_graficos
from codigo_fonte.modelos import salvar_modelo, treinar_mlp, treinar_xgboost
from codigo_fonte.preprocessamento import carregar_serie_ghi, preparar_serie_temporal
from codigo_fonte.utilitarios import criar_pastas


warnings.filterwarnings("ignore")


def executar_pipeline(data_path: str | Path | None = None, gerar_graficos: bool = True) -> dict[str, object]:
    """Executa preparacao, treino, avaliacao e salvamento dos resultados."""
    criar_pastas()

    print("=" * 60)
    print("TREINAMENTO PRINCIPAL - PREVISAO DIARIA DE GHI")
    print("=" * 60)

    print("\n[1/5] Carregando serie de GHI...")
    serie_ghi = carregar_serie_ghi(data_path)
    print(f"      Observacoes carregadas: {len(serie_ghi)}")

    print("[2/5] Preparando features temporais...")
    preparation = preparar_serie_temporal(serie_ghi)
    dados = preparation.dados_modelagem
    feature_columns = preparation.feature_columns

    X_train, X_test, y_train, y_test, _, dados_teste = dividir_treino_teste_temporal(
        dados,
        feature_columns,
        target_column="ghi_alvo",
        train_ratio=0.8,
    )
    datas_teste = pd.to_datetime(dados_teste["data_alvo"]).reset_index(drop=True)
    y_test_reset = y_test.reset_index(drop=True)

    print("[3/5] Treinando modelos...")
    xgb_model = treinar_xgboost(X_train, y_train)
    mlp_model = treinar_mlp(X_train, y_train)

    predicoes = {
        "XGBoost": pd.Series(xgb_model.predict(X_test), index=y_test.index).clip(0, 1).reset_index(drop=True),
        "MLP": pd.Series(mlp_model.predict(X_test), index=y_test.index).clip(0, 1).reset_index(drop=True),
    }

    print("[4/5] Salvando modelos, metricas e previsoes...")
    salvar_modelo(xgb_model, PASTA_MODELOS / "xgboost_ghi.joblib")
    salvar_modelo(mlp_model, PASTA_MODELOS / "mlp_ghi.joblib")

    metricas = [
        calcular_metricas(y_test_reset, predicoes["XGBoost"], "XGBoost"),
        calcular_metricas(y_test_reset, predicoes["MLP"], "MLP"),
    ]
    df_metricas = salvar_metricas(metricas, PASTA_METRICAS / "metricas_modelos.csv")
    salvar_previsoes(datas_teste, y_test_reset, predicoes, PASTA_METRICAS)

    if gerar_graficos:
        print("[5/5] Gerando graficos...")
        salvar_graficos(datas_teste, y_test_reset, predicoes, PASTA_FIGURAS)
    else:
        print("[5/5] Geracao de graficos ignorada.")

    print("\nMetricas:")
    print(df_metricas.to_string(index=False))
    print("\n[OK] Pipeline finalizado.")

    return {
        "metricas": df_metricas,
        "dados_modelagem": dados,
        "predicoes": predicoes,
        "modelos": {"XGBoost": xgb_model, "MLP": mlp_model},
    }


def main() -> dict[str, object]:
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


if __name__ == "__main__":
    main()
