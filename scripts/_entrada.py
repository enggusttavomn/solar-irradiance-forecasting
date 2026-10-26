"""Executa um comando histórico mantendo seu bloco de linha de comando."""

from __future__ import annotations

from runpy import run_module


def executar(modulo: str) -> None:
    """Reutiliza o comando original, inclusive argumentos e códigos de saída."""
    run_module(modulo, run_name="__main__", alter_sys=True)
