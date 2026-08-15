"""Entrada publica do protocolo mensal global canonico."""

from codigo_fonte.experimento_mensal_canonico import (
    ConfiguracaoExperimento,
    executar_experimento,
    main,
)


Configuracao = ConfiguracaoExperimento
executar = executar_experimento

__all__ = ["Configuracao", "executar", "main"]
