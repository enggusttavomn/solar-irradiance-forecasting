"""Cadastro publico das dez localidades associadas as fabricas."""

from codigo_fonte.localidades_ev import (
    LOCALIDADES_EV,
    dataframe_localidades,
    distancia_haversine_km,
)


LOCALIDADES = LOCALIDADES_EV
listar_localidades = dataframe_localidades

__all__ = ["LOCALIDADES", "distancia_haversine_km", "listar_localidades"]
