"""Reconstrucao diaria/mensal historica que preserva o contrato da API atual.

O diario original usa intervalo de 60 minutos com amostras no minuto 30, nao a
media das amostras 00/30 usada no modelo horario. O fuso fixo e aplicado pelo
deslocamento circular anual da API. Isso reutiliza as primeiras horas UTC do
mesmo ano na ultima tarde/noite local de 31/dezembro, explicitamente auditado.
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

from codigo_fonte.coleta_e_preparacao.dados_horarios_nsrdb import carregar_registro_pontos
from codigo_fonte.coleta_e_preparacao.historico_nsrdb_expandido import ANOS, PASTA_DIARIA, PASTA_HISTORICO, PASTA_MENSAL, PASTA_RELATORIO, RAIZ, agora, salvar_json, sha256
from codigo_fonte.analises_e_relatorios.auditar_agregacao_historica import auditar


def media_diaria_api(matriz: np.ndarray, timezone_horas: int, ano: int) -> np.ndarray:
    """Replica amostragem e fronteira anuais, sem preencher valores ausentes."""
    dias = len(pd.date_range(f"{ano}-01-01", f"{ano+1}-01-01", inclusive="left", freq="D"))
    valores = np.asarray(matriz)
    if valores.shape != (dias * 48,) or not np.isfinite(valores).all() or (valores < 0).any():
        raise ValueError("A serie de 30 minutos precisa cobrir o ano civil integralmente.")
    if int(timezone_horas) != timezone_horas or not -12 <= timezone_horas <= 14:
        raise ValueError("Fuso horario fixo invalido.")
    local = np.roll(valores, int(timezone_horas * 2))
    return local[1::2].astype(float).reshape(dias, 24).mean(axis=1)


def agregar() -> dict:
    manifesto_path = PASTA_HISTORICO / "manifesto_historico.json"
    manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
    if not manifesto.get("completo"):
        raise ValueError("A coleta 1998--2022 precisa estar completa antes da agregacao.")
    registro = carregar_registro_pontos()
    amostras = {}
    for ano in ANOS:
        item = manifesto["arquivos"][str(ano)]["amostras_30min"]
        caminho = RAIZ / item["arquivo"]
        if sha256(caminho) != item["sha256"]:
            raise ValueError(f"Cache 30min alterado em {ano}.")
        with np.load(caminho, allow_pickle=False) as cache:
            if not np.array_equal(cache["site_ids"], registro.site_id_nsrdb.to_numpy()):
                raise ValueError("IDs divergentes no cache de 30 minutos.")
            amostras[ano] = cache["ghi"]
    sobreposicao = []
    for ano in range(2019, 2023):
        auditoria = auditar(ano)
        confirmacao = [x for x in auditoria["comparacoes"] if x["tipo"] == "minuto_30"]
        if len(confirmacao) != 10 or any(x["dias_diferentes_tol_1e_8"] for x in confirmacao):
            raise ValueError(f"A amostragem minuto30 nao reproduziu o diario original de {ano}.")
        sobreposicao.extend(confirmacao)
    PASTA_DIARIA.mkdir(parents=True, exist_ok=True)
    PASTA_MENSAL.mkdir(parents=True, exist_ok=True)
    resumo = []
    fronteiras = []
    for posicao, linha in enumerate(registro.itertuples(index=False)):
        quadros = []
        for ano in ANOS:
            datas = pd.date_range(f"{ano}-01-01", f"{ano+1}-01-01", inclusive="left", freq="D")
            media = media_diaria_api(amostras[ano][:, posicao], linha.timezone_nsrdb, ano)
            quadros.append(pd.DataFrame({"data": datas, "ghi": media}))
            horas = -int(linha.timezone_nsrdb)
            fonte_inicio = pd.Timestamp(f"{ano}-01-01", tz="UTC") + pd.Timedelta(minutes=30)
            fonte_fim = fonte_inicio + pd.Timedelta(hours=horas - 1)
            registro_fronteira = {"ano": ano, "localidade": linha.localidade, "timezone_horas": int(linha.timezone_nsrdb),
                "data_local_afetada": f"{ano}-12-31", "quantidade_amostras_60min_reutilizadas": horas,
                "horarios_locais_rotulados": [f"{24-horas:02d}:30", "23:30"],
                "origem_real_primeira_amostra": fonte_inicio.isoformat(), "origem_real_ultima_amostra": fonte_fim.isoformat(),
                "politica": "replica deslocamento circular anual do endpoint API utc=False; nao e uma media diaria continua entre arquivos anuais"}
            if ano < ANOS[-1]:
                real_proximo_ano = amostras[ano+1][1:horas*2:2, posicao].astype(float)
                usado_mesmo_ano = amostras[ano][1:horas*2:2, posicao].astype(float)
                delta = float((usado_mesmo_ano - real_proximo_ano).sum() / 24)
                registro_fronteira["diferenca_media_diaria_api_menos_continua_wm2"] = delta
            else:
                registro_fronteira["comparacao_continua"] = "nao calculada; fonte30min2023 fora do periodo solicitado"
            fronteiras.append(registro_fronteira)
        diario = pd.concat(quadros, ignore_index=True)
        original = pd.read_csv(RAIZ / "dados/brutos/localidades_ev" / linha.arquivo_diario, nrows=1)
        for coluna in original.columns:
            if coluna not in diario.columns:
                diario[coluna] = original.iloc[0][coluna]
        diario["ano"] = diario.data.dt.year
        diario["versao_dados"] = "4.0.0 (GOES/aggregated/v4.0.0 HDF5)"
        diario["endpoint_api"] = "extracao_public_S3; contrato_API_interval60_utcFalse_reproduzido"
        diario["intervalo_minutos"] = 60
        diario["amostra_minuto"] = 30
        diario["agregacao"] = "media_diaria_24_amostras_60min_fuso_fixo_roll_anual"
        diario["data_coleta_utc"] = agora()
        caminho = PASTA_DIARIA / linha.arquivo_diario
        diario.to_csv(caminho, index=False, date_format="%Y-%m-%d", lineterminator="\n")
        mensal = diario.set_index("data").ghi.resample("ME").mean().rename("ghi").reset_index()
        mensal["localidade"] = linha.localidade
        mensal["site_id_nsrdb"] = int(linha.site_id_nsrdb)
        mensal["timezone_nsrdb"] = int(linha.timezone_nsrdb)
        mensal["unidade_ghi"] = "W/m2"
        mensal["agregacao"] = "media_mensal_das_medias_diarias_API_60min_minuto30"
        caminho_mensal = PASTA_MENSAL / linha.arquivo_diario
        mensal.to_csv(caminho_mensal, index=False, date_format="%Y-%m-%d", lineterminator="\n")
        if len(diario) != 9131 or len(mensal) != 300:
            raise ValueError("Cobertura diaria/mensal inesperada.")
        resumo.append({"localidade": linha.localidade, "site_id_nsrdb": int(linha.site_id_nsrdb),
                       "dias": len(diario), "meses": len(mensal), "arquivo_diario": caminho.relative_to(RAIZ).as_posix(),
                       "sha256_diario": sha256(caminho), "arquivo_mensal": caminho_mensal.relative_to(RAIZ).as_posix(),
                       "sha256_mensal": sha256(caminho_mensal)})
    resultado = {"concluido_em_utc": agora(), "ok": True, "manifesto_horario_sha256": sha256(manifesto_path),
                 "anos": list(ANOS), "localidades": resumo, "sobreposicao_2019_2022": sobreposicao,
                 "protocolo_diario": "24 amostras minuto30/dia local fixo, deslocamento circular anual; mesmo contrato da API original",
                 "protocolo_horario": "media das duas amostras minuto00/30 por hora UTC; nao e a fonte direta da media diaria",
                 "observacoes_sobreposicao": 14610, "tolerancia_sobreposicao_wm2": 1e-8,
                 "fronteiras_anuais": fronteiras, "sem_interpolacao_ou_imputacao": True}
    salvar_json(resultado, PASTA_RELATORIO / "auditoria_agregacao_completa.json")
    salvar_json(resultado, PASTA_DIARIA / "manifesto_historico.json")
    salvar_json(resultado, PASTA_MENSAL / "manifesto_historico.json")
    return resultado


if __name__ == "__main__":
    resultado = agregar()
    print(json.dumps({"ok": resultado["ok"], "localidades": len(resultado["localidades"]),
                      "observacoes_sobreposicao": resultado["observacoes_sobreposicao"]}), flush=True)
