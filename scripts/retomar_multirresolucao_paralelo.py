"""Retoma pares modelo/semente ausentes sem alterar o protocolo cientifico.

O experimento original e deliberadamente sequencial. Este coordenador apenas
distribui pares independentes em processos isolados; cada processo chama a
mesma funcao de treinamento, com a configuracao canonica e gravacao atomica.
Depois, o pipeline original relê todos os caches e consolida os artefatos.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
from typing import Sequence


RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
PASTA_TAREFA = RAIZ / "resultados" / "avaliacao_multirresolucao" / "daily_30"
CONTRATO = PASTA_TAREFA / "contrato_execucao.json"
MODELOS = ("TimesNet", "DilatedRNN")
SLUGS = {"TimesNet": "timesnet", "DilatedRNN": "dilatedrnn"}
SEMENTES = (11, 23, 42, 67, 89)


def _sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _relativo_do_contrato(caminho: str) -> Path:
    """Converte tanto chaves Windows antigas quanto chaves portateis."""

    win = PureWindowsPath(caminho)
    partes = list(win.parts)
    if "TCC" in partes:
        partes = partes[partes.index("TCC") + 1 :]
    return Path(*partes)


def validar_contrato_existente() -> dict[str, object]:
    contrato = json.loads(CONTRATO.read_text(encoding="utf-8"))
    base = dict(contrato)
    declarado = str(base.pop("sha256_contrato"))
    serializado = json.dumps(
        base, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if hashlib.sha256(serializado).hexdigest() != declarado:
        raise RuntimeError("O hash interno do contrato diario diverge.")
    for grupo in ("entradas_sha256", "codigo_sha256"):
        for registrado, esperado in contrato[grupo].items():
            caminho = RAIZ / _relativo_do_contrato(str(registrado))
            if not caminho.is_file():
                raise FileNotFoundError(f"Arquivo contratado ausente: {caminho}")
            observado = _sha256(caminho)
            if observado != esperado:
                raise RuntimeError(f"Hash divergente para {caminho}.")
    import importlib.metadata
    import platform

    dependencias = {
        "python": platform.python_version(),
        "numpy": importlib.metadata.version("numpy"),
        "pandas": importlib.metadata.version("pandas"),
        "torch": importlib.metadata.version("torch"),
        "scikit-learn": importlib.metadata.version("scikit-learn"),
        "xgboost": importlib.metadata.version("xgboost"),
        "joblib": importlib.metadata.version("joblib"),
    }
    if dependencias != contrato["dependencias"]:
        raise RuntimeError(
            "Dependencias diferentes do contrato: "
            f"observado={dependencias!r}; esperado={contrato['dependencias']!r}."
        )
    return contrato


def _preparar_janelas():
    import codigo_fonte.experimento_multirresolucao as experimento

    tarefa = experimento.TAREFAS_CANONICAS["daily_30"]
    configuracao = experimento.ConfiguracaoMultirresolucao(
        modo_execucao="completa",
        sementes=experimento.SEMENTES_CANONICAS,
    )
    series, _ = experimento.carregar_series_diarias()
    particoes = {
        "ajuste": experimento.construir_janelas(
            series,
            seq_len=tarefa.seq_len,
            pred_len=tarefa.pred_len,
            intervalo=tarefa.ajuste,
            particao="ajuste",
        ),
        "validacao": experimento.construir_janelas(
            series,
            seq_len=tarefa.seq_len,
            pred_len=tarefa.pred_len,
            intervalo=tarefa.validacao,
            particao="validacao_2023",
        ),
        "refit": experimento.construir_janelas(
            series,
            seq_len=tarefa.seq_len,
            pred_len=tarefa.pred_len,
            intervalo=tarefa.refit,
            particao="refit",
        ),
        "teste": experimento.construir_janelas(
            series,
            seq_len=tarefa.seq_len,
            pred_len=tarefa.pred_len,
            intervalo=tarefa.teste,
            particao="teste_2024",
        ),
    }
    escalas_selecao = experimento.ajustar_escalas_pre_corte(
        series,
        fim_exclusivo="2023-01-01",
        nome_ajuste="ajuste_para_validacao",
    )
    escalas_refit = experimento.ajustar_escalas_pre_corte(
        series,
        fim_exclusivo="2024-01-01",
        nome_ajuste="refit_para_teste",
    )
    return experimento, tarefa, configuracao, series, particoes, escalas_selecao, escalas_refit


def executar_par(modelo: str, semente: int) -> None:
    if modelo not in MODELOS or semente not in SEMENTES:
        raise ValueError("Par modelo/semente fora do protocolo canonico.")
    validar_contrato_existente()
    (
        experimento,
        tarefa,
        configuracao,
        series,
        particoes,
        escalas_selecao,
        escalas_refit,
    ) = _preparar_janelas()
    bruto_val, bruto_teste, epocas, _ = experimento.executar_modelo_aprendido(
        modelo,
        tarefa=tarefa,
        configuracao=configuracao,
        semente=semente,
        treino=particoes["ajuste"],
        validacao=particoes["validacao"],
        refit=particoes["refit"],
        teste=particoes["teste"],
        escalas_selecao=escalas_selecao,
        escalas_refit=escalas_refit,
        num_localidades=len(series),
        pasta_tarefa=PASTA_TAREFA,
        retomar=True,
    )
    if bruto_val.shape != particoes["validacao"].y_bruto.shape:
        raise RuntimeError("Cache de validacao produzido com forma invalida.")
    if bruto_teste.shape != particoes["teste"].y_bruto.shape:
        raise RuntimeError("Cache de teste produzido com forma invalida.")
    print(json.dumps({"modelo": modelo, "semente": semente, "epocas": epocas}))


def pares_ausentes() -> list[tuple[str, int]]:
    ausentes = []
    for modelo in MODELOS:
        for semente in SEMENTES:
            cache = PASTA_TAREFA / "cache" / f"{SLUGS[modelo]}_seed{semente}.npz"
            if not cache.is_file():
                ausentes.append((modelo, semente))
    return ausentes


def executar_pares(max_processos: int) -> None:
    validar_contrato_existente()
    pendentes = pares_ausentes()
    if not pendentes:
        print("Nenhum par ausente.")
        return
    ativos: list[tuple[subprocess.Popen[str], str, int]] = []
    fila = list(pendentes)
    falhas: list[str] = []
    while fila or ativos:
        while fila and len(ativos) < max_processos:
            modelo, semente = fila.pop(0)
            comando = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                modelo,
                str(semente),
            ]
            processo = subprocess.Popen(
                comando,
                cwd=RAIZ,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            ativos.append((processo, modelo, semente))
            print(f"iniciado {modelo} seed={semente}", flush=True)
        processo, modelo, semente = ativos.pop(0)
        saida, _ = processo.communicate()
        print(saida, end="")
        if processo.returncode:
            falhas.append(f"{modelo}/seed={semente} (codigo {processo.returncode})")
        else:
            print(f"concluido {modelo} seed={semente}", flush=True)
    if falhas:
        raise RuntimeError("Falharam: " + ", ".join(falhas))


def consolidar_com_contrato_existente() -> None:
    contrato = validar_contrato_existente()
    import codigo_fonte.experimento_multirresolucao as experimento

    construir_original = experimento.construir_contrato
    experimento.construir_contrato = lambda **_: contrato
    try:
        resumos = experimento.executar_avaliacao_multirresolucao(
            tarefas="daily_30",
            configuracao=experimento.ConfiguracaoMultirresolucao(
                modo_execucao="completa",
                sementes=experimento.SEMENTES_CANONICAS,
            ),
            pasta_saida=RAIZ / "resultados" / "avaliacao_multirresolucao",
            retomar=True,
        )
    finally:
        experimento.construir_contrato = construir_original
    if not resumos or resumos[0].get("resultado_publicavel") is not True:
        raise RuntimeError("A consolidacao nao marcou o resultado como publicavel.")


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-processos", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--worker", nargs=2, metavar=("MODELO", "SEMENTE"))
    parser.add_argument("--somente-consolidar", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    argumentos = construir_parser().parse_args(argv)
    if argumentos.worker:
        executar_par(argumentos.worker[0], int(argumentos.worker[1]))
        return 0
    if not argumentos.somente_consolidar:
        executar_pares(max(1, argumentos.max_processos))
    consolidar_com_contrato_existente()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
