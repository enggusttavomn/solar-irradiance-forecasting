"""Estimativas locais de tempo, sem acesso a modelos, datasets ou checkpoints.

O chamador fornece apenas metadados validados do mesmo contrato, fase,
modelo e caso. A faixa e heuristica; nao e intervalo de confianca nem
prazo garantido. Auditorias, outros trabalhos e revisao humana ficam fora.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from numbers import Real


def _instante(valor):
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace('Z', '+00:00'))
        except ValueError:
            return None
    if not isinstance(valor, datetime) or valor.tzinfo is None:
        return None
    try:
        return valor.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        return None


def _duracao(valor):
    if isinstance(valor, bool) or not isinstance(valor, Real):
        return None
    valor = float(valor)
    return valor if math.isfinite(valor) and valor > 0 else None


def estimar_restante(registros, total, agora, inicio=None,
                     executando=False, encerrando=False):
    """Estima apenas as sementes restantes deste trabalho homogeneo.

    Todos os registros contam como concluidos, mesmo quando nao registram
    duracao utilizavel. Entre duracoes validas, usa as ultimas oito pela
    conclusao UTC (a ordem recebida desempata ou supre datas ausentes).
    ``inicio`` deve identificar a execucao atual, nao uma tentativa antiga.
    """
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ValueError('total deve ser um inteiro nao negativo')
    registros = list(registros)
    restantes = max(0, total - len(registros))
    amostras = []
    for indice, registro in enumerate(registros):
        duracao = _duracao(registro.get('duracao_s'))
        if duracao is not None:
            instante = _instante(registro.get('concluido_em_utc'))
            chave = instante.timestamp() if instante else float('-inf')
            amostras.append((chave, indice, duracao))
    duracoes = [item[2] for item in sorted(amostras)[-8:]]
    resposta = {
        'status': 'sem_base', 'min_s': None, 'max_s': None,
        'amostras': len(duracoes), 'restantes': restantes,
        'recalibrado': False, 'tipo': 'faixa_heuristica',
    }
    if encerrando or (executando and restantes == 0):
        resposta['status'] = 'finalizando'
        return resposta
    if restantes == 0:
        resposta.update(status='concluido', min_s=0.0, max_s=0.0)
        return resposta
    if not duracoes:
        return resposta

    # A dispersao observada e mantida e ampliada; poucas observacoes exigem
    # uma margem maior. Nao se infere velocidade de outro modelo ou fase.
    fator_min, fator_max = (0.5, 2.0) if len(duracoes) < 3 else (0.65, 1.5)
    por_seed_min = min(duracoes) * fator_min
    por_seed_max = max(duracoes) * fator_max
    atual_min, atual_max = por_seed_min, por_seed_max
    agora_utc, inicio_utc = _instante(agora), _instante(inicio)
    if executando and agora_utc and inicio_utc and inicio_utc <= agora_utc:
        ancoras = [inicio_utc]
        for registro in registros:
            fim = _instante(registro.get('concluido_em_utc'))
            if fim and inicio_utc <= fim <= agora_utc:
                ancoras.append(fim)
        decorrido = (agora_utc - max(ancoras)).total_seconds()
        if decorrido >= por_seed_max:
            # A seed excedeu a referencia observada. Manter uma nova janela
            # positiva sinaliza a incerteza, sem anunciar prazo ja vencido.
            resposta['recalibrado'] = True
            atual_min = max(por_seed_min * 0.25, decorrido * 0.1)
            atual_max = max(por_seed_max, decorrido * 0.5, atual_min)
        else:
            atual_min = max(por_seed_min * 0.15, por_seed_min - decorrido)
            atual_max = max(por_seed_max * 0.3, por_seed_max - decorrido)

    resposta.update(
        status='estimado',
        min_s=atual_min + (restantes - 1) * por_seed_min,
        max_s=atual_max + (restantes - 1) * por_seed_max,
    )
    return resposta