"""Agenda selecoes e refits retomaveis com limites separados de CPU e GPU."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from scripts.json_atomico import salvar_json
from scripts.processos_quantizacao import TravaDiretorio, ProcessoProprio, identidade

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "resultados/quantizacao_todos_modelos_20260929"
REL = RAIZ / "relatorios/quantizacao_todos_modelos_20260929"
TAREFAS = ("daily_30", "hourly_72_extension", "monthly_6", "monthly_1")
MODELOS = ("GRU", "LSTM", "DilatedRNN", "Transformer", "Informer", "XGBoost",
           "ARIMA", "Persistencia", "Sazonal ingenuo", "Climatologia", "TimesNet")
ESTATISTICOS = {"ARIMA", "Persistencia", "Sazonal ingenuo", "Climatologia"}


def agora():
    return datetime.now(timezone.utc).isoformat()


def salvar(dados, path):
    salvar_json(dados, path)


def hash_arquivo(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def slug(modelo):
    return modelo.lower().replace(" ", "_")


def recurso(args, tarefa, modelo):
    return "gpu" if tarefa in ("hourly_72_extension", "daily_30") and modelo in args.gpu_modelos else "cpu"


def comando(args, tarefa, modelo, fase):
    modulo = "experimento_quantizacao_estatisticos" if modelo in ESTATISTICOS else "experimento_quantizacao_concorrentes"
    if args.regime == 'atual' and tarefa == 'hourly_72_extension' and modelo == 'ARIMA' and not args.smoke:
        modulo = 'experimento_arima_horario_controle_auditado_v1'
    if (args.regime == 'atual' and tarefa == 'hourly_72_extension' and modelo == 'XGBoost'
            and fase == 'refit' and not args.smoke):
        modulo = 'experimento_xgboost_horario_controle_auditado_v1'
    if tarefa in ('daily_30', 'hourly_72_extension') and modelo in ('Transformer', 'Informer'):
        modulo = 'experimento_atencao_deterministica_v1'
    if (args.regime in ('historico_1998_2022', 'historico_curto_pareado')
            and tarefa in ('monthly_1', 'monthly_6') and modelo == 'Sazonal ingenuo'
            and not args.smoke):
        modulo = 'experimento_sazonal_mensal_controle_auditado_v1'
    cmd = [sys.executable, "-X", "utf8", "-m", "codigo_fonte." + modulo,
           "--tarefa", tarefa, "--modelo", modelo, "--regime", args.regime,
           "--fase", fase, "--saida", str(args.saida)]
    if tarefa in ("hourly_72_extension", "daily_30") and modelo in ("LSTM", "GRU", "DilatedRNN"):
        cmd += ["--dispositivo", "cuda"]
    if args.smoke:
        cmd.append("--smoke")
    if args.protocolo:
        cmd += ["--protocolo", str(args.protocolo.resolve())]
    return cmd


def fases(args):
    if getattr(args, "somente_refit", False):
        return ("refit",)
    return ("selecao",) if args.somente_selecao else ("selecao", "refit")


def congelar(args, pares):
    global_path = args.saida / args.regime / "selecao_global_congelada.json"
    somente_refit = getattr(args, "somente_refit", False)
    if somente_refit and not global_path.is_file():
        raise ValueError("Somente refit requer congelamento global existente; selecoes nao serao criadas.")
    fontes = {}
    for tarefa, modelo in pares:
        pasta = args.saida / args.regime / tarefa / slug(modelo)
        path = pasta / "selecao_congelada.json"
        selecao = json.loads(path.read_text(encoding="utf-8"))
        if not (selecao.get("selecao_concluida_antes_refit") is True
                or selecao.get("selecao_concluida_antes_do_teste") is True):
            raise ValueError(f"Selecao nao congelada: {path}")
        for p in (path, pasta / "contrato_execucao.json", pasta / "contrato.json"):
            if p.is_file():
                fontes[str(p.resolve())] = hash_arquivo(p)
    payload = {"regime": args.regime, "modo": "smoke" if args.smoke else "completa",
               "pares": [list(x) for x in pares], "fontes_sha256": fontes}
    if global_path.exists():
        anterior = json.loads(global_path.read_text(encoding="utf-8"))
        if not isinstance(anterior, dict):
            raise ValueError("Congelamento global deve ser um objeto JSON.")
        if any(anterior.get(k) != v for k, v in payload.items()):
            raise ValueError("Congelamento global existente diverge; arquivos nao sobrescritos.")
    else:
        # Nao recriar se o arquivo desaparecer durante a verificacao.
        if somente_refit:
            raise ValueError("Congelamento global desapareceu; somente refit bloqueado.")
        salvar({**payload, "congelado_em_utc": agora()}, global_path)
    return str(global_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regime", choices=("atual", "historico_1998_2022", "historico_curto_pareado"), default="atual")
    ap.add_argument("--saida", type=Path, default=SAIDA)
    ap.add_argument("--relatorios", type=Path, default=REL)
    ap.add_argument("--tarefas", nargs="+", choices=TAREFAS, default=list(TAREFAS))
    ap.add_argument("--modelos", nargs="+", choices=MODELOS, default=list(MODELOS))
    ap.add_argument("--cpu-workers", type=int, default=2)
    ap.add_argument("--gpu-workers", type=int, default=1)
    ap.add_argument("--gpu-modelos", nargs="+", default=["LSTM", "GRU", "DilatedRNN", "Transformer", "Informer", "TimesNet"])
    ap.add_argument("--protocolo", type=Path)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    grupo_fases = ap.add_mutually_exclusive_group()
    grupo_fases.add_argument("--somente-selecao", action="store_true")
    grupo_fases.add_argument("--somente-refit", action="store_true")
    args = ap.parse_args()
    if min(args.cpu_workers, args.gpu_workers) < 1:
        ap.error("Numero de workers deve ser positivo.")
    if len(set(args.tarefas)) != len(args.tarefas) or len(set(args.modelos)) != len(args.modelos):
        ap.error("Tarefas e modelos devem ser unicos.")
    if args.smoke and args.saida == SAIDA:
        args.saida = RAIZ / "tmp/quantizacao_todos_modelos_20260929/smoke_runner"
    todos_pares = [(t, m) for t in args.tarefas for m in args.modelos]
    # TimesNet atual e importada de execucoes completas previamente auditadas.
    pares = [(t, m) for t, m in todos_pares if not (args.regime == "atual" and m == "TimesNet" and not args.smoke)]
    fases_plano = ("refit",) if args.somente_refit else ("selecao",)
    plan = [{"fase": fase, "tarefa": t, "modelo": m, "recurso": recurso(args, t, m),
             "comando": comando(args, t, m, fase)} for fase in fases_plano for t, m in pares]
    if args.dry_run:
        if args.somente_refit:
            congelar(args, todos_pares)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    rel = args.relatorios / args.regime / ("smoke" if args.smoke else "completa")
    rel.mkdir(parents=True, exist_ok=True)
    with TravaDiretorio(rel):
        executar_fila(args, rel, pares, todos_pares)


def executar_fila(args, rel, pares, todos_pares):
    status_path = rel / 'runner.json'
    registro_runner = identidade(os.getpid())
    processos_historico = []
    executando, concluidos, falhas = [], [], []
    inicio = agora()
    suspensao = False
    if os.name == "nt":
        suspensao = bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
        if not suspensao:
            raise OSError("Falha ao manter computador ativo durante os experimentos.")

    def registrar(fase, pendentes=()):
        salvar({"regime": args.regime, "modo": "smoke" if args.smoke else "completa",
                "etapa": fase, "iniciado_em_utc": inicio, "atualizado_em_utc": agora(),
                "pid_runner": os.getpid(), "identidade_runner": registro_runner,
                "processos_historico": processos_historico, "saida": str(args.saida.resolve()),
                "pendentes": [list(x) for x in pendentes], "concluidos": concluidos,
                "falhas": falhas, "processos": [{k: j[k] for k in ("tarefa", "modelo", "recurso", "pid", "creation_time", "log", "inicio")}
                                                 for j in executando]}, status_path)

    try:
        for fase in fases(args):
            if fase == "refit":
                congelar(args, todos_pares)
            pendentes = list(pares)
            while pendentes or executando:
                for classe, limite in (("gpu", args.gpu_workers), ("cpu", args.cpu_workers)):
                    while sum(j["recurso"] == classe for j in executando) < limite:
                        indice = next((i for i, (t, m) in enumerate(pendentes)
                                       if recurso(args, t, m) == classe), None)
                        if indice is None:
                            break
                        t, modelo = pendentes.pop(indice)
                        path_log = rel / f"{fase}_{t}_{slug(modelo)}.log"
                        handle = path_log.open("a", encoding="utf-8")
                        cmd = comando(args, t, modelo, fase)
                        handle.write(f"\nInicio {agora()}\n")
                        handle.flush()
                        try:
                            processo = ProcessoProprio(cmd, cwd=RAIZ, stdout=handle, stderr=subprocess.STDOUT)
                        except BaseException:
                            handle.close()
                            raise
                        processos_historico.append(processo.registro)
                        executando.append({"tarefa": t, "modelo": modelo, "recurso": classe,
                                           "pid": processo.pid, "creation_time": processo.registro["creation_time"], "log": str(path_log), "inicio": agora(),
                                           "processo": processo, "handle": handle})
                        print(f"{fase}: iniciado {t}/{modelo} ({classe}) pid={processo.pid}", flush=True)
                for job in executando[:]:
                    retorno = job["processo"].poll()
                    if retorno is None:
                        continue
                    job["processo"].fechar()
                    job["handle"].close()
                    registro = {"fase": fase, "tarefa": job["tarefa"], "modelo": job["modelo"],
                                "returncode": retorno, "log": job["log"], "concluido_em_utc": agora()}
                    (concluidos if retorno == 0 else falhas).append(registro)
                    executando.remove(job)
                    print(f"{fase}: finalizado {job['tarefa']}/{job['modelo']} retorno={retorno}", flush=True)
                registrar(fase, pendentes)
                if pendentes or executando:
                    time.sleep(5)
            if falhas:
                raise RuntimeError(f"{len(falhas)} execucoes falharam; outras selecoes foram preservadas. Consulte {status_path}")
        registrar("selecao_concluida" if args.somente_selecao else "concluida")
        print(f"Regime {args.regime}: fases solicitadas concluidas. Auditoria ainda obrigatoria antes do PDF.", flush=True)
    except BaseException as exc:
        falhas.append({"tipo": type(exc).__name__, "mensagem": str(exc), "instante": agora()})
        registrar("interrompida" if isinstance(exc, KeyboardInterrupt) else "erro")
        raise
    finally:
        for job in executando:
            job["processo"].encerrar()
            job["handle"].close()
        if suspensao:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        print("Suspensao normal restabelecida; checkpoints anteriores preservados.", flush=True)


if __name__ == "__main__":
    main()
