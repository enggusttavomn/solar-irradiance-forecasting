"""Transformer e Informer da revisao na GPU, com o mesmo protocolo da CPU.

Executar (ambiente com torch==2.12.0+cu126):
  python -m codigo_fonte.experimento_baselines_gpu --modelo Transformer --modo completa
Reutiliza experimento_baselines_adicionais sem alteracao: janelas, selecao, refit,
sementes, caches e status. Muda somente onde a rede calcula: as entradas vao para
a GPU e a saida volta para a CPU, entao perda, early stopping e previsoes seguem o
laco canonico. O contrato registra GPU, CUDA e o hash deste arquivo, logo destinos
CPU e GPU nunca se misturam. Checkpoints .pt guardam tensores CUDA: carregar com
map_location="cpu".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

# cuBLAS so e deterministico com workspace fixo, definido antes de iniciar CUDA.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import torch
from torch import nn

from codigo_fonte import experimento_baselines_adicionais as e
from codigo_fonte import experimento_multirresolucao as m

MODELOS_GPU = ("Transformer", "Informer")
TAREFAS_GPU = ("daily_30", "hourly_72_extension")
_contrato_cpu = e.contrato
_criar_baseline_cpu = e.redes.criar_baseline


def no_dispositivo(rede: nn.Module, dispositivo: torch.device) -> nn.Module:
    """Move a rede; entradas seguem para o dispositivo e a saida volta a CPU."""
    rede.to(dispositivo)
    rede.register_forward_pre_hook(lambda _, entradas: tuple(t.to(dispositivo) for t in entradas))
    rede.register_forward_hook(lambda _, __, saida: saida.cpu())
    return rede


def contrato_gpu(ctx: e.Contexto, modelo: str) -> dict:
    c = _contrato_cpu(ctx, modelo)
    c.pop("sha256_contrato")
    c["execucao"] = {"dispositivo": "cuda", "gpu": torch.cuda.get_device_name(0),
        "cuda": torch.version.cuda, "cudnn": torch.backends.cudnn.version(),
        "cublas_workspace_config": os.environ["CUBLAS_WORKSPACE_CONFIG"]}
    c["arquivos_codigo"].append({"arquivo": str(Path(__file__).resolve()), "sha256": m.sha256_arquivo(Path(__file__))})
    c["sha256_contrato"] = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()
    return json.loads(json.dumps(c))


def ativar_gpu() -> None:
    """Redireciona a criacao das redes e o contrato; o restante do fluxo e o da CPU."""
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA indisponivel: use o ambiente com torch==2.12.0+cu126.")
    gpu = torch.device("cuda")
    e.redes.criar_baseline = lambda *a, **k: no_dispositivo(_criar_baseline_cpu(*a, **k), gpu)
    e.contrato = contrato_gpu


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tarefa", choices=list(e.TAREFAS), nargs="+", default=list(TAREFAS_GPU))
    ap.add_argument("--modelo", choices=MODELOS_GPU, required=True)
    ap.add_argument("--modo", choices=["smoke", "completa"], default="smoke")
    ap.add_argument("--saida", type=Path)
    args = ap.parse_args()
    saida = args.saida or (e.SAIDA if args.modo == "completa" else e.RAIZ / "tmp/revisao_literatura_20260912/smoke_baselines_gpu")
    ativar_gpu()
    for tarefa in args.tarefa:
        e.executar(e.preparar_contexto(tarefa, args.modo), args.modelo, saida)


if __name__ == "__main__":
    main()
