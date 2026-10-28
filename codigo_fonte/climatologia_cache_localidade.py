"""Mesma climatologia canonica, com estatisticas calculadas uma vez por local.

Conserva operacoes, dtype, ordem dos dados, groupby pandas e consultas do
prever_climatologia original. Somente mascara, calendario, tabela e media
global invariantes saem do laco de origens. O cache e local a chamada;
nao atravessa fases, localidades ou niveis de quantizacao.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def prever_climatologia(janelas, series, *, fim_ajuste_exclusivo):
    fim = pd.Timestamp(fim_ajuste_exclusivo)
    por_id = {s.localidade_id: s for s in series}
    resultado = np.empty_like(janelas.y_bruto, dtype=float)
    tabelas = {}
    for linha, localidade_id in enumerate(janelas.localidade_id):
        ident = int(localidade_id)
        if ident not in tabelas:
            serie = por_id[ident]
            mascara = serie.datas < fim
            datas = serie.datas[mascara]
            valores = serie.ghi[mascara].astype(float)
            mensal = serie.frequencia == "ME"
            if mensal:
                chaves = pd.Index(datas.month)
            else:
                chaves = pd.Index(datas.strftime("%m-%d"))
            tabela = pd.Series(valores).groupby(chaves).mean()
            global_media = float(np.mean(valores))
            tabelas[ident] = (mensal, tabela, global_media)
        mensal, tabela, global_media = tabelas[ident]
        if mensal:
            alvo_chaves = [pd.Timestamp(d).month for d in janelas.datas_alvo[linha]]
        else:
            alvo_chaves = [
                pd.Timestamp(d).strftime("%m-%d")
                for d in janelas.datas_alvo[linha]
            ]
        previsoes = []
        for chave in alvo_chaves:
            if chave in tabela.index:
                previsoes.append(float(tabela.loc[chave]))
            elif chave == "02-29" and "02-28" in tabela.index:
                previsoes.append(float(tabela.loc["02-28"]))
            else:
                previsoes.append(global_media)
        resultado[linha] = previsoes
    return resultado
