"""Quantizacao historica das referencias e do ARIMA, com min-max preservado.

Referencias: os valores observados usados como entrada sao quantizados antes
da persistencia, busca anual ou media climatologica. As medias nao sao
arredondadas depois. O controle usa os valores brutos originais, evitando
erro numerico de um min-max seguido da sua inversa (identidade matematica).

ARIMA: nao existe uma separacao supervisionada X/y no ajuste da serie
endogena. Quantizamos a serie historica do ajuste E os contextos filtrados,
mantendo parametros fixos na previsao. Os alvos de validacao e de teste
continuam reais e continuos; previsoes e parametros nao sao quantizados.
Ordens dos modos quantizados devem vir da selecao do controle sem
quantizacao. A contingencia numerica e exatamente a do ARIMA robusto.

Este modulo nao ajusta escalas, nao escolhe configuracoes pelo teste e nao
faz pos-processamento fisico. O chamador fornece Contexto e escalas de
treino, salva contratos e aplica a mesma mascara noturna aos resultados.
"""
from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import numpy as np
import pandas as pd

from codigo_fonte.experimentos import experimento_baselines_adicionais as e
from codigo_fonte.experimentos import experimento_horario_timesnet as h
from codigo_fonte.experimentos import experimento_multirresolucao as m
from codigo_fonte.experimentos import experimento_arima_robusto as arima
from codigo_fonte.modelos.referencias_simples.arima_checkpoint_compacto import compactar_resultado, hash_array
from codigo_fonte.modelos.referencias_simples.climatologia_cache_localidade import prever_climatologia as prever_climatologia_cache
from codigo_fonte.experimentos.quantizacao_timesnet import _validar_niveis, diagnosticar_quantizacao, normalizar_entradas, quantizar_entradas

MODELOS_REFERENCIA = ("Persistencia", "Sazonal ingenuo", "Climatologia")


def _escala(escalas: pd.DataFrame, localidade_id: int) -> tuple[float, float]:
    obrigatorias = {"localidade_id", "minimo_treino_wm2", "amplitude_escala_wm2"}
    if not obrigatorias.issubset(escalas.columns) or escalas.localidade_id.duplicated().any():
        raise ValueError("Escalas incompletas ou duplicadas.")
    por_id = escalas.set_index("localidade_id")
    if localidade_id not in por_id.index:
        raise ValueError("Localidade sem escala de treino.")
    linha = por_id.loc[localidade_id]
    minimo, amplitude = float(linha.minimo_treino_wm2), float(linha.amplitude_escala_wm2)
    if not np.isfinite([minimo, amplitude]).all() or amplitude <= 0:
        raise ValueError("Escala nao finita ou amplitude nao positiva.")
    return minimo, amplitude


def quantizar_historico_bruto(valores, escalas, localidade_id, niveis):
    """Normaliza, quantiza e restaura W/m2; nao escreve no array original."""
    niveis = _validar_niveis(niveis)
    valores = np.asarray(valores)
    if valores.dtype.kind not in "fiu" or not np.isfinite(valores).all():
        raise ValueError("Historico deve conter somente valores finitos.")
    minimo, amplitude = _escala(escalas, int(localidade_id))
    if niveis is None:
        return valores.copy()
    normalizado = (valores.astype(np.float32) - np.float32(minimo)) / np.float32(amplitude)
    return quantizar_entradas(normalizado, niveis).astype(float) * amplitude + minimo


def _fase(particao: str, fase: str | None) -> str:
    if fase is not None:
        if fase not in {"selecao", "refit"}:
            raise ValueError("Fase deve ser selecao ou refit.")
        return fase
    if particao.startswith("validacao"):
        return "selecao"
    if particao.startswith("teste"):
        return "refit"
    raise ValueError("Informe a fase para particao diferente de validacao/teste.")


def corte_fase(ctx, fase: str) -> pd.Timestamp:
    """Corte local: primeira data da validacao/teste, inicio do mes mensal."""
    if fase not in {"selecao", "refit"}:
        raise ValueError("Fase invalida.")
    intervalo = ctx.tarefa.validacao if fase == "selecao" else ctx.tarefa.teste
    corte = pd.Timestamp(intervalo.inicio_origem)
    return corte.to_period("M").start_time if ctx.tarefa.resolucao == "mensal" else corte


def _datas_locais(serie, horaria: bool) -> pd.DatetimeIndex:
    datas = serie.timestamp_local if horaria else serie.datas
    return pd.DatetimeIndex(datas).tz_localize(None)


def prever_climatologia_horaria(janelas, series, *, fim_ajuste_exclusivo):
    """Media fixa por mes-dia-hora local, usando somente historico pre-corte.

    Em 29/2 ausente usa 28/2 na mesma hora. Se outra chave nao existir,
    usa a media historica da hora e, em ultimo caso, a media global.
    Essas regras sao fixas e nao consultam o alvo real ou dados pos-corte.
    """
    corte = pd.Timestamp(fim_ajuste_exclusivo)
    if corte.tz is not None:
        raise ValueError("Corte deve estar em horario local sem fuso.")
    resultado = np.empty((len(janelas.x_bruto), janelas.pred_len), dtype=float)
    passos = pd.to_timedelta(np.arange(janelas.pred_len), unit="h")
    tabelas = {}
    for serie in series:
        datas = _datas_locais(serie, True)
        uso = datas < corte
        if not uso.any():
            raise ValueError(f"Climatologia sem historico: {serie.localidade}")
        datas, valores = datas[uso], np.asarray(serie.ghi[uso], dtype=float)
        if not np.isfinite(valores).all():
            raise ValueError("Historico climatologico nao finito.")
        base = pd.Series(valores)
        tabelas[int(serie.localidade_id)] = (
            base.groupby(pd.Index(datas.strftime("%m-%d-%H"))).mean().to_dict(),
            base.groupby(pd.Index(datas.hour)).mean().to_dict(),
            float(valores.mean()),
        )
    for linha, (ident, origem) in enumerate(zip(janelas.localidade_id, janelas.origem_local, strict=True)):
        origem = pd.Timestamp(origem).tz_localize(None)
        if origem < corte:
            raise ValueError("Climatologia foi ajustada depois da origem avaliada.")
        tabela, por_hora, global_media = tabelas[int(ident)]
        alvos = pd.DatetimeIndex(origem + passos)
        for passo, data in enumerate(alvos):
            chave = data.strftime("%m-%d-%H")
            if chave not in tabela and data.month == 2 and data.day == 29:
                chave = data.replace(day=28).strftime("%m-%d-%H")
            resultado[linha, passo] = tabela.get(chave, por_hora.get(data.hour, global_media))
    return resultado


def previsoes_referencias(ctx, particao: str, niveis=None, *, fase=None,
                         fim_ajuste_exclusivo=None, modelos=None) -> dict[str, np.ndarray]:
    """Retorna previsoes brutas W/m2; y real nunca e quantizado ou consultado."""
    niveis = _validar_niveis(niveis)
    modelos = MODELOS_REFERENCIA if modelos is None else tuple(modelos)
    if not modelos or len(set(modelos)) != len(modelos) or not set(modelos).issubset(MODELOS_REFERENCIA):
        raise ValueError("Referencias desconhecidas ou duplicadas.")
    fase = _fase(particao, fase)
    janelas, escalas = ctx.janelas[particao], ctx.escalas[fase]
    corte = corte_fase(ctx, fase) if fim_ajuste_exclusivo is None else pd.Timestamp(fim_ajuste_exclusivo)
    if corte > corte_fase(ctx, fase):
        raise ValueError("Corte climatologico ultrapassa o fim do ajuste.")
    # Somente x e ghi historico mudam; os arrays y da fonte ficam intactos.
    if niveis is None:
        for serie in ctx.series:
            _escala(escalas, int(serie.localidade_id))
        entradas, series = janelas, ctx.series
    else:
        x = np.empty_like(janelas.x_bruto, dtype=float)
        for ident in np.unique(janelas.localidade_id):
            uso = janelas.localidade_id == ident
            x[uso] = quantizar_historico_bruto(janelas.x_bruto[uso], escalas, ident, niveis)
        # SimpleNamespace evita validar y: inferencia tambem funciona com y=NaN.
        entradas = SimpleNamespace(**{**vars(janelas), "x_bruto": x})
        series = tuple(replace(s, ghi=quantizar_historico_bruto(s.ghi, escalas, s.localidade_id, niveis))
                       for s in ctx.series)
    if ctx.tarefa.resolucao == "horaria":
        funcoes = {
            "Persistencia": lambda: h.prever_persistencia_diaria(entradas),
            "Sazonal ingenuo": lambda: h.prever_sazonal_ingenuo_anual(entradas, series),
            "Climatologia": lambda: prever_climatologia_horaria(entradas, series, fim_ajuste_exclusivo=corte),
        }
    else:
        funcoes = {
            "Persistencia": lambda: m.prever_persistencia(entradas),
            "Sazonal ingenuo": lambda: m.prever_sazonal_anual(entradas, series),
            "Climatologia": lambda: prever_climatologia_cache(entradas, series, fim_ajuste_exclusivo=corte),
        }
    return {modelo: funcoes[modelo]() for modelo in modelos}


def _particao(ctx, tipo: str) -> str:
    chaves = [p for p in ctx.janelas if p == tipo or p.startswith(tipo + "_")]
    if len(chaves) != 1:
        raise ValueError(f"Esperada uma particao {tipo}; encontradas {chaves}.")
    return chaves[0]


def _ordem(valor) -> tuple[int, int, int]:
    if isinstance(valor, str):
        valor = ast.literal_eval(valor)
    if not isinstance(valor, (tuple, list)) or len(valor) != 3:
        raise ValueError("Ordem ARIMA deve ter tres inteiros.")
    if any(isinstance(x, bool) or not isinstance(x, (int, np.integer)) or x < 0 for x in valor):
        raise ValueError("Ordem ARIMA invalida.")
    return tuple(int(x) for x in valor)


def ordens_de_csv(caminho: str | Path) -> dict[str, tuple[int, int, int]]:
    """Le somente ordens de selecao explicita; rejeita duplicidade/ambiguidade."""
    quadro = pd.read_csv(caminho)
    if not {"fase", "selecionada", "localidade", "ordem"}.issubset(quadro.columns):
        raise ValueError("CSV nao contem selecao ARIMA explicita.")
    escolhidas = quadro[(quadro.fase == "selecao") &
                         (quadro.selecionada.astype(str).str.lower() == "true")]
    if escolhidas.empty or escolhidas.localidade.duplicated().any():
        raise ValueError("Ordens de controle ausentes ou duplicadas.")
    return {str(r.localidade): _ordem(r.ordem) for r in escolhidas.itertuples()}


def _ordem_local(ordens: Mapping, serie) -> tuple[int, int, int]:
    for chave in (serie.localidade, str(serie.localidade_id), serie.localidade_id):
        if chave in ordens:
            return _ordem(ordens[chave])
    raise ValueError(f"Ordem de controle ausente: {serie.localidade}")


def selecionar_arima(ctx, niveis=None, pasta=None, ordens_fixas=None) -> dict[str, Any]:
    """Ajusta e avalia ARIMA em validacao; nenhum objeto do teste e acessado.

    Sem ordens_fixas, somente o controle pode selecionar ORDENS_ARIMA pelo
    MSE normalizado continuo. Todos os niveis usam as ordens desse controle.
    Checkpoints por localidade guardam modelo, escala, nivel e ordem.
    """
    niveis = _validar_niveis(niveis)
    if niveis is not None and ordens_fixas is None:
        raise ValueError("Quantizacao exige ordens fixadas pela validacao do controle.")
    particao = _particao(ctx, "validacao")
    janelas = ctx.janelas[particao]
    escalas = ctx.escalas["selecao"]
    x = normalizar_entradas(janelas, escalas, niveis)
    _, y = janelas.normalizar(escalas)  # continuo, somente selecao
    previstos = np.empty_like(y, dtype=float)
    registros, ordens, diagnosticos = [], {}, []
    for serie in ctx.series:
        ident = int(serie.localidade_id)
        mascara = janelas.localidade_id == ident
        if not mascara.any():
            raise ValueError(f"Localidade sem origens de validacao: {serie.localidade}")
        historico = e.serie_ajuste_arima(ctx, serie, "selecao")
        transformado = quantizar_entradas(historico, niveis)
        diagnosticos.append({"localidade": serie.localidade, "uso": "serie_ajuste_endogena",
                             **diagnosticar_quantizacao(historico, niveis)})
        candidatos = [_ordem_local(ordens_fixas, serie)] if ordens_fixas is not None else e.ORDENS_ARIMA
        melhor = None
        detalhes = []
        for ordem in candidatos:
            reg = {"localidade": serie.localidade, "localidade_id": ident,
                   "ordem": list(ordem), "fase": "selecao"}
            try:
                ajustado, tentativas = arima.ajustar(transformado, ordem)
                pred = e.previsoes_arima_fixos(ajustado, x[mascara], ctx.tarefa.pred_len)
                mse = float(np.mean((pred - y[mascara]) ** 2))
                if not np.isfinite(mse):
                    raise ValueError("MSE de validacao nao finito.")
                reg.update(convergiu=True, mse_validacao_normalizado=mse, tentativas=tentativas)
                if melhor is None or mse < melhor[0]:
                    melhor = (mse, ordem, pred, ajustado)
            except (ValueError, RuntimeError, np.linalg.LinAlgError) as erro:
                reg.update(convergiu=False, erro=str(erro))
            detalhes.append(reg)
        if melhor is None:
            raise RuntimeError(f"ARIMA sem ajuste valido em {serie.localidade}: {detalhes}")
        _, ordem, pred, ajustado = melhor
        previstos[mascara] = pred
        ordens[serie.localidade] = list(ordem)
        for r in detalhes:
            r["selecionada"] = r["ordem"] == list(ordem)
        registros.extend(detalhes)
        if pasta is not None:
            cp = {"modelo": compactar_resultado(ajustado), "niveis": niveis, "fase": "selecao",
                  "ordem": list(ordem), "localidade_id": ident,
                  "escalas": escalas.copy(), "serie_ajuste_quantizada": transformado,
                  "sha256_serie_ajuste_quantizada": hash_array(transformado)}
            m.salvar_joblib_atomico(cp, Path(pasta) / "modelos" / f"localidade{ident}_selecao.joblib")
    return {"previsao_bruta": janelas.inverter(previstos, escalas), "ordens": ordens,
            "registros": registros, "diagnosticos": diagnosticos, "niveis": niveis,
            "ordens_fixas_do_controle": ordens_fixas is not None}


def refit_arima(ctx, niveis, pasta, selecao: Mapping) -> dict[str, Any]:
    """Refaz ajuste na serie pre-teste e filtra cada contexto com ordem fixa."""
    niveis = _validar_niveis(niveis)
    if selecao.get("niveis") != niveis:
        raise ValueError("Nivel diverge da selecao congelada.")
    ordens = selecao["ordens"]
    particao = _particao(ctx, "teste")
    janelas, escalas = ctx.janelas[particao], ctx.escalas["refit"]
    x = normalizar_entradas(janelas, escalas, niveis)
    previstos = np.empty((len(x), ctx.tarefa.pred_len), dtype=float)
    registros, diagnosticos = [], []
    for serie in ctx.series:
        ident = int(serie.localidade_id)
        mascara = janelas.localidade_id == ident
        if not mascara.any():
            raise ValueError(f"Localidade sem origens de teste: {serie.localidade}")
        ordem = _ordem_local(ordens, serie)
        historico = e.serie_ajuste_arima(ctx, serie, "refit")
        transformado = quantizar_entradas(historico, niveis)
        diagnosticos.append({"localidade": serie.localidade, "uso": "serie_ajuste_endogena",
                             **diagnosticar_quantizacao(historico, niveis)})
        ajustado, tentativas = arima.ajustar(transformado, ordem)
        previstos[mascara] = e.previsoes_arima_fixos(ajustado, x[mascara], ctx.tarefa.pred_len)
        registros.append({"localidade": serie.localidade, "localidade_id": ident,
                          "ordem": list(ordem), "fase": "refit", "tentativas": tentativas,
                          "n_refit": len(historico)})
        if pasta is not None:
            cp = {"modelo": compactar_resultado(ajustado), "niveis": niveis, "fase": "refit",
                  "ordem": list(ordem), "localidade_id": ident,
                  "escalas": escalas.copy(), "serie_ajuste_quantizada": transformado,
                  "sha256_serie_ajuste_quantizada": hash_array(transformado)}
            m.salvar_joblib_atomico(cp, Path(pasta) / "modelos" / f"localidade{ident}_refit.joblib")
    return {"previsao_bruta": janelas.inverter(previstos, escalas), "ordens": dict(ordens),
            "registros": registros, "diagnosticos": diagnosticos, "niveis": niveis}


def prever_checkpoint_arima(checkpoint, janelas) -> np.ndarray:
    """Reproduz somente as linhas da localidade do checkpoint sem consultar y."""
    ident = checkpoint["localidade_id"]
    mascara = janelas.localidade_id == ident
    x = normalizar_entradas(janelas, checkpoint["escalas"], checkpoint["niveis"])
    previsto = e.previsoes_arima_fixos(checkpoint["modelo"], x[mascara], janelas.pred_len)
    minimo, amplitude = _escala(checkpoint["escalas"], ident)
    return previsto * amplitude + minimo


def protocolo_referencias() -> dict[str, Any]:
    return {
        "quantizacao": "minmax_treino_seguido_clip_0_1_rint_Nmenos1_so_historico",
        "controle": "identidade_minmax_inversa_valores_originais_sem_roundtrip",
        "alvos_metricas": "continuos_observados_sem_quantizacao",
        "persistencia_horaria": "repete_ultimas_24_horas",
        "persistencia_diaria_mensal": "repete_ultima_observacao",
        "sazonal": "mesma_data_hora_ano_anterior_29fev_mapeado28fev_causal",
        "climatologia_horaria": "media_mes_dia_hora_local_antes_corte",
        "climatologia_diaria": "media_mes_dia_antes_corte",
        "climatologia_mensal": "media_mes_antes_corte",
        "climatologia_quantizacao": "quantiza_historico_antes_media_saida_continua",
        "arima_quantizacao": "serie_endogena_de_ajuste_e_contextos_filtragem",
        "arima_ordens": "controle_seleciona_validacao_MSE_normalizado_demais_niveis_fixam",
        "arima_numerico": [list(x) for x in arima.OTIMIZADORES],
        "arima_inferencia": "apply_refitFalse_na_mesma_janela_limitada",
        "arima_checkpoint": "especificacao_parametros_covariancia_evidencia_fit_historico_hash_sem_estados_longos",
    }
