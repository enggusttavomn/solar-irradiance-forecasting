"""Estado compacto para reproduzir ARIMAResults.apply(refit=False).

O benchmark reinicializa o filtro em cada janela com copy_initialization=False.
Logo os grandes estados filtrados/suavizados do historico de ajuste nao entram
na previsao. Guardamos a mesma especificacao usada por model.clone, parametros,
covariancia pequena e evidencias do fit. Ao aplicar, reproduzimos o caminho
clone + _apply da versao instalada, sem estimar parametros novamente.

Referencia oficial: https://www.statsmodels.org/stable/generated/
statsmodels.tsa.arima.model.ARIMAResults.apply.html
Implementacao conferida: tsa/statespace/mlemodel.py (apply/_apply),
tsa/statespace/sarimax.py (clone), tsa/arima/model.py (ARIMA).
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import importlib.metadata

import numpy as np
from statsmodels.tsa.arima.model import ARIMA


def hash_array(valores):
    arr = np.ascontiguousarray(valores)
    cabecalho = f"{arr.dtype.str}|{arr.shape}|".encode()
    return hashlib.sha256(cabecalho + arr.tobytes()).hexdigest()


@dataclass(frozen=True)
class ARIMACompacto:
    especificacao: dict
    params: np.ndarray
    suavizar: bool
    cov_type: str
    cov_params_default: np.ndarray | None
    cov_descricao: str
    fixed_params: dict | None
    versao_statsmodels: str
    evidencia_fit: dict
    politica_inicializacao: str = "clone_copy_initialization_False"

    def apply(self, endog, exog=None, refit=False, fit_kwargs=None,
              copy_initialization=False, **kwargs):
        """Reconstrucao exata do caminho usado no benchmark; nao faz fit."""
        if refit or copy_initialization or exog is not None or kwargs:
            raise ValueError("Checkpoint compacto aceita somente apply sem refit/exog/copia de estado.")
        if importlib.metadata.version("statsmodels") != self.versao_statsmodels:
            raise ValueError("Versao statsmodels difere do checkpoint compacto.")
        valores = np.asarray(endog, dtype=float)
        if valores.ndim != 1 or not len(valores) or not np.isfinite(valores).all():
            raise ValueError("Contexto ARIMA deve ser vetor finito nao vazio.")
        config = {} if fit_kwargs is None else deepcopy(fit_kwargs)
        if "cov_type" in config or "cov_kwds" in config:
            raise ValueError("Covariancia nao pode ser alterada sem refit.")
        if self.cov_type == "none":
            config["cov_type"] = "none"
        else:
            config["cov_type"] = "custom"
            config["cov_kwds"] = {
                "custom_cov_type": self.cov_type,
                "custom_cov_params": self.cov_params_default,
                "custom_description": (
                    "Parameters and standard errors were estimated using a different dataset and were then applied to this dataset. "
                    + self.cov_descricao),
            }
        mod = ARIMA(valores, **deepcopy(self.especificacao))
        func = mod.smooth if self.suavizar else mod.filter
        if self.fixed_params is not None:
            with mod.fix_params(self.fixed_params):
                config.setdefault("includes_fixed", True)
                return func(self.params, **config)
        return func(self.params, **config)


def compactar_resultado(ajustado) -> ARIMACompacto:
    """Copia apenas o necessario para aplicar parametros em outra janela.

    Nao modifica o objeto original, nem chama remove_data, fit, filter ou smooth.
    A serie endogena completa continua preservada pelo checkpoint externo,
    acompanhada deste hash da representacao usada internamente no ajuste.
    """
    if not isinstance(ajustado.model, ARIMA) or ajustado.model.k_exog != 0:
        raise ValueError("Compactacao implementada somente para ARIMA sem exogenas.")
    parametros = np.asarray(ajustado.params, dtype=float).copy()
    if not np.isfinite(parametros).all():
        raise ValueError("Parametros ARIMA nao finitos.")
    especificacao = deepcopy(ajustado.model._get_init_kwds())
    endog = np.asarray(ajustado.model.endog)
    evidencia = {
        "nobs": int(ajustado.nobs), "loglik": float(ajustado.llf),
        "param_names": list(ajustado.param_names),
        "mle_retvals": deepcopy(getattr(ajustado, "mle_retvals", {})),
        "serie_endogena_shape": tuple(endog.shape), "serie_endogena_dtype": endog.dtype.str,
        "serie_endogena_sha256": hash_array(endog),
        "inicializacao_do_fit": deepcopy(ajustado.model.ssm.initialization.initialization_type),
        "inicializacao_de_apply": "novo_modelo_com_especificacao_original_sem_copiar_estado_do_fit",
    }
    cov_type = str(ajustado.cov_type)
    cov = None if cov_type == "none" else np.asarray(ajustado.cov_params_default).copy()
    fixos = deepcopy(ajustado._fixed_params) if ajustado._has_fixed_params else None
    return ARIMACompacto(especificacao, parametros, ajustado.smoother_results is not None,
                        cov_type, cov, str(ajustado.cov_kwds.get("description", "Unknown.")),
                        fixos, importlib.metadata.version("statsmodels"), evidencia)
