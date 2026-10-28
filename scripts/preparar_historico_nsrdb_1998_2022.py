"""Executa coleta e auditoria historicas, com retomada e registros de estado."""
from __future__ import annotations

import json
import os
import time
import traceback

import aiohttp
import requests

from codigo_fonte.historico_nsrdb_expandido import (
    ANOS, PASTA_ATUAL, PASTA_HISTORICO, PASTA_RELATORIO, RAIZ, agora,
    coletar, salvar_json, sha256,
)
from codigo_fonte.historico_nsrdb_agregacao import agregar


def executar() -> None:
    caminhos_codigo = [RAIZ / "codigo_fonte/historico_nsrdb_expandido.py", RAIZ / "codigo_fonte/historico_nsrdb_agregacao.py",
                       RAIZ / "scripts/auditar_agregacao_historica.py", RAIZ / "scripts/preparar_historico_nsrdb_1998_2022.py"]
    caminhos_anteriores = sorted(PASTA_ATUAL.glob("*.csv.gz")) + sorted((RAIZ / "dados/brutos/localidades_ev").glob("*.csv"))
    codigo = {p.relative_to(RAIZ).as_posix(): sha256(p) for p in caminhos_codigo}
    originais = {p.relative_to(RAIZ).as_posix(): sha256(p) for p in caminhos_anteriores}
    estado = {"status": "em_execucao", "inicio_utc": agora(), "pid": os.getpid(), "codigo_sha256": codigo,
              "originais_sha256": originais, "anos_objetivo": list(ANOS), "anos_processados": []}
    destino = PASTA_RELATORIO / "status_coleta.json"
    salvar_json(estado, destino)
    try:
        for ano in ANOS:
            estado.update({"ano_atual": ano, "etapa": "coleta_e_validacao_anual", "atualizado_utc": agora()})
            salvar_json(estado, destino)
            for tentativa in range(1, 4):
                try:
                    coletar((ano,))
                    break
                except (requests.RequestException, aiohttp.ClientError, TimeoutError, ConnectionError) as exc:
                    if tentativa == 3:
                        raise
                    print(json.dumps({"ano": ano, "tentativa": tentativa, "erro_transitorio": str(exc)}), flush=True)
                    time.sleep(tentativa * 5)
            estado["anos_processados"].append(ano)
        estado.update({"etapa": "agregacao_diaria_mensal_e_auditoria", "atualizado_utc": agora()})
        salvar_json(estado, destino)
        resultado = agregar()
        for relativo, esperado in {**codigo, **originais}.items():
            if sha256(RAIZ / relativo) != esperado:
                raise ValueError(f"Arquivo anterior ou codigo mudou durante a coleta: {relativo}")
        estado.update({"status": "concluido", "etapa": "concluida", "fim_utc": agora(),
                       "auditoria_agregacao_ok": resultado["ok"], "originais_preservados": True,
                       "manifesto_historico_sha256": sha256(PASTA_HISTORICO / "manifesto_historico.json")})
        salvar_json(estado, destino)
        print(json.dumps({"status": "concluido", "anos": len(ANOS), "localidades": 10, "auditoria_ok": resultado["ok"]}), flush=True)
    except Exception as exc:
        estado.update({"status": "falhou", "erro": str(exc), "atualizado_utc": agora()})
        salvar_json(estado, destino)
        traceback.print_exc()
        raise


if __name__ == "__main__":
    executar()
