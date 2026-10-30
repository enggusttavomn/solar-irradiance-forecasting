"""Apendice auditavel da quantizacao de entrada da TimesNet mensal.

Preserva as quatro paginas existentes e acrescenta duas paginas de resultados.
O CLI so permite publicar apos conferir os quatro niveis de ambas as tarefas.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from codigo_fonte.analises_e_relatorios.gerar_tabela_resultados_ghi_otimizada import CHAVES, METRICAS, calcular_macro, conferir_observacoes, normalizar_chaves, numero, sha256

TAREFAS = {"monthly_1": (1,), "monthly_6": (1, 3, 6)}
VARIANTES = {"sem_quantizacao": None, "q64": 64, "q128": 128, "q256": 256}
SEMENTES = [11, 23, 42, 67, 89]
COLUNA_PREVISAO = "previsao_pos_timesnet_ensemble_wm2"
ROTULOS = {"sem_quantizacao": "Sem quantiza\u00e7\u00e3o",
           "q64": "64 n\u00edveis", "q128": "128 n\u00edveis", "q256": "256 n\u00edveis"}


def escrever_apendices(relatorio: dict, destino) -> None:
    """Desenha duas paginas a partir de dados previamente validados."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph, Table, TableStyle

    c = canvas.Canvas(destino if hasattr(destino, "write") else str(destino), pagesize=A4)
    largura, altura = A4
    margem = 35
    util = largura - 2 * margem
    texto = colors.HexColor("#142435")
    azul = colors.HexColor("#edf4fb")
    cinza = colors.HexColor("#596773")
    nota = ParagraphStyle("quant-nota", fontName="Times-Roman", fontSize=9,
                          leading=11.1, textColor=texto)
    pequena = ParagraphStyle("quant-pequena", parent=nota, fontSize=8, leading=9.7)

    def paragrafo(txt, y, estilo=nota):
        p = Paragraph(txt, estilo)
        _, h = p.wrap(util, altura)
        p.drawOn(c, margem, y - h)
        return y - h

    def titulo(txt, y):
        c.setFillColor(texto)
        c.setFont("Times-Bold", 11)
        c.drawString(margem, y - 11, txt)
        return y - 19

    def tabela(linhas, larguras, y, selecionadas=(), divisorias=(), fonte=8.8):
        comandos = [
            ("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
            ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), fonte),
            ("LEADING", (0, 0), (-1, -1), fonte + 1.3),
            ("TEXTCOLOR", (0, 0), (-1, -1), texto),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEABOVE", (0, 0), (-1, 0), 0.7, colors.black),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEBELOW", (0, -1), (-1, -1), 0.7, colors.black),
        ]
        for row in selecionadas:
            comandos.extend([("BACKGROUND", (0, row), (-1, row), azul),
                             ("FONTNAME", (0, row), (-1, row), "Times-Bold")])
        for row in divisorias:
            comandos.append(("LINEABOVE", (0, row), (-1, row), .3, colors.HexColor("#adb7c0")))
        tab = Table(linhas, colWidths=larguras)
        tab.setStyle(TableStyle(comandos))
        _, h = tab.wrap(util, altura)
        tab.drawOn(c, margem, y - h)
        return y - h - 8

    for numero_pagina, (tarefa, horizontes) in enumerate(TAREFAS.items(), 5):
        info = relatorio["tarefas"][tarefa]
        config = info["hiperparametros"]
        vencedor = info["vencedor"]
        y = altura - 31
        c.setFillColor(texto)
        c.setFont("Times-Roman", 9)
        c.drawString(margem, y, "Previs\u00e3o de GHI | ap\u00eandice de quantiza\u00e7\u00e3o da entrada")
        y -= 23
        c.setFont("Times-Bold", 18)
        c.drawString(margem, y, "TimesNet mensal - " + ("1 m\u00eas" if tarefa == "monthly_1" else "at\u00e9 6 meses"))
        y -= 13
        passos = max(horizontes)
        origens = info["N_origens_por_local"]
        resumo = (f"Hist\u00f3rico: {config['seq_len']} meses. Previs\u00e3o direta de {passos} "
                  + ("m\u00eas" if passos == 1 else "meses")
                  + f"; {origens} origens de teste por localidade. Ensemble de cinco sementes: 11, 23, 42, 67 e 89.")
        y = paragrafo(resumo, y) - 5
        parametros = (f"Hiperpar\u00e2metros fixos: d_model={config['d_model']}; d_ff={config['d_ff']}; "
                      f"blocos={config['blocos']}; dropout={numero(config['dropout'], 1)}; "
                      f"taxa de aprendizado={numero(config['taxa_aprendizado'], 4)}; perda={escape(config['perda'].upper())}. "
                      f"Teto de {info['max_epocas']} \u00e9pocas; paci\u00eancia {info['paciencia']}; execu\u00e7\u00e3o em CPU. Todas as variantes, incluindo o controle, s\u00e3o treinadas novamente.")
        y = paragrafo(parametros, y, pequena) - 8
        y = titulo("1. Escolha da entrada pela valida\u00e7\u00e3o de 2023", y)
        linhas = [["Pos.", "Entrada da TimesNet", "MAE 2023 (W/m\u00b2)", "\u00c9pocas por semente (11 / 23 / 42 / 67 / 89)"]]
        for posicao, variante in enumerate(info["ranking"], 1):
            epocas = " / ".join(str(variante["epocas"][str(s)]) for s in SEMENTES)
            linhas.append([str(posicao), ROTULOS[variante["nome"]], numero(variante["MAE_validacao_wm2"], 4), epocas])
        y = tabela(linhas, [25, 137, 113, util - 275], y, selecionadas=(1,), fonte=8.7)
        y = paragrafo("Azul: variante escolhida pelo menor MAE f\u00edsico do ensemble em 2023, "
                      "com sele\u00e7\u00e3o congelada antes da avalia\u00e7\u00e3o deste experimento em 2024.", y, pequena) - 7
        y = titulo("2. Teste de 2024 - todas as variantes", y)
        linhas = [["Horizonte", "Entrada", "MAE\n(W/m\u00b2)", "MSE\n((W/m\u00b2)\u00b2)",
                   "RMSE\n(W/m\u00b2)", "nRMSE\n(%)", "R\u00b2"]]
        selecionadas, divisorias = [], []
        for horizonte in horizontes:
            if len(linhas) > 1:
                divisorias.append(len(linhas))
            for index, nome in enumerate(VARIANTES):
                metrica = next(m for m in info["variantes"][nome]["metricas"] if m["horizonte"] == horizonte)
                if nome == vencedor:
                    selecionadas.append(len(linhas))
                rotulo = "Sem quant." if nome == "sem_quantizacao" else str(VARIANTES[nome])
                unidade = "m\u00eas" if horizonte == 1 else "meses"
                vals = [numero(metrica[col] * (100 if col == "nRMSE" else 1), 4 if col == "MAE_wm2" else (3 if col == "R2" else 2))
                        for col in METRICAS]
                linhas.append([f"1-{horizonte} {unidade}" if index == 0 and horizonte > 1 else
                               (f"1 {unidade}" if index == 0 else ""), rotulo, *vals])
        y = tabela(linhas, [59, 57, 79, 98, 81, 78, util - 452], y,
                   selecionadas=selecionadas, divisorias=divisorias)
        y = titulo("3. Clipping das entradas normalizadas em [0, 1]", y)
        linhas = [["Fase", "Abaixo de 0", "Acima de 1", "Total de valores de entrada", "Valores fora da faixa (%)"]]
        for fase, rotulo in (("ajuste", "Ajuste at\u00e9 2022"), ("validacao", "Valida\u00e7\u00e3o 2023"),
                             ("refit", "Reajuste at\u00e9 2023"), ("teste", "Teste 2024")):
            clip = info["clipping"][fase]
            linhas.append([rotulo, str(clip["abaixo_zero"]), str(clip["acima_um"]),
                           str(clip["total"]), numero(100 * (clip["abaixo_zero"] + clip["acima_um"]) / clip["total"], 3)])
        y = tabela(linhas, [102, 71, 69, 141, util - 383], y, fonte=8)
        y = paragrafo("Contagens por valor em janela, antes do clipping, comuns aos tr\u00eas n\u00edveis quantizados; "
                      "janelas sobrepostas repetem valores. O controle conserva o min-max cont\u00ednuo, sem clipping adicional. A compara\u00e7\u00e3o inclui o efeito da satura\u00e7\u00e3o.", y, pequena) - 6
        metodologia = ("<b>Protocolo.</b> Min-max por localidade preservado: ajuste at\u00e9 2022 para a sele\u00e7\u00e3o; "
                       "reajuste at\u00e9 2023 para o teste. Quantiza\u00e7\u00e3o uniforme somente das entradas: "
                       "rint(clip(x, 0, 1) \u00d7 (L - 1)) / (L - 1), com empates para inteiro par. Alvos GHI cont\u00ednuos; pesos do modelo "
                       "n\u00e3o quantizados. GHI previsto diretamente, sem climatologia. M\u00e9tricas em escala f\u00edsica "
                       "ap\u00f3s invers\u00e3o do min-max e limite inferior zero nas previs\u00f5es.")
        y = paragrafo(metodologia, y, pequena) - 5
        nota_metricas = ("<b>Leitura.</b> M\u00e9dia aritm\u00e9tica das m\u00e9tricas por localidade (10 locais, NSRDB). "
                         "MSE e RMSE agregados separadamente; nRMSE = RMSE/m\u00e9dia observada por local. "
                         "Horizontes cumulativos incluem todos os passos at\u00e9 o limite. "
                         "As quatro p\u00e1ginas anteriores preservam integralmente os valores j\u00e1 publicados.")
        y = paragrafo(nota_metricas, y, pequena) - 5
        y = paragrafo("<b>Limite da evid\u00eancia.</b> Compara\u00e7\u00e3o retrospectiva e explorat\u00f3ria: "
                      "2024 j\u00e1 havia sido consultado e os hiperpar\u00e2metros foram fixados a partir da busca anterior. "
                      "O teste de 2024 n\u00e3o escolhe o n\u00edvel. Confirma\u00e7\u00e3o exige outro per\u00edodo.", y, pequena)
        if y < 29:
            raise ValueError(f"Conteudo excedeu a area util da pagina: {tarefa}, y={y:.1f}")
        c.setFillColor(cinza)
        c.setFont("Times-Roman", 8)
        c.drawString(margem, 16, "Fontes, hashes e m\u00e9tricas sem arredondamento acompanham a gera\u00e7\u00e3o na pasta de auditoria.")
        c.drawRightString(largura - margem, 16, f"{numero_pagina}/6")
        c.showPage()
    c.save()


def escrever_pdf(relatorio: dict, fonte: Path, destino: Path) -> None:
    """Mantem as paginas de origem e altera somente o denominador do rodape."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    origem = PdfReader(str(fonte))
    if len(origem.pages) != 4:
        raise ValueError("O PDF fonte deve conter exatamente as quatro paginas originais.")
    escritor = PdfWriter()
    for numero_pagina, pagina in enumerate(origem.pages, 1):
        largura, altura = float(pagina.mediabox.width), float(pagina.mediabox.height)
        overlay = BytesIO()
        c = canvas.Canvas(overlay, pagesize=(largura, altura))
        c.setFillColor(colors.white)
        c.rect(largura - 56, 13, 23, 11, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#596773"))
        c.setFont("Times-Roman", 8)
        c.drawRightString(largura - 35, 16, f"{numero_pagina}/6")
        c.save()
        overlay.seek(0)
        pagina.merge_page(PdfReader(overlay).pages[0])
        escritor.add_page(pagina)
    apendice = BytesIO()
    escrever_apendices(relatorio, apendice)
    apendice.seek(0)
    for pagina in PdfReader(apendice).pages:
        escritor.add_page(pagina)
    escritor.add_metadata({"/Title": "Previsao de GHI - teste 2024 e quantizacao da entrada TimesNet",
                           "/Author": "Projeto TCC - previsao de GHI"})
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("wb") as stream:
        escritor.write(stream)
    if len(PdfReader(str(destino)).pages) != 6:
        raise ValueError("O PDF atualizado deve conter seis paginas.")

def ler_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validar_metadados(tarefa: str, contrato: dict, selecao: dict, status: dict) -> None:
    """Recusa execucao parcial, hibrida, smoke ou sem congelamento previo."""
    if (status.get("etapa") != "concluida" or status.get("modo") != "completa"
            or status.get("teste_avaliado") is not True):
        raise ValueError(f"Experimento incompleto ou smoke: {tarefa}")
    if (contrato.get("tarefa", {}).get("slug") != tarefa or selecao.get("tarefa") != tarefa
            or status.get("tarefa") != tarefa):
        raise ValueError(f"Tarefa incoerente: {tarefa}")
    q = contrato.get("quantizacao", {})
    config = contrato.get("configuracao", {})
    candidato = contrato.get("candidato_base", {})
    if (contrato.get("minmax") is not True or q.get("onde") != "somente_entradas"
            or q.get("alvos_quantizados") is not False or q.get("pesos_quantizados") is not False
            or q.get("controle") != "sem_quantizacao_e_sem_clip" or q.get("intervalo") != [0, 1]
            or q.get("niveis") != [64, 128, 256] or candidato.get("alvo") != "bruto"
            or contrato.get("regressao") != "continua"):
        raise ValueError(f"Protocolo minmax/entrada/alvo continuo incoerente: {tarefa}")
    variantes = contrato.get("variantes", [])
    if (len(variantes) != 4 or {r["nome"]: r["niveis"] for r in variantes} != VARIANTES
            or config.get("sementes") != SEMENTES or config.get("modo_execucao") != "completa"
            or config.get("max_epocas_mensal") != 300 or config.get("paciencia_mensal") != 30
            or contrato.get("dispositivo") != "cpu"):
        raise ValueError(f"Variantes, sementes ou configuracao congelada incoerentes: {tarefa}")
    if (selecao.get("selecao_concluida_antes_do_teste") is not True
            or selecao.get("modo") != "completa"
            or selecao.get("contrato_sha256") != contrato.get("sha256_contrato")):
        raise ValueError(f"Selecao nao congelada no contrato: {tarefa}")
    corpo = {k: v for k, v in contrato.items() if k != "sha256_contrato"}
    digest = hashlib.sha256(json.dumps(corpo, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()
    if digest != contrato.get("sha256_contrato"):
        raise ValueError(f"Hash do contrato inconsistente: {tarefa}")
    ranking = selecao.get("ranking", [])
    if len(ranking) != 4 or {r["nome"]: r["niveis"] for r in ranking} != VARIANTES:
        raise ValueError(f"Ranking deve conter exatamente os quatro niveis: {tarefa}")
    for linha in ranking:
        epocas = linha.get("epocas", {})
        if (set(epocas) != {str(s) for s in SEMENTES}
                or any(not isinstance(e, int) or isinstance(e, bool) or not 1 <= e <= 300 for e in epocas.values())
                or not np.isfinite(linha["MAE_validacao_wm2"])):
            raise ValueError(f"Ranking com sementes/epocas/MAE invalidos: {tarefa}")
    ordem = {nome: i for i, nome in enumerate(VARIANTES)}
    esperado = sorted(ranking, key=lambda r: (r["MAE_validacao_wm2"], ordem[r["nome"]]))
    if (ranking != esperado or selecao.get("vencedor") != esperado[0]
            or status.get("vencedor") != esperado[0]):
        raise ValueError(f"Vencedor/ranking nao corresponde ao MAE de validacao: {tarefa}")


def validar_previsoes(df: pd.DataFrame, tarefa: str, ano: int) -> pd.DataFrame:
    """Confere periodo, amostra e media de cinco sementes em escala fisica."""
    df = normalizar_chaves(df)
    pred_len = max(TAREFAS[tarefa])
    n_origens = 12 if tarefa == "monthly_1" else 7
    if (df.localidade.nunique() != 10 or len(df) != 10 * n_origens * pred_len
            or not (df.data_alvo.dt.year == ano).all() or not (df.origem.dt.year == ano).all()
            or set(df.passo) != set(range(1, pred_len + 1))):
        raise ValueError(f"Amostra/periodo incompleto: {tarefa}, {ano}")
    for _, grupo in df.groupby("localidade"):
        if grupo.origem.nunique() != n_origens or len(grupo) != n_origens * pred_len:
            raise ValueError(f"Origens por localidade inconsistentes: {tarefa}, {ano}")
    if not (df.groupby(["localidade", "origem"]).size() == pred_len).all():
        raise ValueError(f"Horizonte incompleto em alguma origem: {tarefa}, {ano}")
    brutas = [f"previsao_bruta_timesnet_seed{s}_wm2" for s in SEMENTES]
    pos = [f"previsao_pos_timesnet_seed{s}_wm2" for s in SEMENTES]
    cols = ["ghi_real_wm2", *brutas, *pos, "previsao_bruta_timesnet_ensemble_wm2", COLUNA_PREVISAO]
    if not np.isfinite(df[cols].to_numpy(dtype=float)).all():
        raise ValueError("Previsoes ou alvos nao finitos.")
    media = df[brutas].mean(axis=1).to_numpy(dtype=float)
    if (not np.allclose(df.previsao_bruta_timesnet_ensemble_wm2, media, atol=1e-7, rtol=0)
            or not np.allclose(df[COLUNA_PREVISAO], np.maximum(media, 0), atol=1e-7, rtol=0)
            or not np.allclose(df[pos], np.maximum(df[brutas].to_numpy(), 0), atol=1e-7, rtol=0)):
        raise ValueError("Ensemble ou pos-processamento inconsistente com as cinco sementes.")
    return df


def conferir_macro(salvas: pd.DataFrame, calculadas: pd.DataFrame, tarefa: str, particao: str) -> None:
    recorte = salvas[(salvas.tarefa == tarefa) & (salvas.particao == particao)
                    & (salvas.modelo == "TimesNet") & (salvas.tipo_estimativa == "ensemble")
                    & (salvas.tipo_horizonte == "cumulativo")]
    if recorte.horizonte.duplicated().any() or set(recorte.horizonte) != set(TAREFAS[tarefa]):
        raise ValueError(f"Metricas ensemble incompletas: {tarefa}, {particao}")
    salvas_indice = recorte.set_index("horizonte")
    for linha in calculadas.to_dict(orient="records"):
        for campo in ("MAE_wm2", "RMSE_wm2", "nRMSE", "R2", "N_localidades", "N_origens", "N_pontos"):
            if not np.isclose(linha[campo], salvas_indice.loc[linha["horizonte"], campo], atol=1e-7, rtol=1e-9):
                raise ValueError(f"Metrica difere das previsoes: {tarefa}, {particao}, {campo}")


def conferir_hashes(mapa: dict, fontes: set[Path]) -> None:
    if not mapa:
        raise ValueError("Manifesto de hashes vazio.")
    for caminho, digest in mapa.items():
        p = Path(caminho).resolve()
        if not p.is_file() or sha256(p) != digest:
            raise ValueError(f"Fonte ausente ou alterada: {p}")
        fontes.add(p)


def validar_diagnostico(diagnostico: dict, niveis, esperado_total: int) -> dict:
    total = diagnostico["total"]
    campos = ("total", "abaixo_zero", "acima_um", "saturados")
    if (any(not isinstance(total[c], int) or isinstance(total[c], bool) or total[c] < 0 for c in campos)
            or total["total"] != esperado_total or total["niveis"] != niveis):
        raise ValueError("Diagnostico de quantizacao incompleto ou inconsistente.")
    fora = total["abaixo_zero"] + total["acima_um"]
    if (fora > total["total"] or total["saturados"] != (fora if niveis is not None else 0)
            or not np.isclose(total["fracao_saturados"], total["saturados"] / total["total"], atol=1e-12)):
        raise ValueError("Contagem de clipping inconsistente.")
    locais = [v for k, v in diagnostico.items() if k != "total"]
    if len(locais) != 10 or any(sum(v[c] for v in locais) != total[c] for c in campos):
        raise ValueError("Diagnostico exige as dez localidades e soma consistente.")
    return total


def montar_dados(experimento: Path, benchmark: Path) -> dict:
    fontes = {Path(__file__).resolve(), (Path(__file__).parents[2] / 'codigo_fonte/analises_e_relatorios/gerar_tabela_resultados_ghi_otimizada.py').resolve()}
    global_path = experimento / "selecao_global_congelada.json"
    global_ = ler_json(global_path)
    if set(global_.get("tarefas", [])) != set(TAREFAS):
        raise ValueError("Congelamento global deve incluir as duas tarefas mensais.")
    conferir_hashes(global_["fontes_selecao_sha256"], fontes)
    fontes.add(global_path.resolve())
    relatorio = {"criado_em_utc": datetime.now(timezone.utc).isoformat(), "tarefas": {}}
    for tarefa, horizontes in TAREFAS.items():
        pasta = experimento / tarefa
        contrato_path, selecao_path, status_path = [pasta / n for n in
            ("contrato_execucao.json", "selecao_congelada.json", "status_execucao.json")]
        contrato, selecao, status = [ler_json(p) for p in (contrato_path, selecao_path, status_path)]
        fontes.update(p.resolve() for p in (contrato_path, selecao_path, status_path))
        validar_metadados(tarefa, contrato, selecao, status)
        for campo in ("codigo_sha256", "entradas_sha256", "fontes_configuracao"):
            conferir_hashes(contrato[campo], fontes)
        manifesto_path = pasta / "manifesto_artefatos.json"
        manifesto = ler_json(manifesto_path)
        conferir_hashes({str(pasta / r["arquivo"]): r["sha256"] for r in manifesto["arquivos"]}, fontes)
        fontes.add(manifesto_path.resolve())
        canonicas_path = benchmark / tarefa / "previsoes_teste.csv.gz"
        canonicas = pd.read_csv(canonicas_path, usecols=lambda c: c in set(CHAVES) | {"ghi_real_wm2"})
        fontes.add(canonicas_path.resolve())
        ranking = selecao["ranking"]
        por_nome = {r["nome"]: r for r in ranking}
        info = {"hiperparametros": contrato["candidato_base"], "max_epocas": contrato["configuracao"]["max_epocas_mensal"],
                "paciencia": contrato["configuracao"]["paciencia_mensal"], "ranking": ranking,
                "vencedor": selecao["vencedor"]["nome"], "N_origens_por_local": 12 if tarefa == "monthly_1" else 7,
                "variantes": {}, "clipping": {}, "contrato": contrato, "selecao": selecao}
        referencia_validacao = None
        for nome, niveis in VARIANTES.items():
            variante = pasta / "variantes" / nome
            estado = ler_json(variante / "status_execucao.json")
            if (estado.get("etapa") != "concluida" or estado.get("modo") != "completa"
                    or estado.get("nome") != nome or estado.get("niveis") != niveis
                    or estado.get("selecionada") is not (nome == info["vencedor"])):
                raise ValueError(f"Variante incompleta/incoerente: {tarefa}, {nome}")
            teste = validar_previsoes(pd.read_csv(variante / "previsoes_teste.csv"), tarefa, 2024)
            validacao = validar_previsoes(pd.read_csv(variante / "previsoes_validacao.csv"), tarefa, 2023)
            conferir_observacoes(teste, canonicas)
            if referencia_validacao is not None:
                conferir_observacoes(validacao, referencia_validacao)
            referencia_validacao = validacao
            met_test = calcular_macro(teste, COLUNA_PREVISAO, horizontes)
            met_val = calcular_macro(validacao, COLUNA_PREVISAO, horizontes)
            conferir_macro(pd.read_csv(variante / "metricas_macro.csv"), met_test, tarefa, "teste_2024")
            conferir_macro(pd.read_csv(variante / "metricas_macro_validacao.csv"), met_val, tarefa, "validacao_2023")
            mae_val = float(met_val.loc[met_val.horizonte == max(horizontes), "MAE_wm2"].iloc[0])
            mae_test = float(met_test.loc[met_test.horizonte == max(horizontes), "MAE_wm2"].iloc[0])
            if (not np.isclose(mae_val, por_nome[nome]["MAE_validacao_wm2"], atol=1e-7, rtol=0)
                    or not np.isclose(mae_val, estado["MAE_validacao_wm2"], atol=1e-7, rtol=0)
                    or not np.isclose(mae_test, estado["MAE_teste_wm2"], atol=1e-7, rtol=0)):
                raise ValueError(f"MAE de selecao/teste difere das previsoes: {tarefa}, {nome}")
            diag = {**ler_json(variante / "diagnostico_selecao.json"), **ler_json(variante / "diagnostico_refit.json")}
            diags = {}
            for fase in ("ajuste", "validacao", "refit", "teste"):
                n = contrato["tarefa"][fase]["origens_esperadas_por_localidade"] * 10 * contrato["candidato_base"]["seq_len"]
                diags[fase] = validar_diagnostico(diag[fase], niveis, n)
                if nome == "q64":
                    info["clipping"][fase] = diags[fase]
                elif nome in {"q128", "q256"}:
                    if any(diags[fase][c] != info["clipping"][fase][c] for c in ("total", "abaixo_zero", "acima_um", "saturados")):
                        raise ValueError("Clipping deveria ter mesmas contagens nos tres niveis.")
            info["variantes"][nome] = {"niveis": niveis, "metricas": met_test.to_dict(orient="records"),
                                      "metricas_validacao": met_val.to_dict(orient="records"), "diagnosticos": diags}
        relatorio["tarefas"][tarefa] = info
    relatorio["fontes"] = [{"path": str(p), "sha256": sha256(p)} for p in sorted(fontes, key=str)]
    return relatorio


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experimento", type=Path, default=RAIZ / "resultados/quantizacao_timesnet_mensal_20260923")
    parser.add_argument("--benchmark", type=Path, default=RAIZ / "resultados/avaliacao_baselines_revisao_20260912/consolidado")
    parser.add_argument("--base", type=Path, default=RAIZ / "documentacao/tabela_resultados_ghi_2024.pdf")
    parser.add_argument("--saida", type=Path, default=RAIZ / "tmp/pdfs/timesnet_quantizacao_20260923.pdf")
    parser.add_argument("--pasta-auditoria", type=Path, default=RAIZ / "resultados/relatorios/quantizacao_timesnet_20260923")
    parser.add_argument("--somente-validar", action="store_true")
    args = parser.parse_args()
    dados = montar_dados(args.experimento, args.benchmark)
    if args.somente_validar:
        for tarefa, info in dados["tarefas"].items():
            print(tarefa, "selecionada:", info["vencedor"])
        return
    from pypdf import PdfReader
    args.pasta_auditoria.mkdir(parents=True, exist_ok=True)
    backup = args.pasta_auditoria / "fonte_4_paginas.pdf"
    if not backup.exists():
        if len(PdfReader(str(args.base)).pages) != 4:
            raise ValueError("A fonte inicial deve possuir quatro paginas antes do backup.")
        shutil.copy2(args.base, backup)
    if len(PdfReader(str(backup)).pages) != 4:
        raise ValueError("Backup invalido; nao sera sobrescrito.")
    if args.saida.resolve() == backup.resolve():
        raise ValueError("A saida nao pode sobrescrever o backup original.")
    dados["pdf_original"] = {"path": str(backup.resolve()), "sha256": sha256(backup)}
    escrever_pdf(dados, backup, args.saida)
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
    dados["pdf"] = {"path": str(args.saida.resolve()), "sha256": sha256(args.saida), "paginas": 6}
    (args.pasta_auditoria / "manifesto_pdf.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(args.saida.resolve())


if __name__ == "__main__":
    main()