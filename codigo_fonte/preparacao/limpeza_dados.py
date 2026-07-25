"""Operacoes de limpeza e agregacao anteriores a base mensal."""

from codigo_fonte.preprocessamento import (
    detectar_colunas,
    garantir_resolucao_diaria,
    garantir_resolucao_mensal,
    limpar_serie_ghi,
)


limpar_ghi = limpar_serie_ghi
agregar_por_dia = garantir_resolucao_diaria
agregar_por_mes = garantir_resolucao_mensal

__all__ = [
    "agregar_por_dia",
    "agregar_por_mes",
    "detectar_colunas",
    "limpar_ghi",
]
