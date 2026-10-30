"""Redes DeepNPTS do GluonTS com embeddings registrados pelo PyTorch.

No GluonTS 0.16.2, o ``FeatureEmbedder`` interno do DeepNPTS armazena as
camadas ``Embedding`` em uma lista Python comum. Com isso, seus pesos nao
entram em ``parameters()`` nem em ``state_dict()``, embora sejam usados no
``forward``. As subclasses abaixo preservam integralmente as redes oficiais e
apenas convertem essa lista em ``nn.ModuleList`` logo apos a inicializacao.

Essa correcao faz com que a categoria estatica da localidade seja efetivamente
treinada e que o predictor serializado reproduza o modelo ajustado.
"""

from __future__ import annotations

from typing import Any

from torch import nn

from gluonts.torch.model.deep_npts import (
    DeepNPTSNetworkDiscrete,
    DeepNPTSNetworkSmooth,
)


def _registrar_embeddings(rede: nn.Module) -> None:
    """Substitui a lista nao registrada por ``ModuleList`` sem reinicializar."""

    embedders = rede.embedder.embedders
    if not isinstance(embedders, nn.ModuleList):
        rede.embedder.embedders = nn.ModuleList(list(embedders))


class DeepNPTSNetworkDiscreteRegistrada(DeepNPTSNetworkDiscrete):
    """Variante discreta oficial com registro correto dos embeddings."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _registrar_embeddings(self)


class DeepNPTSNetworkSmoothRegistrada(DeepNPTSNetworkSmooth):
    """Variante suave oficial com registro correto dos embeddings."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _registrar_embeddings(self)


__all__ = [
    "DeepNPTSNetworkDiscreteRegistrada",
    "DeepNPTSNetworkSmoothRegistrada",
]
