"""Gera e exporta as figuras do protocolo mensal global canônico.

Saidas ``smoke`` ou parciais sao rejeitadas. Por padrao, o comando grava na
pasta auditavel de resultados; uma exportacao explicita copia apenas os quatro
PNG necessarios aos artigos e pode atualizar arquivos de mesmo nome.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from codigo_fonte.figuras_experimento_canonico import (
    figura_deepnpts_vs_melhor_concorrente,
    figura_intervalo_deepnpts,
    figura_ranking_mae,
    figura_serie_previsoes,
)


ARQUIVOS_OBRIGATORIOS = (
    "metricas_medias_modelos.csv",
    "metricas_por_localidade.csv",
    "previsoes_consolidadas.csv",
    "amostras_probabilisticas.npz",
    "manifesto_execucao.json",
    "status_execucao.json",
)


def validar_execucao_concluida(pasta_resultados: str | Path) -> Path:
    """Valida status, modo e artefatos antes de qualquer figura."""

    pasta = Path(pasta_resultados)
    if not pasta.is_dir():
        raise FileNotFoundError(f"Pasta de resultados inexistente: {pasta}")
    faltantes = [nome for nome in ARQUIVOS_OBRIGATORIOS if not (pasta / nome).is_file()]
    if faltantes:
        raise FileNotFoundError(
            "Execucao incompleta; arquivos ausentes: " + ", ".join(faltantes)
        )
    status = json.loads((pasta / "status_execucao.json").read_text(encoding="utf-8"))
    if status.get("etapa") != "concluido":
        raise RuntimeError(
            f"A execucao ainda nao foi concluida (etapa={status.get('etapa')!r})."
        )
    manifesto = json.loads(
        (pasta / "manifesto_execucao.json").read_text(encoding="utf-8")
    )
    configuracao = manifesto.get("configuracao", {})
    metadados = manifesto.get("metadados", {})
    if configuracao.get("modo_execucao") != "completa":
        raise RuntimeError("Figuras cientificas nao podem ser geradas de uma saida smoke.")
    if metadados.get("protocolo_canonico") is not True:
        raise RuntimeError("O manifesto nao identifica o protocolo canonico esperado.")
    if metadados.get("fonte_artigos_atuais") is not True:
        raise RuntimeError("Metadado fonte_artigos_atuais ausente ou inconsistente.")
    return pasta


def gerar(
    pasta_resultados: str | Path,
    pasta_exportacao: str | Path | None = None,
) -> list[Path]:
    """Gera figuras canônicas e, se solicitado, exporta os PNG dos artigos."""

    pasta = validar_execucao_concluida(pasta_resultados)
    resumo = pd.read_csv(pasta / "metricas_medias_modelos.csv")
    localidades = pd.read_csv(pasta / "metricas_por_localidade.csv")
    previsoes = pd.read_csv(pasta / "previsoes_consolidadas.csv")
    with np.load(pasta / "amostras_probabilisticas.npz") as arquivo:
        if "DeepNPTS_amostras_wm2" not in arquivo:
            raise KeyError("Amostras DeepNPTS ausentes no arquivo NPZ.")
        amostras = np.asarray(arquivo["DeepNPTS_amostras_wm2"], dtype=float)

    destino = pasta / "figuras"
    localidade = "BYD Camacari"
    candidatas = localidades.loc[
        (localidades["Localidade"] == localidade)
        & (localidades["Modelo"] != "DeepNPTS")
    ].sort_values("MAE_wm2")
    if candidatas.empty:
        raise ValueError(f"Nao ha concorrente para a localidade {localidade}.")
    comparacao = str(candidatas.iloc[0]["Modelo"])

    artefatos: list[Path] = []
    artefatos.extend(
        figura_ranking_mae(
            resumo, destino / "mae_medio_modelos"
        )
    )
    artefatos.extend(
        figura_deepnpts_vs_melhor_concorrente(
            localidades,
            destino / "mae_deepnpts_por_localidade",
        )
    )
    artefatos.extend(
        figura_serie_previsoes(
            previsoes,
            localidade,
            comparacao,
            destino / "previsao_mensal_byd_camacari",
        )
    )
    artefatos.extend(
        figura_intervalo_deepnpts(
            previsoes,
            amostras,
            localidade,
            destino / "intervalo_deepnpts_byd_camacari",
        )
    )

    if pasta_exportacao is not None:
        exportacao = Path(pasta_exportacao).resolve()
        exportacao.mkdir(parents=True, exist_ok=True)
        for caminho in (item for item in artefatos if item.suffix.lower() == ".png"):
            destino_exportado = exportacao / caminho.name
            # ``copyfile`` evita tentar preservar metadados em volumes montados
            # pelo editor, nos quais ``copystat`` pode ser recusado mesmo quando
            # o conteúdo do arquivo pode ser atualizado normalmente.
            shutil.copyfile(caminho, destino_exportado)
    return artefatos


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Gera figuras do protocolo global canonico somente depois de uma "
            "execucao completa e concluida."
        )
    )
    parser.add_argument(
        "--resultados",
        type=Path,
        default=Path("resultados/avaliacao_mensal_canonica"),
    )
    parser.add_argument(
        "--exportar-para",
        type=Path,
        default=None,
        help="Copia os quatro PNG para a pasta indicada, atualizando nomes iguais.",
    )
    args = parser.parse_args()
    for caminho in gerar(args.resultados, args.exportar_para):
        print(caminho)


if __name__ == "__main__":
    main()
