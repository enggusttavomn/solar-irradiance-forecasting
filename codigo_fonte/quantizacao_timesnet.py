"""Quantizacao uniforme das entradas TimesNet depois do min-max existente.

Os alvos continuam sendo regressao continua, na mesma escala min-max de
treino. Para N niveis, a entrada e limitada a [0, 1] e transformada por
``rint(x * (N - 1)) / (N - 1)``. Os empates seguem o arredondamento para o
inteiro par de ``numpy.rint``. Nenhuma escala e ajustada por este modulo.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

import numpy as np
import pandas as pd

from codigo_fonte.experimento_multirresolucao import JanelasDiretas


def _validar_niveis(niveis: int | None) -> int | None:
    if niveis is None:
        return None
    if isinstance(niveis, (bool, np.bool_)) or not isinstance(niveis, (int, np.integer)):
        raise ValueError("niveis deve ser None ou um inteiro maior ou igual a 2.")
    niveis = int(niveis)
    if niveis < 2:
        raise ValueError("niveis deve ser None ou um inteiro maior ou igual a 2.")
    try:
        passo_inverso = float(niveis - 1)
    except OverflowError as erro:
        raise ValueError("niveis excede a representacao numerica finita.") from erro
    if not np.isfinite(passo_inverso):
        raise ValueError("niveis excede a representacao numerica finita.")
    return niveis


def _entrada_finita(x_normalizado: np.ndarray) -> np.ndarray:
    valores = np.asarray(x_normalizado)
    if valores.dtype.kind not in "fiu" or not np.isfinite(valores).all():
        raise ValueError("As entradas normalizadas devem ser numeros reais finitos.")
    return valores


def quantizar_entradas(x_normalizado: np.ndarray, niveis: int | None) -> np.ndarray:
    """Aplica a mesma transformacao de entradas no treino e na inferencia.

    Retorna um novo array float32 quando ha quantizacao. ``None`` devolve
    uma copia exata, preservando inclusive dtype e valores fora de [0, 1].
    A entrada nunca e alterada. Valores nao finitos sao rejeitados em ambos
    os modos. O limite de erro 1/(2*(N-1)) vale antes da conversao float32
    para entradas que ja pertencem a [0, 1].
    """

    niveis = _validar_niveis(niveis)
    valores = _entrada_finita(x_normalizado)
    if niveis is None:
        return valores.copy()
    # Limitar antes de converter tambem evita overflow para entradas finitas
    # de maior precisao. Calcular em float64 torna os empates explicitos.
    limitados = np.clip(valores, 0.0, 1.0).astype(np.float64, copy=False)
    fator = float(niveis - 1)
    return (np.rint(limitados * fator) / fator).astype(np.float32)


@dataclass(frozen=True)
class JanelasDiretasQuantizadas(JanelasDiretas):
    """Mantem dados e metadados brutos; quantiza somente x ao normalizar."""

    niveis: int | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "niveis", _validar_niveis(self.niveis))

    def normalizar(self, escalas: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        x, y = super().normalizar(escalas)
        return quantizar_entradas(x, self.niveis), y


def aplicar_quantizacao(janelas: JanelasDiretas, niveis: int | None) -> JanelasDiretasQuantizadas:
    """Cria adaptador compativel com o treinador sem alterar as janelas.

    Os campos brutos sao compartilhados, sem copia ou escrita. A inversao
    min-max herdada continua produzindo previsoes continuas. Aplicar outro
    N a um adaptador substitui sua configuracao, sem quantizacao acumulada.
    """

    if not isinstance(janelas, JanelasDiretas):
        raise TypeError("janelas deve ser uma instancia de JanelasDiretas.")
    niveis = _validar_niveis(niveis)
    dados = {campo.name: getattr(janelas, campo.name) for campo in fields(JanelasDiretas)}
    return JanelasDiretasQuantizadas(**dados, niveis=niveis)


def normalizar_entradas(
    janelas: JanelasDiretas, escalas: pd.DataFrame, niveis: int | None
) -> np.ndarray:
    """Prepara x para inferencia sem ler, normalizar ou depender de y.

    Repete a formula e o dtype do min-max de JanelasDiretas, usando somente
    as escalas recebidas. IDs sem escala, escalas duplicadas/nao finitas e
    amplitudes nao positivas sao rejeitados antes da transformacao.
    """

    niveis = _validar_niveis(niveis)
    obrigatorias = {"localidade_id", "minimo_treino_wm2", "amplitude_escala_wm2"}
    if not obrigatorias.issubset(escalas.columns):
        raise ValueError("Escalas sem ID, minimo ou amplitude obrigatorios.")
    if escalas["localidade_id"].duplicated().any():
        raise ValueError("Informe uma unica escala por localidade.")
    ids = np.asarray(janelas.localidade_id)
    if ids.dtype.kind not in "iu" or (ids < 0).any():
        raise ValueError("IDs de localidade devem ser inteiros nao negativos.")
    por_id = escalas.set_index("localidade_id")
    if not set(ids).issubset(set(por_id.index)):
        raise ValueError("Ha localidade sem escala ajustada.")
    valores = escalas[["minimo_treino_wm2", "amplitude_escala_wm2"]].to_numpy(dtype=float)
    if not np.isfinite(valores).all() or (valores[:, 1] <= 0).any():
        raise ValueError("Escalas devem ser finitas e ter amplitude positiva.")
    minimo = por_id.loc[ids, "minimo_treino_wm2"].to_numpy(dtype=np.float32)
    amplitude = por_id.loc[ids, "amplitude_escala_wm2"].to_numpy(dtype=np.float32)
    if not np.isfinite(minimo).all() or not np.isfinite(amplitude).all() or (amplitude <= 0).any():
        raise ValueError("Escalas devem ser representaveis em float32 com amplitude positiva.")
    x_bruto = _entrada_finita(janelas.x_bruto)
    x = (x_bruto.astype(np.float32) - minimo[:, None]) / amplitude[:, None]
    return quantizar_entradas(x.astype(np.float32, copy=False), niveis)


def diagnosticar_quantizacao(x_normalizado: np.ndarray, niveis: int | None) -> dict[str, int | float | None]:
    """Conta alteracoes e saturacao por elemento de entrada, sem usar alvos.

    ``abaixo_zero`` e ``acima_um`` contam valores originais fora da faixa.
    ``saturados`` conta os efetivamente limitados: zero quando N e None.
    Fracoes de arrays vazios sao zero; nenhuma entrada e modificada.
    """

    niveis = _validar_niveis(niveis)
    original = _entrada_finita(x_normalizado)
    quantizado = quantizar_entradas(original, niveis)
    total = int(original.size)
    alterados = int(np.count_nonzero(original != quantizado))
    abaixo_zero = int(np.count_nonzero(original < 0.0))
    acima_um = int(np.count_nonzero(original > 1.0))
    saturados = abaixo_zero + acima_um if niveis is not None else 0
    return {
        "niveis": niveis,
        "total": total,
        "alterados": alterados,
        "fracao_alterados": alterados / total if total else 0.0,
        "abaixo_zero": abaixo_zero,
        "acima_um": acima_um,
        "saturados": saturados,
        "fracao_saturados": saturados / total if total else 0.0,
    }


__all__ = [
    "JanelasDiretasQuantizadas",
    "aplicar_quantizacao",
    "diagnosticar_quantizacao",
    "normalizar_entradas",
    "quantizar_entradas",
]
