"""Compara sem alterar dados as tres amostragens possiveis do HDF5."""
from __future__ import annotations

import argparse
import json
import numpy as np
import pandas as pd

from codigo_fonte.dados_horarios_nsrdb import carregar_registro_pontos
from codigo_fonte.historico_nsrdb_expandido import PASTA_HISTORICO, PASTA_RELATORIO, RAIZ, salvar_json, sha256


def auditar(ano: int) -> dict:
    caminho = PASTA_HISTORICO / "amostras_30min" / f"nsrdb_ghi_30min_{ano}.npz"
    with np.load(caminho, allow_pickle=False) as bruto:
        matriz, ids = bruto["ghi"], bruto["site_ids"]
    datas = pd.date_range(f"{ano}-01-01", f"{ano+1}-01-01", inclusive="left", freq="D")
    linhas = []
    for r in carregar_registro_pontos().itertuples(index=False):
        indice = list(ids).index(r.site_id_nsrdb)
        local = np.roll(matriz[:, indice], int(r.timezone_nsrdb * 2))
        caminho_original = RAIZ / "dados/brutos/localidades_ev" / r.arquivo_diario
        original = pd.read_csv(caminho_original, usecols=["data", "ghi"], parse_dates=["data"]).set_index("data").ghi.reindex(datas).to_numpy(dtype=float)
        for tipo, valores in [("minuto_00", local[::2]), ("minuto_30", local[1::2]), ("media_30min", local)]:
            diaria = valores.astype(float).reshape(len(datas), -1).mean(axis=1)
            dif = np.abs(diaria - original)
            linhas.append({"ano": ano, "localidade": r.localidade, "tipo": tipo,
                           "mae_entre_fontes_wm2": float(np.mean(dif)), "max_abs_wm2": float(np.max(dif)),
                           "dias_diferentes_tol_1e_8": int(np.sum(dif > 1e-8)), "dias": len(datas),
                           "original_sha256": sha256(caminho_original)})
    resultado = {"ano": ano, "amostras_30min_sha256": sha256(caminho), "metodo": "Fuso fixo NSRDB via np.roll anual, como hipotese a auditar do endpoint utc=False; nao altera dados", "comparacoes": linhas}
    salvar_json(resultado, PASTA_RELATORIO / f"auditoria_agregacao_{ano}.json")
    return resultado


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ano", type=int, default=2019)
    resultado = auditar(parser.parse_args().ano)
    print(json.dumps(resultado, ensure_ascii=False), flush=True)
