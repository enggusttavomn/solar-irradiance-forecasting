"""Sincroniza os resultados horários canônicos com o artigo IEEE do Overleaf.

O script altera somente os blocos ``AUTO-*`` de ``overlief/IEEE/artigo.tex``
e atualiza as figuras publicadas. Os resultados brutos permanecem imutáveis;
a camada editorial seleciona apenas os modelos pertencentes ao escopo do
manuscrito. O artigo do MCSM nunca é lido nem modificado.
"""

from __future__ import annotations

import argparse
import io
import os
import tempfile
import textwrap
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache-tcc-artigo")

import numpy as np
import pandas as pd


RAIZ = Path(__file__).resolve().parent
RESULTADOS_PADRAO = RAIZ / "resultados" / "avaliacao_horaria_timesnet"
ARTIGO_PADRAO = RAIZ / "overlief" / "IEEE" / "artigo.tex"
PASTA_FIGURAS_PADRAO = RAIZ / "overlief" / "IEEE" / "figuras"
FIGURAS_CANONICAS = (
    "previsao_horaria_timesnet_72h.png",
    "comparacao_rmse_modelos.png",
)

# O experimento bruto preserva o XGBoost para auditoria. A política editorial
# do artigo IEEE, porém, compara somente o TimesNet, a LSTM e as duas
# referências ingênuas. Centralizar essa lista impede que uma atualização
# automática volte a inserir no manuscrito um modelo fora de seu escopo.
ORDEM_MODELOS_ARTIGO = (
    "Persistência",
    "Sazonal Ingênuo",
    "LSTM",
    "TimesNet",
)
NOMES_TABELA = {
    "Persistência": "Persistência",
    "Sazonal Ingênuo": "Sazonal ingênuo",
    "LSTM": "LSTM",
    "TimesNet": "TimesNet",
}
NOMES_LOCAIS = {
    "BMW San Luis Potosi": "BMW San Luis Potosí",
    "BYD Camacari": "BYD Camaçari",
    "Ford Rouge Electric Vehicle Center": "Ford Rouge",
    "GM Factory Zero": "GM Factory Zero",
    "Hyundai Metaplant Georgia": "Hyundai Georgia",
    "Lucid AMP 1 Casa Grande": "Lucid Casa Grande",
    "Rivian Normal": "Rivian Normal",
    "Tesla Fremont Factory": "Tesla Fremont",
    "Tesla Gigafactory Nevada": "Tesla Nevada",
    "Tesla Gigafactory Texas": "Tesla Texas",
}


def _decimal(valor: float, casas: int = 2) -> str:
    if not np.isfinite(valor):
        raise ValueError("Não é permitido escrever métrica não finita no artigo.")
    return f"{float(valor):.{casas}f}".replace(".", ",")


def _inteiro(valor: int) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _percentual_reducao(referencia: float, candidato: float) -> float:
    if referencia <= 0:
        raise ValueError("A referência do percentual deve ser positiva.")
    return 100.0 * (referencia - candidato) / referencia


def _paragrafo(texto: str) -> str:
    return textwrap.fill(
        " ".join(texto.split()),
        width=78,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _substituir_bloco(
    fonte: str,
    nome: str,
    conteudo: str,
) -> str:
    inicio = f"% AUTO-{nome}-BEGIN"
    fim = f"% AUTO-{nome}-END"
    if fonte.count(inicio) != 1 or fonte.count(fim) != 1:
        raise ValueError(
            f"O artigo deve conter exatamente um par de marcadores {nome}."
        )
    antes, restante = fonte.split(inicio, maxsplit=1)
    _, depois = restante.split(fim, maxsplit=1)
    return (
        antes
        + inicio
        + "\n"
        + conteudo.strip()
        + "\n"
        + fim
        + depois
    )


def _carregar_metricas(
    pasta: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    macro = pd.read_csv(pasta / "metricas_macro.csv")
    locais = pd.read_csv(pasta / "metricas_por_localidade.csv")
    filtro_macro = (
        macro["particao"].eq("teste_2024")
        & macro["escopo"].eq("todas_horas")
        & macro["versao_previsao"].eq("pos_processada")
        & macro["horizonte_h"].isin((24, 48, 72))
    )
    filtro_locais = (
        locais["particao"].eq("teste_2024")
        & locais["escopo"].eq("todas_horas")
        & locais["versao_previsao"].eq("pos_processada")
        & locais["horizonte_h"].eq(72)
    )
    macro_bruto = macro.loc[filtro_macro].copy()
    locais_bruto = locais.loc[filtro_locais].copy()
    modelos_necessarios = set(ORDEM_MODELOS_ARTIGO)
    if not modelos_necessarios <= set(macro_bruto["Modelo"]):
        raise ValueError("Faltam modelos necessários nas métricas macro.")
    if not modelos_necessarios <= set(locais_bruto["Modelo"]):
        raise ValueError("Faltam modelos necessários nas métricas locais.")

    # A filtragem ocorre somente na camada de publicação. Os CSVs científicos
    # permanecem completos e não são reescritos por este utilitário.
    macro = macro_bruto.loc[
        macro_bruto["Modelo"].isin(ORDEM_MODELOS_ARTIGO)
    ].copy()
    locais = locais_bruto.loc[
        locais_bruto["Modelo"].isin(ORDEM_MODELOS_ARTIGO)
    ].copy()
    if len(macro) != 12:
        raise ValueError(f"Esperavam-se 12 linhas macro; foram obtidas {len(macro)}.")
    if len(locais) != 40:
        raise ValueError(
            f"Esperavam-se 40 linhas locais em 72 h; foram obtidas {len(locais)}."
        )
    if set(locais["Localidade"]) != set(NOMES_LOCAIS):
        raise ValueError("O conjunto de localidades não é o canônico.")
    return macro, locais


def _tabela_macro(macro: pd.DataFrame) -> str:
    nomes_compactos = {
        "Persistência": "Persist.",
        "Sazonal Ingênuo": "Sazonal",
        "LSTM": "LSTM",
        "TimesNet": "TimesNet",
    }
    tabelas = []
    for horizonte in (24, 48, 72):
        linhas = [
            r"\begin{tabular}{lrrrr}",
            r"\toprule",
            rf"\multicolumn{{5}}{{c}}{{\textbf{{{horizonte} h}}}} \\",
            (
                r"\textbf{Modelo} & \textbf{RMSE} & \textbf{MAE} & "
                r"\textbf{nRMSE} & \textbf{$R^2$} \\"
            ),
            r"\midrule",
        ]
        for modelo in ORDEM_MODELOS_ARTIGO:
            linha = _por_modelo_horizonte(macro, modelo, horizonte)
            linhas.append(
                f"{nomes_compactos[modelo]} & "
                f"{_decimal(linha['RMSE_macro_wm2'])} & "
                f"{_decimal(linha['MAE_macro_wm2'])} & "
                f"{_decimal(linha['nRMSE_macro_percentual'])} & "
                f"{_decimal(linha['R2_macro'], 3)} " + r"\\"
            )
        linhas.extend((r"\bottomrule", r"\end{tabular}"))
        tabelas.append("\n".join(linhas))
    return "\n\\hfill\n".join(tabelas)


def _por_modelo_horizonte(
    macro: pd.DataFrame,
    modelo: str,
    horizonte: int,
) -> pd.Series:
    linha = macro.loc[
        macro["Modelo"].eq(modelo) & macro["horizonte_h"].eq(horizonte)
    ]
    if len(linha) != 1:
        raise ValueError(f"Métrica ausente ou duplicada para {modelo}/{horizonte}.")
    return linha.iloc[0]


def _abstract(macro: pd.DataFrame) -> str:
    horizonte = 72
    timesnet = _por_modelo_horizonte(macro, "TimesNet", horizonte)
    lstm = _por_modelo_horizonte(macro, "LSTM", horizonte)
    reducao_lstm = _percentual_reducao(
        float(lstm["RMSE_macro_wm2"]),
        float(timesnet["RMSE_macro_wm2"]),
    )
    texto = (
        "Em 72 h, o TimesNet obteve raiz do erro quadrático médio (RMSE) macro "
        f"de {_decimal(timesnet['RMSE_macro_wm2'])} W/m$^2$, enquanto a LSTM "
        f"obteve {_decimal(lstm['RMSE_macro_wm2'])} W/m$^2$, o que corresponde "
        f"a uma redução relativa de {_decimal(reducao_lstm)}\\%. O TimesNet "
        "também apresentou RMSE menor que o da LSTM nos demais horizontes e "
        "que o das duas referências nos três horizontes. Os resultados "
        "limitam-se às localidades, aos anos e ao protocolo estudados."
    )
    return _paragrafo(texto)


def _metricas_diurnas(pasta: Path) -> pd.DataFrame:
    macro = pd.read_csv(pasta / "metricas_macro.csv")
    filtro = (
        macro["particao"].eq("teste_2024")
        & macro["escopo"].eq("diurno_elevacao_gt_0")
        & macro["versao_previsao"].eq("pos_processada")
        & macro["horizonte_h"].eq(72)
    )
    resultado = macro.loc[
        filtro & macro["Modelo"].isin(ORDEM_MODELOS_ARTIGO)
    ].copy()
    if len(resultado) != 4:
        raise ValueError("Esperavam-se quatro métricas macro diurnas em 72 h.")
    return resultado


def _discussao_macro(macro: pd.DataFrame, diurno: pd.DataFrame) -> str:
    rmse_timesnet: list[float] = []
    rmse_lstm: list[float] = []
    reducao_lstm = []
    reducao_persistencia = []
    reducao_sazonal = []
    for horizonte in (24, 48, 72):
        timesnet = _por_modelo_horizonte(macro, "TimesNet", horizonte)
        lstm = _por_modelo_horizonte(macro, "LSTM", horizonte)
        persistencia = _por_modelo_horizonte(macro, "Persistência", horizonte)
        sazonal = _por_modelo_horizonte(macro, "Sazonal Ingênuo", horizonte)
        rmse_timesnet.append(float(timesnet["RMSE_macro_wm2"]))
        rmse_lstm.append(float(lstm["RMSE_macro_wm2"]))
        reducao_lstm.append(
            _percentual_reducao(
                float(lstm["RMSE_macro_wm2"]),
                float(timesnet["RMSE_macro_wm2"]),
            )
        )
        reducao_persistencia.append(
            _percentual_reducao(
                float(persistencia["RMSE_macro_wm2"]),
                float(timesnet["RMSE_macro_wm2"]),
            )
        )
        reducao_sazonal.append(
            _percentual_reducao(
                float(sazonal["RMSE_macro_wm2"]),
                float(timesnet["RMSE_macro_wm2"]),
            )
        )
    if any(valor < 0 for valor in reducao_lstm):
        raise ValueError("A redação do artigo pressupõe TimesNet melhor que LSTM.")

    lidera_todas_metricas = True
    for horizonte in (24, 48, 72):
        grupo = macro.loc[macro["horizonte_h"].eq(horizonte)]
        for coluna in (
            "RMSE_macro_wm2",
            "MAE_macro_wm2",
            "nRMSE_macro_percentual",
            "R2_macro",
        ):
            indice = (
                grupo[coluna].idxmax() if coluna == "R2_macro" else grupo[coluna].idxmin()
            )
            lidera_todas_metricas &= str(grupo.loc[indice, "Modelo"]) == "TimesNet"

    paragrafo_1 = (
        "Em 24, 48 e 72 h, os valores de RMSE do TimesNet foram "
        f"{_decimal(rmse_timesnet[0])}, {_decimal(rmse_timesnet[1])} e "
        f"{_decimal(rmse_timesnet[2])} W/m$^2$, contra "
        f"{_decimal(rmse_lstm[0])}, {_decimal(rmse_lstm[1])} e "
        f"{_decimal(rmse_lstm[2])} W/m$^2$ da LSTM: reduções de "
        f"{_decimal(reducao_lstm[0])}\\%, {_decimal(reducao_lstm[1])}\\% e "
        f"{_decimal(reducao_lstm[2])}\\%."
    )
    if lidera_todas_metricas:
        paragrafo_1 += (
            " O mesmo ordenamento entre as duas redes foi observado para "
            "MAE, nRMSE e $R^2$."
        )

    crescimento_timesnet = 100.0 * (
        rmse_timesnet[-1] - rmse_timesnet[0]
    ) / rmse_timesnet[0]
    crescimento_lstm = 100.0 * (
        rmse_lstm[-1] - rmse_lstm[0]
    ) / rmse_lstm[0]
    paragrafo_2 = (
        "Em relação à persistência diária, as reduções de RMSE do TimesNet foram "
        f"{_decimal(reducao_persistencia[0])}\\%, "
        f"{_decimal(reducao_persistencia[1])}\\% e "
        f"{_decimal(reducao_persistencia[2])}\\%; em relação ao sazonal ingênuo, "
        f"foram {_decimal(reducao_sazonal[0])}\\%, "
        f"{_decimal(reducao_sazonal[1])}\\% e "
        f"{_decimal(reducao_sazonal[2])}\\%. Do prefixo de 24 h ao de 72 h, "
        f"o RMSE cresceu {_decimal(crescimento_timesnet)}\\% no TimesNet e "
        f"{_decimal(crescimento_lstm)}\\% na LSTM. Como os prefixos provêm de "
        "uma única saída direta, essa variação descreve a dificuldade "
        "associada à ampliação do horizonte, e não a propagação recursiva de "
        "previsões."
    )

    linhas_diurnas = {
        str(linha["Modelo"]): linha
        for _, linha in diurno.iterrows()
    }
    paragrafo_3 = (
        "Das 261.360 previsões de 72 h, 130.764 pertencem ao subconjunto com "
        "elevação solar positiva. Nesse recorte, o TimesNet obteve RMSE de "
        f"{_decimal(linhas_diurnas['TimesNet']['RMSE_macro_wm2'])} W/m$^2$, "
        f"nRMSE de {_decimal(linhas_diurnas['TimesNet']['nRMSE_macro_percentual'])}"
        "\\% e $R^2$ de "
        f"{_decimal(linhas_diurnas['TimesNet']['R2_macro'], 3)}; o RMSE da LSTM "
        f"foi {_decimal(linhas_diurnas['LSTM']['RMSE_macro_wm2'])} W/m$^2$. "
        "É esperado que o RMSE diurno seja maior do que o calculado considerando "
        "todas as horas, pois as horas noturnas, predominantemente nulas, tornam "
        "a tarefa agregada menos exigente."
    )

    paragrafo_4 = (
        "As diferenças entre as redes são moderadas e descritivas: não há "
        "ablação que as atribua à transformação 1D--2D, e o uso de uma única "
        "semente não permite estimar a variabilidade do treinamento. Os "
        "resultados mostram consistência interna neste protocolo, mas não "
        "constituem um teste de "
        "superioridade estatística."
    )
    return "\n\n".join(
        _paragrafo(item)
        for item in (paragrafo_1, paragrafo_2, paragrafo_3, paragrafo_4)
    )


def _discussao_local(locais: pd.DataFrame) -> str:
    timesnet = locais.loc[locais["Modelo"].eq("TimesNet")].copy()
    melhor = timesnet.loc[timesnet["RMSE_wm2"].idxmin()]
    pior = timesnet.loc[timesnet["RMSE_wm2"].idxmax()]
    menor_nrmse = timesnet.loc[timesnet["nRMSE_percentual"].idxmin()]
    maior_nrmse = timesnet.loc[timesnet["nRMSE_percentual"].idxmax()]
    comparacao_neural = locais.pivot(
        index="Localidade", columns="Modelo", values="RMSE_wm2"
    )
    n_timesnet_lstm = int(
        (comparacao_neural["TimesNet"] < comparacao_neural["LSTM"]).sum()
    )
    n_timesnet_lstm_texto = (
        "dez" if n_timesnet_lstm == 10 else str(n_timesnet_lstm)
    )
    ganhos = 100.0 * (
        comparacao_neural["LSTM"] - comparacao_neural["TimesNet"]
    ) / comparacao_neural["LSTM"]
    local_maior_ganho = str(ganhos.idxmax())
    local_menor_ganho = str(ganhos.idxmin())

    linhas_tabela = [
        r"\begin{table}[!t]",
        r"\centering",
        (
            r"\caption{RMSE por localidade em 72 h. Valores em W/m$^2$; "
            r"$\Delta$ é a redução relativa do TimesNet em relação à LSTM.}"
        ),
        r"\label{tab:metricas_locais}",
        r"\scriptsize",
        r"\setlength{\tabcolsep}{2.4pt}",
        r"\renewcommand{\arraystretch}{0.94}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"\textbf{Localidade} & \textbf{TimesNet} & \textbf{LSTM} & \textbf{$\Delta$ (\%)} \\",
        r"\midrule",
    ]
    nomes_tabela = {
        "BMW San Luis Potosi": "BMW S. L. Potosí",
        "BYD Camacari": "BYD Camaçari",
        "Ford Rouge Electric Vehicle Center": "Ford Rouge",
        "GM Factory Zero": "GM Factory Zero",
        "Hyundai Metaplant Georgia": "Hyundai Georgia",
        "Lucid AMP 1 Casa Grande": "Lucid Casa Grande",
        "Rivian Normal": "Rivian Normal",
        "Tesla Fremont Factory": "Tesla Fremont",
        "Tesla Gigafactory Nevada": "Tesla Nevada",
        "Tesla Gigafactory Texas": "Tesla Texas",
    }
    for localidade, linha in comparacao_neural.sort_values("TimesNet").iterrows():
        linhas_tabela.append(
            f"{nomes_tabela[str(localidade)]} & "
            f"{_decimal(linha['TimesNet'])} & {_decimal(linha['LSTM'])} & "
            f"{_decimal(ganhos.loc[localidade])} " + r"\\"
        )
    linhas_tabela.extend(
        (r"\bottomrule", r"\end{tabular}", r"\end{table}")
    )

    paragrafo_1 = (
        "Em 72 h, o RMSE do TimesNet variou de "
        f"{_decimal(melhor['RMSE_wm2'])} W/m$^2$ em "
        f"{NOMES_LOCAIS[str(melhor['Localidade'])]} a "
        f"{_decimal(pior['RMSE_wm2'])} W/m$^2$ em "
        f"{NOMES_LOCAIS[str(pior['Localidade'])]} e foi inferior ao da LSTM nas "
        f"{n_timesnet_lstm_texto} localidades. O nRMSE variou de "
        f"{_decimal(menor_nrmse['nRMSE_percentual'])}\\% a "
        f"{_decimal(maior_nrmse['nRMSE_percentual'])}\\%, evidenciando "
        "heterogeneidade entre as localidades avaliadas."
    )
    paragrafo_2 = (
        "A redução do TimesNet em relação à LSTM teve mediana de "
        f"{_decimal(float(ganhos.median()))}\\% e variou de "
        f"{_decimal(float(ganhos.min()))}\\% em "
        f"{NOMES_LOCAIS[local_menor_ganho]} a "
        f"{_decimal(float(ganhos.max()))}\\% em "
        f"{NOMES_LOCAIS[local_maior_ganho]}. Assim, o sinal da diferença foi "
        "espacialmente consistente, embora sua magnitude tenha sido pequena "
        "em Camaçari. A amplitude dos erros absolutos e normalizados também "
        "indica que um único valor macro não caracteriza igualmente todos os "
        "regimes climáticos."
    )
    return "\n".join(linhas_tabela) + "\n\n" + "\n\n".join(
        _paragrafo(item) for item in (paragrafo_1, paragrafo_2)
    )


def _pos_processamento(pasta: Path) -> str:
    previsoes = pd.read_csv(
        pasta / "previsoes_teste.csv.gz",
        compression="gzip",
        usecols=(
            "localidade",
            "ghi_real_wm2",
            "previsao_bruta_timesnet_wm2",
            "elevacao_solar_graus",
        ),
    )
    real = previsoes["ghi_real_wm2"].to_numpy(dtype=float)
    bruta = previsoes["previsao_bruta_timesnet_wm2"].to_numpy(dtype=float)
    elevacao = previsoes["elevacao_solar_graus"].to_numpy(dtype=float)
    truncada = np.clip(bruta, 0.0, None)
    pos_processada = np.where(elevacao <= 0, 0.0, truncada)
    negativas = int(np.sum(bruta < 0))
    negativas_noturnas = int(np.sum((bruta < 0) & (elevacao <= 0)))
    negativas_diurnas = negativas - negativas_noturnas
    positivas_noturnas = int(np.sum((truncada > 0) & (elevacao <= 0)))
    media_alvo_noturna = float(np.mean(real[elevacao <= 0]))

    def _rmse_macro(previsao: np.ndarray) -> float:
        quadro = pd.DataFrame(
            {
                "localidade": previsoes["localidade"],
                "erro_quadratico": (real - previsao) ** 2,
            }
        )
        return float(
            np.sqrt(quadro.groupby("localidade")["erro_quadratico"].mean()).mean()
        )

    rmse_bruto = _rmse_macro(bruta)
    rmse_truncado = _rmse_macro(truncada)
    rmse_final = _rmse_macro(pos_processada)
    reducao_conjunta = _percentual_reducao(rmse_bruto, rmse_final)
    aumento_mascara = rmse_final - rmse_truncado
    paragrafo_1 = (
        "No horizonte de 72 h, o TimesNet gerou "
        f"{_inteiro(len(previsoes))} previsões brutas nas dez localidades, das "
        f"quais {_inteiro(negativas)} "
        f"({_decimal(100.0 * negativas / len(previsoes))}\\%) eram negativas. "
        f"Entre as previsões negativas, {_inteiro(negativas_noturnas)} "
        f"({_decimal(100.0 * negativas_noturnas / negativas)}\\%) ocorreram "
        f"fora do período diurno e {_inteiro(negativas_diurnas)} durante ele. "
        "Portanto, esses valores concentram-se nas horas em que a saída "
        "fisicamente esperada está próxima de zero."
    )
    paragrafo_2 = (
        f"O RMSE macro foi {_decimal(rmse_bruto, 3)} W/m$^2$ "
        f"na saída bruta, {_decimal(rmse_truncado, 3)} W/m$^2$ após o truncamento "
        f"e {_decimal(rmse_final, 3)} W/m$^2$ após a máscara. A redução líquida de "
        f"{_decimal(reducao_conjunta)}\\% decorreu do truncamento; isoladamente, a "
        f"máscara elevou o RMSE em {_decimal(aumento_mascara, 3)} W/m$^2$. Ela "
        f"zerou {_inteiro(positivas_noturnas)} estimativas que permaneceram "
        "positivas após o truncamento; contudo, a média da GHI de referência "
        "nessas horas foi "
        f"{_decimal(media_alvo_noturna, 2)} W/m$^2$. Esse resíduo decorre de "
        "intervalos que atravessam o nascer ou o pôr do sol e explica por que "
        "classificar somente pelo centro da hora pode piorar ligeiramente a "
        "métrica."
    )
    return "\n\n".join(_paragrafo(item) for item in (paragrafo_1, paragrafo_2))


def _discussao_curvas(pasta: Path, locais: pd.DataFrame) -> str:
    colunas_modelos = {
        modelo: f"previsao_pos_{slug}_wm2"
        for modelo, slug in {
            "Persistência": "persistencia",
            "Sazonal Ingênuo": "sazonal_ingenuo",
            "LSTM": "lstm",
            "TimesNet": "timesnet",
        }.items()
    }
    previsoes = pd.read_csv(
        pasta / "previsoes_teste.csv.gz",
        compression="gzip",
        usecols=(
            "localidade",
            "passo_h",
            "ghi_real_wm2",
            *colunas_modelos.values(),
        ),
    )
    curvas: dict[str, pd.Series] = {}
    for modelo, coluna in colunas_modelos.items():
        erro_quadratico = (
            previsoes["ghi_real_wm2"].to_numpy(dtype=float)
            - previsoes[coluna].to_numpy(dtype=float)
        ) ** 2
        por_passo = (
            previsoes.assign(erro_quadratico=erro_quadratico)
            .groupby(["localidade", "passo_h"], sort=True)["erro_quadratico"]
            .agg(["sum", "count"])
        )
        por_passo["soma_acumulada"] = por_passo.groupby(level=0)["sum"].cumsum()
        por_passo["n_acumulado"] = por_passo.groupby(level=0)["count"].cumsum()
        por_passo["rmse"] = np.sqrt(
            por_passo["soma_acumulada"] / por_passo["n_acumulado"]
        )
        curvas[modelo] = por_passo.groupby(level=1)["rmse"].mean()
    quadro = pd.DataFrame(curvas).sort_index()
    horizonte_final = int(quadro.index.max())
    def _inicio_dominio(condicao: pd.Series) -> int:
        indices = list(condicao.index)
        for indice in indices:
            if bool(condicao.loc[indice:].all()):
                return int(indice)
        return horizonte_final

    inicio_timesnet_lstm = _inicio_dominio(quadro["TimesNet"] < quadro["LSTM"])
    local_pivo = locais.pivot(index="Localidade", columns="Modelo", values="RMSE_wm2")
    n_timesnet_lstm = int((local_pivo["TimesNet"] < local_pivo["LSTM"]).sum())
    n_timesnet_lstm_texto = (
        "dez" if n_timesnet_lstm == 10 else str(n_timesnet_lstm)
    )

    texto = (
        "Na Fig.~\\ref{fig:comparacao_rmse}(a), o erro inicial próximo de zero "
        "e a não monotonicidade decorrem das origens à meia-noite e da alternância "
        "entre horas diurnas e noturnas. O TimesNet permaneceu abaixo da LSTM a "
        f"partir do prefixo de {inicio_timesnet_lstm} h. No painel (b), seu RMSE "
        f"foi inferior nas {n_timesnet_lstm_texto} localidades, logo a diferença "
        "macro não resulta de uma única localidade."
    )
    return _paragrafo(texto)


def _conclusao(macro: pd.DataFrame) -> str:
    horizonte = 72
    timesnet = _por_modelo_horizonte(macro, "TimesNet", horizonte)
    lstm = _por_modelo_horizonte(macro, "LSTM", horizonte)
    reducao_lstm = _percentual_reducao(
        float(lstm["RMSE_macro_wm2"]),
        float(timesnet["RMSE_macro_wm2"]),
    )
    texto = (
        "Em 72 h, o TimesNet obteve RMSE macro de "
        f"{_decimal(timesnet['RMSE_macro_wm2'])} W/m$^2$, ante "
        f"{_decimal(lstm['RMSE_macro_wm2'])} W/m$^2$ da LSTM, o que corresponde "
        f"a uma redução relativa de {_decimal(reducao_lstm)}\\%. O TimesNet "
        "também apresentou RMSE menor que o da LSTM em 24 e 48 h e que o das "
        "duas referências nos três horizontes, dentro do recorte estudado."
    )
    return _paragrafo(texto)


def _renderizar_figura_comparacao_publicada(pasta: Path) -> bytes:
    """Gera a figura do artigo sem alterar previsões ou artefatos científicos."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    slugs = {
        "Persistência": "persistencia",
        "Sazonal ingênuo": "sazonal_ingenuo",
        "LSTM": "lstm",
        "TimesNet": "timesnet",
    }
    colunas = {
        modelo: f"previsao_pos_{slug}_wm2" for modelo, slug in slugs.items()
    }
    previsoes = pd.read_csv(
        pasta / "previsoes_teste.csv.gz",
        compression="gzip",
        usecols=("localidade", "passo_h", "ghi_real_wm2", *colunas.values()),
    )
    if previsoes.empty or int(previsoes["passo_h"].max()) != 72:
        raise ValueError("Previsões de 72 h ausentes para a figura publicada.")

    curvas: dict[str, pd.Series] = {}
    rmse_locais: dict[str, pd.Series] = {}
    for modelo, coluna in colunas.items():
        erro_quadratico = (previsoes["ghi_real_wm2"] - previsoes[coluna]) ** 2
        por_passo = (
            previsoes.assign(erro_quadratico=erro_quadratico)
            .groupby(["localidade", "passo_h"], sort=True)["erro_quadratico"]
            .agg(["sum", "count"])
        )
        por_passo["soma_acumulada"] = por_passo.groupby(level=0)["sum"].cumsum()
        por_passo["n_acumulado"] = por_passo.groupby(level=0)["count"].cumsum()
        por_passo["rmse_acumulado"] = np.sqrt(
            por_passo["soma_acumulada"] / por_passo["n_acumulado"]
        )
        curvas[modelo] = por_passo.groupby(level=1)["rmse_acumulado"].mean()
        rmse_locais[modelo] = np.sqrt(
            previsoes.assign(erro_quadratico=erro_quadratico)
            .groupby("localidade", sort=True)["erro_quadratico"]
            .mean()
        )

    nomes_locais = {
        "BMW San Luis Potosi": "BMW San Luis Potosí",
        "BYD Camacari": "BYD Camaçari",
        "Ford Rouge Electric Vehicle Center": "Ford Rouge",
        "GM Factory Zero": "GM Factory Zero",
        "Hyundai Metaplant Georgia": "Hyundai Georgia",
        "Lucid AMP 1 Casa Grande": "Lucid Casa Grande",
        "Rivian Normal": "Rivian Normal",
        "Tesla Fremont Factory": "Tesla Fremont",
        "Tesla Gigafactory Nevada": "Tesla Nevada",
        "Tesla Gigafactory Texas": "Tesla Texas",
    }
    cores = {
        "Persistência": "#6F6F6F",
        "Sazonal ingênuo": "#B2B2B2",
        "LSTM": "#009E73",
        "TimesNet": "#245AA5",
    }
    estilos = {
        "Persistência": "--",
        "Sazonal ingênuo": ":",
        "LSTM": "-.",
        "TimesNet": "-",
    }

    with plt.rc_context(
        {
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
        }
    ):
        figura, (eixo_a, eixo_b) = plt.subplots(
            1,
            2,
            figsize=(12.2, 4.7),
            gridspec_kw={"width_ratios": [1.08, 1.0]},
        )

        for modelo in ORDEM_MODELOS_ARTIGO:
            rotulo = NOMES_TABELA[modelo]
            curva = curvas[rotulo]
            destaque = modelo == "TimesNet"
            eixo_a.plot(
                curva.index,
                curva.values,
                color=cores[rotulo],
                linestyle=estilos[rotulo],
                linewidth=2.35 if destaque else 1.5,
                label=rotulo,
                zorder=4 if destaque else 2,
            )
            eixo_a.scatter(
                [24, 48, 72],
                curva.loc[[24, 48, 72]],
                color=cores[rotulo],
                s=20 if destaque else 13,
                zorder=5,
            )
        eixo_a.set(
            title="(a) RMSE por extensão do horizonte",
            xlabel="Extensão do horizonte (h)",
            ylabel=r"RMSE macro (W m$^{-2}$)",
            xlim=(1, 72),
        )
        eixo_a.set_xticks([1, 24, 48, 72])
        eixo_a.grid(alpha=0.18)
        eixo_a.legend(ncol=2, frameon=False, loc="upper left")

        quadro_local = pd.DataFrame(
            {"TimesNet": rmse_locais["TimesNet"], "LSTM": rmse_locais["LSTM"]}
        ).sort_values("TimesNet", ascending=True)
        posicoes = np.arange(len(quadro_local))
        for posicao, (_, linha) in enumerate(quadro_local.iterrows()):
            eixo_b.plot(
                [linha["TimesNet"], linha["LSTM"]],
                [posicao, posicao],
                color="#C8C8C8",
                linewidth=1.15,
                zorder=1,
            )
        eixo_b.scatter(
            quadro_local["TimesNet"],
            posicoes,
            color=cores["TimesNet"],
            marker="s",
            s=34,
            label="TimesNet",
            zorder=4,
        )
        eixo_b.scatter(
            quadro_local["LSTM"],
            posicoes,
            color=cores["LSTM"],
            marker="^",
            s=38,
            label="LSTM",
            zorder=4,
        )
        eixo_b.set(
            title="(b) Comparação neural por localidade em 72 h",
            xlabel=r"RMSE (W m$^{-2}$)",
            yticks=posicoes,
            yticklabels=[
                nomes_locais.get(nome, nome) for nome in quadro_local.index
            ],
        )
        eixo_b.grid(axis="x", alpha=0.18)
        eixo_b.legend(ncol=2, frameon=False, loc="lower right")

        for eixo in (eixo_a, eixo_b):
            eixo.spines["top"].set_visible(False)
            eixo.spines["right"].set_visible(False)

        figura.tight_layout(w_pad=2.0)
        buffer = io.BytesIO()
        figura.savefig(
            buffer,
            format="png",
            dpi=240,
            bbox_inches="tight",
            metadata={"Software": "TCC TimesNet — figura editorial IEEE"},
        )
        plt.close(figura)
    return buffer.getvalue()


def _renderizar_artigo(
    fonte: str,
    pasta_resultados: Path,
) -> str:
    macro, locais = _carregar_metricas(pasta_resultados)
    diurno = _metricas_diurnas(pasta_resultados)
    blocos = {
        "RESULTADOS-ABSTRACT": _abstract(macro),
        "TABELA-MACRO": _tabela_macro(macro),
        "DISCUSSAO-MACRO": _discussao_macro(macro, diurno),
        "DISCUSSAO-LOCAL": _discussao_local(locais),
        "DISCUSSAO-CURVAS": _discussao_curvas(pasta_resultados, locais),
        "POS-PROCESSAMENTO": _pos_processamento(pasta_resultados),
        "CONCLUSAO-RESULTADOS": _conclusao(macro),
    }
    for nome, conteudo in blocos.items():
        fonte = _substituir_bloco(fonte, nome, conteudo)
    return fonte


def _salvar_atomico(caminho: Path, conteudo: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=caminho.parent,
        prefix=f".{caminho.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporario:
        temporario.write(conteudo)
        temporario.flush()
        os.fsync(temporario.fileno())
        nome_temporario = Path(temporario.name)
    nome_temporario.replace(caminho)


def atualizar(
    *,
    pasta_resultados: Path,
    artigo: Path,
    pasta_figuras_destino: Path,
    verificar: bool,
) -> bool:
    fonte = artigo.read_text(encoding="utf-8")
    renderizado = _renderizar_artigo(fonte, pasta_resultados)
    figura_temporal = (
        pasta_resultados / "figuras" / "previsao_horaria_timesnet_72h.png"
    )
    if not figura_temporal.is_file():
        raise FileNotFoundError(f"Figura canônica ausente: {figura_temporal}")
    figuras_renderizadas = {
        "previsao_horaria_timesnet_72h.png": figura_temporal.read_bytes(),
        "comparacao_rmse_modelos.png": _renderizar_figura_comparacao_publicada(
            pasta_resultados
        ),
    }
    if set(figuras_renderizadas) != set(FIGURAS_CANONICAS):
        raise AssertionError("O conjunto de figuras publicadas não é canônico.")
    artigo_atualizado = fonte == renderizado
    figuras_atualizadas = all(
        (pasta_figuras_destino / nome).is_file()
        and (pasta_figuras_destino / nome).read_bytes() == conteudo
        for nome, conteudo in figuras_renderizadas.items()
    )
    if verificar:
        return artigo_atualizado and figuras_atualizadas
    if not artigo_atualizado:
        _salvar_atomico(artigo, renderizado)
    pasta_figuras_destino.mkdir(parents=True, exist_ok=True)
    for nome, conteudo in figuras_renderizadas.items():
        figura_destino = pasta_figuras_destino / nome
        if not figura_destino.is_file() or figura_destino.read_bytes() != conteudo:
            figura_destino.write_bytes(conteudo)
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resultados", type=Path, default=RESULTADOS_PADRAO)
    parser.add_argument("--artigo", type=Path, default=ARTIGO_PADRAO)
    parser.add_argument(
        "--pasta-figuras-destino",
        type=Path,
        default=PASTA_FIGURAS_PADRAO,
    )
    parser.add_argument(
        "--verificar",
        action="store_true",
        help="Não escreve; retorna erro se artigo ou figuras estiverem defasados.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    sincronizado = atualizar(
        pasta_resultados=args.resultados.resolve(),
        artigo=args.artigo.resolve(),
        pasta_figuras_destino=args.pasta_figuras_destino.resolve(),
        verificar=args.verificar,
    )
    if args.verificar and not sincronizado:
        raise SystemExit(
            "O artigo IEEE ou suas figuras estão defasados em relação aos resultados."
        )
    print("Artigo IEEE e figuras sincronizados.")


if __name__ == "__main__":
    main()
