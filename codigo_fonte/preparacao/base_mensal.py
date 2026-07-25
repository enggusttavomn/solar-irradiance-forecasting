"""Construcao das janelas mensais usadas por todos os modelos."""

from codigo_fonte.dados_mensais_globais import (
    BaseMensalGlobal,
    SerieMensalGlobal,
    auditar_arquivos_diarios,
    carregar_base_mensal_global,
    matrizes_keras,
)


BaseMensal = BaseMensalGlobal
SerieMensal = SerieMensalGlobal
carregar_base_mensal = carregar_base_mensal_global
criar_matrizes_recorrentes = matrizes_keras
auditar_dados_diarios = auditar_arquivos_diarios

__all__ = [
    "BaseMensal",
    "SerieMensal",
    "auditar_dados_diarios",
    "carregar_base_mensal",
    "criar_matrizes_recorrentes",
]
