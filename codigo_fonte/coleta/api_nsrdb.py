"""Interface publica para a coleta de GHI no produto NSRDB usado no projeto.

A implementacao cientifica permanece em :mod:`codigo_fonte.preprocessamento`
porque esse arquivo faz parte do manifesto da execucao canonica. Este modulo
oferece um nome e um caminho mais diretos para novas leituras do projeto.
"""

from codigo_fonte.preprocessamento import (
    NSRDB_API_URL,
    NSRDB_DATASET,
    NSRDB_PRODUCT,
    coletar_ghi_nrel,
    consultar_anos_disponiveis_nsrdb,
)


coletar_ghi = coletar_ghi_nrel
consultar_anos_disponiveis = consultar_anos_disponiveis_nsrdb

__all__ = [
    "NSRDB_API_URL",
    "NSRDB_DATASET",
    "NSRDB_PRODUCT",
    "coletar_ghi",
    "consultar_anos_disponiveis",
]
