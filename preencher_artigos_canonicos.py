"""Preenche os manuscritos LaTeX com os resultados canônicos consolidados.

O script evita transcrição manual de tabelas e só produz os arquivos oficiais
quando a execução indicada possui status e manifesto de conclusão.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

import numpy as np
import pandas as pd


RAIZ_REPOSITORIO = Path(__file__).resolve().parent

MODELOS_TOKENS = {
    "Persistencia": "PERSISTENCIA",
    "Sazonal ingenuo": "SAZONAL",
    "Climatologia": "CLIMATOLOGIA",
    "XGBoost": "XGBOOST",
    "MLP": "MLP",
    "RNN": "RNN",
    "LSTM": "LSTM",
    "DilatedRNN": "DILATEDRNN",
    "DeepAR": "DEEPAR",
    "DeepNPTS": "DEEPNPTS",
}

MODELOS_APRENDIDOS = (
    "XGBoost",
    "MLP",
    "RNN",
    "LSTM",
    "DilatedRNN",
    "DeepAR",
    "DeepNPTS",
)
MODELOS_PROBABILISTICOS = ("DeepNPTS", "DeepAR")
SEMENTES_ARTIGOS = (11, 23, 42, 67, 89)
MODELOS_EXIBICAO = {
    "Persistencia": "Persistência",
    "Sazonal ingenuo": "Sazonal ingênuo",
    **{
        modelo: modelo
        for modelo in MODELOS_TOKENS
        if modelo not in {"Persistencia", "Sazonal ingenuo"}
    },
}

LOCALIDADES = {
    "BMW San Luis Potosi": ("BMW", "BMW San Luis Potosí"),
    "BYD Camacari": ("BYD", "BYD Camaçari"),
    "Ford Rouge Electric Vehicle Center": (
        "FORD",
        "Ford Rouge Electric Vehicle Center",
    ),
    "GM Factory Zero": ("GM", "GM Factory Zero"),
    "Hyundai Metaplant Georgia": ("HYUNDAI", "Hyundai Metaplant Georgia"),
    "Lucid AMP 1 Casa Grande": ("LUCID", "Lucid AMP 1 Casa Grande"),
    "Rivian Normal": ("RIVIAN", "Rivian Normal"),
    "Tesla Fremont Factory": ("FREMONT", "Tesla Fremont Factory"),
    "Tesla Gigafactory Nevada": ("NEVADA", "Tesla Gigafactory Nevada"),
    "Tesla Gigafactory Texas": ("TEXAS", "Tesla Gigafactory Texas"),
}

MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def _numero(valor: float, casas: int = 2, *, sinal: bool = False) -> str:
    if not np.isfinite(float(valor)):
        raise RuntimeError(f"Valor não finito não pode ser publicado: {valor!r}.")
    formato = f"{{:{'+' if sinal else ''}.{casas}f}}"
    return formato.format(float(valor)).replace(".", ",")


def _lista_natural(itens: Iterable[str]) -> str:
    valores = list(itens)
    if not valores:
        return "nenhum"
    if len(valores) == 1:
        return valores[0]
    return ", ".join(valores[:-1]) + " e " + valores[-1]


def _nomes_meses(numeros: Iterable[int]) -> str:
    valores = list(numeros)
    if not valores:
        return "nenhum mês"
    return _lista_natural(MESES[int(numero) - 1] for numero in valores)


def _quantidade_antes_de_meses(quantidade: int) -> str:
    if quantidade == 0:
        return "nenhum dos"
    if quantidade == 1:
        return "apenas 1 dos"
    return str(quantidade)


def _texto_latex(valor: object) -> str:
    substituicoes = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(substituicoes.get(caractere, caractere) for caractere in str(valor))


def _plural(quantidade: int, singular: str, plural: str) -> str:
    return singular if quantidade == 1 else plural


def _comparar(valor_a: float, valor_b: float) -> int:
    """Retorna -1, 0 ou 1, com tolerância apenas para ruído numérico."""
    if np.isclose(float(valor_a), float(valor_b), rtol=1e-12, atol=1e-12):
        return 0
    return -1 if valor_a < valor_b else 1


def _exigir_colunas(
    tabela: pd.DataFrame, nome: str, colunas: Iterable[str]
) -> None:
    ausentes = sorted(set(colunas) - set(tabela.columns))
    if ausentes:
        raise RuntimeError(
            f"Colunas ausentes em {nome}: {', '.join(ausentes)}."
        )


def _exigir_numeros_finitos(
    tabela: pd.DataFrame, nome: str, colunas: Iterable[str]
) -> None:
    nomes = sorted(colunas)
    valores = tabela.loc[:, nomes].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(valores.to_numpy(dtype=float)).all():
        raise RuntimeError(f"Valores ausentes, não numéricos ou infinitos em {nome}.")


def _iteracoes_mlp_salvas(pasta: Path, sementes: Iterable[int]) -> list[int]:
    """Recupera n_iter_ dos modelos quando a execução retomada não o exportou."""
    import joblib

    valores: list[int] = []
    for seed in sementes:
        caminho = pasta / "modelos" / f"mlp_global_seed_{seed}.joblib"
        if not caminho.is_file():
            raise RuntimeError(
                "A coluna iteracoes_efetivas está ausente e não foi encontrado "
                f"o modelo MLP da semente {seed}: {caminho}."
            )
        modelo = joblib.load(caminho)
        candidatos = [
            etapa
            for _, etapa in getattr(modelo, "steps", ())
            if hasattr(etapa, "n_iter_")
        ]
        if len(candidatos) != 1:
            raise RuntimeError(
                f"Não foi possível identificar n_iter_ univocamente em {caminho}."
            )
        valor = int(candidatos[0].n_iter_)
        if valor <= 0:
            raise RuntimeError(f"n_iter_ inválido em {caminho}: {valor}.")
        valores.append(valor)
    return valores


def _validar_execucao(pasta: Path) -> dict:
    status = json.loads((pasta / "status_execucao.json").read_text(encoding="utf-8"))
    manifesto = json.loads(
        (pasta / "manifesto_execucao.json").read_text(encoding="utf-8")
    )
    if status.get("etapa") != "concluido":
        raise RuntimeError("A execução ainda não está concluída.")
    detalhes = status.get("detalhes", {})
    if not detalhes.get("protocolo_canonico") or not detalhes.get(
        "fonte_artigos_atuais"
    ):
        raise RuntimeError("A execução não está autorizada como fonte dos artigos.")
    metadados = manifesto.get("metadados", {})
    if metadados.get("modo_execucao") != "completa":
        raise RuntimeError("Resultados smoke não podem preencher os artigos.")
    if not metadados.get("protocolo_canonico") or not metadados.get(
        "fonte_artigos_atuais"
    ):
        raise RuntimeError("O manifesto não autoriza o preenchimento dos artigos.")
    configuracao = manifesto.get("configuracao", {})
    sementes = tuple(configuracao.get("sementes", ()))
    if sementes != SEMENTES_ARTIGOS:
        raise RuntimeError(
            "As sementes do manifesto não correspondem às declaradas nos artigos: "
            f"{sementes!r}."
        )
    contrato_artigos = {
        "amostras_probabilisticas_por_semente": 500,
        "contexto": 12,
        "epocas_deepar": 100,
        "epocas_deepnpts": 100,
        "lotes_por_epoca_deepar": 50,
        "lotes_por_epoca_deepnpts": 100,
        "max_epocas_keras": 300,
        "nivel_intervalo": 0.9,
        "niveis_quantizacao": 128,
        "paciencia_keras": 30,
    }
    divergentes = {
        chave: configuracao.get(chave)
        for chave, esperado in contrato_artigos.items()
        if configuracao.get(chave) != esperado
    }
    if divergentes:
        raise RuntimeError(
            "A configuração diverge dos valores declarados nos artigos: "
            f"{divergentes!r}."
        )

    ambiente = manifesto.get("ambiente", {})
    dependencias = ambiente.get("dependencias", {})
    versoes_divergentes = {}
    if ambiente.get("python") != "3.12.1":
        versoes_divergentes["python"] = ambiente.get("python")
    for pacote, prefixo in {
        "gluonts": "0.16.2",
        "tensorflow": "2.21",
        "torch": "2.6",
    }.items():
        versao = str(dependencias.get(pacote, ""))
        if not versao.startswith(prefixo):
            versoes_divergentes[pacote] = versao or None
    if versoes_divergentes:
        raise RuntimeError(
            "As versões do ambiente divergem das declaradas nos artigos: "
            f"{versoes_divergentes!r}."
        )

    entradas = manifesto.get("arquivos_entrada")
    if not isinstance(entradas, list) or not entradas:
        raise RuntimeError("O manifesto não registra os arquivos de entrada.")
    arquivos_divergentes = []
    for registro in entradas:
        relativo = Path(str(registro.get("caminho", "")))
        caminho = (RAIZ_REPOSITORIO / relativo).resolve()
        if (
            not caminho.is_relative_to(RAIZ_REPOSITORIO)
            or not caminho.is_file()
        ):
            arquivos_divergentes.append(str(relativo))
            continue
        with caminho.open("rb") as arquivo:
            sha256 = hashlib.file_digest(arquivo, "sha256").hexdigest()
        if sha256 != registro.get("sha256"):
            arquivos_divergentes.append(str(relativo))
    if arquivos_divergentes:
        raise RuntimeError(
            "Arquivos de entrada ausentes ou divergentes do manifesto: "
            f"{', '.join(arquivos_divergentes)}."
        )
    return manifesto


def _mapa_substituicoes(pasta: Path) -> dict[str, str]:
    manifesto = _validar_execucao(pasta)
    medias = pd.read_csv(pasta / "metricas_medias_modelos.csv")
    locais = pd.read_csv(pasta / "metricas_por_localidade.csv")
    previsoes = pd.read_csv(pasta / "previsoes_consolidadas.csv")
    probabilisticas = pd.read_csv(pasta / "metricas_probabilisticas_medias.csv")
    hiper = pd.read_csv(pasta / "hiperparametros_executados.csv")
    vencedores = pd.read_csv(pasta / "vencedores_por_localidade.csv")

    colunas_metricas = {
        "MAE_media_wm2",
        "MAE_dp_sementes_wm2",
        "MSE_media_wm4",
        "RMSE_media_wm2",
        "R2_medio",
        "nRMSE_medio_percentual",
    }
    colunas_locais = {
        "MAE_wm2",
        "MSE_wm4",
        "RMSE_wm2",
        "R2",
        "nRMSE_percentual",
    }
    _exigir_colunas(
        medias,
        "metricas_medias_modelos.csv",
        {"Modelo", *colunas_metricas},
    )
    _exigir_colunas(
        locais,
        "metricas_por_localidade.csv",
        {"Localidade", "Modelo", *colunas_locais},
    )
    _exigir_colunas(
        previsoes,
        "previsoes_consolidadas.csv",
        {"Localidade", "data_alvo", "y_wm2", *MODELOS_TOKENS},
    )
    _exigir_colunas(
        probabilisticas,
        "metricas_probabilisticas_medias.csv",
        {
            "Modelo",
            "CRPS_medio_wm2",
            "PICP_medio_percentual",
            "MPIW_medio_wm2",
        },
    )
    _exigir_colunas(
        hiper,
        "hiperparametros_executados.csv",
        {"Modelo", "seed", "retomado"},
    )
    _exigir_colunas(
        vencedores,
        "vencedores_por_localidade.csv",
        {"Localidade", "Modelo"},
    )
    _exigir_numeros_finitos(
        medias, "metricas_medias_modelos.csv", colunas_metricas
    )
    _exigir_numeros_finitos(
        locais, "metricas_por_localidade.csv", colunas_locais
    )
    _exigir_numeros_finitos(
        previsoes,
        "previsoes_consolidadas.csv",
        {"y_wm2", *MODELOS_TOKENS},
    )
    _exigir_numeros_finitos(
        probabilisticas,
        "metricas_probabilisticas_medias.csv",
        {"CRPS_medio_wm2", "PICP_medio_percentual", "MPIW_medio_wm2"},
    )

    esperado = set(MODELOS_TOKENS)
    if medias["Modelo"].duplicated().any() or set(medias["Modelo"]) != esperado:
        raise RuntimeError("Conjunto de modelos inesperado na tabela de médias.")
    pares_esperados = {
        (localidade, modelo)
        for localidade in LOCALIDADES
        for modelo in MODELOS_TOKENS
    }
    pares_locais = set(
        locais[["Localidade", "Modelo"]].itertuples(index=False, name=None)
    )
    if (
        locais[["Localidade", "Modelo"]].duplicated().any()
        or pares_locais != pares_esperados
    ):
        raise RuntimeError("A tabela de métricas locais não forma a grade 10 x 10.")
    if (
        len(previsoes) != 120
        or previsoes[["Localidade", "data_alvo"]].duplicated().any()
        or set(previsoes["Localidade"]) != set(LOCALIDADES)
        or not previsoes.groupby("Localidade").size().eq(12).all()
    ):
        raise RuntimeError(
            "As previsões consolidadas não têm as 120 origens esperadas."
        )
    datas_previsoes = pd.to_datetime(previsoes["data_alvo"], errors="coerce")
    if datas_previsoes.isna().any() or not datas_previsoes.dt.year.eq(2024).all():
        raise RuntimeError("As previsões não contêm somente datas válidas de 2024.")
    periodos_esperados = set(pd.period_range("2024-01", "2024-12", freq="M"))
    periodos_por_localidade = previsoes.assign(
        _periodo=datas_previsoes.dt.to_period("M")
    ).groupby("Localidade")["_periodo"]
    if any(
        set(periodos) != periodos_esperados
        for _, periodos in periodos_por_localidade
    ):
        raise RuntimeError(
            "Cada localidade deve conter exatamente os 12 meses de 2024."
        )
    if (
        probabilisticas["Modelo"].duplicated().any()
        or set(probabilisticas["Modelo"]) != set(MODELOS_PROBABILISTICOS)
    ):
        raise RuntimeError("Métricas probabilísticas incompletas ou duplicadas.")
    if (
        vencedores["Localidade"].duplicated().any()
        or set(vencedores["Localidade"]) != set(LOCALIDADES)
        or not set(vencedores["Modelo"]) <= esperado
    ):
        raise RuntimeError("Vencedores por localidade incompletos ou inesperados.")
    sementes = list(SEMENTES_ARTIGOS)
    grade_hiper = {
        (modelo, seed) for modelo in MODELOS_APRENDIDOS for seed in sementes
    }
    pares_hiper = set(hiper[["Modelo", "seed"]].itertuples(index=False, name=None))
    if (
        hiper[["Modelo", "seed"]].duplicated().any()
        or pares_hiper != grade_hiper
    ):
        raise RuntimeError("Hiperparâmetros não formam a grade de modelos e sementes.")

    subs: dict[str, str] = {}
    medias_idx = medias.set_index("Modelo")
    for modelo, token in MODELOS_TOKENS.items():
        linha = medias_idx.loc[modelo]
        subs[f"MAE-{token}"] = _numero(linha["MAE_media_wm2"])
        subs[f"MSE-{token}"] = _numero(linha["MSE_media_wm4"])
        subs[f"RMSE-{token}"] = _numero(linha["RMSE_media_wm2"])
        subs[f"R2-{token}"] = _numero(linha["R2_medio"], 3)
        subs[f"NRMSE-{token}"] = _numero(linha["nRMSE_medio_percentual"])
        if modelo in MODELOS_APRENDIDOS:
            subs[f"DP-{token}"] = _numero(linha["MAE_dp_sementes_wm2"])

    ranking = medias.sort_values("MAE_media_wm2").reset_index(drop=True)
    melhor = ranking.iloc[0]
    pos_deep = int(ranking.index[ranking["Modelo"].eq("DeepNPTS")][0]) + 1
    deep_media = medias_idx.loc["DeepNPTS", "MAE_media_wm2"]
    clim_media = medias_idx.loc["Climatologia", "MAE_media_wm2"]
    subs.update(
        {
            "MODELO-MELHOR": MODELOS_EXIBICAO[str(melhor["Modelo"])],
            "MAE-MELHOR": _numero(melhor["MAE_media_wm2"]),
            "POSICAO-DEEPNPTS": f"{pos_deep}ª entre {len(ranking)} métodos",
            "DELTA-DEEPNPTS-CLIM": _numero(deep_media - clim_media, sinal=True),
        }
    )

    deep_local = locais.loc[locais["Modelo"].eq("DeepNPTS")].set_index("Localidade")
    if set(deep_local.index) != set(LOCALIDADES):
        raise RuntimeError("Métricas locais do DeepNPTS incompletas.")
    for nome_csv, (token, _) in LOCALIDADES.items():
        linha = deep_local.loc[nome_csv]
        subs[f"{token}-MAE"] = _numero(linha["MAE_wm2"])
        subs[f"{token}-MSE"] = _numero(linha["MSE_wm4"])
        subs[f"{token}-RMSE"] = _numero(linha["RMSE_wm2"])
        subs[f"{token}-R2"] = _numero(linha["R2"], 3)
        subs[f"{token}-NRMSE"] = _numero(linha["nRMSE_percentual"])

    melhor_local_csv = str(deep_local["MAE_wm2"].idxmin())
    pior_local_csv = str(deep_local["MAE_wm2"].idxmax())
    melhor_local = deep_local.loc[melhor_local_csv]
    pior_local = deep_local.loc[pior_local_csv]
    subs.update(
        {
            "LOCAL-MELHOR-DEEPNPTS": LOCALIDADES[melhor_local_csv][1],
            "MAE-LOCAL-MELHOR-DEEPNPTS": _numero(melhor_local["MAE_wm2"]),
            "LOCAL-PIOR-DEEPNPTS": LOCALIDADES[pior_local_csv][1],
            "MAE-LOCAL-PIOR-DEEPNPTS": _numero(pior_local["MAE_wm2"]),
            "AMPLITUDE-MAE-DEEPNPTS": _numero(
                pior_local["MAE_wm2"] - melhor_local["MAE_wm2"]
            ),
        }
    )

    contagens = vencedores["Modelo"].value_counts()
    ordem_vitorias = [
        modelo for modelo in ranking["Modelo"] if modelo in set(contagens.index)
    ]
    contagem_texto = [
        f"{MODELOS_EXIBICAO[modelo]} ({int(contagens[modelo])})"
        for modelo in ordem_vitorias
    ]
    if "DeepNPTS" not in contagens:
        contagem_texto.append("DeepNPTS (0)")
    grupos = []
    for modelo in ordem_vitorias:
        nomes = [
            LOCALIDADES[nome][1]
            for nome in vencedores.loc[vencedores["Modelo"].eq(modelo), "Localidade"]
        ]
        grupos.append(
            f"{MODELOS_EXIBICAO[modelo]}: {_lista_natural(nomes)}"
        )
    if "DeepNPTS" not in contagens:
        grupos.append("DeepNPTS: nenhuma localidade")
    subs["CONTAGEM-VITORIAS"] = _lista_natural(contagem_texto)
    subs["VENCEDORES-POR-LOCALIDADE"] = "; ".join(grupos)

    local_byd = "BYD Camacari"
    concorrente = (
        locais.loc[
            locais["Localidade"].eq(local_byd) & ~locais["Modelo"].eq("DeepNPTS")
        ]
        .sort_values("MAE_wm2")
        .iloc[0]
    )
    nome_concorrente = str(concorrente["Modelo"])
    byd = previsoes.loc[previsoes["Localidade"].eq(local_byd)].copy()
    byd["data_alvo"] = pd.to_datetime(byd["data_alvo"], errors="raise")
    byd = byd.sort_values("data_alvo")
    erro_deep = np.abs(byd["y_wm2"] - byd["DeepNPTS"])
    erro_comp = np.abs(byd["y_wm2"] - byd[nome_concorrente])
    meses_deep = byd.loc[erro_deep < erro_comp, "data_alvo"].dt.month.tolist()
    subs.update(
        {
            "COMPARACAO-BYD": MODELOS_EXIBICAO[nome_concorrente],
            "MESES-DEEPNPTS-MELHOR-BYD": _quantidade_antes_de_meses(
                len(meses_deep)
            ),
            "BYD-MAE-COMPARACAO": _numero(concorrente["MAE_wm2"]),
            "COMENTARIO-SOBREPOSICAO-BYD": _nomes_meses(meses_deep),
        }
    )

    prob_idx = probabilisticas.set_index("Modelo")
    for modelo in MODELOS_PROBABILISTICOS:
        token = MODELOS_TOKENS[modelo]
        linha = prob_idx.loc[modelo]
        subs[f"CRPS-{token}"] = _numero(linha["CRPS_medio_wm2"])
        subs[f"PICP-{token}"] = _numero(linha["PICP_medio_percentual"])
        subs[f"MPIW-{token}"] = _numero(linha["MPIW_medio_wm2"])
    crps_deep = float(prob_idx.loc["DeepNPTS", "CRPS_medio_wm2"])
    crps_ar = float(prob_idx.loc["DeepAR", "CRPS_medio_wm2"])
    picp_deep = float(prob_idx.loc["DeepNPTS", "PICP_medio_percentual"])
    picp_ar = float(prob_idx.loc["DeepAR", "PICP_medio_percentual"])
    largura_deep = float(prob_idx.loc["DeepNPTS", "MPIW_medio_wm2"])
    largura_ar = float(prob_idx.loc["DeepAR", "MPIW_medio_wm2"])
    if not (0 <= picp_deep <= 100 and 0 <= picp_ar <= 100):
        raise RuntimeError("PICP fora do intervalo de 0 a 100%.")
    if min(crps_deep, crps_ar, largura_deep, largura_ar) < 0:
        raise RuntimeError("CRPS e MPIW não podem ser negativos.")

    relacao_cobertura = _comparar(abs(picp_deep - 90), abs(picp_ar - 90))
    if relacao_cobertura < 0:
        frase_cobertura = "o DeepNPTS ficou mais próximo da cobertura nominal"
    elif relacao_cobertura > 0:
        frase_cobertura = "o DeepAR ficou mais próximo da cobertura nominal"
    else:
        frase_cobertura = (
            "DeepNPTS e DeepAR ficaram igualmente próximos da cobertura nominal"
        )

    relacao_crps = _comparar(crps_deep, crps_ar)
    if relacao_crps < 0:
        frase_crps = "o DeepNPTS obteve menor CRPS"
    elif relacao_crps > 0:
        frase_crps = "o DeepAR obteve menor CRPS"
    else:
        frase_crps = "DeepNPTS e DeepAR obtiveram o mesmo CRPS"

    relacao_largura = _comparar(largura_deep, largura_ar)
    if relacao_largura == 0:
        frase_largura = "os dois modelos tiveram a mesma largura média"
    else:
        nome_largo, largura_maior, largura_menor = (
            ("DeepNPTS", largura_deep, largura_ar)
            if relacao_largura > 0
            else ("DeepAR", largura_ar, largura_deep)
        )
        if largura_menor == 0:
            frase_largura = (
                f"somente o {nome_largo} apresentou intervalos de largura positiva"
            )
        else:
            frase_largura = (
                f"o {nome_largo} apresentou intervalos "
                f"{_numero(largura_maior / largura_menor)} vezes mais largos"
            )
    interpretacao_probabilistica = _lista_natural(
        (frase_cobertura, frase_crps, frase_largura)
    )
    subs["INTERPRETACAO-PROBABILISTICA"] = interpretacao_probabilistica

    hardware = manifesto["metadados"].get("hardware", {})
    chaves_hardware = {
        "sistema",
        "kernel",
        "cpus_logicas",
        "arquitetura",
        "memoria_total_gib",
        "gpu",
    }
    ausentes_hardware = sorted(chaves_hardware - set(hardware))
    if ausentes_hardware:
        raise RuntimeError(
            "Metadados de hardware incompletos: "
            f"{', '.join(ausentes_hardware)}."
        )
    if "nenhuma" not in str(hardware["gpu"]).casefold():
        raise RuntimeError(
            "O artigo declara execução sem GPU, mas o manifesto diverge."
        )
    subs["HARDWARE-CPU-RAM-SO"] = (
        f"{_texto_latex(hardware['sistema'])} {_texto_latex(hardware['kernel'])}, "
        f"{hardware['cpus_logicas']} vCPUs "
        f"{_texto_latex(hardware['arquitetura'])}, "
        f"{_numero(hardware['memoria_total_gib'], 2)} GiB de RAM e "
        "sem GPU; execução forçada em CPU"
    )

    def lista_int(
        modelo: str,
        coluna: str,
        *,
        fallback: Iterable[int] | None = None,
    ) -> str:
        linhas = hiper.loc[hiper["Modelo"].eq(modelo)].sort_values("seed")
        if coluna not in linhas or linhas[coluna].isna().any():
            if fallback is None:
                raise RuntimeError(
                    f"Hiperparâmetro {coluna} incompleto para {modelo}."
                )
            valores_numericos = np.asarray(list(fallback), dtype=float)
        else:
            valores_numericos = pd.to_numeric(
                linhas[coluna], errors="coerce"
            ).to_numpy()
        if (
            len(valores_numericos) != len(sementes)
            or not np.isfinite(valores_numericos).all()
            or not np.equal(valores_numericos, np.floor(valores_numericos)).all()
            or (valores_numericos <= 0).any()
        ):
            raise RuntimeError(f"Hiperparâmetro {coluna} incompleto para {modelo}.")
        return ", ".join(str(int(valor)) for valor in valores_numericos)

    subs["XGBOOST-ARVORES-EFETIVAS"] = lista_int("XGBoost", "n_estimators")
    linhas_mlp = hiper.loc[hiper["Modelo"].eq("MLP")]
    fallback_mlp = (
        _iteracoes_mlp_salvas(pasta, sementes)
        if "iteracoes_efetivas" not in linhas_mlp
        or linhas_mlp["iteracoes_efetivas"].isna().any()
        else None
    )
    subs["MLP-ITERACOES-EFETIVAS"] = lista_int(
        "MLP",
        "iteracoes_efetivas",
        fallback=fallback_mlp,
    )
    epocas_rnn = lista_int("RNN", "epocas_selecionadas")
    epocas_lstm = lista_int("LSTM", "epocas_selecionadas")
    subs["RNN-EPOCAS-EFETIVAS"] = epocas_rnn
    subs["LSTM-EPOCAS-EFETIVAS"] = epocas_lstm
    subs["RNN-LSTM-EPOCAS-EFETIVAS"] = (
        f"RNN ({epocas_rnn}); LSTM ({epocas_lstm})"
    )
    subs["DILATEDRNN-EPOCAS-EFETIVAS"] = lista_int(
        "DilatedRNN", "epocas_selecionadas"
    )
    for modelo, lotes_esperados in (("DeepNPTS", 100), ("DeepAR", 50)):
        linhas = hiper.loc[hiper["Modelo"].eq(modelo)]
        epocas = lista_int(modelo, "epocas")
        lotes = lista_int(modelo, "lotes_por_epoca")
        retomado = linhas["retomado"].astype(str).str.casefold()
        if (
            set(epocas.split(", ")) != {"100"}
            or set(lotes.split(", ")) != {str(lotes_esperados)}
            or not retomado.eq("false").all()
        ):
            raise RuntimeError(
                f"A execução efetiva de {modelo} diverge da descrita no artigo."
            )
    subs["DEEPNPTS-CONFIG-EFETIVA"] = (
        "cinco ajustes novos de 100 épocas, com embeddings registrados"
    )
    subs["DEEPAR-CONFIG-EFETIVA"] = "cinco ajustes novos de 100 épocas"

    comparacoes_mae = medias.loc[
        ~medias["Modelo"].eq("DeepNPTS"), "MAE_media_wm2"
    ]
    melhores_que_deep = int((comparacoes_mae < deep_media).sum())
    piores_que_deep = int((comparacoes_mae > deep_media).sum())
    empates_deep = len(comparacoes_mae) - melhores_que_deep - piores_que_deep
    frases_referencias = []
    if melhores_que_deep:
        frases_referencias.append(
            f"foi superado por {melhores_que_deep} "
            f"{_plural(melhores_que_deep, 'método', 'métodos')}"
        )
    else:
        frases_referencias.append("não foi superado por nenhum outro método")
    if piores_que_deep:
        frases_referencias.append(
            f"superou {piores_que_deep} "
            f"{_plural(piores_que_deep, 'método', 'métodos')}"
        )
    else:
        frases_referencias.append("não superou nenhum outro método")
    if empates_deep:
        frases_referencias.append(
            f"empatou com {empates_deep} "
            f"{_plural(empates_deep, 'método', 'métodos')}"
        )
    subs["RESUMO-DEEPNPTS-VS-REFERENCIAS"] = _lista_natural(
        frases_referencias
    )
    deep_ar_mae = medias_idx.loc["DeepAR", "MAE_media_wm2"]
    relacao_mae = _comparar(deep_media, deep_ar_mae)
    if relacao_mae < 0:
        frase_mae = "o DeepNPTS teve MAE menor que o DeepAR"
    elif relacao_mae > 0:
        frase_mae = "o DeepNPTS teve MAE maior que o DeepAR"
    else:
        frase_mae = "DeepNPTS e DeepAR tiveram o mesmo MAE"
    subs["RESUMO-DEEPNPTS-VS-DEEPAR"] = (
        f"{frase_mae}; {interpretacao_probabilistica}"
    )
    return subs


def _renderizar(origem: Path, subs: dict[str, str]) -> str:
    texto = origem.read_text(encoding="utf-8")
    for chave, valor in subs.items():
        texto = texto.replace(f"@@{chave}@@", valor)
    restantes = sorted(set(re.findall(r"@@[A-Z0-9-]+@@", texto)))
    if restantes:
        raise RuntimeError(
            f"Placeholders sem valor em {origem}: {', '.join(restantes)}"
        )
    return texto


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resultados", type=Path, required=True)
    parser.add_argument("--ieee-rascunho", type=Path, required=True)
    parser.add_argument("--ieee-saida", type=Path, required=True)
    parser.add_argument("--mcsm-rascunho", type=Path)
    parser.add_argument("--mcsm-saida", type=Path)
    args = parser.parse_args()
    if (args.mcsm_rascunho is None) != (args.mcsm_saida is None):
        parser.error("Informe simultaneamente --mcsm-rascunho e --mcsm-saida.")

    subs = _mapa_substituicoes(args.resultados)
    texto_ieee = _renderizar(args.ieee_rascunho, subs)
    texto_mcsm = (
        _renderizar(args.mcsm_rascunho, subs)
        if args.mcsm_rascunho is not None
        else None
    )

    # Só inicia as escritas depois que todos os rascunhos foram validados.
    args.ieee_saida.write_text(texto_ieee, encoding="utf-8")
    print(args.ieee_saida)
    if texto_mcsm is not None:
        assert args.mcsm_saida is not None
        args.mcsm_saida.write_text(texto_mcsm, encoding="utf-8")
        print(args.mcsm_saida)


if __name__ == "__main__":
    main()
