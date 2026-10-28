"""Treino de candidatos TimesNet selecionados por macro-MAE fisico.

O modulo preserva o protocolo canonico e nao recebe dados de teste. As perdas
de treino MSE, MAE e Huber atuam na escala min-max; Huber usa delta=0.1 nessa
escala. A selecao usa MAE em W/m2 apos inversao e piso zero, com peso igual
para cada localidade. O refit cria outra rede e executa as epocas escolhidas.

A rede pode aprender o GHI ou o desvio em relacao a climatologia. No segundo
caso quem chama informa `deslocamento_validacao` com a climatologia dos alvos,
para que o MAE de selecao continue medindo GHI.
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from codigo_fonte.experimento_multirresolucao import (
    ConfiguracaoMultirresolucao,
    EspecificacaoTarefa,
    JanelasDiretas,
    criar_modelo_neural,
    fixar_semente,
    prever_rede,
)


def _validar_escalas(janelas: JanelasDiretas, escalas: pd.DataFrame) -> None:
    obrigatorias = {"localidade_id", "minimo_treino_wm2", "amplitude_escala_wm2"}
    if not obrigatorias.issubset(escalas.columns):
        raise ValueError("Escalas sem ID, minimo ou amplitude obrigatorios.")
    if escalas["localidade_id"].duplicated().any():
        raise ValueError("Informe uma unica escala por localidade e fase.")
    ids = np.asarray(janelas.localidade_id)
    if ids.dtype.kind not in "iu" or (ids < 0).any():
        raise ValueError("IDs de localidade devem ser inteiros nao negativos.")
    if not set(ids).issubset(set(escalas["localidade_id"])):
        raise ValueError("Ha localidade sem escala ajustada.")
    valores = escalas[list(obrigatorias - {"localidade_id"})].to_numpy(dtype=float)
    if not np.isfinite(valores).all():
        raise ValueError("Escalas devem conter valores finitos.")
    if (escalas["amplitude_escala_wm2"].to_numpy(dtype=float) <= 0).any():
        raise ValueError("Amplitude da escala deve ser positiva.")
    identidades = pd.DataFrame({"id": ids, "nome": janelas.localidade})
    if (
        identidades.groupby("id")["nome"].nunique().gt(1).any()
        or identidades.groupby("nome")["id"].nunique().gt(1).any()
    ):
        raise ValueError("IDs e nomes de localidade devem ter correspondencia unica.")


def macro_mae_fisico(
    janelas: JanelasDiretas,
    previsao_normalizada: np.ndarray,
    escalas: pd.DataFrame,
    deslocamento: np.ndarray | None = None,
) -> float:
    """Inverte min-max, aplica piso zero e calcula MAE com peso igual por local.

    Quando a rede preve anomalias, `deslocamento` traz a parcela conhecida (a
    climatologia dos alvos) e as janelas trazem o desvio. Somar antes do piso
    mantem o piso zero atuando sobre o GHI, e nao sobre o desvio, que e
    negativo em cerca de metade dos meses.
    """

    _validar_escalas(janelas, escalas)
    previsto = np.asarray(previsao_normalizada, dtype=float)
    real = np.asarray(janelas.y_bruto, dtype=float)
    if previsto.shape != real.shape or real.size == 0:
        raise ValueError("Previsao normalizada possui forma incompatível.")
    if not np.isfinite(previsto).all() or not np.isfinite(real).all():
        raise ValueError("Previsao e alvo devem conter somente valores finitos.")
    if deslocamento is None:
        deslocamento = np.zeros_like(real)
    else:
        deslocamento = np.asarray(deslocamento, dtype=float)
        if deslocamento.shape != real.shape or not np.isfinite(deslocamento).all():
            raise ValueError("Deslocamento deve acompanhar a forma finita dos alvos.")
        real = real + deslocamento
    fisico = np.maximum(janelas.inverter(previsto, escalas) + deslocamento, 0.0)
    if not np.isfinite(fisico).all():
        raise ValueError("Inversao da escala produziu previsao nao finita.")
    ids = np.asarray(janelas.localidade_id)
    maes = [float(np.mean(np.abs(fisico[ids == i] - real[ids == i]))) for i in np.unique(ids)]
    resultado = float(np.mean(maes))
    if not math.isfinite(resultado):
        raise ValueError("Macro-MAE fisico nao finito.")
    return resultado


def _validar_janelas(janelas: JanelasDiretas, tarefa: EspecificacaoTarefa) -> None:
    if (janelas.seq_len, janelas.pred_len) != (tarefa.seq_len, tarefa.pred_len):
        raise ValueError("Janelas nao correspondem ao contexto/horizonte da tarefa.")
    if not np.isfinite(janelas.x_bruto).all() or not np.isfinite(janelas.y_bruto).all():
        raise ValueError("Janelas contem valores nao finitos.")


def treinar_candidato(
    *,
    tarefa: EspecificacaoTarefa,
    configuracao: ConfiguracaoMultirresolucao,
    semente: int,
    ajuste: JanelasDiretas,
    escalas: pd.DataFrame,
    validacao: JanelasDiretas | None = None,
    perda: str = "mse",
    epocas_fixas: int | None = None,
    deslocamento_validacao: np.ndarray | None = None,
) -> tuple[nn.Module, int, pd.DataFrame]:
    """Cria uma TimesNet nova; seleciona por MAE fisico ou realiza refit fixo.

    Com validacao, retorna o estado da melhor epoca e sua contagem (base 1).
    Sem validacao, exige epocas_fixas e retorna o estado final. O historico
    contem epoca, perda_treino e mae_validacao_wm2 (NaN durante o refit).
    """

    perdas = {"mse": nn.MSELoss, "mae": nn.L1Loss, "huber": lambda: nn.HuberLoss(delta=0.1)}
    if perda not in perdas:
        raise ValueError("perda deve ser mse, mae ou huber.")
    if isinstance(semente, (bool, np.bool_)) or not isinstance(semente, (int, np.integer)):
        raise ValueError("semente deve ser um inteiro em [0, 2**32).")
    if not 0 <= int(semente) < 2**32:
        raise ValueError("semente deve pertencer a [0, 2**32).")
    if validacao is not None and epocas_fixas is not None:
        raise ValueError("epocas_fixas nao pode acompanhar validacao.")
    if validacao is None and epocas_fixas is None:
        raise ValueError("Informe validacao ou epocas_fixas para o refit.")
    if validacao is None and deslocamento_validacao is not None:
        raise ValueError("deslocamento_validacao exige janelas de validacao.")
    if epocas_fixas is not None and (
        isinstance(epocas_fixas, (bool, np.bool_))
        or not isinstance(epocas_fixas, (int, np.integer))
        or epocas_fixas < 1
    ):
        raise ValueError("epocas_fixas deve ser um inteiro positivo.")
    _validar_janelas(ajuste, tarefa)
    _validar_escalas(ajuste, escalas)
    if validacao is not None:
        _validar_janelas(validacao, tarefa)
        _validar_escalas(validacao, escalas)
        if not set(validacao.localidade_id).issubset(set(ajuste.localidade_id)):
            raise ValueError("Validacao contem localidade sem exemplos de ajuste.")
        if ajuste.datas_alvo.max() >= validacao.datas_alvo.min():
            raise ValueError("Alvos de ajuste devem anteceder os alvos de validacao.")

    x_treino, y_treino = ajuste.normalizar(escalas)
    if not np.isfinite(x_treino).all() or not np.isfinite(y_treino).all():
        raise ValueError("Normalizacao produziu dados de treino nao finitos.")
    x_val = None
    if validacao is not None:
        x_val, _ = validacao.normalizar(escalas)
        if not np.isfinite(x_val).all():
            raise ValueError("Normalizacao produziu dados de validacao nao finitos.")
    fixar_semente(int(semente), configuracao.threads_torch)
    modelo = criar_modelo_neural(
        "TimesNet",
        tarefa=tarefa,
        configuracao=configuracao,
        num_localidades=int(np.max(ajuste.localidade_id)) + 1,
        semente=int(semente),
    )
    batch_size = configuracao.batch_size(tarefa)
    carregador = DataLoader(
        TensorDataset(
            torch.as_tensor(x_treino, dtype=torch.float32),
            torch.as_tensor(y_treino, dtype=torch.float32),
            torch.as_tensor(ajuste.localidade_id, dtype=torch.long),
        ),
        batch_size=min(batch_size, len(x_treino)),
        shuffle=True,
        num_workers=0,
        generator=torch.Generator().manual_seed(int(semente)),
    )
    otimizador = torch.optim.Adam(
        modelo.parameters(),
        lr=configuracao.taxa_aprendizado,
        weight_decay=configuracao.peso_decay,
    )
    criterio = perdas[perda]()
    limite = int(epocas_fixas) if epocas_fixas is not None else configuracao.max_epocas(tarefa)
    paciencia = configuracao.paciencia(tarefa)
    melhor_mae = math.inf
    melhor_epoca = 0
    melhor_estado = None
    sem_melhora = 0
    historico: list[dict[str, float | int]] = []
    for epoca in range(1, limite + 1):
        modelo.train()
        soma_perdas = 0.0
        quantidade = 0
        for x, y, ids in carregador:
            otimizador.zero_grad(set_to_none=True)
            saida = modelo(x, ids)
            if saida.shape != y.shape:
                raise ValueError("Modelo produziu forma de saida incompatível.")
            valor_perda = criterio(saida, y)
            if not bool(torch.isfinite(valor_perda)):
                raise ValueError(f"Perda de treino nao finita na epoca {epoca}.")
            valor_perda.backward()
            if any(p.grad is not None and not bool(torch.isfinite(p.grad).all()) for p in modelo.parameters()):
                raise ValueError(f"Gradiente nao finito na epoca {epoca}.")
            otimizador.step()
            if any(not bool(torch.isfinite(p).all()) for p in modelo.parameters()):
                raise ValueError(f"Parametro nao finito na epoca {epoca}.")
            soma_perdas += float(valor_perda.item()) * y.numel()
            quantidade += y.numel()
        mae = math.nan
        if validacao is not None:
            previsto = prever_rede(modelo, x_val, validacao.localidade_id, batch_size=batch_size)
            mae = macro_mae_fisico(validacao, previsto, escalas, deslocamento_validacao)
        historico.append(
            {"epoca": epoca, "perda_treino": soma_perdas / quantidade, "mae_validacao_wm2": mae}
        )
        if validacao is None:
            melhor_epoca = epoca
        elif mae < melhor_mae - 1e-12:
            melhor_mae = mae
            melhor_epoca = epoca
            melhor_estado = copy.deepcopy(modelo.state_dict())
            sem_melhora = 0
        else:
            sem_melhora += 1
            if sem_melhora >= paciencia:
                break
    if melhor_estado is not None:
        modelo.load_state_dict(melhor_estado)
    modelo.eval()
    return modelo, melhor_epoca, pd.DataFrame(historico)


__all__ = ["macro_mae_fisico", "treinar_candidato"]
