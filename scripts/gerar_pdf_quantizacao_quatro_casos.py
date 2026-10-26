"""Acrescenta quantizacao horaria/diaria ao PDF historico de seis paginas.

O autor deve executar o marcador de artefato antes de invocar este CLI sem
--somente-validar. Nenhum resultado parcial ou smoke pode ser publicado.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from scripts.gerar_pdf_quantizacao_timesnet import (
    VARIANTES, ROTULOS, conferir_hashes, ler_json, validar_diagnostico,
)
from scripts.gerar_tabela_resultados_ghi_otimizada import (
    CHAVES, METRICAS, calcular_macro, conferir_observacoes,
    normalizar_chaves, numero, sha256,
)

TAREFAS = {"hourly_72_extension": (24, 48, 72), "daily_30": (1, 3, 7, 14, 30)}
SEMENTES = {"hourly_72_extension": [42], "daily_30": [11, 23, 42, 67, 89]}
ORIGENS = {"hourly_72_extension": {2023: 363, 2024: 363},
           "daily_30": {2023: 336, 2024: 337}}
COLUNA_PREVISAO = "previsao_pos_timesnet_ensemble_wm2"


def validar_metadados(tarefa: str, contrato: dict, selecao: dict, status: dict) -> None:
    if (status.get("etapa") != "concluida" or status.get("modo") != "completa"
            or status.get("teste_avaliado") is not True):
        raise ValueError(f"Experimento incompleto ou smoke: {tarefa}")
    if (contrato.get("tarefa", {}).get("slug") != tarefa or selecao.get("tarefa") != tarefa
            or status.get("tarefa") != tarefa):
        raise ValueError(f"Tarefa incoerente: {tarefa}")
    q = contrato.get("quantizacao", {})
    cfg = contrato.get("configuracao", {})
    candidato = contrato.get("candidato_base", {})
    if (contrato.get("minmax") is not True or q.get("onde") != "somente_entradas"
            or q.get("alvos_quantizados") is not False or q.get("pesos_quantizados") is not False
            or q.get("controle") != "sem_quantizacao_e_sem_clip" or q.get("intervalo") != [0, 1]
            or q.get("niveis") != [64, 128, 256]):
        raise ValueError(f"Protocolo min-max/quantizacao incoerente: {tarefa}")
    variantes = contrato.get("variantes", [])
    teto = cfg.get("max_epocas_diario")
    if (len(variantes) != 4 or {r["nome"]: r["niveis"] for r in variantes} != VARIANTES
            or contrato.get("sementes") != SEMENTES[tarefa]
            or contrato.get("n_localidades") != 10 or contrato.get("modo") != "completa"
            or cfg.get("modo_execucao") != "completa"
            or not isinstance(teto, int) or isinstance(teto, bool) or teto < 1
            or cfg.get("paciencia_diario", 0) < 1
            or contrato.get("dispositivo") not in {"cpu", "cuda"}
            or candidato.get("contexto") != contrato["tarefa"].get("seq_len")
            or tuple(contrato["tarefa"].get("horizontes", [])) != TAREFAS[tarefa]):
        raise ValueError(f"Variantes, sementes ou configuracao incoerentes: {tarefa}")
    corpo = {k: v for k, v in contrato.items() if k != "sha256_contrato"}
    digest = hashlib.sha256(json.dumps(corpo, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()
    if digest != contrato.get("sha256_contrato"):
        raise ValueError(f"Hash do contrato inconsistente: {tarefa}")
    if (selecao.get("selecao_concluida_antes_do_teste") is not True
            or selecao.get("modo") != "completa"
            or selecao.get("contrato_sha256") != digest):
        raise ValueError(f"Selecao nao congelada no contrato: {tarefa}")
    ranking = selecao.get("ranking", [])
    if len(ranking) != 4 or {r["nome"]: r["niveis"] for r in ranking} != VARIANTES:
        raise ValueError(f"Ranking deve conter exatamente os quatro niveis: {tarefa}")
    for linha in ranking:
        epocas = linha.get("epocas", {})
        if (set(epocas) != {str(s) for s in SEMENTES[tarefa]}
                or any(not isinstance(e, int) or isinstance(e, bool) or not 1 <= e <= teto for e in epocas.values())
                or not np.isfinite(linha["MAE_validacao_wm2"])):
            raise ValueError(f"Ranking com sementes/epocas/MAE invalidos: {tarefa}")
    ordem = {nome: i for i, nome in enumerate(VARIANTES)}
    esperado = sorted(ranking, key=lambda r: (r["MAE_validacao_wm2"], ordem[r["nome"]]))
    if (ranking != esperado or selecao.get("vencedor") != esperado[0]
            or status.get("vencedor") != esperado[0]):
        raise ValueError(f"Vencedor/ranking nao corresponde ao MAE de validacao: {tarefa}")


def validar_previsoes(df: pd.DataFrame, tarefa: str, ano: int) -> pd.DataFrame:
    """Confere amostra, media bruta e piso/mascara noturna por observacao."""
    df = normalizar_chaves(df)
    pred_len, n_origens = max(TAREFAS[tarefa]), ORIGENS[tarefa][ano]
    if (df.localidade.nunique() != 10 or len(df) != 10 * n_origens * pred_len
            or not (df.origem.dt.year == ano).all()
            or set(df.passo) != set(range(1, pred_len + 1))):
        raise ValueError(f"Amostra/periodo incompleto: {tarefa}, {ano}")
    for _, grupo in df.groupby("localidade"):
        if grupo.origem.nunique() != n_origens or len(grupo) != n_origens * pred_len:
            raise ValueError(f"Origens por localidade inconsistentes: {tarefa}, {ano}")
    if not (df.groupby(["localidade", "origem"]).size() == pred_len).all():
        raise ValueError(f"Horizonte incompleto em alguma origem: {tarefa}, {ano}")
    sementes = SEMENTES[tarefa]
    brutas = [f"previsao_bruta_timesnet_seed{s}_wm2" for s in sementes]
    pos = [f"previsao_pos_timesnet_seed{s}_wm2" for s in sementes]
    cols = ["ghi_real_wm2", *brutas, *pos, "previsao_bruta_timesnet_ensemble_wm2", COLUNA_PREVISAO]
    if not np.isfinite(df[cols].to_numpy(dtype=float)).all():
        raise ValueError("Previsoes ou alvos nao finitos.")
    media = df[brutas].mean(axis=1).to_numpy(dtype=float)
    esperado, esperado_seeds = np.maximum(media, 0), np.maximum(df[brutas].to_numpy(), 0)
    if tarefa == "hourly_72_extension":
        elevacao = df["elevacao_solar_graus"].to_numpy(dtype=float)
        if not np.isfinite(elevacao).all() or (np.abs(elevacao) > 90).any():
            raise ValueError("Elevacao solar invalida.")
        esperado[elevacao <= 0] = 0
        esperado_seeds[elevacao <= 0] = 0
    if (not np.allclose(df.previsao_bruta_timesnet_ensemble_wm2, media, atol=1e-7, rtol=0)
            or not np.allclose(df[COLUNA_PREVISAO], esperado, atol=1e-7, rtol=0)
            or not np.allclose(df[pos], esperado_seeds, atol=1e-7, rtol=0)):
        raise ValueError("Ensemble ou pos-processamento inconsistente.")
    return df


def conferir_macro(salvas: pd.DataFrame, calculadas: pd.DataFrame, tarefa: str, particao: str) -> None:
    recorte = salvas[(salvas.tarefa == tarefa) & (salvas.particao == particao)
                    & (salvas.tipo_horizonte == "cumulativo")]
    if recorte.horizonte.duplicated().any() or set(recorte.horizonte) != set(TAREFAS[tarefa]):
        raise ValueError(f"Metricas incompletas: {tarefa}, {particao}")
    salvas_indice = recorte.set_index("horizonte")
    for linha in calculadas.to_dict(orient="records"):
        for campo in METRICAS:
            if not np.isclose(linha[campo], salvas_indice.loc[linha["horizonte"], campo], atol=1e-7, rtol=1e-9):
                raise ValueError(f"Metrica difere das previsoes: {tarefa}, {particao}, {campo}")


def montar_dados(experimento: Path, benchmark: Path) -> dict:
    fontes = {Path(__file__).resolve(), Path(__file__).with_name("gerar_pdf_quantizacao_timesnet.py").resolve(),
              Path(__file__).with_name("gerar_tabela_resultados_ghi_otimizada.py").resolve()}
    global_path = experimento / "selecao_global_congelada.json"
    global_ = ler_json(global_path)
    if set(global_.get("tarefas", [])) != set(TAREFAS):
        raise ValueError("Congelamento global deve incluir as tarefas horaria e diaria.")
    conferir_hashes(global_["fontes_selecao_sha256"], fontes)
    fontes.add(global_path.resolve())
    relatorio = {"criado_em_utc": datetime.now(timezone.utc).isoformat(), "tarefas": {}}
    for tarefa, horizontes in TAREFAS.items():
        pasta = experimento / tarefa
        paths = [pasta / n for n in ("contrato_execucao.json", "selecao_congelada.json", "status_execucao.json")]
        contrato, selecao, status = [ler_json(p) for p in paths]
        fontes.update(p.resolve() for p in paths)
        validar_metadados(tarefa, contrato, selecao, status)
        for campo in ("codigo", "entradas", "fontes_configuracao"):
            conferir_hashes(contrato[campo], fontes)
        manifesto_path = pasta / "manifesto_artefatos.json"
        manifesto = ler_json(manifesto_path)
        conferir_hashes({str(pasta / r["arquivo"]): r["sha256"] for r in manifesto["arquivos"]}, fontes)
        fontes.add(manifesto_path.resolve())
        cfg, ranking = contrato["configuracao"], selecao["ranking"]
        por_nome = {r["nome"]: r for r in ranking}
        info = {"hiperparametros": contrato["candidato_base"], "configuracao": cfg,
                "max_epocas": cfg["max_epocas_diario"], "paciencia": cfg["paciencia_diario"],
                "sementes": contrato["sementes"], "dispositivo": contrato["dispositivo"], "ranking": ranking,
                "vencedor": selecao["vencedor"]["nome"], "N_origens_por_local": ORIGENS[tarefa][2024],
                "variantes": {}, "clipping": {}, "contrato": contrato, "selecao": selecao}
        canonicas = {}
        for particao in ("validacao", "teste"):
            p = benchmark / tarefa / f"previsoes_{particao}.csv.gz"
            canonicas[particao] = pd.read_csv(p, usecols=lambda c: c in set(CHAVES) |
                {"ghi_real_wm2", "origem_utc", "timestamp_alvo_utc", "passo_h"})
            fontes.add(p.resolve())
        elevacoes_referencia = {}
        for nome, niveis in VARIANTES.items():
            variante = pasta / "variantes" / nome
            estado = ler_json(variante / "status_execucao.json")
            if (estado.get("etapa") != "concluida" or estado.get("modo") != "completa"
                    or estado.get("nome") != nome or estado.get("niveis") != niveis
                    or estado.get("selecionada") is not (nome == info["vencedor"])):
                raise ValueError(f"Variante incompleta/incoerente: {tarefa}, {nome}")
            metricas = {}
            for particao, ano in (("validacao", 2023), ("teste", 2024)):
                quadro = validar_previsoes(pd.read_csv(variante / f"previsoes_{particao}.csv.gz"), tarefa, ano)
                conferir_observacoes(quadro, canonicas[particao])
                if nome == "sem_quantizacao":
                    fase_controle = "selecao" if particao == "validacao" else "refit"
                    reproducao_path = variante / f"reproducao_controle_{fase_controle}.json"
                    reproducao = ler_json(reproducao_path)
                    fonte_controle = Path(reproducao["fonte"])
                    controle_anterior = normalizar_chaves(pd.read_csv(fonte_controle))
                    conferir_observacoes(quadro, controle_anterior)
                    delta = float(np.max(np.abs(quadro.previsao_bruta_timesnet_ensemble_wm2.to_numpy() -
                        controle_anterior.previsao_bruta_timesnet_otimizada_wm2.to_numpy())))
                    if (reproducao.get("aprovado") is not True or delta > 1e-6
                            or not np.isclose(delta, reproducao["diferenca_maxima_wm2"], rtol=0, atol=1e-12)):
                        raise ValueError("Controle novo nao reproduz os resultados anteriores.")
                    fontes.update((reproducao_path.resolve(), fonte_controle.resolve()))
                if tarefa == "hourly_72_extension":
                    elev = quadro.elevacao_solar_graus.to_numpy()
                    if particao in elevacoes_referencia and not np.array_equal(elev, elevacoes_referencia[particao]):
                        raise ValueError("Elevacao solar difere entre as variantes.")
                    elevacoes_referencia[particao] = elev
                metrica = calcular_macro(quadro, COLUNA_PREVISAO, horizontes)
                conferir_macro(pd.read_csv(variante / f"metricas_{particao}_macro.csv"),
                               metrica, tarefa, f"{particao}_{ano}")
                mae = float(metrica.loc[metrica.horizonte == max(horizontes), "MAE_wm2"].iloc[0])
                if not np.isclose(mae, estado[f"MAE_{particao}_wm2"], atol=1e-7, rtol=0):
                    raise ValueError(f"MAE salvo difere das previsoes: {tarefa}, {nome}, {particao}")
                if particao == "validacao" and not np.isclose(mae, por_nome[nome]["MAE_validacao_wm2"], atol=1e-7, rtol=0):
                    raise ValueError("MAE da selecao difere das previsoes de validacao.")
                metricas[particao] = metrica.to_dict(orient="records")
            diag = {**ler_json(variante / "diagnostico_selecao.json"), **ler_json(variante / "diagnostico_refit.json")}
            diags = {}
            for fase in ("ajuste", "validacao", "refit", "teste"):
                n = contrato["tarefa"][fase]["origens_esperadas_por_localidade"] * 10 * contrato["candidato_base"]["contexto"]
                diags[fase] = validar_diagnostico(diag[fase], niveis, n)
                if nome == "q64":
                    info["clipping"][fase] = diags[fase]
                elif nome in {"q128", "q256"}:
                    if any(diags[fase][c] != info["clipping"][fase][c] for c in ("total", "abaixo_zero", "acima_um", "saturados")):
                        raise ValueError("Clipping deveria ter mesmas contagens nos tres niveis.")
            info["variantes"][nome] = {"niveis": niveis, "metricas": metricas["teste"],
                "metricas_validacao": metricas["validacao"], "diagnosticos": diags}
        relatorio["tarefas"][tarefa] = info
    relatorio["fontes"] = [{"path": str(p), "sha256": sha256(p)} for p in sorted(fontes, key=str)]
    return relatorio


def escrever_apendices(relatorio: dict, destino) -> None:
    """Duas paginas; mesma linguagem visual dos apendices mensais anteriores."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph, Table, TableStyle

    c = canvas.Canvas(destino if hasattr(destino, "write") else str(destino), pagesize=A4)
    largura, altura = A4
    margem, util = 35, largura - 70
    texto, azul = colors.HexColor("#142435"), colors.HexColor("#edf4fb")
    nota = ParagraphStyle("nota", fontName="Times-Roman", fontSize=8.7, leading=10.2, textColor=texto)
    pequena = ParagraphStyle("pequena", parent=nota, fontSize=8, leading=9.1)

    def paragrafo(txt, y, estilo=nota):
        p = Paragraph(txt, estilo)
        _, h = p.wrap(util, altura)
        p.drawOn(c, margem, y - h)
        return y - h

    def titulo(txt, y):
        c.setFillColor(texto)
        c.setFont("Times-Bold", 10.7)
        c.drawString(margem, y - 11, txt)
        return y - 17

    def tabela(linhas, larguras, y, selecionadas=(), divisorias=(), fonte=8.4, padding=2.0):
        comandos = [("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
            ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), fonte), ("LEADING", (0, 0), (-1, -1), fonte + 1),
            ("TEXTCOLOR", (0, 0), (-1, -1), texto), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), padding), ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
            ("LINEABOVE", (0, 0), (-1, 0), .7, colors.black),
            ("LINEBELOW", (0, 0), (-1, 0), .5, colors.black),
            ("LINEBELOW", (0, -1), (-1, -1), .7, colors.black)]
        for row in selecionadas:
            comandos.extend([("BACKGROUND", (0, row), (-1, row), azul),
                             ("FONTNAME", (0, row), (-1, row), "Times-Bold")])
        for row in divisorias:
            comandos.append(("LINEABOVE", (0, row), (-1, row), .3, colors.HexColor("#adb7c0")))
        tab = Table(linhas, colWidths=larguras)
        tab.setStyle(TableStyle(comandos))
        _, h = tab.wrap(util, altura)
        tab.drawOn(c, margem, y - h)
        return y - h - 7

    for pagina, (tarefa, horizontes) in enumerate(TAREFAS.items(), 7):
        info = relatorio["tarefas"][tarefa]
        cfg, hp, seeds = info["configuracao"], info["hiperparametros"], info["sementes"]
        horario = tarefa == "hourly_72_extension"
        unidade = "horas" if horario else "dias"
        y = altura - 31
        c.setFillColor(texto)
        c.setFont("Times-Roman", 9)
        c.drawString(margem, y, "Previsão de GHI | apêndice de quantização da entrada")
        y -= 23
        c.setFont("Times-Bold", 18)
        c.drawString(margem, y, "TimesNet " + ("horária - até 72 horas" if horario else "diária - até 30 dias"))
        y -= 13
        sementes_txt = "Semente única: 42." if horario else "Média de cinco sementes: 11, 23, 42, 67 e 89."
        y = paragrafo(f"Entrada: {hp['contexto']} {unidade}; previsão direta de {max(horizontes)} {unidade}. "
                      f"Teste: {info['N_origens_por_local']} origens por localidade. {sementes_txt}", y) - 4
        y = paragrafo(f"Configuração fixa: d_model={cfg['timesnet_d_model']}; d_ff={cfg['timesnet_d_ff']}; "
            f"blocos={cfg['timesnet_blocos']}; dropout={numero(cfg['timesnet_dropout'], 1)}; "
            f"taxa={numero(hp['taxa'], 4)}; lote={hp['lote']}; perda={hp['perda'].upper()}. "
            f"Teto: {info['max_epocas']} épocas; paciência: {info['paciencia']}; "
            f"dispositivo: {info['dispositivo'].upper()}. Controle e três níveis treinados novamente.", y, pequena) - 6
        y = titulo("1. Escolha da entrada pela validação de 2023", y)
        ordem_seeds = " / ".join(map(str, seeds))
        linhas = [["Pos.", "Entrada da TimesNet", "MAE 2023 (W/m²)", f"Épocas selecionadas ({ordem_seeds})"]]
        for pos, r in enumerate(info["ranking"], 1):
            linhas.append([str(pos), ROTULOS[r["nome"]], numero(r["MAE_validacao_wm2"], 4),
                           " / ".join(str(r["epocas"][str(s)]) for s in seeds)])
        y = tabela(linhas, [25, 137, 113, util - 275], y, selecionadas=(1,))
        teto_atingido = any(e == info["max_epocas"] for r in info["ranking"] for e in r["epocas"].values())
        detalhe = " Há seleção no teto de épocas; isso não comprova convergência." if teto_atingido else ""
        y = paragrafo("Azul: menor MAE de validação no horizonte completo; escolha congelada antes do teste." + detalhe,
                      y, pequena) - 5
        y = titulo("2. Teste de 2024 - todas as variantes e horizontes cumulativos", y)
        linhas = [["Horizonte", "Entrada", "MAE\n(W/m²)", "MSE\n((W/m²)²)", "RMSE\n(W/m²)", "nRMSE\n(%)", "R²"]]
        selecionadas, divisorias = [], []
        for h in horizontes:
            if len(linhas) > 1:
                divisorias.append(len(linhas))
            for i, nome in enumerate(VARIANTES):
                m = next(r for r in info["variantes"][nome]["metricas"] if r["horizonte"] == h)
                if nome == info["vencedor"]:
                    selecionadas.append(len(linhas))
                rotulo = "Sem quant." if nome == "sem_quantizacao" else str(VARIANTES[nome])
                vals = [numero(m[k] * (100 if k == "nRMSE" else 1), 4 if k == "MAE_wm2" else (3 if k == "R2" else 2)) for k in METRICAS]
                intervalo = (f"1-{h} " + ("h" if horario else "dias")) if h > 1 else "1 dia"
                linhas.append([intervalo if i == 0 else "", rotulo, *vals])
        y = tabela(linhas, [59, 57, 79, 98, 81, 78, util - 452], y,
                   selecionadas=selecionadas, divisorias=divisorias)
        y = titulo("3. Clipping das entradas normalizadas em [0, 1]", y)
        linhas = [["Fase", "Abaixo de 0", "Acima de 1", "Valores de entrada", "Fora da faixa (%)"]]
        for fase, rotulo in (("ajuste", "Ajuste até 2022"), ("validacao", "Validação 2023"),
                             ("refit", "Reajuste até 2023"), ("teste", "Teste 2024")):
            r = info["clipping"][fase]
            linhas.append([rotulo, str(r["abaixo_zero"]), str(r["acima_um"]), str(r["total"]),
                           numero(100 * (r["abaixo_zero"] + r["acima_um"]) / r["total"], 3)])
        y = tabela(linhas, [108, 78, 76, 130, util - 392], y, fonte=8)
        y = paragrafo("Contagens por posição nas janelas, com repetições por sobreposição. Os três níveis têm o mesmo clipping. "
                      "O controle conserva valores fora de [0, 1]; a comparação inclui arredondamento e saturação.", y, pequena) - 4
        mascara = " No horário, previsões com elevação solar ≤ 0° são zeradas." if horario else ""
        y = paragrafo("<b>Protocolo.</b> Min-max por localidade: ajuste até 2022 na seleção e até 2023 no reajuste. "
            "Entradas: rint(clip(x, 0, 1) × (L - 1)) / (L - 1), com empates para inteiro par. "
            "Alvos e pesos contínuos; GHI direto, sem climatologia. Inversão do min-max e piso zero nas previsões." + mascara,
            y, pequena) - 4
        y = paragrafo("<b>Métricas.</b> Média das métricas de 10 localidades NSRDB; MSE e RMSE agregados separadamente; "
                      "nRMSE = RMSE/média observada por local. Azul mantém a escolha de 2023, não o menor erro de 2024.", y, pequena) - 4
        y = paragrafo("<b>Limites.</b> Base restrita a 2019-2024; histórico anterior ainda não coletado. "
            "A influência desse recorte no MAE não foi isolada. Análise retrospectiva: 2024 já havia sido observado; "
            "confirmação exige outro período. As seis páginas anteriores mantêm os resultados históricos.", y, pequena)
        if y < 30:
            raise ValueError(f"Conteudo excedeu a area util da pagina: {tarefa}, y={y:.1f}")
        c.setFillColor(colors.HexColor("#596773"))
        c.setFont("Times-Roman", 8)
        c.drawString(margem, 16, "Fontes, hashes e métricas sem arredondamento acompanham a geração na pasta de auditoria.")
        c.drawRightString(largura - margem, 16, f"{pagina}/8")
        c.showPage()
    c.save()


def escrever_pdf(relatorio: dict, fonte: Path, destino: Path) -> None:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    origem = PdfReader(str(fonte))
    if len(origem.pages) != 6:
        raise ValueError("O PDF fonte deve conter exatamente as seis paginas anteriores.")
    if destino.resolve() == fonte.resolve():
        raise ValueError("A saida nao pode sobrescrever a fonte.")
    escritor = PdfWriter()
    for n, pagina in enumerate(origem.pages, 1):
        w, h = float(pagina.mediabox.width), float(pagina.mediabox.height)
        overlay = BytesIO()
        c = canvas.Canvas(overlay, pagesize=(w, h))
        c.setFillColor(colors.white)
        c.rect(w - 56, 13, 23, 11, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#596773"))
        c.setFont("Times-Roman", 8)
        c.drawRightString(w - 35, 16, f"{n}/8")
        c.save()
        overlay.seek(0)
        pagina.merge_page(PdfReader(overlay).pages[0])
        escritor.add_page(pagina)
    apendice = BytesIO()
    escrever_apendices(relatorio, apendice)
    apendice.seek(0)
    for pagina in PdfReader(apendice).pages:
        escritor.add_page(pagina)
    escritor.add_metadata({"/Title": "Previsao de GHI - quantizacao TimesNet nos quatro casos",
                           "/Author": "Projeto TCC - previsao de GHI"})
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("wb") as stream:
        escritor.write(stream)
    if len(PdfReader(str(destino)).pages) != 8:
        raise ValueError("O PDF atualizado deve conter oito paginas.")


def verificar_pdf(fonte: Path, destino: Path, relatorio: dict) -> dict:
    """Leitura independente: pixels historicos e valores impressos dos apendices."""
    import fitz

    resultado = {"paginas": 8, "paginas_historicas_preservadas": [], "metricas_novas_conferidas": 0,
                 "maes_validacao_conferidos": 0, "epocas_conferidas": 0}
    with fitz.open(fonte) as original, fitz.open(destino) as novo:
        if len(original) != 6 or len(novo) != 8:
            raise ValueError("Quantidade inesperada de paginas na verificacao.")
        for i in range(6):
            # A unica alteracao autorizada nas paginas antigas e o contador no rodape.
            area = fitz.Rect(0, 0, original[i].rect.width, original[i].rect.height - 30)
            a = original[i].get_pixmap(matrix=fitz.Matrix(1, 1), clip=area, alpha=False)
            b = novo[i].get_pixmap(matrix=fitz.Matrix(1, 1), clip=area, alpha=False)
            if (a.width, a.height, a.samples) != (b.width, b.height, b.samples):
                raise ValueError(f"Conteudo historico mudou na pagina {i + 1}.")
            resultado["paginas_historicas_preservadas"].append(i + 1)
        for i, tarefa in enumerate(TAREFAS, 6):
            text = re.sub(r"\s+", " ", novo[i].get_text())
            info = relatorio["tarefas"][tarefa]
            secao_val = text.split("1. Escolha", 1)[1].split("2. Teste", 1)[0]
            secao_teste = text.split("2. Teste", 1)[1].split("3. Clipping", 1)[0]
            for r in info["ranking"]:
                sequencia = numero(r["MAE_validacao_wm2"], 4) + " " + " / ".join(
                    str(r["epocas"][str(s)]) for s in info["sementes"])
                if sequencia not in secao_val:
                    raise ValueError(f"Ranking/epocas ausentes do PDF: {tarefa}, {r['nome']}.")
                secao_val = secao_val.replace(sequencia, "", 1)
                resultado["maes_validacao_conferidos"] += 1
                resultado["epocas_conferidas"] += len(info["sementes"])
            for variante in info["variantes"].values():
                for m in variante["metricas"]:
                    valores = [numero(m[k] * (100 if k == "nRMSE" else 1),
                        4 if k == "MAE_wm2" else (3 if k == "R2" else 2)) for k in METRICAS]
                    sequencia = " ".join(valores)
                    if sequencia not in secao_teste:
                        raise ValueError(f"Metricas ausentes do PDF: {tarefa}, {m['horizonte']}, {valores}.")
                    secao_teste = secao_teste.replace(sequencia, "", 1)
                    resultado["metricas_novas_conferidas"] += len(METRICAS)
            if f"{i + 1}/8" not in text:
                raise ValueError(f"Rodape incorreto na pagina {i + 1}.")
    resultado["aprovado"] = True
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experimento", type=Path, default=RAIZ / "resultados/quantizacao_timesnet_resolucoes_20260927")
    parser.add_argument("--benchmark", type=Path, default=RAIZ / "resultados/avaliacao_multirresolucao_corrigida_v2")
    parser.add_argument("--base", type=Path, default=RAIZ / "relatorios/quantizacao_timesnet_quatro_casos_20260927/fonte_6_paginas.pdf")
    parser.add_argument("--saida", type=Path, default=RAIZ / "tmp/pdfs/quantizacao_quatro_casos_20260927.pdf")
    parser.add_argument("--pasta-auditoria", type=Path, default=RAIZ / "relatorios/quantizacao_timesnet_quatro_casos_20260927")
    parser.add_argument("--somente-validar", action="store_true")
    args = parser.parse_args()
    dados = montar_dados(args.experimento, args.benchmark)
    if args.somente_validar:
        for tarefa, info in dados["tarefas"].items():
            print(tarefa, "selecionada:", info["vencedor"])
        return
    from pypdf import PdfReader
    if not args.base.is_file() or len(PdfReader(str(args.base)).pages) != 6:
        raise ValueError("O backup de seis paginas deve existir antes da geracao.")
    dados["pdf_original"] = {"path": str(args.base.resolve()), "sha256": sha256(args.base)}
    escrever_pdf(dados, args.base, args.saida)
    dados["verificacao_pdf"] = verificar_pdf(args.base, args.saida, dados)
    args.pasta_auditoria.mkdir(parents=True, exist_ok=True)
    metricas, ranking, clipping = [], [], []
    for tarefa, info in dados["tarefas"].items():
        ranking.extend({"tarefa": tarefa, "posicao": i, **r} for i, r in enumerate(info["ranking"], 1))
        for nome, variante in info["variantes"].items():
            metricas.extend({"tarefa": tarefa, "variante": nome, "niveis": variante["niveis"],
                             "selecionada": nome == info["vencedor"], **r} for r in variante["metricas"])
            clipping.extend({"tarefa": tarefa, "variante": nome, "fase": fase, **r}
                            for fase, r in variante["diagnosticos"].items())
    for nome, linhas in (("metricas_teste_2024.csv", metricas), ("ranking_validacao_2023.csv", ranking),
                         ("clipping_por_fase.csv", clipping)):
        p = args.pasta_auditoria / nome
        pd.DataFrame(linhas).to_csv(p, index=False)
        dados.setdefault("tabelas", []).append({"path": str(p.resolve()), "sha256": sha256(p)})
    dados["pdf"] = {"path": str(args.saida.resolve()), "sha256": sha256(args.saida), "paginas": 8}
    (args.pasta_auditoria / "manifesto_pdf.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(args.saida.resolve())


if __name__ == "__main__":
    main()
