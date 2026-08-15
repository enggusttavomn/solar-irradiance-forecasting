"""Long Short-Term Memory global usada no protocolo mensal."""

from codigo_fonte.modelos_neurais_globais import (
    construir_rede_global,
    prever_rede_global,
    salvar_rede_global,
    treinar_rede_global_com_validacao_temporal,
)


def construir(**configuracao):
    """Constroi a arquitetura LSTM global."""

    return construir_rede_global("LSTM", **configuracao)


def treinar(*args, **configuracao):
    """Seleciona epocas temporalmente e reajusta a LSTM no pre-teste."""

    return treinar_rede_global_com_validacao_temporal("LSTM", *args, **configuracao)


prever = prever_rede_global
salvar = salvar_rede_global

__all__ = ["construir", "prever", "salvar", "treinar"]
