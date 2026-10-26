"""Busca temporal isolada da TimesNet; resultados canonicos nunca sao alterados."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import torch

from codigo_fonte import experimento_multirresolucao as base
from codigo_fonte.treinamento_timesnet_otimizacao import treinar_candidato


@dataclass(frozen=True)
class Candidato:
    nome: str
    seq_len: int = 12
    perda: str = "mse"
    taxa_aprendizado: float = 1e-3
    d_model: int = 8
    d_ff: int = 16
    blocos: int = 1
    dropout: float = 0.1
    alvo: str = "bruto"

    def __post_init__(self) -> None:
        if not self.nome or not all(c.isalnum() or c in "_-" for c in self.nome):
            raise ValueError("Nome do candidato deve ser um identificador simples.")
        if self.perda not in {"mse", "mae", "huber"}:
            raise ValueError("Perda deve ser mse, mae ou huber.")
        if self.alvo not in {"bruto", "anomalia"}:
            raise ValueError("Alvo deve ser bruto ou anomalia.")
        if self.seq_len < 12 or self.d_model < 2 or self.d_model % 2:
            raise ValueError("Contexto deve ter >=12 meses e d_model deve ser par.")
        if self.d_ff < 1 or self.blocos < 1:
            raise ValueError("Dimensoes devem ser positivas.")
        if not np.isfinite(self.taxa_aprendizado) or self.taxa_aprendizado <= 0:
            raise ValueError("Taxa de aprendizado deve ser positiva e finita.")
        if not 0 <= self.dropout < 1:
            raise ValueError("Dropout deve pertencer a [0, 1).")

    def configurar(self, config: base.ConfiguracaoMultirresolucao):
        return replace(
            config, taxa_aprendizado=self.taxa_aprendizado,
            timesnet_d_model=self.d_model, timesnet_d_ff=self.d_ff,
            timesnet_blocos=self.blocos, timesnet_dropout=self.dropout,
        )


def candidatos_padrao() -> tuple[Candidato, ...]:
    """Busca de hiperparametros da TimesNet pura, sem alvo residual ou climatologia."""
    return (
        Candidato("referencia_mse"),
        Candidato("mae", perda="mae"),
        Candidato("huber", perda="huber"),
        Candidato("mae_lr_0003", perda="mae", taxa_aprendizado=3e-4),
        Candidato("mae_dim16", perda="mae", d_model=16, d_ff=32),
        Candidato("mae_dim16_lr_0003", perda="mae", d_model=16, d_ff=32,
                  taxa_aprendizado=3e-4),
        Candidato("mae_dois_blocos", perda="mae", d_model=16, d_ff=32, blocos=2),
        Candidato("mae_contexto24", perda="mae", seq_len=24),
        Candidato("mae_contexto36", perda="mae", seq_len=36),
    )


def adaptar_tarefa(
    tarefa: base.EspecificacaoTarefa, series: Sequence[base.SerieResolucao],
    seq_len: int, *, minimo_origens: int = 18, inicio_ajuste: str = "2020-01-31",
) -> base.EspecificacaoTarefa:
    """Declara explicitamente as janelas perdidas ao aumentar o contexto.

    Treino usa todas as origens admissiveis; validacao e teste ficam fixos.
    Logo, contexto e quantidade de treino variam juntos nesta busca.
    """
    if tarefa.resolucao != "mensal" or minimo_origens < 1:
        raise ValueError("A busca exige tarefa mensal e minimo_origens positivo.")
    inicio_solicitado = pd.Timestamp(inicio_ajuste)
    if inicio_solicitado != inicio_solicitado + pd.offsets.MonthEnd(0):
        raise ValueError("inicio_ajuste deve ser o ultimo dia de um mes.")
    if any(len(s.datas) <= seq_len for s in series):
        raise ValueError("Historico insuficiente para o contexto.")
    primeiro = max(inicio_solicitado, *(s.datas[seq_len] for s in series))

    def intervalo(original: base.IntervaloParticao) -> base.IntervaloParticao:
        fim = pd.Timestamp(original.fim_origem)
        n = len(pd.date_range(primeiro, fim, freq="ME"))
        if n < minimo_origens:
            raise ValueError(f"Contexto {seq_len}: apenas {n} origens por local; minimo {minimo_origens}.")
        return replace(original, inicio_origem=primeiro.date().isoformat(),
                       origens_esperadas_por_localidade=n)

    if primeiro > pd.Timestamp(tarefa.ajuste.fim_origem):
        raise ValueError("Nao restam origens de ajuste anteriores a validacao.")
    return replace(tarefa, seq_len=seq_len, ajuste=intervalo(tarefa.ajuste),
                   refit=intervalo(tarefa.refit))


def macro_mae(janelas: base.JanelasDiretas, bruto: np.ndarray) -> float:
    bruto = np.asarray(bruto, dtype=float)
    if bruto.shape != janelas.y_bruto.shape or not np.isfinite(bruto).all():
        raise ValueError("Previsao fisica invalida.")
    previsto = np.maximum(bruto, 0.0)
    erros = np.abs(previsto - janelas.y_bruto)
    return float(np.mean([erros[janelas.localidade_id == i].mean()
                          for i in np.unique(janelas.localidade_id)]))


def climatologia_mensal(series, *, fim_exclusivo) -> dict[int, np.ndarray]:
    """Media de cada mes civil por localidade, ajustada so antes do corte.

    Reproduz a baseline `prever_climatologia`, inclusive o recurso a media geral
    quando um mes nao aparece no historico pre-corte.
    """
    fim = pd.Timestamp(fim_exclusivo)
    tabela: dict[int, np.ndarray] = {}
    for serie in series:
        mascara = serie.datas < fim
        valores = serie.ghi[mascara].astype(float)
        if len(valores) < 1:
            raise ValueError(f"Sem dado pre-corte em {serie.localidade}.")
        medias = pd.Series(valores).groupby(pd.Index(serie.datas[mascara].month)).mean()
        por_mes = np.full(12, float(np.mean(valores)))
        for mes, media in medias.items():
            por_mes[int(mes) - 1] = float(media)
        tabela[int(serie.localidade_id)] = por_mes
    return tabela


def _aplicar_tabela(tabela, localidade_id, meses) -> np.ndarray:
    saida = np.empty(meses.shape, dtype=float)
    ids = np.asarray(localidade_id, dtype=int)
    for identificador in np.unique(ids):
        if int(identificador) not in tabela:
            raise ValueError(f"Localidade {identificador} ausente na climatologia.")
        linhas = ids == identificador
        saida[linhas] = tabela[int(identificador)][meses[linhas] - 1]
    return saida


def climatologia_nas_janelas(janelas, tabela) -> tuple[np.ndarray, np.ndarray]:
    """Climatologia nas posicoes de contexto e de alvo de cada janela.

    A grade e mensal e regular, entao o mes de cada posicao de contexto vem da
    origem por aritmetica de calendario, sem depender de deslocamentos de data.
    """
    meses_alvo = pd.DatetimeIndex(
        np.asarray(janelas.datas_alvo).reshape(-1)
    ).month.to_numpy().reshape(janelas.datas_alvo.shape)
    passos = np.arange(janelas.seq_len, 0, -1)[None, :]
    meses_contexto = ((janelas.origem.month.to_numpy()[:, None] - 1 - passos) % 12) + 1
    return (_aplicar_tabela(tabela, janelas.localidade_id, meses_contexto),
            _aplicar_tabela(tabela, janelas.localidade_id, meses_alvo))


def escalas_anomalia(janelas, nome_ajuste: str, fim_exclusivo) -> pd.DataFrame:
    """Min--max das anomalias de ajuste; nenhuma janela posterior ao corte entra."""
    linhas = []
    fim = pd.Timestamp(fim_exclusivo)
    if bool((janelas.datas_alvo >= np.datetime64(fim)).any()):
        raise ValueError("Escalas de anomalia nao podem usar alvos posteriores ao corte.")
    ids = np.asarray(janelas.localidade_id, dtype=int)
    for identificador in np.unique(ids):
        recorte = ids == identificador
        valores = np.concatenate([janelas.x_bruto[recorte].reshape(-1),
                                  janelas.y_bruto[recorte].reshape(-1)]).astype(float)
        minimo, maximo = float(np.min(valores)), float(np.max(valores))
        amplitude = maximo - minimo
        linhas.append({
            "ajuste": nome_ajuste, "localidade": str(janelas.localidade[recorte][0]),
            "localidade_id": int(identificador), "fim_exclusivo": fim.isoformat(),
            "N_observacoes": int(valores.size),
            "minimo_treino_wm2": minimo, "maximo_treino_wm2": maximo,
            "amplitude_real_wm2": amplitude,
            "amplitude_escala_wm2": amplitude if amplitude > 0 else 1.0,
        })
    return pd.DataFrame(linhas)


def preparar_treino(candidato, series, ajuste, avaliacao, *, fim_exclusivo, nome_ajuste):
    """Devolve janelas de treino, escalas e a parcela conhecida da previsao.

    No alvo bruto nada muda. No alvo anomalia, a rede recebe o desvio em relacao
    a climatologia e a previsao fisica volta somando essa climatologia.
    """
    if candidato.alvo == "bruto":
        escalas = base.ajustar_escalas_pre_corte(series, fim_exclusivo=fim_exclusivo,
                                                 nome_ajuste=nome_ajuste)
        return ajuste, avaliacao, escalas, None
    tabela = climatologia_mensal(series, fim_exclusivo=fim_exclusivo)
    contexto_ajuste, alvo_ajuste = climatologia_nas_janelas(ajuste, tabela)
    contexto_avaliacao, alvo_avaliacao = climatologia_nas_janelas(avaliacao, tabela)
    ajuste_anomalia = replace(ajuste, x_bruto=(ajuste.x_bruto - contexto_ajuste).astype(np.float32),
                              y_bruto=(ajuste.y_bruto - alvo_ajuste).astype(np.float32))
    avaliacao_anomalia = replace(
        avaliacao, x_bruto=(avaliacao.x_bruto - contexto_avaliacao).astype(np.float32),
        y_bruto=(avaliacao.y_bruto - alvo_avaliacao).astype(np.float32))
    return (ajuste_anomalia, avaliacao_anomalia,
            escalas_anomalia(ajuste_anomalia, nome_ajuste, fim_exclusivo), alvo_avaliacao)


def _janelas(series, tarefa, particao, config):
    return base.construir_janelas(
        series, seq_len=tarefa.seq_len, pred_len=tarefa.pred_len,
        intervalo=getattr(tarefa, particao), particao=particao,
        limite_origens_por_localidade=(config.limite_origens_smoke
                                      if config.modo_execucao == "smoke" else None),
    )


def _prever(modelo, janelas, escalas, config):
    x, _ = janelas.normalizar(escalas)
    normalizada = base.prever_rede(modelo, x, janelas.localidade_id,
                                 batch_size=config.batch_size_mensal)
    return janelas.inverter(normalizada, escalas)


def _contrato(series, candidatos, config, tarefa, minimo, inicio):
    arquivos_codigo = [Path(__file__), Path(base.__file__),
                       Path(__file__).with_name("treinamento_timesnet_otimizacao.py"),
                       Path(__file__).with_name("timesnet_horario.py")]
    contrato = {
        "versao": 1, "tarefa": tarefa, "configuracao": asdict(config),
        "candidatos": [asdict(c) for c in candidatos],
        "minimo_origens_ajuste": minimo, "inicio_ajuste_solicitado": inicio,
        "criterio": "macro_MAE_fisico_ensemble_validacao_2023_com_piso_zero",
        "epocas": "macro_MAE_fisico_individual_validacao_2023",
        "quantizacao": False, "huber_delta_normalizado": 0.1,
        "python": platform.python_version(), "torch": torch.__version__,
        "numpy": np.__version__, "pandas": pd.__version__,
        "entradas": [{"arquivo": str(s.caminho_fonte.resolve()),
                       "sha256": base.sha256_arquivo(s.caminho_fonte),
                       "localidade": s.localidade, "id": s.localidade_id,
                       "inicio": str(s.datas.min()), "fim": str(s.datas.max())}
                      for s in series],
        "codigo": {p.name: base.sha256_arquivo(p) for p in arquivos_codigo},
        "limitacoes": [
            "Busca dirigida motivada por resultados de 2024 ja observados; requer confirmacao futura.",
            "Janelas maiores podem reduzir o numero de origens de treino; nao e ablacao isolada de contexto.",
            "Mesmo ano de validacao seleciona epocas e hiperparametros; risco de sobreajuste a validacao.",
            "Mensal de seis passos tem sete origens de teste sobrepostas por localidade.",
        ],
    }
    if any(c.alvo == "anomalia" for c in candidatos):
        contrato["climatologia_anomalia"] = "media_por_mes_civil_por_localidade_ajustada_pre_corte"
        contrato["limitacoes"].append(
            "Candidatos de anomalia preveem o desvio em relacao a climatologia; a previsao "
            "publicada soma de volta essa climatologia e so depois aplica o piso zero.")
    # Sem este resumo a retomada aceitaria uma pasta escrita sob outra configuracao.
    serializado = json.dumps(contrato, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    contrato["sha256_contrato"] = hashlib.sha256(serializado.encode("utf-8")).hexdigest()
    return contrato


def _cache_selecao(pasta, tarefa, candidato, config, semente, ajuste, validacao, escalas,
                   deslocamento=None):
    """A previsao em cache e sempre GHI, qualquer que seja o alvo do candidato."""
    cache = pasta / "candidatos" / candidato.nome / f"seed{semente}.npz"
    if cache.exists():
        with np.load(cache, allow_pickle=False) as dados:
            return dados["previsao"], int(dados["epocas"].item())
    print(f"[{tarefa.slug}] validacao {candidato.nome}, seed={semente}", flush=True)
    modelo, epocas, historico = treinar_candidato(
        tarefa=tarefa, configuracao=config, semente=semente, ajuste=ajuste,
        validacao=validacao, escalas=escalas, perda=candidato.perda,
        deslocamento_validacao=deslocamento,
    )
    bruto = _prever(modelo, validacao, escalas, config)
    if deslocamento is not None:
        bruto = bruto + deslocamento
    base.salvar_csv_atomico(historico, cache.with_suffix(".csv"))
    base.salvar_npz_atomico(cache, previsao=bruto, epocas=np.asarray(epocas))
    return bruto, epocas


def selecionar(
    *, series, tarefa, candidatos, configuracao, pasta, minimo_origens=18,
    inicio_ajuste="2020-01-31",
):
    """Seleciona sem construir janelas de teste nem ajustar escalas de refit."""
    # A propria funcao remove 2024 da visao usada pelo treinamento.
    series = tuple(replace(s, datas=s.datas[s.datas < "2024-01-01"],
                           ghi=s.ghi[s.datas < "2024-01-01"]) for s in series)
    escalas = base.ajustar_escalas_pre_corte(series, fim_exclusivo="2023-01-01",
                                          nome_ajuste="selecao")
    base.salvar_csv_atomico(escalas, pasta / "escalas_selecao.csv")
    ranking, rejeitados, sementes_linhas = [], [], []
    alinhamento = None
    resultados = {}
    for candidato in candidatos:
        try:
            especificacao = adaptar_tarefa(tarefa, series, candidato.seq_len,
                                           minimo_origens=minimo_origens, inicio_ajuste=inicio_ajuste)
        except ValueError as erro:
            rejeitados.append({"candidato": candidato.nome, "motivo": str(erro)})
            continue
        config = candidato.configurar(configuracao)
        ajuste = _janelas(series, especificacao, "ajuste", config)
        validacao = _janelas(series, especificacao, "validacao", config)
        chaves = (validacao.origem.asi8, validacao.localidade_id, validacao.datas_alvo,
                  validacao.y_bruto)
        if alinhamento is not None and any(not np.array_equal(a, b) for a, b in zip(alinhamento, chaves)):
            raise AssertionError("Os candidatos devem compartilhar alvos e origens de validacao.")
        alinhamento = chaves
        base.salvar_json_atomico(asdict(especificacao), pasta / "candidatos" / candidato.nome / "protocolo.json")
        ajuste_treino, validacao_treino, escalas_treino, deslocamento = preparar_treino(
            candidato, series, ajuste, validacao,
            fim_exclusivo="2023-01-01", nome_ajuste="selecao")
        if candidato.alvo != "bruto":
            base.salvar_csv_atomico(escalas_treino,
                                    pasta / "candidatos" / candidato.nome / "escalas.csv")
        previsoes, epocas, maes = [], {}, []
        for semente in config.sementes_efetivas:
            bruto, n = _cache_selecao(pasta, especificacao, candidato, config, semente,
                                     ajuste_treino, validacao_treino, escalas_treino,
                                     deslocamento)
            previsoes.append(bruto)
            epocas[str(semente)] = n
            maes.append(macro_mae(validacao, bruto))
            sementes_linhas.append({"candidato": candidato.nome, "semente": semente,
                                   "epocas": n, "MAE_validacao_wm2": maes[-1]})
        media_bruta = np.mean(previsoes, axis=0)
        ranking.append({**asdict(candidato), "MAE_validacao_ensemble_wm2": macro_mae(validacao, media_bruta),
                        "MAE_validacao_media_sementes_wm2": float(np.mean(maes)),
                        "DP_MAE_sementes_wm2": float(np.std(maes, ddof=1)) if len(maes) > 1 else 0.,
                        "origens_ajuste_por_local": len(ajuste.x_bruto) // len(series),
                        "origens_validacao_por_local": len(validacao.x_bruto) // len(series),
                        "epocas": epocas})
        resultados[candidato.nome] = (especificacao, config, validacao, media_bruta)
        base.salvar_csv_atomico(pd.DataFrame(ranking).drop(columns="epocas"), pasta / "ranking_validacao.csv")
    base.salvar_json_atomico(rejeitados, pasta / "candidatos_descartados.json")
    if not ranking:
        raise ValueError("Nenhum candidato tem historico suficiente; consulte candidatos_descartados.json.")
    # Desempate deterministico por nome, nunca pelo resultado no teste.
    ranking.sort(key=lambda r: (r["MAE_validacao_ensemble_wm2"], r["nome"]))
    vencedor = ranking[0]
    base.salvar_csv_atomico(pd.DataFrame(ranking).drop(columns="epocas"), pasta / "ranking_validacao.csv")
    base.salvar_csv_atomico(pd.DataFrame(sementes_linhas), pasta / "selecao_por_semente.csv")
    tarefa_final, _, jval, bruto = resultados[vencedor["nome"]]
    estimativas = [base.Estimativa("TimesNet", "ensemble", None, bruto, np.maximum(bruto, 0))]
    for nome, previsto in base.previsoes_baselines(jval, series, fim_ajuste_exclusivo="2023-01-01").items():
        estimativas.append(base.Estimativa(nome, "deterministica", None, previsto, np.maximum(previsto, 0)))
    local, macro = base.calcular_metricas_estimativas(tarefa=tarefa_final, particao="validacao_2023",
                                                     janelas=jval, estimativas=estimativas)
    base.salvar_csv_atomico(local, pasta / "metricas_validacao_por_localidade.csv")
    base.salvar_csv_atomico(macro, pasta / "metricas_validacao_macro.csv")
    base.salvar_csv_atomico(base.montar_tabela_previsoes(tarefa=tarefa_final, janelas=jval, estimativas=estimativas),
                           pasta / "previsoes_validacao.csv")
    congelado = {"vencedor": vencedor, "tarefa": asdict(tarefa_final),
                 "selecao_concluida_antes_do_teste": True,
                 "criterio": "menor_macro_MAE_fisico_do_ensemble_na_validacao_2023"}
    base.salvar_json_atomico(congelado, pasta / "selecao_congelada.json")
    return congelado


def prever_checkpoint(caminho: str | Path, janelas: base.JanelasDiretas) -> np.ndarray:
    """Recarrega pesos e transformacoes congeladas, sem ler os CSVs de treino.

    Retorna GHI bruto em W/m2; o ensemble deve ser promediado antes do piso zero.
    Os alvos das janelas servem apenas para a estrutura de saida, nao a inferencia.
    Checkpoints antigos exigem reconstruir as transformacoes com os insumos
    originais; nunca se estima uma nova escala usando os dados de previsao.
    """
    checkpoint = torch.load(caminho, map_location="cpu", weights_only=True)
    if "preprocessamento" not in checkpoint:
        raise ValueError("Checkpoint antigo sem preprocessamento; use seus insumos originais.")
    prep = checkpoint["preprocessamento"]
    if prep.get("versao") != 1:
        raise ValueError("Versao de preprocessamento desconhecida.")
    especificacao = dict(checkpoint["tarefa"])
    for particao in ("ajuste", "validacao", "refit", "teste"):
        especificacao[particao] = base.IntervaloParticao(**especificacao[particao])
    tarefa = base.EspecificacaoTarefa(**especificacao)
    if (janelas.seq_len, janelas.pred_len) != (tarefa.seq_len, tarefa.pred_len):
        raise ValueError("Contexto ou horizonte diferente do checkpoint.")
    for identificador, nome in zip(janelas.localidade_id, janelas.localidade):
        if prep["localidades"].get(str(int(identificador))) != str(nome):
            raise ValueError("Identidade de localidade diferente do checkpoint.")
    config = base.ConfiguracaoMultirresolucao(**checkpoint["configuracao"])
    modelo = base.criar_modelo_neural(
        "TimesNet", tarefa=tarefa, configuracao=config,
        num_localidades=max(int(i) for i in prep["localidades"]) + 1,
        semente=int(checkpoint["semente"]),
    )
    modelo.load_state_dict(checkpoint["state_dict"])
    escalas = pd.DataFrame(prep["escalas"])
    deslocamento = None
    entrada = janelas
    if checkpoint["candidato"]["alvo"] == "anomalia":
        if prep["climatologia"] is None:
            raise ValueError("Climatologia de refit ausente no checkpoint de anomalia.")
        tabela = {int(i): np.asarray(v, dtype=float) for i, v in prep["climatologia"].items()}
        contexto, deslocamento = climatologia_nas_janelas(janelas, tabela)
        entrada = replace(janelas, x_bruto=(janelas.x_bruto - contexto).astype(np.float32))
    bruto = _prever(modelo, entrada, escalas, config)
    if deslocamento is not None:
        bruto = bruto + deslocamento
    if not np.isfinite(bruto).all():
        raise ValueError("Previsao nao finita ao recarregar checkpoint.")
    return bruto


def avaliar_vencedor(*, series, tarefa, candidato, configuracao, pasta, epocas,
                    minimo_origens=18, inicio_ajuste="2020-01-31"):
    """Refaz somente o vencedor; nenhuma metrica de teste retorna ao seletor."""
    config = candidato.configurar(configuracao)
    tarefa = adaptar_tarefa(tarefa, series, candidato.seq_len, minimo_origens=minimo_origens,
                            inicio_ajuste=inicio_ajuste)
    refit = _janelas(series, tarefa, "refit", config)
    teste = _janelas(series, tarefa, "teste", config)
    refit_treino, teste_treino, escalas, deslocamento = preparar_treino(
        candidato, series, refit, teste, fim_exclusivo="2024-01-01", nome_ajuste="refit")
    base.salvar_csv_atomico(escalas, pasta / "escalas_refit.csv")
    tabela = (climatologia_mensal(series, fim_exclusivo="2024-01-01")
              if candidato.alvo == "anomalia" else None)
    preprocessamento = {
        "versao": 1, "fim_ajuste_exclusivo": "2024-01-01",
        "escalas": escalas.to_dict(orient="records"),
        "climatologia": ({str(i): v.tolist() for i, v in tabela.items()}
                          if tabela is not None else None),
        "localidades": {str(s.localidade_id): s.localidade for s in series},
    }
    base.salvar_json_atomico(preprocessamento, pasta / "preprocessamento_refit.json")
    estimativas, brutas = [], []
    for semente in config.sementes_efetivas:
        cache = pasta / "refit" / f"seed{semente}.npz"
        if cache.exists():
            with np.load(cache, allow_pickle=False) as dados:
                bruto = dados["previsao"]
        else:
            print(f"[{tarefa.slug}] refit vencedor={candidato.nome}, seed={semente}", flush=True)
            modelo, n, historico = treinar_candidato(
                tarefa=tarefa, configuracao=config, semente=semente, ajuste=refit_treino,
                escalas=escalas, perda=candidato.perda, epocas_fixas=int(epocas[str(semente)]),
            )
            bruto = _prever(modelo, teste_treino, escalas, config)
            if deslocamento is not None:
                bruto = bruto + deslocamento
            base.salvar_torch_atomico({"state_dict": modelo.state_dict(), "tarefa": asdict(tarefa),
                                      "configuracao": asdict(config), "candidato": asdict(candidato),
                                      "semente": semente, "epocas_refit": n,
                                      "preprocessamento": preprocessamento},
                                     pasta / "modelos" / f"timesnet_seed{semente}_refit.pt")
            base.salvar_csv_atomico(historico, cache.with_suffix(".csv"))
            base.salvar_npz_atomico(cache, previsao=bruto, epocas=np.asarray(n))
        macro_mae(teste, bruto)  # valida forma e finitude tambem ao retomar
        brutas.append(bruto)
        estimativas.append(base.Estimativa("TimesNet", "semente", semente, bruto, np.maximum(bruto, 0)))
    ensemble = np.mean(brutas, axis=0)
    estimativas.append(base.Estimativa("TimesNet", "ensemble", None, ensemble, np.maximum(ensemble, 0)))
    for nome, bruto in base.previsoes_baselines(teste, series, fim_ajuste_exclusivo="2024-01-01").items():
        estimativas.append(base.Estimativa(nome, "deterministica", None, bruto, np.maximum(bruto, 0)))
    local, macro = base.calcular_metricas_estimativas(tarefa=tarefa, particao="teste_2024",
                                                     janelas=teste, estimativas=estimativas)
    base.salvar_csv_atomico(local, pasta / "metricas_por_localidade.csv")
    base.salvar_csv_atomico(macro, pasta / "metricas_macro.csv")
    base.salvar_csv_atomico(base.resumir_variabilidade_sementes(macro), pasta / "variabilidade_sementes.csv")
    base.salvar_csv_atomico(base.montar_tabela_previsoes(tarefa=tarefa, janelas=teste, estimativas=estimativas),
                           pasta / "previsoes_teste.csv")
    return macro_mae(teste, ensemble)


def executar(*, pasta_saida: str | Path, pasta_csv=None, tarefas=("monthly_1", "monthly_6"),
             candidatos=None, configuracao=None, avaliar_teste=False,
             minimo_origens=18, inicio_ajuste="2020-01-31"):
    config = configuracao or base.ConfiguracaoMultirresolucao()
    candidatos = tuple(candidatos if candidatos is not None else candidatos_padrao())
    if not candidatos or len({c.nome for c in candidatos}) != len(candidatos):
        raise ValueError("Forneca candidatos com nomes unicos.")
    if not tarefas or set(tarefas) - {"monthly_1", "monthly_6"}:
        raise ValueError("Tarefas permitidas: monthly_1, monthly_6.")
    diarias, auditoria = base.carregar_series_diarias(pasta_csv)
    series = base.agregar_series_mensais(diarias)
    if config.modo_execucao == "smoke":
        series = series[:config.limite_localidades_smoke]
    pasta_saida = Path(pasta_saida).resolve()
    raiz_canonica = Path(base.PASTA_RESULTADOS).resolve()
    for protegida in ("avaliacao_multirresolucao_corrigida_v2", "avaliacao_multirresolucao",
                      "avaliacao_horaria_timesnet_corrigida_retomavel"):
        protegida = raiz_canonica / protegida
        if pasta_saida == protegida or protegida in pasta_saida.parents:
            raise ValueError("Escolha uma pasta nova fora dos resultados canonicos.")
    resumo = []
    for nome in tarefas:
        pasta = pasta_saida / nome
        legado = pasta / "execucao.lock"
        if legado.exists():
            raise RuntimeError(
                f"{legado} indica busca em andamento (PID {legado.read_text(encoding='utf-8').strip()}). "
                "Se nenhum processo estiver rodando, apague o arquivo para retomar."
            )
        # O lock fica fora da pasta da tarefa para proteger inclusive a limpeza
        # de temporarios feita pelo contrato, e nao entra no manifesto.
        pasta_saida.mkdir(parents=True, exist_ok=True)
        lock = pasta_saida / f".{nome}.execucao.lock"
        try:
            with lock.open("x", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except FileExistsError as erro:
            raise RuntimeError(
                f"{lock} indica busca em andamento (PID {lock.read_text(encoding='utf-8').strip()}). "
                "Se nenhum processo estiver rodando, apague o arquivo para retomar."
            ) from erro
        try:
            # Reconhece uma execucao iniciada pela versao anterior sem tocar
            # nos artefatos dela nem remover seus temporarios.
            if legado.exists():
                raise RuntimeError(
                    f"{legado} indica busca em andamento. "
                    "Se nenhum processo estiver rodando, apague o arquivo para retomar."
                )
            contrato = _contrato(series, candidatos, config, nome, minimo_origens, inicio_ajuste)
            base.validar_ou_criar_contrato(pasta, contrato, retomar=True)
            try:
                caminho_status = pasta / "status_execucao.json"
                anterior = (json.loads(caminho_status.read_text(encoding="utf-8"))
                            if caminho_status.exists() else {})
                base.salvar_csv_atomico(auditoria, pasta / "auditoria_entradas.csv")
                base.salvar_json_atomico({"etapa": "em_execucao", "smoke": config.modo_execucao == "smoke"},
                                        caminho_status)
                caminho_selecao = pasta / "selecao_congelada.json"
                if caminho_selecao.exists():
                    selecao = json.loads(caminho_selecao.read_text(encoding="utf-8"))
                else:
                    selecao = selecionar(series=series, tarefa=base.TAREFAS_CANONICAS[nome],
                                         candidatos=candidatos, configuracao=config, pasta=pasta,
                                         minimo_origens=minimo_origens, inicio_ajuste=inicio_ajuste)
                vencedor = selecao["vencedor"]
                linha = {"tarefa": nome, "candidato": vencedor["nome"],
                         "MAE_validacao_wm2": vencedor["MAE_validacao_ensemble_wm2"],
                         "modo": config.modo_execucao, "teste_avaliado": avaliar_teste}
                if avaliar_teste:
                    candidato = next(c for c in candidatos if c.nome == vencedor["nome"])
                    linha["MAE_teste_wm2"] = avaliar_vencedor(
                        series=series, tarefa=base.TAREFAS_CANONICAS[nome], candidato=candidato,
                        configuracao=config, pasta=pasta, epocas=vencedor["epocas"],
                        minimo_origens=minimo_origens, inicio_ajuste=inicio_ajuste)
                elif (
                    anterior.get("etapa") == "concluida"
                    and anterior.get("teste_avaliado") is True
                    and anterior.get("candidato") == vencedor["nome"]
                    and "MAE_teste_wm2" in anterior
                    and all((pasta / arquivo).is_file() for arquivo in (
                        "metricas_macro.csv", "metricas_por_localidade.csv",
                        "variabilidade_sementes.csv", "previsoes_teste.csv"))
                ):
                    # Retomar apenas a selecao nao desfaz a avaliacao ja concluida.
                    mae_anterior = float(anterior["MAE_teste_wm2"])
                    if not np.isfinite(mae_anterior) or mae_anterior < 0:
                        raise ValueError("MAE de teste anterior invalido.")
                    linha.update(teste_avaliado=True, MAE_teste_wm2=mae_anterior)
                resumo.append(linha)
                base.salvar_json_atomico({"etapa": "concluida", **linha,
                                         "atualizado_em_utc": datetime.now(timezone.utc).isoformat()},
                                        caminho_status)
                base.salvar_json_atomico(base.gerar_manifesto_artefatos(pasta),
                                        pasta / "manifesto_artefatos.json")
            except Exception as erro:
                base.salvar_json_atomico({"etapa": "falhou", "erro": str(erro)}, pasta / "status_execucao.json")
                raise
        finally:
            lock.unlink()
    base.salvar_csv_atomico(pd.DataFrame(resumo), pasta_saida / "resumo.csv")
    return resumo


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pasta-saida", type=Path, required=True)
    parser.add_argument("--pasta-csv", type=Path, default=None,
                        help="CSV diarios auditados; permite fornecer historico ampliado.")
    parser.add_argument("--tarefas", nargs="+", choices=["monthly_1", "monthly_6"],
                        default=["monthly_1", "monthly_6"])
    parser.add_argument("--sementes", nargs="+", type=int, default=list(base.SEMENTES_CANONICAS))
    parser.add_argument("--candidatos", nargs="+", choices=[c.nome for c in candidatos_padrao()])
    parser.add_argument("--max-epocas", type=int, default=300)
    parser.add_argument("--paciencia", type=int, default=30)
    parser.add_argument("--minimo-origens", type=int, default=18)
    parser.add_argument("--inicio-ajuste", default="2020-01-31")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--avaliar-teste", action="store_true",
                        help="Apos congelar selecao em 2023, refaz e avalia apenas vencedor em 2024.")
    args = parser.parse_args(argv)
    config = base.ConfiguracaoMultirresolucao(
        modo_execucao="smoke" if args.smoke else "completa", sementes=tuple(args.sementes),
        max_epocas_mensal=args.max_epocas, paciencia_mensal=args.paciencia)
    candidatos = tuple(c for c in candidatos_padrao() if not args.candidatos or c.nome in args.candidatos)
    resumo = executar(pasta_saida=args.pasta_saida, pasta_csv=args.pasta_csv, tarefas=tuple(args.tarefas),
                      candidatos=candidatos, configuracao=config, avaliar_teste=args.avaliar_teste,
                      minimo_origens=args.minimo_origens, inicio_ajuste=args.inicio_ajuste)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
