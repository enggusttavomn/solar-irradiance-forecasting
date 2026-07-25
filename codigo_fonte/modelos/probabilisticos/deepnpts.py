"""DeepNPTS discreto, modelo principal avaliado pelo projeto."""

from codigo_fonte.modelos_globais_gluonts import (
    DeepNPTSGlobalGluonTS,
    carregar_modelo_global_gluonts,
    previsoes_para_dataframe,
)


DeepNPTS = DeepNPTSGlobalGluonTS
carregar = carregar_modelo_global_gluonts
para_dataframe = previsoes_para_dataframe


def redes_com_embeddings_registrados():
    """Retorna as redes corrigidas, importando PyTorch apenas quando necessario."""

    from codigo_fonte.redes_deepnpts_registradas import (
        DeepNPTSNetworkDiscreteRegistrada,
        DeepNPTSNetworkSmoothRegistrada,
    )

    return DeepNPTSNetworkDiscreteRegistrada, DeepNPTSNetworkSmoothRegistrada


__all__ = [
    "DeepNPTS",
    "carregar",
    "para_dataframe",
    "redes_com_embeddings_registrados",
]
