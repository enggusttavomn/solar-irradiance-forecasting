"""Executa selecao das duas tarefas, congela e executa refits; registra logs."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

RAIZ = Path(__file__).resolve().parents[1]
TAREFAS = ("hourly_72_extension", "daily_30")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    saida = RAIZ / ("tmp/quantizacao_resolucoes_smoke_20260927" if args.smoke else
                    "resultados/quantizacao_timesnet_resolucoes_20260927")
    rel = RAIZ / "relatorios/quantizacao_timesnet_quatro_casos_20260927"
    rel.mkdir(parents=True, exist_ok=True)
    status_path = rel / ("runner_smoke.json" if args.smoke else "runner_completo.json")
    processos = []
    handles = []
    flag = 0x80000001
    if not ctypes.windll.kernel32.SetThreadExecutionState(flag):
        raise OSError("Nao foi possivel manter a execucao ativa.")

    def registrar(**dados):
        dados["atualizado_em_utc"] = datetime.now(timezone.utc).isoformat()
        status_path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        for fase in ("selecao", "refit"):
            if fase == "refit":
                subprocess.run([sys.executable, "-X", "utf8", "-m", "codigo_fonte.experimento_quantizacao_resolucoes",
                    "--fase", "congelar", "--saida", str(saida)], cwd=RAIZ, check=True)
            processos = []
            for tarefa in TAREFAS:
                log = rel / f"{'smoke_' if args.smoke else ''}{fase}_{tarefa}.log"
                h = log.open("a", encoding="utf-8")
                handles.append(h)
                cmd = [sys.executable, "-X", "utf8", "-m", "codigo_fonte.experimento_quantizacao_resolucoes",
                       "--tarefa", tarefa, "--fase", fase, "--saida", str(saida), "--workers", "1"]
                if args.smoke:
                    cmd.append("--smoke")
                p = subprocess.Popen(cmd, cwd=RAIZ, stdout=h, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                processos.append((tarefa, p, log))
            registrar(etapa=fase, modo="smoke" if args.smoke else "completa", pasta_saida=str(saida),
                      processos=[{"tarefa": t, "pid": p.pid, "log": str(log)} for t, p, log in processos])
            ultimo = 0.
            while any(p.poll() is None for _, p, _ in processos):
                if time.monotonic() - ultimo >= 60:
                    print(f"{fase}: " + "; ".join(f"{t}={'rodando' if p.poll() is None else p.returncode}"
                          for t, p, _ in processos), flush=True)
                    ultimo = time.monotonic()
                time.sleep(5)
            falhas = [(t, p.returncode) for t, p, _ in processos if p.returncode]
            if falhas:
                raise RuntimeError(f"Fase {fase} falhou: {falhas}; verificar logs.")
            for h in handles:
                h.close()
            handles.clear()
        registrar(etapa="concluida", modo="smoke" if args.smoke else "completa", pasta_saida=str(saida))
        print("Duas tarefas completas. Suspensao normal sera restaurada.", flush=True)
    except BaseException as exc:
        registrar(etapa="erro", tipo=type(exc).__name__, mensagem=str(exc))
        raise
    finally:
        for _, p, _ in processos:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=30)
        for h in handles:
            h.close()
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        print("Preferencia normal de suspensao restabelecida.", flush=True)


if __name__ == "__main__":
    main()
