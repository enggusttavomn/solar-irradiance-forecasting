"""DeepAR global probabilistico usado como comparador do DeepNPTS."""

from codigo_fonte.modelos_globais_gluonts import (
    DeepARGlobalGluonTS,
    carregar_modelo_global_gluonts,
    previsoes_para_dataframe,
)


DeepAR = DeepARGlobalGluonTS
carregar = carregar_modelo_global_gluonts
para_dataframe = previsoes_para_dataframe

__all__ = ["DeepAR", "carregar", "para_dataframe"]
