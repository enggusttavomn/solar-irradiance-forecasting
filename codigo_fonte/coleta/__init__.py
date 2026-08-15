"""Coleta da GHI e cadastro auditavel das localidades."""

from codigo_fonte.coleta.api_nsrdb import coletar_ghi, consultar_anos_disponiveis
from codigo_fonte.coleta.localidades import LOCALIDADES, listar_localidades

__all__ = [
    "LOCALIDADES",
    "coletar_ghi",
    "consultar_anos_disponiveis",
    "listar_localidades",
]
