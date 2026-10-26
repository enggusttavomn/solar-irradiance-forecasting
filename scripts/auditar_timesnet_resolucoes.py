"""Auditoria somente leitura da busca TimesNet diaria/horaria.

O comando escreve apenas relatorios fora das fontes. Sem --reproduzir-modelos,
nao executa inferencia nem usa CUDA. Com a opcao, usa exatamente dispositivo
e tamanho de lote registrados em cada checkpoint; coordenar o uso da GPU.

python scripts/auditar_timesnet_resolucoes.py --fonte resultados/busca_timesnet_resolucoes_20260922
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import torch

from codigo_fonte import experimento_baselines_adicionais as e
from codigo_fonte import experimento_multirresolucao as m
from codigo_fonte import otimizacao_timesnet_resolucoes as busca
from codigo_fonte import treinamento_timesnet_resolucoes as treino

METRICAS = ("MAE_wm2", "MSE_w2m4", "RMSE_wm2", "nRMSE", "R2")
BRUTA = "previsao_bruta_timesnet_otimizada_wm2"
POS = "previsao_pos_timesnet_otimizada_wm2"


def ler_json(caminho):
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def normalizar_json(valor):
    return json.loads(json.dumps(valor, sort_keys=True))


def exigir(condicao, mensagem):
    if not condicao:
        raise ValueError(mensagem)


def proximidade(a, b, nome, tolerancia=1e-7, permitir_nan=False):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    exigir(a.shape == b.shape and a.size > 0, f"Forma invalida: {nome}.")
    if permitir_nan:
        exigir(np.array_equal(np.isnan(a), np.isnan(b)), f"NaNs divergentes: {nome}.")
        mascara = ~np.isnan(a)
        a, b = a[mascara], b[mascara]
        if not a.size:
            return 0.0
    exigir(np.isfinite(a).all() and np.isfinite(b).all(), f"Valores nao finitos: {nome}.")
    erro = float(np.max(np.abs(a - b)))
    exigir(erro <= tolerancia, f"{nome}: erro maximo {erro} > {tolerancia}.")
    return erro


def conferir_manifesto(pasta):
    pasta = Path(pasta).resolve()
    manifesto = ler_json(pasta / "manifesto_artefatos.json")
    registros = manifesto["arquivos"]
    nomes = [r["arquivo"] for r in registros]
    exigir(len(nomes) == len(set(nomes)) == manifesto["N_arquivos"], "Manifesto duplicado/incompleto.")
    atuais = {p.relative_to(pasta).as_posix() for p in pasta.rglob("*")
              if p.is_file() and p.name != "manifesto_artefatos.json" and not m._eh_temporario_do_modulo(p)}
    exigir(atuais == set(nomes), "Inventario atual difere do manifesto.")
    for registro in registros:
        caminho = (pasta / registro["arquivo"]).resolve()
        exigir(caminho.is_relative_to(pasta), "Manifesto aponta para fora da fonte.")
        exigir(caminho.is_file() and caminho.stat().st_size == registro["bytes"]
               and m.sha256_arquivo(caminho) == registro["sha256"], f"Artefato alterado: {caminho}.")
    return {"arquivos_verificados": len(registros), "divergencias": []}


def conferir_contrato(contrato):
    sem_hash = {k: v for k, v in contrato.items() if k != "sha256_contrato"}
    calculado = hashlib.sha256(json.dumps(sem_hash, sort_keys=True).encode()).hexdigest()
    exigir(calculado == contrato["sha256_contrato"], "Hash interno do contrato invalido.")
    contagens = {}
    for grupo in ("codigo", "entradas"):
        for caminho, esperado in contrato[grupo].items():
            exigir(Path(caminho).is_file() and m.sha256_arquivo(caminho) == esperado,
                   f"{grupo}: arquivo ausente ou alterado: {caminho}.")
        contagens[grupo] = len(contrato[grupo])
    return contagens


def alinhar_tabela(ctx, particao, tabela):
    """Alinha CSV pelas chaves, sem depender da ordem de gravacao das linhas."""
    horario = ctx.tarefa.resolucao == "horaria"
    datas = ("origem_utc", "timestamp_alvo_utc") if horario else ("origem", "data_alvo")
    chaves = ["localidade", *datas, "passo_h" if horario else "passo"]
    esperado = e.tabela_chaves(ctx, particao).copy()
    tabela = tabela.copy()
    for coluna in datas:
        esperado[coluna] = pd.to_datetime(esperado[coluna], utc=True)
        tabela[coluna] = pd.to_datetime(tabela[coluna], utc=True)
    exigir(len(esperado) == len(tabela), "Numero de linhas difere das origens canonicas.")
    exigir(not esperado.duplicated(chaves).any() and not tabela.duplicated(chaves).any(), "Chaves duplicadas.")
    junto = esperado.merge(tabela[chaves + ["ghi_real_wm2", BRUTA, POS]], on=chaves,
                            how="left", validate="one_to_one", sort=False, suffixes=("", "_salvo"))
    proximidade(junto.ghi_real_wm2, junto.ghi_real_wm2_salvo, "Alvos canonicos", 1e-6)
    exigir(np.isfinite(junto[[BRUTA, POS]].to_numpy()).all(), "Previsoes ausentes ou nao finitas.")
    return junto.drop(columns="ghi_real_wm2_salvo")


def metricas_independentes(tabela, horizontes, horario=False):
    """Recalcula metricas locais e macro sem chamar o avaliador da busca."""
    passo = "passo_h" if horario else "passo"
    linhas = []
    for localidade, local in tabela.groupby("localidade", sort=True):
        for h in horizontes:
            for tipo in ("cumulativo", "lead_exato"):
                g = local.loc[local[passo] <= h if tipo == "cumulativo" else local[passo] == h]
                real, previsto = g.ghi_real_wm2.to_numpy(float), g[POS].to_numpy(float)
                exigir(len(real) > 0, "Horizonte sem observacoes.")
                erro = previsto - real
                mse = float(np.mean(erro ** 2))
                rmse = float(np.sqrt(mse))
                media = float(np.mean(real))
                sst = float(np.sum((real - media) ** 2))
                linhas.append({"localidade": localidade, "tipo_horizonte": tipo, "horizonte": h,
                    "N_pontos": len(g), "MAE_wm2": float(np.mean(np.abs(erro))), "MSE_w2m4": mse,
                    "RMSE_wm2": rmse, "nRMSE": np.nan if np.isclose(media, 0.) else rmse / media,
                    "R2": np.nan if len(real) < 2 or np.isclose(sst, 0.) else 1. - float(np.sum(erro ** 2)) / sst})
    locais = pd.DataFrame(linhas)
    macro = locais.groupby(["tipo_horizonte", "horizonte"], as_index=False)[list(METRICAS)].mean()
    return locais, macro


def comparar_metricas(calculadas, salvas, local=False):
    chaves = (["localidade"] if local else []) + ["tipo_horizonte", "horizonte"]
    colunas = list(METRICAS) + (["N_pontos"] if local else [])
    a = calculadas.sort_values(chaves).reset_index(drop=True)
    b = salvas.sort_values(chaves).reset_index(drop=True)
    pd.testing.assert_frame_equal(a[chaves], b[chaves], check_dtype=False)
    return proximidade(a[colunas], b[colunas], "Metricas locais" if local else "Metricas macro",
                       permitir_nan=True)


def mae_independente(ctx, particao, bruto):
    j = ctx.janelas[particao]
    fisico = e.pos_processar(ctx, particao, bruto)
    return float(np.mean([np.mean(np.abs(fisico[j.localidade_id == i] - j.y_bruto[j.localidade_id == i]))
                          for i in np.unique(j.localidade_id)]))


def epoca_historico(historico):
    exigir(len(historico) > 0, "Historico vazio.")
    exigir(np.array_equal(historico.epoca.to_numpy(), np.arange(1, len(historico) + 1)), "Epocas nao consecutivas.")
    scores = historico.mae_validacao_wm2.to_numpy(float)
    exigir(np.isfinite(scores).all(), "Historico de validacao nao finito.")
    melhor, epoca = np.inf, 0
    for i, score in enumerate(scores, 1):
        if score < melhor - 1e-12:
            melhor, epoca = score, i
    return epoca


def auditar_selecao(ctx, pasta, contrato, selecao):
    seeds = contrato["sementes"]
    exigir(selecao["sementes"] == seeds, "Sementes congeladas divergem do contrato.")
    exigir(selecao["tarefa"] == ctx.tarefa.slug and selecao["criterio"] == contrato["criterio"], "Selecao de outra tarefa/criterio.")
    exigir(selecao["selecao_concluida_antes_do_teste"] is True, "Selecao nao declara congelamento antes do teste.")
    referencia = busca.previsao_original(ctx, "validacao_2023")
    ranking = [{"nome": "referencia_original", "MAE_validacao_wm2": mae_independente(ctx, "validacao_2023", referencia),
                "epocas": {}, "contexto": ctx.tarefa.seq_len}]
    validacoes = {"referencia_original": referencia}
    for dados in contrato["candidatos"]:
        candidato = busca.Candidato(**dados)
        brutas, epocas = [], {}
        for seed in seeds:
            arquivo = pasta / "candidatos" / candidato.nome / f"seed{seed}.npz"
            with np.load(arquivo, allow_pickle=False) as cache:
                previsto = cache["previsao"]
                epoca = int(cache["epocas"].item())
            mae = mae_independente(ctx, "validacao_2023", previsto)
            historico = pd.read_csv(arquivo.with_suffix(".csv"))
            exigir(epoca == epoca_historico(historico), f"Epoca selecionada difere do historico: {arquivo}.")
            proximidade(mae, historico.iloc[epoca - 1].mae_validacao_wm2, "Cache vs historico da melhor epoca")
            brutas.append(previsto)
            epocas[str(seed)] = epoca
        media = np.mean(brutas, axis=0)
        validacoes[candidato.nome] = media
        ranking.append({**dados, "MAE_validacao_wm2": mae_independente(ctx, "validacao_2023", media), "epocas": epocas})
    ranking.sort(key=lambda r: (r["MAE_validacao_wm2"], r["nome"] != "referencia_original", r["nome"]))
    salvo = pd.read_csv(pasta / "ranking_validacao.csv")
    exigir(salvo.nome.tolist() == [r["nome"] for r in ranking], "Ranking salvo diverge do recalculado.")
    proximidade(salvo.MAE_validacao_wm2, [r["MAE_validacao_wm2"] for r in ranking], "MAEs do ranking")
    vencedor = selecao["vencedor"]
    exigir(vencedor["nome"] == ranking[0]["nome"], "Vencedor nao minimiza MAE da validacao.")
    exigir(vencedor["epocas"] == ranking[0]["epocas"], "Epocas congeladas diferentes das selecionadas.")
    for chave, valor in ranking[0].items():
        if chave != "MAE_validacao_wm2":
            exigir(vencedor[chave] == valor, f"Campo do vencedor divergente: {chave}.")
    proximidade(vencedor["MAE_validacao_wm2"], ranking[0]["MAE_validacao_wm2"], "MAE congelado")
    return ranking, validacoes[vencedor["nome"]]


def _conferir_escalas(a, b):
    colunas = ["minimo_treino_wm2", "maximo_treino_wm2", "amplitude_escala_wm2"]
    colunas = [c for c in colunas if c in a and c in b]
    a, b = a.sort_values("localidade_id"), b.sort_values("localidade_id")
    exigir(a.localidade_id.tolist() == b.localidade_id.tolist(), "IDs de escalas divergentes.")
    return proximidade(a[colunas], b[colunas], "Escalas do preprocessamento")


def auditar_checkpoints(ctx, pasta, contrato, selecao, reproduzir=False):
    vencedor = selecao["vencedor"]
    if vencedor["nome"] == "referencia_original":
        exigir(not list((pasta / "modelos").glob("*.pt")), "Referencia original nao deve ter novos checkpoints de refit.")
        return {"situacao": "referencia_original_sem_novo_modelo", "modelos": []}, busca.previsao_original(ctx, "teste_2024")
    candidato = next(busca.Candidato(**x) for x in contrato["candidatos"] if x["nome"] == vencedor["nome"])
    config = candidato.configurar(ctx)
    tarefa = replace(ctx.tarefa, seq_len=candidato.contexto)
    teste = busca.recortar(ctx.janelas["teste_2024"], candidato.contexto)
    escala = ctx.escalas["refit"]
    _conferir_escalas(escala, pd.read_csv(pasta / "escalas_refit.csv"))
    relatos, brutas = [], []
    for seed in contrato["sementes"]:
        caminho = pasta / "modelos" / f"timesnet_seed{seed}_refit.pt"
        cp = torch.load(caminho, map_location="cpu", weights_only=True)
        exigir(normalizar_json(cp["tarefa"]) == normalizar_json(asdict(tarefa)), "Tarefa do checkpoint diverge da selecionada.")
        exigir(normalizar_json(cp["configuracao"]) == normalizar_json(asdict(config)), "Configuracao do checkpoint diverge da selecionada.")
        exigir(cp["candidato"] == asdict(candidato) and cp["semente"] == seed, "Candidato/semente do checkpoint divergente.")
        exigir(cp["epocas_refit"] == vencedor["epocas"][str(seed)], "Refit usou numero de epocas diferente.")
        exigir(cp["dispositivo_inferencia"] == contrato["dispositivo"], "Dispositivo de inferencia diferente do contrato.")
        exigir(cp["batch_size_inferencia"] == config.batch_size_diario, "Tamanho do lote de inferencia diferente da configuracao.")
        exigir(cp["pos_processamento"] == ("piso_zero_e_mascara_solar" if tarefa.resolucao == "horaria" else "piso_zero"),
               "Pos-processamento do checkpoint incorreto.")
        erro_escala = _conferir_escalas(escala, pd.DataFrame(cp["escalas"]))
        with np.load(pasta / "refit" / f"seed{seed}.npz", allow_pickle=False) as cache:
            bruto = cache["previsao"]
        mae = mae_independente(ctx, "teste_2024", bruto)
        historico = pd.read_csv(pasta / "refit" / f"seed{seed}.csv")
        exigir(len(historico) == cp["epocas_refit"], "Historico de refit nao tem a quantidade congelada de epocas.")
        relato = {"semente": seed, "epocas_refit": cp["epocas_refit"], "MAE_teste_wm2": mae,
                  "erro_maximo_escalas_wm2": erro_escala, "dispositivo": cp["dispositivo_inferencia"],
                  "batch_size": cp["batch_size_inferencia"], "reproduzido": False}
        if reproduzir:
            rede = m.criar_modelo_neural("TimesNet", tarefa=tarefa, configuracao=config,
                                          num_localidades=len(ctx.series), semente=seed)
            rede.load_state_dict(cp["state_dict"], strict=True)
            previsto = treino.prever(rede, teste, pd.DataFrame(cp["escalas"]),
                                     batch_size=cp["batch_size_inferencia"], dispositivo=cp["dispositivo_inferencia"])
            relato["erro_maximo_reproducao_wm2"] = proximidade(previsto, bruto, "Checkpoint vs cache de refit")
            relato["reproduzido"] = True
            del rede
        relatos.append(relato)
        brutas.append(bruto)
    return {"situacao": "reproduzidos" if reproduzir else "metadados_verificados_inferencia_pendente",
            "modelos": relatos}, np.mean(brutas, axis=0)


def auditar_tarefa(pasta, reproduzir=False):
    pasta = Path(pasta).resolve()
    status = ler_json(pasta / "status_execucao.json")
    exigir(status["etapa"] == "concluida", "Execucao ainda nao concluida.")
    exigir(status["modo"] == "completa" and status["resultado_smoke_nao_publicavel"] is False,
           "A auditoria publicavel exige execucao completa.")
    exigir(not (pasta.parent / f".{pasta.name}.lock").exists(), "Busca ainda possui lock ativo; auditar apos encerrar.")
    contrato = ler_json(pasta / "contrato_execucao.json")
    hashes = conferir_contrato(contrato)
    manifesto = conferir_manifesto(pasta)
    selecao = ler_json(pasta / "selecao_congelada.json")
    ctx = e.preparar_contexto(pasta.name, "completa")
    e.verificar_alinhamento(ctx)
    exigir(contrato["tarefa"] == normalizar_json(asdict(ctx.tarefa)), "Protocolo da tarefa diferente do canonico.")
    ctx.config = m.ConfiguracaoMultirresolucao(**contrato["configuracao"])
    exigir(contrato["candidatos"] == [asdict(c) for c in busca.grade(ctx)], "Grade diferente da fonte atual.")
    seeds = [42] if ctx.tarefa.resolucao == "horaria" else list(ctx.config.sementes_efetivas)
    exigir(contrato["sementes"] == seeds, "Sementes do contrato diferentes do protocolo.")
    _conferir_escalas(ctx.escalas["selecao"], pd.read_csv(pasta / "escalas_selecao.csv"))
    ranking, bruto_val = auditar_selecao(ctx, pasta, contrato, selecao)
    checkpoints, bruto_teste = auditar_checkpoints(ctx, pasta, contrato, selecao, reproduzir)
    partes = {}
    for particao, sufixo, esperado in (("validacao_2023", "validacao", bruto_val), ("teste_2024", "teste", bruto_teste)):
        tabela = alinhar_tabela(ctx, particao, pd.read_csv(pasta / f"previsoes_{sufixo}.csv.gz"))
        janelas = ctx.janelas[particao]
        bruto = tabela[BRUTA].to_numpy().reshape(janelas.y_bruto.shape)
        erro = proximidade(bruto, esperado, "Ensemble salvo vs caches/referencia")
        fisico = e.pos_processar(ctx, particao, bruto)
        erro_pos = proximidade(tabela[POS], fisico.reshape(-1), "Pos-processamento fisico")
        locais, macro = metricas_independentes(tabela, ctx.tarefa.horizontes, ctx.tarefa.resolucao == "horaria")
        erros_metricas = {
            "local": comparar_metricas(locais, pd.read_csv(pasta / f"metricas_{sufixo}_por_localidade.csv"), True),
            "macro": comparar_metricas(macro, pd.read_csv(pasta / f"metricas_{sufixo}_macro.csv"))}
        mae = mae_independente(ctx, particao, bruto)
        proximidade(mae, status[f"MAE_{sufixo}_wm2"], f"MAE {sufixo} do status")
        if sufixo == "validacao":
            proximidade(mae, selecao["vencedor"]["MAE_validacao_wm2"], "MAE da selecao congelada")
        partes[particao] = {"linhas": len(tabela), "localidades": int(tabela.localidade.nunique()),
            "MAE_wm2": mae, "erro_maximo_ensemble_wm2": erro, "erro_maximo_pos_processamento": erro_pos,
            "erros_metricas": erros_metricas, "metricas_macro": macro.to_dict(orient="records")}
    congelado_em = (pasta / "selecao_congelada.json").stat().st_mtime_ns
    posteriores = [pasta / "previsoes_teste.csv.gz", *list((pasta / "refit").glob("*")),
                   *list((pasta / "modelos").glob("*"))]
    exigir(all(p.stat().st_mtime_ns >= congelado_em for p in posteriores), "Artefatos de teste/refit anteriores ao congelamento.")
    exigir(status["candidato"] == selecao["vencedor"]["nome"], "Status aponta outro vencedor.")
    return {"tarefa": ctx.tarefa.slug, "ok": True, "hashes": hashes, "manifesto": manifesto,
            "vencedor": selecao["vencedor"], "ranking_recalculado": ranking, "particoes": partes,
            "checkpoints": checkpoints, "cronologia_artefatos_coerente": True,
            "nota_cronologia": "Timestamps e codigo sao coerentes; nao constituem prova historica independente de acesso aos dados.",
            "limitacoes": selecao["limitacoes"], "fontes": {nome: m.sha256_arquivo(pasta / nome) for nome in
            ("contrato_execucao.json", "manifesto_artefatos.json", "selecao_congelada.json")}}


def evidencia_mensal(caminho):
    caminho = Path(caminho)
    relatorio = ler_json(caminho)
    relatos = []
    for tarefa in relatorio["tarefas"]:
        pasta = Path(relatorio["fonte"]) / tarefa["tarefa"]
        for arquivo, esperado in tarefa["fontes"].items():
            exigir(m.sha256_arquivo(pasta / arquivo) == esperado, f"Fonte mensal mudou desde auditoria: {arquivo}.")
        manifesto = conferir_manifesto(pasta)
        contrato = ler_json(pasta / "contrato_execucao.json")
        for entrada in contrato["entradas"]:
            exigir(m.sha256_arquivo(entrada["arquivo"]) == entrada["sha256"],
                   f"Entrada mensal alterada desde auditoria: {entrada['arquivo']}.")
        exigir(len(tarefa["checkpoints"]) == 5 and all(c["erro_maximo_npz_wm2"] <= 1e-7 for c in tarefa["checkpoints"]),
               "Auditoria mensal nao demonstra reproducao dos cinco checkpoints.")
        relatos.append({"tarefa": tarefa["tarefa"], "manifesto_atual": manifesto,
            "MAE_teste_wm2": tarefa["comparacao"]["teste_timesnet"], "metodo": "TimesNet + climatologia",
            "checkpoints_reproduzidos_na_auditoria_anterior": len(tarefa["checkpoints"]),
            "codigo_divergente_declarado": [nome for nome, v in tarefa["codigo"].items() if not v["confere_atualmente"]],
            "limitacoes": tarefa["limitacoes"]})
    exigir({t["tarefa"] for t in relatos} == {"monthly_1", "monthly_6"}, "Auditoria mensal incompleta.")
    return {"relatorio": str(caminho.resolve()), "sha256_relatorio": m.sha256_arquivo(caminho),
            "gerado_em_utc": relatorio["gerado_em_utc"], "valores_sustentados_pelos_artefatos_preservados": True,
            "reproducao_mensal_nao_reexecutada_nesta_auditoria": True, "tarefas": relatos}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonte", type=Path, default=ROOT / "resultados/busca_timesnet_resolucoes_20260922")
    parser.add_argument("--saida", type=Path, default=ROOT / "relatorios/otimizacao_timesnet_4casos_20260922")
    parser.add_argument("--tarefa", nargs="+", choices=["daily_30", "hourly_72_extension"], default=["daily_30", "hourly_72_extension"])
    parser.add_argument("--reproduzir-modelos", action="store_true")
    parser.add_argument("--auditoria-mensal", type=Path, default=ROOT / "relatorios/otimizacao_timesnet_20260922/auditoria.json")
    args = parser.parse_args(argv)
    fonte, saida = args.fonte.resolve(), args.saida.resolve()
    exigir(not saida.is_relative_to(fonte) and not saida.is_relative_to(e.FONTE.resolve())
           and not saida.is_relative_to((ROOT / "resultados").resolve()), "Relatorio deve ficar fora das fontes de resultados.")
    resultado = {"gerado_em_utc": datetime.now(timezone.utc).isoformat(), "fonte": str(fonte),
                 "sem_treinamento": True, "reproducao_solicitada": args.reproduzir_modelos,
                 "torch": str(torch.__version__), "tarefas": []}
    for slug in args.tarefa:
        try:
            registro = auditar_tarefa(fonte / slug, args.reproduzir_modelos)
        except (AssertionError, ValueError, RuntimeError, OSError, KeyError) as erro:
            registro = {"tarefa": slug, "ok": False, "erro": f"{type(erro).__name__}: {erro}"}
        resultado["tarefas"].append(registro)
        print(json.dumps({k: v for k, v in registro.items() if k in {"tarefa", "ok", "erro"}}, ensure_ascii=False), flush=True)
    try:
        resultado["mensal"] = evidencia_mensal(args.auditoria_mensal)
    except (AssertionError, ValueError, RuntimeError, OSError, KeyError) as erro:
        resultado["mensal"] = {"erro": f"{type(erro).__name__}: {erro}"}
    resultado["ok"] = all(t["ok"] for t in resultado["tarefas"]) and "erro" not in resultado["mensal"]
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "auditoria_resolucoes.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    linhas = ["# Auditoria TimesNet: diaria e horaria", "", f"Integridade e metricas: {'aprovadas' if resultado['ok'] else 'ha pendencias'}.", ""]
    for t in resultado["tarefas"]:
        if not t["ok"]:
            linhas.append(f"- {t['tarefa']}: {t['erro']}")
        else:
            linhas.append(f"- {t['tarefa']}: {t['vencedor']['nome']}; MAE teste {t['particoes']['teste_2024']['MAE_wm2']:.8f} W/m2; checkpoints: {t['checkpoints']['situacao']}.")
    linhas += ["", "Mensais: artefatos revalidados; reproducao dos checkpoints documentada na auditoria anterior." if "erro" not in resultado["mensal"] else "Mensais: " + resultado["mensal"]["erro"],
               "", "A busca foi motivada por 2024 ja observado; o teste e retrospectivo e requer confirmacao futura."]
    (saida / "auditoria_resolucoes.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
