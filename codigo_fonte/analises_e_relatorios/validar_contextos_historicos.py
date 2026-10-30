"""Valida contextos historicos sem treinar e sem modificar o motor congelado.

Um subprocesso por contexto evita reter memoria entre carregamentos. Concorrentes
compartilham a mesma construcao; TimesNet e reconstruida separadamente para
conferir o contexto otimizado e o pareamento de alvos.
"""
from __future__ import annotations

import argparse
import ast
import gc
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

RAIZ = Path(__file__).resolve().parents[2]
REL = RAIZ / "resultados/relatorios/quantizacao_todos_modelos_20260929/historico"
SAIDA = REL / "validacao_estrutural"
MOTOR = RAIZ / "codigo_fonte/experimentos/experimento_quantizacao_concorrentes.py"
REGIMES = ("historico_1998_2022", "historico_curto_pareado")
TAREFAS = ("monthly_1", "monthly_6", "daily_30", "hourly_72_extension")
FASES = ("selecao", "refit")
GRUPOS = ("concorrentes", "TimesNet")


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def salvar(d, p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def arquivo_contexto(regime, tarefa, fase, grupo):
    return SAIDA / regime / tarefa / fase / f"{grupo}.json"


def verificar_worker(regime, tarefa, fase, grupo):
    import numpy as np
    import pandas as pd
    from codigo_fonte.experimentos import experimento_quantizacao_concorrentes as motor

    inicio_execucao = time.perf_counter()
    antes = digest(MOTOR)
    proto_path = REL / f"protocolo_{regime}.json"
    protocolo = json.loads(proto_path.read_text(encoding="utf-8"))
    modelos = list(motor.MODELOS[:-1]) if grupo == "concorrentes" else ["TimesNet"]
    modelo = "XGBoost" if grupo == "concorrentes" else "TimesNet"
    ctx = motor.preparar_contexto(tarefa, fase, "completa", protocolo, modelo)
    inicio = pd.Timestamp(protocolo["inicio_dados"])
    corte = pd.Timestamp(protocolo["inicio_validacao"] if fase == "selecao" else protocolo["inicio_teste"])
    fim_contexto = pd.Timestamp(protocolo["inicio_teste"]) if fase == "selecao" else pd.Timestamp(protocolo["fim_dados"]) + pd.Timedelta(days=1)
    horario = ctx.tarefa.resolucao == "horaria"
    por_id = {s.localidade_id: s for s in ctx.series}
    erros = []
    avisos = []
    assert len(por_id) == 10
    assert digest(MOTOR) == antes
    parametros_modelos = {}
    for nome in modelos:
        par = motor.parametros(ctx, nome)
        parametros_modelos[nome] = {k: par[k] for k in ("sementes", "dispositivo", "perda", "batch_size", "max_epocas")}
    if grupo == "TimesNet":
        pasta = "busca_timesnet_mensal_20260920" if ctx.tarefa.resolucao == "mensal" else "busca_timesnet_resolucoes_20260922"
        vencedor = json.loads((RAIZ / "resultados" / pasta / tarefa / "selecao_congelada.json").read_text(encoding="utf-8"))["vencedor"]
        esperado_seq = vencedor["seq_len"] if ctx.tarefa.resolucao == "mensal" else vencedor["contexto"]
        if ctx.tarefa.seq_len != esperado_seq:
            erros.append(f"TimesNet recebeu seq_len={ctx.tarefa.seq_len}, vencedor exige {esperado_seq}.")
    else:
        esperado_seq = ctx.tarefa.seq_len
    escalas = ctx.escalas[fase].set_index("localidade_id")
    resumo_series = []
    for ident, serie in por_id.items():
        datas = serie.timestamp_local if horario else serie.datas
        assert datas.min() >= inicio and datas.max() < fim_contexto
        mask = (datas >= inicio) & (datas < corte)
        valores = serie.ghi[mask]
        escala = escalas.loc[ident]
        assert len(valores) == int(escala["N_horas_ajuste" if horario else "N_observacoes"])
        assert float(valores.min()) == float(escala["minimo_treino_wm2"])
        assert float(valores.max()) == float(escala["maximo_treino_wm2"])
        amplitude = float(valores.max()) - float(valores.min())
        assert float(escala["amplitude_escala_wm2"]) == (amplitude if amplitude > 0 else 1.0)
        if horario and pd.Timestamp(escala["inicio_local_inclusivo"]) != datas.min():
            avisos.append({"tipo": "metadado_inicio_escala_nominal", "localidade": serie.localidade,
                           "declarado": str(escala["inicio_local_inclusivo"]), "primeira_observacao_real": str(datas.min()),
                           "escala_recalculada_somente_com_dados_do_perfil": True})
        resumo_series.append({"localidade": serie.localidade, "inicio_real": str(datas.min()), "fim_real": str(datas.max()),
                              "n_observacoes_escala": len(valores), "corte_exclusivo": str(corte)})
    particoes = {}
    for parte, j in ctx.janelas.items():
        avaliacao = parte in ("validacao", "teste")
        inicio_parte = corte if avaliacao else inicio
        fim_parte = fim_contexto if avaliacao else corte
        origens = j.origem_local if horario else j.origem
        hchaves = hashlib.sha256()
        hchaves.update(j.localidade_id.astype("<i8").tobytes())
        hchaves.update(origens.as_unit("ns").asi8.astype("<i8").tobytes())
        if horario:
            hchaves.update(j.origem_utc.as_unit("ns").asi8.astype("<i8").tobytes())
        else:
            hchaves.update(j.datas_alvo.astype("datetime64[ns]").astype("<i8").tobytes())
        contagens = {}
        coberturas = []
        declarado = getattr(ctx.tarefa, parte).origens_esperadas_por_localidade
        for ident, serie in por_id.items():
            datas = serie.timestamp_local if horario else serie.datas
            pos_j = np.flatnonzero(j.localidade_id == ident)
            orig = origens[pos_j]
            pos = datas.get_indexer(orig)
            assert np.all(pos >= j.seq_len) and np.all(pos + j.pred_len <= len(datas))
            assert (orig >= inicio_parte).all()
            assert (datas[pos + j.pred_len - 1] < fim_parte).all()
            assert (datas[pos - j.seq_len] >= inicio).all()
            candidatos = np.flatnonzero((datas >= inicio_parte) & (datas < fim_parte))
            if horario:
                candidatos = candidatos[(datas[candidatos].hour == 0) & (datas[candidatos].minute == 0)]
            candidatos = candidatos[(candidatos >= j.seq_len) & (candidatos + j.pred_len <= len(datas))]
            candidatos = candidatos[datas[candidatos + j.pred_len - 1] < fim_parte]
            assert np.array_equal(pos, candidatos), f"Janelas omitidas/extras em {parte}/{serie.localidade}"
            for comeco in range(0, len(pos), 256):
                local = pos[comeco:comeco+256]
                linhas = pos_j[comeco:comeco+256]
                expected_x = serie.ghi[local[:, None] - j.seq_len + np.arange(j.seq_len)]
                expected_y = serie.ghi[local[:, None] + np.arange(j.pred_len)]
                assert np.array_equal(j.x_bruto[linhas], expected_x)
                assert np.array_equal(j.y_bruto[linhas], expected_y)
                if not horario:
                    expected_dates = datas.to_numpy(dtype="datetime64[ns]")[local[:, None] + np.arange(j.pred_len)]
                    assert np.array_equal(j.datas_alvo[linhas], expected_dates)
            contagens[serie.localidade] = len(pos)
            if len(pos) != declarado:
                erros.append(f"{parte}/{serie.localidade}: contrato declara {declarado} origens, disponiveis e construidas {len(pos)}.")
            coberturas.append({"localidade": serie.localidade, "origem_inicial": str(orig.min()), "origem_final": str(orig.max()),
                               "primeiro_contexto": str(datas[pos[0]-j.seq_len]), "ultimo_alvo": str(datas[pos[-1]+j.pred_len-1]),
                               "ultima_observacao_disponivel": str(datas.max())})
        particoes[parte] = {"n": len(j.x_bruto), "origens_por_localidade": contagens,
                            "origens_declaradas_por_localidade": declarado, "chaves_sha256": hchaves.hexdigest(),
                            "x_bruto_sha256": hashlib.sha256(j.x_bruto.astype("<f4").tobytes()).hexdigest(),
                            "y_bruto_sha256": hashlib.sha256(j.y_bruto.astype("<f4").tobytes()).hexdigest(),
                            "cobertura": coberturas, "horizontes": list(ctx.tarefa.horizontes),
                            "alvos_e_contextos_reconstruidos_da_fonte": True}
    assert digest(MOTOR) == antes
    out = {"ok": not erros, "regime": regime, "tarefa": tarefa, "fase": fase, "grupo": grupo,
           "modelos": modelos, "seq_len": ctx.tarefa.seq_len, "seq_len_otimizado_esperado": esperado_seq,
           "pred_len": ctx.tarefa.pred_len, "motor_sha256": antes, "protocolo_sha256": digest(proto_path),
           "treinamento_iniciado": False, "escalas_recalculadas_train_only": True,
           "contextos_anteriores_ao_inicio": False, "series": resumo_series, "particoes": particoes,
           "parametros_modelos": parametros_modelos, "erros": erros, "avisos": avisos,
           "segundos": time.perf_counter() - inicio_execucao}
    salvar(out, arquivo_contexto(regime, tarefa, fase, grupo))
    del ctx, por_id, j, serie, escalas
    gc.collect()
    print(json.dumps({k: out[k] for k in ("ok", "regime", "tarefa", "fase", "grupo", "seq_len", "segundos")}), flush=True)
    return out


def consolidar():
    resultados = []
    for regime in REGIMES:
        for tarefa in TAREFAS:
            for fase in FASES:
                for grupo in GRUPOS:
                    resultados.append(json.loads(arquivo_contexto(regime, tarefa, fase, grupo).read_text(encoding="utf-8")))
    pares = []
    for tarefa in TAREFAS:
        for fase in FASES:
            parte = "validacao" if fase == "selecao" else "teste"
            conjunto = [r for r in resultados if r["tarefa"] == tarefa and r["fase"] == fase and "particoes" in r]
            igual = len(conjunto) == 4 and all(len({r["particoes"][parte][chave] for r in conjunto}) == 1
                                              for chave in ("chaves_sha256", "x_bruto_sha256", "y_bruto_sha256"))
            pares.append({"tarefa": tarefa, "fase": fase, "particao": parte,
                          "mesmos_alvos_origens_contextos_brutos_entre_perfis_e_modelos": igual})
    pares_modelos = []
    for regime in REGIMES:
        for tarefa in TAREFAS:
            for fase in FASES:
                conjunto = [r for r in resultados if r["regime"] == regime and r["tarefa"] == tarefa and r["fase"] == fase and "particoes" in r]
                igual = len(conjunto) == 2 and all(
                    len({r["particoes"][parte][chave] for r in conjunto}) == 1
                    for parte in conjunto[0]["particoes"] for chave in ("chaves_sha256", "x_bruto_sha256", "y_bruto_sha256"))
                pares_modelos.append({"regime": regime, "tarefa": tarefa, "fase": fase,
                                      "todas_particoes_iguais_entre_concorrentes_e_TimesNet": igual})
    arvore = ast.parse(MOTOR.read_text(encoding="utf-8"))
    funcao = next(n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name == "preparar_contexto")
    usos_modelo = sum(isinstance(n, ast.Name) and n.id == "modelo" for n in ast.walk(funcao))
    aprovado = (all(r.get("ok", False) for r in resultados)
                and all(p["mesmos_alvos_origens_contextos_brutos_entre_perfis_e_modelos"] for p in pares)
                and all(p["todas_particoes_iguais_entre_concorrentes_e_TimesNet"] for p in pares_modelos))
    relatorio = {"ok": aprovado, "aprovado": aprovado, "treinamentos_iniciados": False,
                 "contextos_construidos": len(resultados), "comparacoes_pareadas": pares,
                 "comparacoes_entre_modelos_por_perfil": pares_modelos,
                 "argumento_modelo_sem_ramo_no_contexto": usos_modelo == 0,
                 "escopo_modelos": "Os seis concorrentes compartilham a construcao; seus parametros foram conferidos. TimesNet foi construida separadamente. Nenhuma rede foi criada ou treinada.",
                 "resultados": resultados, "motor_sha256_atual": digest(MOTOR)}
    salvar(relatorio, REL / "validacao_contextos_historicos.json")
    print(json.dumps({"ok": aprovado, "contextos": len(resultados), "pareamentos_ok": sum(x["mesmos_alvos_origens_contextos_brutos_entre_perfis_e_modelos"] for x in pares)}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worker", nargs=4, metavar=("REGIME", "TAREFA", "FASE", "GRUPO"))
    p.add_argument("--somente-consolidar", action="store_true")
    args = p.parse_args()
    if args.worker:
        try:
            verificar_worker(*args.worker)
        except Exception as exc:
            salvar({"ok": False, "regime": args.worker[0], "tarefa": args.worker[1], "fase": args.worker[2], "grupo": args.worker[3],
                    "erro_construcao": str(exc), "traceback": traceback.format_exc(), "motor_sha256": digest(MOTOR), "treinamento_iniciado": False}, arquivo_contexto(*args.worker))
            traceback.print_exc()
            raise
        return
    if args.somente_consolidar:
        consolidar()
        return
    fonte = digest(MOTOR)
    for regime in REGIMES:
        for tarefa in TAREFAS:
            for fase in FASES:
                for grupo in GRUPOS:
                    if digest(MOTOR) != fonte:
                        raise RuntimeError("Motor mudou durante a validacao; nao misturar revisoes.")
                    destino = arquivo_contexto(regime, tarefa, fase, grupo)
                    if destino.exists():
                        antigo = json.loads(destino.read_text(encoding="utf-8"))
                        if antigo.get("motor_sha256") == fonte and "particoes" in antigo:
                            continue
                    r = subprocess.run([sys.executable, "-X", "utf8", "-u", "-m", "codigo_fonte.analises_e_relatorios.validar_contextos_historicos", "--worker", regime, tarefa, fase, grupo], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
                    print(r.stdout.strip() or r.stderr[-2000:], flush=True)
                    gc.collect()
    consolidar()


if __name__ == "__main__":
    main()
