"""Busca de TimesNet diaria/horaria alinhada ao protocolo do PDF.

As buscas mensais existentes sao auditadas separadamente. Nenhum artefato
canonico e sobrescrito; 2024 e avaliado apenas depois de congelar a escolha.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from codigo_fonte.experimentos import experimento_multirresolucao as m
from codigo_fonte.experimentos import experimento_baselines_adicionais as e
from codigo_fonte.experimentos import treinamento_timesnet_resolucoes as treino
from codigo_fonte.analises_e_relatorios.consolidar_baselines_adicionais import metricas_vetor


@dataclass(frozen=True)
class Candidato:
    nome: str
    contexto: int
    perda: str = "mae"
    taxa: float = 0.001
    dimensao: int = 8
    lote: int = 128

    def configurar(self, ctx):
        return replace(ctx.config, taxa_aprendizado=self.taxa,
                       timesnet_d_model=self.dimensao, timesnet_d_ff=self.dimensao * 2,
                       batch_size_diario=self.lote)


def grade(ctx):
    comprimento = ctx.tarefa.seq_len
    menor = 168 if ctx.tarefa.resolucao == "horaria" else 182
    return (Candidato("mae", comprimento), Candidato("huber", comprimento, perda="huber"),
            Candidato("mae_dim16_lr0003", comprimento, taxa=0.0003, dimensao=16, lote=64),
            Candidato("mae_contexto_curto", menor))


def recortar(janelas, contexto):
    if isinstance(contexto, bool) or not isinstance(contexto, int) or not 2 <= contexto <= janelas.seq_len:
        raise ValueError("O contexto deve ser inteiro e nao exceder a janela causal existente.")
    return replace(janelas, x_bruto=janelas.x_bruto[:, -contexto:].copy(), seq_len=contexto)


def preparar(slug, modo):
    if slug not in {"daily_30", "hourly_72_extension"}:
        raise ValueError("Esta busca cobre apenas diario e horario.")
    ctx = e.preparar_contexto(slug, modo)
    e.verificar_alinhamento(ctx)
    return ctx


def previsao_original(ctx, particao):
    arquivo = "previsoes_validacao.csv.gz" if particao == "validacao_2023" else "previsoes_teste.csv.gz"
    antigo = pd.read_csv(e.FONTE / ctx.tarefa.slug / arquivo)
    chaves = e.tabela_chaves(ctx, particao)
    horario = ctx.tarefa.resolucao == "horaria"
    datas = ("origem_utc", "timestamp_alvo_utc") if horario else ("origem", "data_alvo")
    ids = ["localidade", *datas, "passo_h" if horario else "passo"]
    for coluna in datas:
        antigo[coluna] = pd.to_datetime(antigo[coluna], utc=True)
        chaves[coluna] = pd.to_datetime(chaves[coluna], utc=True)
    coluna = "previsao_bruta_timesnet_wm2" if horario else "previsao_bruta_timesnet_ensemble_wm2"
    junto = chaves.merge(antigo[ids + [coluna, "ghi_real_wm2"]], on=ids, how="left",
                         validate="one_to_one", suffixes=("", "_oficial"), sort=False)
    if not np.allclose(junto.ghi_real_wm2, junto.ghi_real_wm2_oficial, atol=1e-6, rtol=0):
        raise ValueError("Previsao de referencia nao alinhada.")
    bruto = junto[coluna].to_numpy().reshape(ctx.janelas[particao].y_bruto.shape)
    treino.macro_mae_fisico(ctx.janelas[particao], bruto, ctx.elevacoes.get(particao))
    return bruto


def avaliar_metricas(ctx, particao, bruto):
    tabela = e.tabela_chaves(ctx, particao)
    tabela["previsao_bruta_timesnet_otimizada_wm2"] = bruto.reshape(-1)
    tabela["previsao_pos_timesnet_otimizada_wm2"] = e.pos_processar(ctx, particao, bruto).reshape(-1)
    linhas = []
    passo = "passo_h" if ctx.tarefa.resolucao == "horaria" else "passo"
    for local, grupo in tabela.groupby("localidade"):
        for horizonte in ctx.tarefa.horizontes:
            for tipo, filtro in (("cumulativo", grupo[passo] <= horizonte),
                                  ("lead_exato", grupo[passo] == horizonte)):
                g = grupo.loc[filtro]
                linhas.append({"tarefa": ctx.tarefa.slug, "particao": particao,
                    "modelo": "TimesNet otimizada", "localidade": local,
                    "tipo_horizonte": tipo, "horizonte": horizonte, "N_pontos": len(g),
                    **metricas_vetor(g.ghi_real_wm2.to_numpy(),
                                    g.previsao_pos_timesnet_otimizada_wm2.to_numpy())})
    local = pd.DataFrame(linhas)
    macro = local.groupby(["tarefa", "particao", "modelo", "tipo_horizonte", "horizonte"],
                           as_index=False).agg(**{col: (col, "mean") for col in
                           ("MAE_wm2", "MSE_w2m4", "RMSE_wm2", "nRMSE", "R2")})
    return tabela, local, macro


def contrato(ctx, candidatos, dispositivo):
    codigos = [Path(__file__), Path(treino.__file__), Path(m.__file__), Path(e.__file__),
               Path(__file__).parents[2] / 'codigo_fonte/modelos/timesnet_horario.py',
               Path(__file__).parents[2] / 'codigo_fonte/experimentos/treinamento_timesnet_otimizacao.py',
               Path(__file__).parents[2] / 'codigo_fonte/analises_e_relatorios/consolidar_baselines_adicionais.py',
               Path(__file__).parents[2] / 'codigo_fonte/experimentos/experimento_horario_timesnet.py']
    fontes = ctx.entradas + [e.FONTE / ctx.tarefa.slug / f for f in
                            ("previsoes_validacao.csv.gz", "previsoes_teste.csv.gz")]
    c = {"versao": 1, "tarefa": asdict(ctx.tarefa), "configuracao": asdict(ctx.config),
         "candidatos": [asdict(x) for x in candidatos], "dispositivo": dispositivo,
         "python": platform.python_version(), "torch": str(torch.__version__),
         "numpy": np.__version__, "pandas": pd.__version__,
         "criterio": "macro_MAE_fisico_validacao_2023_apos_pos_processamento",
         "referencia": "TimesNet canonica elegivel pela previsao de validacao ja salva",
         "sementes": [42] if ctx.tarefa.resolucao == "horaria" else list(ctx.config.sementes_efetivas),
         "codigo": {str(p.resolve()): m.sha256_arquivo(p) for p in codigos},
         "entradas": {str(p.resolve()): m.sha256_arquivo(p) for p in fontes},
         "limitacoes": ["2024 ja observado motivou a busca; necessita confirmacao futura.",
                         "Janela menor preserva exatamente origens, alvos e exemplos de treino.",
                         "Grade limitada; nenhuma garantia de superar outras arquiteturas.",
                         "Horaria usa apenas semente42; diaria usa cinco sementes."]}
    c["sha256_contrato"] = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()
    return c


def executar(slug, saida, *, modo="completa", dispositivo="cpu", max_epocas=30, paciencia=5):
    ctx = preparar(slug, modo)
    ctx.config = replace(ctx.config, max_epocas_diario=max_epocas, paciencia_diario=paciencia)
    candidatos = grade(ctx)
    seeds = [42] if ctx.tarefa.resolucao == "horaria" else list(ctx.config.sementes_efetivas)
    raiz = Path(saida).resolve()
    destino = raiz / slug
    if raiz == e.FONTE or e.FONTE in raiz.parents or destino.exists() and destino.is_symlink():
        raise ValueError("Use pasta nova fora da fonte canonica.")
    raiz.mkdir(parents=True, exist_ok=True)
    lock = raiz / f".{slug}.lock"
    with lock.open("x", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    try:
        c = contrato(ctx, candidatos, dispositivo)
        m.validar_ou_criar_contrato(destino, c, retomar=True)
        m.salvar_json_atomico({"etapa": "em_execucao", "tarefa": slug, "modo": modo},
                              destino / "status_execucao.json")
        escala = ctx.escalas["selecao"]
        m.salvar_csv_atomico(escala, destino / "escalas_selecao.csv")
        escolha = destino / "selecao_congelada.json"
        if escolha.exists():
            selecionado = json.loads(escolha.read_text(encoding="utf-8"))
        else:
            referencia = previsao_original(ctx, "validacao_2023")
            ranking = [{"nome": "referencia_original", "MAE_validacao_wm2":
                treino.macro_mae_fisico(ctx.janelas["validacao_2023"], referencia,
                                        ctx.elevacoes.get("validacao_2023")),
                "epocas": {}, "contexto": ctx.tarefa.seq_len}]
            for candidato in candidatos:
                conf = candidato.configurar(ctx)
                tarefa = replace(ctx.tarefa, seq_len=candidato.contexto)
                ajuste = recortar(ctx.janelas["ajuste"], candidato.contexto)
                validacao = recortar(ctx.janelas["validacao_2023"], candidato.contexto)
                brutas, epocas = [], {}
                for seed in seeds:
                    arquivo = destino / "candidatos" / candidato.nome / f"seed{seed}.npz"
                    if arquivo.exists():
                        with np.load(arquivo, allow_pickle=False) as z:
                            bruto, n = z["previsao"], int(z["epocas"].item())
                    else:
                        print(f"[{slug}] {candidato.nome} seed={seed} selecao", flush=True)
                        modelo, n, historico = treino.treinar(tarefa=tarefa, config=conf, semente=seed,
                            ajuste=ajuste, escalas=escala, validacao=validacao,
                            elevacao_validacao=ctx.elevacoes.get("validacao_2023"),
                            perda=candidato.perda, dispositivo=dispositivo)
                        bruto = treino.prever(modelo, validacao, escala,
                            batch_size=conf.batch_size_diario, dispositivo=dispositivo)
                        m.salvar_csv_atomico(historico, arquivo.with_suffix(".csv"))
                        m.salvar_npz_atomico(arquivo, previsao=bruto, epocas=np.asarray(n))
                        del modelo
                    treino.macro_mae_fisico(validacao, bruto, ctx.elevacoes.get("validacao_2023"))
                    brutas.append(bruto)
                    epocas[str(seed)] = n
                media = np.mean(brutas, axis=0)
                mae = treino.macro_mae_fisico(validacao, media, ctx.elevacoes.get("validacao_2023"))
                ranking.append({**asdict(candidato), "MAE_validacao_wm2": mae, "epocas": epocas})
                m.salvar_csv_atomico(pd.DataFrame(ranking).drop(columns="epocas"), destino / "ranking_validacao.csv")
            ranking.sort(key=lambda r: (r["MAE_validacao_wm2"], r["nome"] != "referencia_original", r["nome"]))
            m.salvar_csv_atomico(pd.DataFrame(ranking).drop(columns="epocas"), destino / "ranking_validacao.csv")
            selecionado = {"vencedor": ranking[0], "metodo": "TimesNet otimizada",
                          "tarefa": slug, "selecao_concluida_antes_do_teste": True,
                          "sementes": seeds, "criterio": c["criterio"], "limitacoes": c["limitacoes"]}
            m.salvar_json_atomico(selecionado, escolha)
        vencedor = selecionado["vencedor"]
        if vencedor["nome"] == "referencia_original":
            bruto_teste = previsao_original(ctx, "teste_2024")
            bruto_val = previsao_original(ctx, "validacao_2023")
        else:
            candidato = next(x for x in candidatos if x.nome == vencedor["nome"])
            conf = candidato.configurar(ctx)
            tarefa = replace(ctx.tarefa, seq_len=candidato.contexto)
            refit = recortar(ctx.janelas["refit"], candidato.contexto)
            teste = recortar(ctx.janelas["teste_2024"], candidato.contexto)
            escala = ctx.escalas["refit"]
            m.salvar_csv_atomico(escala, destino / "escalas_refit.csv")
            brutas, validacoes = [], []
            for seed in seeds:
                arquivo = destino / "refit" / f"seed{seed}.npz"
                if arquivo.exists():
                    with np.load(arquivo, allow_pickle=False) as z:
                        bruto = z["previsao"]
                else:
                    n = int(vencedor["epocas"][str(seed)])
                    print(f"[{slug}] vencedor {candidato.nome} seed={seed} refit {n}", flush=True)
                    modelo, _, historico = treino.treinar(tarefa=tarefa, config=conf, semente=seed,
                        ajuste=refit, escalas=escala, perda=candidato.perda,
                        epocas_fixas=n, dispositivo=dispositivo)
                    bruto = treino.prever(modelo, teste, escala,
                        batch_size=conf.batch_size_diario, dispositivo=dispositivo)
                    m.salvar_torch_atomico({"state_dict": {k: v.cpu() for k,v in modelo.state_dict().items()},
                        "tarefa": asdict(tarefa), "configuracao": asdict(conf),
                        "candidato": asdict(candidato), "semente": seed, "epocas_refit": n,
                        "escalas": escala.to_dict(orient="records"), "dispositivo_inferencia": dispositivo,
                        "batch_size_inferencia": conf.batch_size_diario, "pos_processamento":
                        "piso_zero_e_mascara_solar" if slug.startswith("hourly") else "piso_zero"},
                        destino / "modelos" / f"timesnet_seed{seed}_refit.pt")
                    m.salvar_csv_atomico(historico, arquivo.with_suffix(".csv"))
                    m.salvar_npz_atomico(arquivo, previsao=bruto)
                    del modelo
                treino.macro_mae_fisico(teste, bruto, ctx.elevacoes.get("teste_2024"))
                brutas.append(bruto)
                with np.load(destino / "candidatos" / candidato.nome / f"seed{seed}.npz") as z:
                    validacoes.append(z["previsao"])
            bruto_teste, bruto_val = np.mean(brutas, axis=0), np.mean(validacoes, axis=0)
        for particao, arquivo, bruto in (("validacao_2023", "validacao", bruto_val),
                                         ("teste_2024", "teste", bruto_teste)):
            tabela, locais, macro = avaliar_metricas(ctx, particao, bruto)
            m.salvar_csv_atomico(tabela, destino / f"previsoes_{arquivo}.csv.gz")
            m.salvar_csv_atomico(locais, destino / f"metricas_{arquivo}_por_localidade.csv")
            m.salvar_csv_atomico(macro, destino / f"metricas_{arquivo}_macro.csv")
        mae_teste = treino.macro_mae_fisico(ctx.janelas["teste_2024"], bruto_teste,
                                           ctx.elevacoes.get("teste_2024"))
        status = {"etapa": "concluida", "modo": modo, "tarefa": slug,
                  "candidato": vencedor["nome"], "MAE_validacao_wm2": vencedor["MAE_validacao_wm2"],
                  "MAE_teste_wm2": mae_teste, "resultado_smoke_nao_publicavel": modo == "smoke",
                  "concluido_em_utc": datetime.now(timezone.utc).isoformat()}
        m.salvar_json_atomico(status, destino / "status_execucao.json")
        m.salvar_json_atomico(m.gerar_manifesto_artefatos(destino), destino / "manifesto_artefatos.json")
        print(json.dumps(status, ensure_ascii=False), flush=True)
        return status
    finally:
        lock.unlink()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tarefa", choices=["daily_30", "hourly_72_extension"], required=True)
    ap.add_argument("--saida", type=Path, default=Path("resultados/busca_timesnet_resolucoes_20260922"))
    ap.add_argument("--modo", choices=["completa", "smoke"], default="completa")
    ap.add_argument("--dispositivo", choices=["cpu", "cuda"], default="cpu")
    ap.add_argument("--max-epocas", type=int, default=30)
    ap.add_argument("--paciencia", type=int, default=5)
    a = ap.parse_args(argv)
    executar(a.tarefa, a.saida, modo=a.modo, dispositivo=a.dispositivo,
             max_epocas=a.max_epocas, paciencia=a.paciencia)


if __name__ == "__main__":
    main()
