"""Entrada reproduzivel da revisao (ARIMA com contingencia numerica incluida).

Na raiz: python -m codigo_fonte.experimentos.executar_baselines_revisao --modo completa --workers 3
Padrao smoke: resultados de teste rapido, nunca publicaveis.
Use o Python do ambiente requirements-baselines-adicionais.txt (CPython 3.14).
Nao execute uma segunda instancia sobre processos ainda ativos no mesmo destino.
"""
import argparse
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys

RAIZ = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--modo", choices=["smoke", "completa"], default="smoke")
    ap.add_argument("--workers", type=int, choices=[1, 2, 3, 4], default=1)
    args = ap.parse_args()
    env = {**os.environ, "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def executar(modelo):
        if modelo == "ARIMA":
            cmd = [sys.executable, "-u", "-m", "codigo_fonte.experimentos.experimento_arima_robusto", "--modo", args.modo]
        else:
            cmd = [sys.executable, "-u", "-m", "codigo_fonte.experimentos.experimento_baselines_adicionais", "--modelo", modelo, "--modo", args.modo]
        retorno = subprocess.run(cmd, cwd=RAIZ, env=env, creationflags=flags)
        if retorno.returncode:
            raise RuntimeError(f"{modelo} falhou; consultar status e logs, sem substituir resultados.")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        resultados = [pool.submit(executar, modelo) for modelo in ("GRU", "Transformer", "Informer", "ARIMA")]
        for resultado in concurrent.futures.as_completed(resultados):
            resultado.result()
    if args.modo == "completa":
        subprocess.run([sys.executable, "-m", "codigo_fonte.analises_e_relatorios.consolidar_baselines_adicionais"], cwd=RAIZ, env=env, check=True)
        subprocess.run([sys.executable, "-m", "codigo_fonte.publicacoes.gerar_tabelas_baselines_adicionais"], cwd=RAIZ, env=env, check=True)


if __name__ == "__main__":
    main()
