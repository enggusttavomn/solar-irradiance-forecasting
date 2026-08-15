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
from codigo_fonte.baselines import normalizar_previsoes_fisicas, prever_baselines
from codigo_fonte.configuracao import PASTA_FIGURAS, PASTA_METRICAS, PASTA_MODELOS
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
from codigo_fonte.preprocessamento import carregar_serie_ghi, preparar_serie_temporal
from codigo_fonte.utilitarios import criar_pastas


# Mantem a saida do terminal concentrada nas etapas e metricas do experimento.
warnings.filterwarnings("ignore")


def executar_pipeline(
    data_path: str | Path | None = None,
    gerar_graficos: bool = True,
    frequencia_modelagem: str = "diaria",
) -> dict[str, object]:
    """Executa todas as etapas para um arquivo ou serie localizada automaticamente.

    Args:
        data_path: Arquivo de entrada. Se for ``None``, procura nas pastas padrao.
        gerar_graficos: Permite desativar as figuras em execucoes mais rapidas.
        frequencia_modelagem: ``diaria`` ou ``mensal``.

    Returns:
        Dicionario com metricas, base preparada, previsoes e modelos ajustados.
    """
    # Garante que todas as pastas de saida existam antes de salvar artefatos.
    criar_pastas()
    pasta_metricas = PASTA_METRICAS / frequencia_modelagem
    pasta_figuras = PASTA_FIGURAS / frequencia_modelagem
    pasta_modelos = PASTA_MODELOS / "serie_unica" / frequencia_modelagem
    for pasta in (pasta_metricas, pasta_figuras, pasta_modelos):
        pasta.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"TREINAMENTO PRINCIPAL - PREVISAO {frequencia_modelagem.upper()} DE GHI")
    print("=" * 60)

    print("\n[1/5] Carregando serie de GHI...")
    # A funcao de carga tambem limpa e converte a entrada para frequencia diaria.
    serie_ghi = carregar_serie_ghi(data_path)
    print(f"      Observacoes carregadas: {len(serie_ghi)}")

    print("[2/5] Preparando features temporais...")
    # Normaliza a serie continua, cria as features e alinha o proximo alvo.
    output_features = pasta_metricas / "ghi_features.csv"
    preparation = preparar_serie_temporal(
        serie_ghi,
        output_path=output_features,
        frequencia_modelagem=frequencia_modelagem,
    )
    dados = preparation.dados_modelagem
    feature_columns = preparation.feature_columns

    # O corte e cronologico. O DataFrame de treino completo nao e usado aqui,
    # por isso sua posicao na tupla e recebida por ``_``.
    X_train, X_test, y_train, y_test, dados_treino, dados_teste = dividir_treino_teste_temporal(
        dados,
        feature_columns,
        target_column="ghi_alvo",
        train_ratio=0.8,
    )
    # Os graficos e CSVs devem usar a data prevista, nao a data das features.
    datas_teste = pd.to_datetime(dados_teste["data_alvo"]).reset_index(drop=True)
    y_test_reset = y_test.reset_index(drop=True)

    print("[3/5] Treinando modelos...")
    # Todos recebem exatamente X_train e y_train, tornando a comparacao justa.
    treinadores = {
        "XGBoost": (treinar_xgboost, pasta_modelos / "xgboost_ghi.joblib"),
        "MLP": (treinar_mlp, pasta_modelos / "mlp_ghi.joblib"),
        "RNN": (treinar_rnn, pasta_modelos / "rnn_ghi.keras"),
        "LSTM": (treinar_lstm, pasta_modelos / "lstm_ghi.keras"),
        "VizinhosHistoricos": (
            treinar_vizinhos_historicos,
            pasta_modelos / "vizinhos_historicos_ghi.joblib",
        ),
    }
    modelos = {}
    for nome_modelo, (treinador, _) in treinadores.items():
        print(f"      Treinando {nome_modelo}...")
        modelos[nome_modelo] = treinador(X_train, y_train)

    # Alguns regressores podem extrapolar. O ``clip`` respeita a escala [0, 1].
    predicoes = {
        nome_modelo: pd.Series(modelo.predict(X_test), index=y_test.index).clip(0, 1).reset_index(drop=True)
        for nome_modelo, modelo in modelos.items()
    }
    y_test_original = dados_teste["ghi_alvo_original"].reset_index(drop=True)
    baselines_original = prever_baselines(
        dados_treino,
        dados_teste,
        frequencia=frequencia_modelagem,
    )
    predicoes.update(
        normalizar_previsoes_fisicas(
            baselines_original,
            preparation.quantization_params,
        )
    )
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

    print("[4/5] Salvando modelos, metricas e previsoes...")
    # Modelos e resultados sao salvos antes dos graficos, que podem ser omitidos.
    for nome_modelo, modelo in modelos.items():
        salvar_modelo(modelo, treinadores[nome_modelo][1])

    # A mesma funcao de metricas e aplicada a todos os vetores de previsao.
    metricas = []
    for nome_modelo in predicoes:
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
        metricas.append(metricas_modelo)
    df_metricas = salvar_metricas(metricas, pasta_metricas / "metricas_modelos.csv")
    salvar_previsoes(
        datas_teste,
        y_test_reset,
        predicoes,
        pasta_metricas,
        y_true_original=y_test_original,
        predicoes_original=predicoes_original,
    )

    # A flag existe para ambientes sem interface grafica ou execucoes de teste.
    if gerar_graficos:
        print("[5/5] Gerando graficos...")
        salvar_graficos(datas_teste, y_test_reset, predicoes, pasta_figuras / "normalizado")
        salvar_graficos(
            datas_teste,
            y_test_original,
            predicoes_original,
            pasta_figuras / "wm2",
            y_label=f"GHI medio {frequencia_modelagem} (W/m2)",
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
        "modelos": modelos,
    }


def main() -> dict[str, object]:
    """Le argumentos da linha de comando e chama o pipeline."""
    # ``argparse`` gera automaticamente a ajuda exibida com ``--help``.
    parser = argparse.ArgumentParser(description="Treina XGBoost, MLP, RNN e LSTM para previsao diaria ou mensal de GHI.")
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
    parser.add_argument(
        "--frequencia",
        choices=["diaria", "mensal"],
        default="diaria",
        help="Escala temporal da modelagem: diaria ou mensal.",
    )
    args = parser.parse_args()
    return executar_pipeline(
        args.data_path,
        gerar_graficos=not args.sem_graficos,
        frequencia_modelagem=args.frequencia,
    )


# Este bloco so executa quando o arquivo e chamado diretamente. Em importacoes,
# as funcoes ficam disponiveis sem iniciar um treinamento automaticamente.
if __name__ == "__main__":
    main()
