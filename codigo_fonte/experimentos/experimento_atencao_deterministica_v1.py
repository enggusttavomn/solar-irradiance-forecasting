"""Execucao estrita e versionada dos quatro pares de atencao em CUDA.

O motor cientifico permanece congelado. Este adaptador conserva modelos,
dados, sementes, otimizador, backend SDPA automatico e criterio de selecao.
Apenas torna os algoritmos deterministas obrigatorios apos cada resemeadura.
O controle e treinado novamente sob essa politica; a comparacao com o treino
legado fica preservada, sem transformar divergencia em reproducao aprovada.
Um piloto curto aprovado e obrigatorio, mas nao prova repetibilidade de todo
treino, de outros equipamentos ou de outras versoes das bibliotecas.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import sys

import numpy as np
import torch

from codigo_fonte.experimentos import experimento_quantizacao_concorrentes as base

RAIZ = base.RAIZ
POLITICA = "atencao_cuda_deterministica_v1"
MODELOS = ("Transformer", "Informer")
TAREFAS = ("hourly_72_extension", "daily_30")
EVIDENCIA = RAIZ / "resultados/relatorios/quantizacao_todos_modelos_20260929/investigacao_atencao/piloto_treinamento_estrito.json"
CONSTRUIR_ORIGINAL = base.construir_contrato
CONFERIR_ORIGINAL = base.conferir_controle
REDE_ORIGINAL = base.nova_rede
SEMENTE_ORIGINAL = base.m.fixar_semente
_ativo = False
_evidencia_ativa: Path | None = None


class _ComparacaoLegadaDivergente(Exception):
    """Interrompe somente o caminho que pediria aceite de controle GPU."""


def ler_evidencia(caminho=None):
    caminho = Path(caminho if caminho is not None else EVIDENCIA).resolve()
    ev = base.ler_json(caminho)
    if (ev.get("schema") != 1 or ev.get("politica") != POLITICA or
            ev.get("aprovado") is not True):
        raise ValueError("Piloto estrito nao aprovado para esta politica.")
    pares = ev.get("pares", [])
    esperados = {(t, m) for t in TAREFAS for m in MODELOS}
    if (not isinstance(pares, list) or len(pares) != 4 or
            {(p.get("tarefa"), p.get("modelo")) for p in pares} != esperados):
        raise ValueError("Piloto deve cobrir exatamente os quatro pares de atencao.")
    for p in pares:
        flags = ("aprovado", "curvas_bitexatas", "pesos_finais_bitexatos",
                 "pesos_retornados_bitexatos", "previsoes_bitexatas")
        if any(p.get(k) is not True for k in flags):
            raise ValueError("Piloto sem curvas, pesos e previsoes bitexatos.")
        for chave, minimo in (("repeticoes", 2), ("optimizer_steps_por_repeticao", 8)):
            n = p.get(chave)
            if isinstance(n, bool) or not isinstance(n, int) or n < minimo:
                raise ValueError("Piloto insuficiente: repeticoes ou updates ausentes.")
    fontes = ev.get("fontes_sha256", {})
    if not isinstance(fontes, dict) or not fontes:
        raise ValueError("Piloto sem fontes hashadas.")
    normalizadas = {str(Path(p).resolve()): h for p, h in fontes.items()}
    obrigatorias = (Path(base.__file__), Path(base.m.__file__), Path(base.e.redes.__file__))
    if not {str(p.resolve()) for p in obrigatorias}.issubset(normalizadas):
        raise ValueError("Piloto nao vincula as tres fontes cientificas obrigatorias.")
    base.conferir_hashes(fontes)
    if not isinstance(ev.get("limitacao"), str) or not ev["limitacao"].strip():
        raise ValueError("Piloto deve declarar seu alcance limitado.")
    return ev


def validar_escopo(ctx, modelo):
    if (modelo not in MODELOS or ctx.tarefa.slug not in TAREFAS or
            ctx.protocolo.get("regime") not in base.REGIMES):
        raise ValueError("Adaptador restrito aos quatro pares horario/diario de atencao.")
    par = base.parametros(ctx, modelo)
    if (par["dispositivo"] != "cuda" or par["dispositivo_original"] != "cuda" or
            par["novo_controle_por_dispositivo"] is not False):
        raise ValueError("Este adaptador nao autoriza mudanca de dispositivo CPU/CUDA.")
    return par


def ambiente_numerico():
    """Somente leitura; nao forca outro backend ou configura flags adicionais."""
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA obrigatoria para o adaptador de atencao.")
    props = torch.cuda.get_device_properties(torch.cuda.current_device())
    return {
        "torch": torch.__version__, "cuda": torch.version.cuda,
        "cudnn": torch.backends.cudnn.version(),
        "gpu": props.name, "capacidade_cuda": [props.major, props.minor],
        "threads_torch": torch.get_num_threads(),
        "float32_matmul_precision": torch.get_float32_matmul_precision(),
        "cudnn_benchmark": torch.backends.cudnn.benchmark,
        "cudnn_deterministic": torch.backends.cudnn.deterministic,
        "cudnn_allow_tf32": torch.backends.cudnn.allow_tf32,
        "matmul_allow_tf32": torch.backends.cuda.matmul.allow_tf32,
        "sdpa_flash": torch.backends.cuda.flash_sdp_enabled(),
        "sdpa_mem_efficient": torch.backends.cuda.mem_efficient_sdp_enabled(),
        "sdpa_math": torch.backends.cuda.math_sdp_enabled(),
        "sdpa_cudnn": torch.backends.cuda.cudnn_sdp_enabled(),
    }


def _exigir_ativo():
    if (not _ativo or _evidencia_ativa is None or
            not torch.are_deterministic_algorithms_enabled() or
            torch.is_deterministic_algorithms_warn_only_enabled()):
        raise RuntimeError("Use ativar_adaptador(): politica estrita obrigatoria.")


def _politica():
    _exigir_ativo()
    return {
        "id": POLITICA, "algoritmos_deterministicos": True, "warn_only": False,
        "sdpa": "automatico", "cublas_workspace_config": ":4096:8",
        "baseline": "minmax_sem_quantizacao_treinado_sob_politica_estrita",
        "escopo": {"modelos": list(MODELOS), "tarefas": list(TAREFAS)},
        "evidencia_piloto": {"arquivo": str(_evidencia_ativa),
            "sha256": base.m.sha256_arquivo(_evidencia_ativa)},
        "ambiente": ambiente_numerico(), "tolerancia_replay_wm2": 1e-6,
        "limitacao": "Piloto curto com updates; nao prova repetibilidade integral nem entre ambientes.",
    }


def fixar_semente(semente, threads_torch=1):
    SEMENTE_ORIGINAL(semente, threads_torch)
    torch.use_deterministic_algorithms(True, warn_only=False)


def construir_contrato(ctx, modelo):
    _exigir_ativo()
    par = validar_escopo(ctx, modelo)
    # Registrar a configuracao efetiva do treino, antes da primeira rede.
    torch.set_num_threads(par['configuracao']['threads_torch'])
    ev = ler_evidencia(_evidencia_ativa)
    contrato = CONSTRUIR_ORIGINAL(ctx, modelo)
    contrato["codigo"].update(base.hashes([Path(__file__)]))
    contrato["parametros"]["fontes_configuracao"].update(ev["fontes_sha256"])
    contrato["parametros"]["fontes_configuracao"].update(base.hashes([_evidencia_ativa]))
    contrato["execucao_numerica"] = _politica()
    contrato["controle_execucao_numerica"] = {
        "novo_baseline_estrito": True, "importar_controle_legado": False,
        "reproducao_legada_exigida": False,
        "comparacao_legada_preservada": True, "autoriza_mudanca_dispositivo": False,
        "replay_independente_obrigatorio": True,
    }
    contrato.pop("sha256_contrato")
    contrato["sha256_contrato"] = base.hash_obj(contrato)
    return contrato


def validar_contrato_adaptado(contrato):
    """Para replay: vincula politica, evidencia e codigo, sem alterar contrato."""
    _exigir_ativo()
    if base.hash_obj({k: v for k, v in contrato.items() if k != "sha256_contrato"}) != contrato.get("sha256_contrato"):
        raise ValueError("Contrato adaptado com hash interno invalido.")
    if contrato.get("execucao_numerica") != _politica():
        raise ValueError("Politica numerica/ambiente/piloto diverge do contrato.")
    codigo = contrato.get("codigo", {})
    if codigo.get(str(Path(__file__).resolve())) != base.m.sha256_arquivo(__file__):
        raise ValueError("Codigo do adaptador diferente do contrato.")
    if (contrato.get("modelo") not in MODELOS or
            contrato.get("tarefa", {}).get("slug") not in TAREFAS or
            contrato.get("protocolo", {}).get("regime") not in base.REGIMES):
        raise ValueError("Contrato fora do escopo do adaptador.")
    p = contrato.get("parametros", {})
    if (p.get("dispositivo") != "cuda" or p.get("dispositivo_original") != "cuda" or
            p.get("novo_controle_por_dispositivo") is not False):
        raise ValueError("Contrato alteraria o dispositivo original.")
    return contrato


def nova_rede(ctx, modelo, seed, par):
    _exigir_ativo()
    esperado = validar_escopo(ctx, modelo)
    evidencia = ler_evidencia(_evidencia_ativa)
    esperado['fontes_configuracao'].update(evidencia['fontes_sha256'])
    esperado['fontes_configuracao'].update(base.hashes([_evidencia_ativa]))
    # O contrato JSON converte tuplas para listas; o conteudo cientifico deve
    # coincidir, incluindo as fontes de proveniencia adicionadas pelo adaptador.
    if base.hash_obj(par) != base.hash_obj(esperado):
        raise ValueError("Parametros de replay/treino diferentes do protocolo.")
    return REDE_ORIGINAL(ctx, modelo, seed, par)


def _nao_emitir_aceite_gpu(*args, **kwargs):
    raise _ComparacaoLegadaDivergente()


def conferir_controle(ctx, modelo, particao, brutas, seeds, destino):
    _exigir_ativo()
    par = validar_escopo(ctx, modelo)
    if particao not in ("validacao", "teste"):
        raise ValueError("Particao de controle invalida.")
    if list(seeds) != par["sementes"] or len(brutas) != len(seeds):
        raise ValueError("Controle estrito com sementes incompletas.")
    shape = ctx.janelas[particao].y_bruto.shape
    if any(np.asarray(x).shape != shape or not np.isfinite(x).all() for x in brutas):
        raise ValueError("Controle estrito com forma/previsao invalida.")
    destino = Path(destino)
    contrato = base.ler_json(destino / "contrato_execucao.json")
    validar_contrato_adaptado(contrato)
    # A funcao congelada audita grade/alvos e grava a divergencia original.
    # Somente a solicitacao de aceite GPU e interrompida; erros de grade,
    # alvos, NaN ou arquivos continuam fatais. Nenhum aceite e fabricado.
    aceite_original = base.validar_aceite_gpu
    base.validar_aceite_gpu = _nao_emitir_aceite_gpu
    try:
        try:
            legado = CONFERIR_ORIGINAL(ctx, modelo, particao, brutas, seeds, destino)
        except _ComparacaoLegadaDivergente:
            legado = base.ler_json(destino / f"controle_{particao}_divergencia.json")
            if (legado.get("aprovado") is not False or
                    legado.get("contrato_sha256") != contrato["sha256_contrato"] or
                    legado.get("novo_controle_por_dispositivo") is not False or
                    legado.get("alvos_primarios_bitexatos") is not True or
                    legado.get("tolerancia") != 1e-6 or
                    set(legado.get("max_diferenca_por_seed", {})) != {str(s) for s in seeds} or
                    not all(np.isfinite(d) for d in legado["max_diferenca_por_seed"].values())):
                raise ValueError("Comparacao legada reprovada fora do escopo auditado.")
    finally:
        base.validar_aceite_gpu = aceite_original
    comparacao = destino / f"controle_{particao}_comparacao_legada.json"
    base.m.salvar_json_atomico(legado, comparacao)
    registro = {
        "aplicavel": True, "aprovado": True,
        "contrato_sha256": contrato["sha256_contrato"], "politica": POLITICA,
        "referencia": "controle_sem_quantizacao_treinado_sob_politica_estrita",
        "novo_controle_execucao_numerica": True, "novo_controle_por_dispositivo": False,
        "reproducao_exata_exigida": False, "controle_legado_importado": False,
        "reproducao_legada_aprovada": legado.get("aprovado") if legado.get("aplicavel") else None,
        "comparacao_legada": {"arquivo": str(comparacao.resolve()),
            "sha256": base.m.sha256_arquivo(comparacao), "aplicavel": legado.get("aplicavel", False),
            "aprovado": legado.get("aprovado")},
        "evidencia_piloto": contrato["execucao_numerica"]["evidencia_piloto"],
        "dispositivo": "cuda", "dispositivo_original": "cuda",
        "replay_independente_obrigatorio": True, "tolerancia_replay_wm2": 1e-6,
        "significado_aprovado": "Baseline estrito finito; publicacao ainda exige replay independente.",
    }
    base.m.salvar_json_atomico(registro, destino / f"controle_{particao}.json")
    return registro


def validar_controle_adaptado(pasta, particao, contrato):
    if particao not in ('validacao', 'teste'):
        raise ValueError('Particao de controle invalida.')
    pasta = Path(pasta).resolve()
    r = base.ler_json(pasta / f'controle_{particao}.json')
    fixos = {'aplicavel': True, 'aprovado': True, 'politica': POLITICA,
             'contrato_sha256': contrato['sha256_contrato'],
             'novo_controle_execucao_numerica': True, 'novo_controle_por_dispositivo': False,
             'controle_legado_importado': False, 'replay_independente_obrigatorio': True,
             'tolerancia_replay_wm2': 1e-6, 'dispositivo': 'cuda', 'dispositivo_original': 'cuda',
             'evidencia_piloto': contrato['execucao_numerica']['evidencia_piloto']}
    if any(r.get(k) != v for k, v in fixos.items()):
        raise ValueError('Registro do baseline estrito divergente ou incompleto.')
    c = r.get('comparacao_legada', {})
    path = pasta / f'controle_{particao}_comparacao_legada.json'
    if Path(c.get('arquivo', '')).resolve() != path or c.get('sha256') != base.m.sha256_arquivo(path):
        raise ValueError('Comparacao legada ausente, alterada ou de outra particao.')
    legado = base.ler_json(path)
    if c.get('aplicavel') != legado.get('aplicavel', False) or c.get('aprovado') != legado.get('aprovado'):
        raise ValueError('Resumo diverge da comparacao legada preservada.')
    aplicavel = contrato['protocolo']['regime'] == 'atual' and contrato['modo'] == 'completa'
    if c.get('aplicavel') is not aplicavel:
        raise ValueError('Aplicabilidade da comparacao legada incorreta.')
    if aplicavel:
        if (legado.get('contrato_sha256') != contrato['sha256_contrato'] or
                legado.get('alvos_primarios_bitexatos') is not True or
                legado.get('novo_controle_por_dispositivo') is not False or
                legado.get('tolerancia') != 1e-6 or
                r.get('reproducao_legada_aprovada') is not legado.get('aprovado')):
            raise ValueError('Comparacao legada nao preserva grade/alvos/resultado.')
    elif r.get('reproducao_legada_aprovada') is not None:
        raise ValueError('Historico sem referencia legada nao aprova reproducao antiga.')
    return r


@contextmanager
def ativar_adaptador(evidencia=None, *, contrato=None):
    """Escopo por processo para treino/replay; restaura funcoes/flags ao sair.

    Se ``contrato`` for informado, valida sua politica antes do replay.
    Nao admite contextos aninhados ou outro adaptador no mesmo motor.
    """
    global _ativo, _evidencia_ativa
    if _ativo:
        raise RuntimeError("Adaptador ja ativo; contextos aninhados proibidos.")
    caminho = Path(evidencia if evidencia is not None else EVIDENCIA).resolve()
    ler_evidencia(caminho)
    if os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8":
        raise ValueError("CUBLAS_WORKSPACE_CONFIG deve ser :4096:8 antes de inicializar CUDA.")
    alvos = ((base, "construir_contrato", CONSTRUIR_ORIGINAL, construir_contrato),
             (base, "conferir_controle", CONFERIR_ORIGINAL, conferir_controle),
             (base, "nova_rede", REDE_ORIGINAL, nova_rede),
             (base.m, "fixar_semente", SEMENTE_ORIGINAL, fixar_semente))
    if any(getattr(mod, nome) is not original for mod, nome, original, _ in alvos):
        raise RuntimeError("Outro adaptador modificou o motor; nao combinar escopos.")
    deterministico = torch.are_deterministic_algorithms_enabled()
    aviso = torch.is_deterministic_algorithms_warn_only_enabled()
    threads_anteriores = torch.get_num_threads()
    _ativo, _evidencia_ativa = True, caminho
    try:
        torch.use_deterministic_algorithms(True, warn_only=False)
        for mod, nome, _, novo in alvos:
            setattr(mod, nome, novo)
        if contrato is not None:
            torch.set_num_threads(contrato['parametros']['configuracao']['threads_torch'])
            validar_contrato_adaptado(contrato)
        yield
    finally:
        for mod, nome, original, _ in alvos:
            setattr(mod, nome, original)
        torch.use_deterministic_algorithms(deterministico, warn_only=aviso)
        torch.set_num_threads(threads_anteriores)
        _ativo, _evidencia_ativa = False, None


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        base.main()
        return
    escopo = argparse.ArgumentParser(add_help=False)
    escopo.add_argument("--modelo", choices=MODELOS, required=True)
    escopo.add_argument("--tarefa", choices=TAREFAS, required=True)
    escopo.parse_known_args()
    with ativar_adaptador():
        base.main()


if __name__ == "__main__":
    main()
