"""DilatedRNN customizada com saltos recorrentes 1, 2 e 4."""

from codigo_fonte.modelos_neurais_globais import (
    construir_rede_global,
    prever_rede_global,
    salvar_rede_global,
    treinar_rede_global_com_validacao_temporal,
)


def construir(**configuracao):
    """Constroi as tres camadas recorrentes dilatadas."""

    return construir_rede_global("DILATEDRNN", **configuracao)


def treinar(*args, **configuracao):
    """Seleciona epocas e reajusta a DilatedRNN em todo o pre-teste."""

    return treinar_rede_global_com_validacao_temporal(
        "DILATEDRNN", *args, **configuracao
    )


prever = prever_rede_global
salvar = salvar_rede_global

__all__ = ["construir", "prever", "salvar", "treinar"]
