"""TimesNet horaria/diaria com quantizacao uniforme somente nas entradas.

Mantem a matematica, inicializacao e selecao de epocas do treinador historico.
A unica transformacao acrescentada e min-max -> quantizacao de X, tambem na
validacao e inferencia. Alvos, pesos e previsoes permanecem continuos. O modo
``niveis=None`` preserva o controle sem clipping do treinador original.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from codigo_fonte import treinamento_timesnet_resolucoes as original
from codigo_fonte.quantizacao_timesnet import quantizar_entradas

base = original.base
ConfiguracaoMultirresolucao = original.ConfiguracaoMultirresolucao
EspecificacaoTarefa = original.EspecificacaoTarefa
Janelas = original.Janelas
macro_mae_fisico = original.macro_mae_fisico


def _normalizar_contexto(
    janelas: Janelas, escalas: pd.DataFrame, niveis: int | None = None,
) -> np.ndarray:
    """Normaliza e quantiza apenas X, sem consultar alvos ou ajustar escalas."""
    return quantizar_entradas(original._normalizar_contexto(janelas, escalas), niveis)


def prever(
    modelo: nn.Module,
    janelas: Janelas,
    escalas: pd.DataFrame,
    batch_size: int = 128,
    dispositivo: str = "cpu",
    niveis: int | None = None,
) -> np.ndarray:
    """Retorna GHI continuo em numpy/CPU usando a mesma quantizacao do treino."""
    if isinstance(batch_size, bool) or not isinstance(batch_size, (int, np.integer)) or batch_size < 1:
        raise ValueError("batch_size deve ser um inteiro positivo.")
    local = original._dispositivo(dispositivo)
    contexto = _normalizar_contexto(janelas, escalas, niveis)
    modelo.to(local).eval()
    partes = []
    with torch.inference_mode():
        for inicio in range(0, len(contexto), batch_size):
            fim = inicio + batch_size
            x = torch.as_tensor(contexto[inicio:fim], dtype=torch.float32, device=local)
            ids = torch.as_tensor(janelas.localidade_id[inicio:fim], dtype=torch.long, device=local)
            saida = modelo(x, ids)
            if saida.shape != (len(x), janelas.pred_len):
                raise ValueError("Modelo produziu forma de saida incompativel.")
            partes.append(saida.detach().cpu().numpy())
    normalizado = np.concatenate(partes).astype(float)
    tabela = escalas.set_index("localidade_id").loc[janelas.localidade_id]
    bruto = normalizado * tabela.amplitude_escala_wm2.to_numpy(dtype=float)[:, None]
    bruto += tabela.minimo_treino_wm2.to_numpy(dtype=float)[:, None]
    if not np.isfinite(bruto).all():
        raise ValueError("Previsao fisica contem valores nao finitos.")
    return bruto


def treinar(
    *,
    tarefa: EspecificacaoTarefa,
    config: ConfiguracaoMultirresolucao,
    semente: int,
    ajuste: Janelas,
    escalas: pd.DataFrame,
    validacao: Janelas | None = None,
    elevacao_validacao: np.ndarray | None = None,
    perda: str = "mae",
    epocas_fixas: int | None = None,
    dispositivo: str = "cpu",
    niveis: int | None = None,
) -> tuple[nn.Module, int, pd.DataFrame]:
    """Seleciona epoca por macro-MAE fisico ou faz refit com rede nova.

    As operacoes seguem o treinador original, incluindo a ordem dos sorteios.
    A quantizacao aplica-se a X antes de TensorDataset e a cada inferencia de
    validacao. O refit recebe epocas congeladas e nao aceita validacao.
    """
    perdas = {"mse": nn.MSELoss, "mae": nn.L1Loss, "huber": lambda: nn.HuberLoss(delta=0.1)}
    if perda not in perdas:
        raise ValueError("perda deve ser mse, mae ou huber.")
    if isinstance(semente, (bool, np.bool_)) or not isinstance(semente, (int, np.integer)) or not 0 <= semente < 2**32:
        raise ValueError("semente deve ser inteiro em [0, 2**32).")
    if (validacao is None) == (epocas_fixas is None):
        raise ValueError("Informe validacao ou epocas_fixas, exclusivamente.")
    if epocas_fixas is not None and (isinstance(epocas_fixas, (bool, np.bool_))
            or not isinstance(epocas_fixas, (int, np.integer)) or epocas_fixas < 1):
        raise ValueError("epocas_fixas deve ser um inteiro positivo.")
    if validacao is None and elevacao_validacao is not None:
        raise ValueError("elevacao_validacao exige validacao.")
    if tarefa.resolucao != "horaria" and elevacao_validacao is not None:
        raise ValueError("Mascara solar e exclusiva da tarefa horaria.")
    if tarefa.resolucao == "horaria" and validacao is not None and elevacao_validacao is None:
        raise ValueError("Validacao horaria exige elevacao_validacao.")
    original._validar_janelas(ajuste, tarefa)
    original._validar_escalas(ajuste, escalas)
    if validacao is not None:
        original._validar_janelas(validacao, tarefa)
        original._validar_escalas(validacao, escalas)
        if not set(validacao.localidade_id).issubset(set(ajuste.localidade_id)):
            raise ValueError("Validacao contem localidade sem exemplos de ajuste.")
        nomes_ajuste = dict(zip(ajuste.localidade_id, ajuste.localidade))
        if any(nomes_ajuste[i] != n for i, n in zip(validacao.localidade_id, validacao.localidade)):
            raise ValueError("Identidade de localidade diverge entre ajuste e validacao.")
        # Os cortes civis sao verificados individualmente para cada localidade.
        for localidade_id in np.unique(validacao.localidade_id):
            if original._limites_alvos(ajuste, localidade_id)[1] >= original._limites_alvos(validacao, localidade_id)[0]:
                raise ValueError("Alvos de ajuste devem anteceder os alvos de validacao por localidade.")
        macro_mae_fisico(validacao, validacao.y_bruto, elevacao_validacao)
    local = original._dispositivo(dispositivo)
    x_treino = _normalizar_contexto(ajuste, escalas, niveis)
    tabela = escalas.set_index("localidade_id").loc[ajuste.localidade_id]
    y_treino = (ajuste.y_bruto.astype(np.float32) - tabela.minimo_treino_wm2.to_numpy(dtype=np.float32)[:, None])
    y_treino /= tabela.amplitude_escala_wm2.to_numpy(dtype=np.float32)[:, None]
    if not np.isfinite(y_treino).all():
        raise ValueError("Normalizacao produziu alvos nao finitos.")
    base.fixar_semente(int(semente), config.threads_torch)
    if local.type == "cuda":
        torch.cuda.manual_seed_all(int(semente))
    modelo = base.criar_modelo_neural(
        "TimesNet", tarefa=tarefa, configuracao=config,
        num_localidades=int(np.max(ajuste.localidade_id)) + 1, semente=int(semente),
    ).to(local)
    mensal = tarefa.resolucao == "mensal"
    batch_size = config.batch_size_mensal if mensal else config.batch_size_diario
    limite = config.max_epocas_mensal if mensal else config.max_epocas_diario
    if config.modo_execucao == "smoke":
        limite = config.epocas_smoke
    if epocas_fixas is not None:
        limite = int(epocas_fixas)
    paciencia = config.paciencia_mensal if mensal else config.paciencia_diario
    carregador = DataLoader(
        TensorDataset(torch.as_tensor(x_treino), torch.as_tensor(y_treino),
                      torch.as_tensor(ajuste.localidade_id, dtype=torch.long)),
        batch_size=min(batch_size, len(x_treino)), shuffle=True, num_workers=0,
        generator=torch.Generator().manual_seed(int(semente)),
    )
    otimizador = torch.optim.Adam(modelo.parameters(), lr=config.taxa_aprendizado, weight_decay=config.peso_decay)
    criterio = perdas[perda]()
    melhor_mae, melhor_epoca, melhor_estado, sem_melhora = math.inf, 0, None, 0
    historico = []
    for epoca in range(1, limite + 1):
        inicio = time.perf_counter()
        modelo.train()
        soma, quantidade = 0.0, 0
        for x, y, ids in carregador:
            x, y, ids = x.to(local), y.to(local), ids.to(local)
            otimizador.zero_grad(set_to_none=True)
            saida = modelo(x, ids)
            if saida.shape != y.shape:
                raise ValueError("Modelo produziu forma de saida incompativel.")
            valor = criterio(saida, y)
            if not bool(torch.isfinite(valor)):
                raise ValueError(f"Perda de treino nao finita na epoca {epoca}.")
            valor.backward()
            if any(p.grad is not None and not bool(torch.isfinite(p.grad).all()) for p in modelo.parameters()):
                raise ValueError(f"Gradiente nao finito na epoca {epoca}.")
            otimizador.step()
            if any(not bool(torch.isfinite(p).all()) for p in modelo.parameters()):
                raise ValueError(f"Parametro nao finito na epoca {epoca}.")
            soma += float(valor.item()) * y.numel()
            quantidade += y.numel()
        mae = math.nan
        if validacao is not None:
            bruto = prever(modelo, validacao, escalas, batch_size, str(local), niveis=niveis)
            mae = macro_mae_fisico(validacao, bruto, elevacao_validacao)
        if local.type == "cuda":
            torch.cuda.synchronize(local)
        historico.append({"epoca": epoca, "perda_treino": soma / quantidade,
                          "mae_validacao_wm2": mae, "segundos": time.perf_counter() - inicio})
        print(f"{tarefa.slug} seed={semente} epoca={epoca}/{limite} "
              f"perda={soma / quantidade:.7f} mae_validacao_wm2={mae:.6f} "
              f"segundos={historico[-1]['segundos']:.2f}", flush=True)
        if validacao is None:
            melhor_epoca = epoca
        elif mae < melhor_mae - 1e-12:
            melhor_mae, melhor_epoca = mae, epoca
            melhor_estado = {k: v.detach().cpu().clone() for k, v in modelo.state_dict().items()}
            sem_melhora = 0
        else:
            sem_melhora += 1
            if sem_melhora >= paciencia:
                break
    if melhor_estado is not None:
        modelo.load_state_dict(melhor_estado)
    modelo.cpu().eval()
    return modelo, melhor_epoca, pd.DataFrame(historico)


__all__ = ["macro_mae_fisico", "prever", "treinar"]
