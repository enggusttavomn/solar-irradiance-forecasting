"""Treino TimesNet por macro-MAE fisico para as quatro tarefas temporais.

Este modulo nao recebe teste durante a selecao. A inferencia usa somente o
contexto e o identificador da localidade. Horaria/diaria usam os limites
operacionais diarios; mensal preserva os limites mensais. A mascara noturna
afeta a previsao horaria avaliada, sem eliminar observacoes da metrica.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from codigo_fonte import experimento_multirresolucao as base
from codigo_fonte.experimento_horario_timesnet import JanelasHorarias, timestamps_alvo
from codigo_fonte.treinamento_timesnet_otimizacao import _validar_escalas

ConfiguracaoMultirresolucao = base.ConfiguracaoMultirresolucao
EspecificacaoTarefa = base.EspecificacaoTarefa
JanelasDiretas = base.JanelasDiretas
Janelas = JanelasDiretas | JanelasHorarias


def _dispositivo(nome: str | torch.device) -> torch.device:
    dispositivo = torch.device(nome)
    if dispositivo.type not in {"cpu", "cuda"}:
        raise ValueError("dispositivo deve ser cpu ou cuda.")
    if dispositivo.type == "cuda":
        if not torch.cuda.is_available():
            raise ValueError("CUDA solicitada, mas nao esta disponivel.")
        if dispositivo.index is not None and dispositivo.index >= torch.cuda.device_count():
            raise ValueError("Indice CUDA nao esta disponivel.")
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    return dispositivo


def _normalizar_contexto(janelas: Janelas, escalas: pd.DataFrame) -> np.ndarray:
    """Normaliza so a entrada: esta funcao nunca consulta os alvos."""
    _validar_escalas(janelas, escalas)
    x = np.asarray(janelas.x_bruto, dtype=np.float32)
    if x.shape != (len(janelas.localidade_id), janelas.seq_len) or not len(x):
        raise ValueError("Contexto possui forma invalida ou esta vazio.")
    tabela = escalas.set_index("localidade_id").loc[janelas.localidade_id]
    minimo = tabela.minimo_treino_wm2.to_numpy(dtype=np.float32)[:, None]
    amplitude = tabela.amplitude_escala_wm2.to_numpy(dtype=np.float32)[:, None]
    normalizado = (x - minimo) / amplitude
    if not np.isfinite(normalizado).all():
        raise ValueError("Contexto normalizado contem valores nao finitos.")
    return normalizado


def prever(
    modelo: nn.Module,
    janelas: Janelas,
    escalas: pd.DataFrame,
    batch_size: int = 128,
    dispositivo: str = "cpu",
) -> np.ndarray:
    """Retorna GHI bruto em numpy/CPU, sem ler, normalizar ou inverter alvos."""
    if isinstance(batch_size, bool) or not isinstance(batch_size, (int, np.integer)) or batch_size < 1:
        raise ValueError("batch_size deve ser um inteiro positivo.")
    local = _dispositivo(dispositivo)
    contexto = _normalizar_contexto(janelas, escalas)
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


def macro_mae_fisico(
    janelas: Janelas,
    previsao_bruta: np.ndarray,
    elevacao: np.ndarray | None = None,
) -> float:
    """MAE em W/m2, media entre localidades, apos piso zero e mascara solar."""
    previsto = np.asarray(previsao_bruta, dtype=float)
    real = np.asarray(janelas.y_bruto, dtype=float)
    if previsto.shape != real.shape or real.size == 0:
        raise ValueError("Previsao possui forma incompativel com os alvos.")
    if not np.isfinite(previsto).all() or not np.isfinite(real).all():
        raise ValueError("Previsao e alvo devem conter valores finitos.")
    previsto = np.maximum(previsto, 0.0)
    if elevacao is not None:
        elevacao = np.asarray(elevacao, dtype=float)
        if elevacao.shape != real.shape or not np.isfinite(elevacao).all():
            raise ValueError("Elevacao solar deve acompanhar a forma finita dos alvos.")
        previsto[elevacao <= 0.0] = 0.0
    ids = np.asarray(janelas.localidade_id)
    if ids.shape != (len(real),):
        raise ValueError("IDs de localidade nao acompanham os alvos.")
    resultado = float(np.mean([
        np.mean(np.abs(previsto[ids == i] - real[ids == i])) for i in np.unique(ids)
    ]))
    if not math.isfinite(resultado):
        raise ValueError("Macro-MAE fisico nao finito.")
    return resultado


def _validar_janelas(janelas: Janelas, tarefa: EspecificacaoTarefa) -> None:
    if (janelas.seq_len, janelas.pred_len) != (tarefa.seq_len, tarefa.pred_len):
        raise ValueError("Janelas nao correspondem ao contexto/horizonte da tarefa.")
    if (janelas.x_bruto.shape != (len(janelas.localidade_id), tarefa.seq_len)
            or janelas.y_bruto.shape != (len(janelas.localidade_id), tarefa.pred_len)):
        raise ValueError("Janelas possuem forma invalida.")
    if not len(janelas.x_bruto) or not np.isfinite(janelas.x_bruto).all() or not np.isfinite(janelas.y_bruto).all():
        raise ValueError("Janelas vazias ou com valores nao finitos.")


def _limites_alvos(janelas: Janelas, localidade_id: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    mascara = np.asarray(janelas.localidade_id) == localidade_id
    if isinstance(janelas, JanelasHorarias):
        datas, _ = timestamps_alvo(janelas)
        datas = datas[np.repeat(mascara, janelas.pred_len)]
    else:
        datas = pd.DatetimeIndex(np.asarray(janelas.datas_alvo)[mascara].reshape(-1))
    if datas.hasnans:
        raise ValueError("Datas dos alvos contem valores ausentes.")
    return datas.min(), datas.max()


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
) -> tuple[nn.Module, int, pd.DataFrame]:
    """Seleciona epoca por validacao fisica ou faz refit com rede nova.

    O refit exige epocas_fixas e nao aceita validacao. Logs incluem tempo
    decorrido da epoca; o modelo retornado esta em CPU, em modo de avaliacao.
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
    _validar_janelas(ajuste, tarefa)
    _validar_escalas(ajuste, escalas)
    if validacao is not None:
        _validar_janelas(validacao, tarefa)
        _validar_escalas(validacao, escalas)
        if not set(validacao.localidade_id).issubset(set(ajuste.localidade_id)):
            raise ValueError("Validacao contem localidade sem exemplos de ajuste.")
        nomes_ajuste = dict(zip(ajuste.localidade_id, ajuste.localidade))
        if any(nomes_ajuste[i] != n for i, n in zip(validacao.localidade_id, validacao.localidade)):
            raise ValueError("Identidade de localidade diverge entre ajuste e validacao.")
        # Cada localidade tem seu corte civil; cidades em fusos distintos
        # podem se sobrepor em UTC sem existir vazamento da propria serie.
        for localidade_id in np.unique(validacao.localidade_id):
            if _limites_alvos(ajuste, localidade_id)[1] >= _limites_alvos(validacao, localidade_id)[0]:
                raise ValueError("Alvos de ajuste devem anteceder os alvos de validacao por localidade.")
        # Valida forma/finitude da mascara antes de criar e treinar a rede.
        macro_mae_fisico(validacao, validacao.y_bruto, elevacao_validacao)
    local = _dispositivo(dispositivo)
    x_treino = _normalizar_contexto(ajuste, escalas)
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
            bruto = prever(modelo, validacao, escalas, batch_size, str(local))
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
