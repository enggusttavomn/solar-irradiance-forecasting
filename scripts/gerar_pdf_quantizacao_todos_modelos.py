"""Gera tabelas por nivel apenas a partir de auditorias completas aprovadas.

Executar o marcador da habilidade PDF antes da primeira autoria. A entrega
do arquivo final exige tambem renderizacao e inspecao visual independente.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.metricas_quantizacao_todos import MODELOS, TAREFAS, VARIANTES, METRICAS, sha256

RAIZ = Path(__file__).resolve().parents[1]
ROTULOS = {"hourly_72_extension": "Horário", "daily_30": "Diário",
           "monthly_1": "Mensal de um mês", "monthly_6": "Mensal exploratório de seis meses"}
NIVEIS = {"sem_quantizacao": "Sem quantização", "q64": "64 níveis", "q128": "128 níveis", "q256": "256 níveis"}
UNIDADES = {"hourly_72_extension": "h", "daily_30": "d", "monthly_1": "mês", "monthly_6": "meses"}
REGIMES = {"atual": "Base 2019-2024", "historico_1998_2022": "Histórico longo 1998-2022",
           "historico_curto_pareado": "Histórico curto pareado - início em abril de 2014"}


def caminho_pdf_logico(path):
    """Canonicaliza o diretorio sem resolver a folha PDF protegida pelo provedor."""
    path = Path(path)
    if path.suffix.casefold() != '.pdf':
        raise ValueError('O artefato deve usar um caminho logico com extensao .pdf.')
    return path.parent.resolve() / path.name


def numero(valor, casas=4):
    return "-" if not np.isfinite(valor) else f"{valor:,.{casas}f}".replace(",", " ").replace(".", ",")


def carregar_auditoria(path):
    a = json.loads(Path(path).read_text(encoding="utf-8"))
    if not (a.get("ok") is True and a.get("publicavel") is True and a.get("escopo_completo") is True
            and a.get("modo") == "completa" and a.get("replay_novo_executado") is True):
        raise ValueError(f"Auditoria incompleta, smoke ou sem replay: {path}")
    for fonte, digest in a.get('fontes_controles_suplementares_sha256', {}).items():
        if sha256(Path(fonte)) != digest:
            raise ValueError('Fonte do controle complementar alterada depois da auditoria.')
    metricas_path = Path(a["metricas"]["path"])
    if sha256(metricas_path) != a["metricas"]["sha256"]:
        raise ValueError("Metricas alteradas depois da auditoria.")
    df = pd.read_csv(metricas_path)
    chaves = ["tarefa", "modelo", "variante", "particao", "horizonte"]
    if df.duplicated(chaves).any() or set(df.regime) != {a["regime"]}:
        raise ValueError("Metricas duplicadas ou com regime incorreto.")
    esperado = {(t,m,v,p,h) for t,hs in TAREFAS.items() for m in MODELOS
                for v in VARIANTES for p in ("validacao", "teste") for h in hs}
    if set(df[chaves].itertuples(index=False, name=None)) != esperado:
        raise ValueError("Grade de modelos, niveis, tarefas ou horizontes incompleta.")
    if (df.N_localidades != 10).any() or not np.isfinite(df[["MAE_wm2", "MSE_w2m4", "RMSE_wm2", "nRMSE"]]).all().all():
        raise ValueError("Metricas invalidas ou localidades incompletas.")
    registros = a.get("resultados", [])
    pares_esperados = {(t, m) for t in TAREFAS for m in MODELOS}
    pares = [(r.get("tarefa"), r.get("modelo")) for r in registros]
    if (len(pares) != len(pares_esperados) or set(pares) != pares_esperados
            or not all(r.get("ok") is True for r in registros)):
        raise ValueError("Auditoria sem todos os pares tarefa/modelo unicos e aprovados.")
    if any(r.get("vencedor_validacao") not in VARIANTES for r in registros):
        raise ValueError("Escolha da validacao ausente ou invalida.")
    return a, df


def validar_pareamento(path, auditorias):
    par = json.loads(Path(path).read_text(encoding="utf-8"))
    registros = par.get("resultados", [])
    esperado = {(t, p) for t in TAREFAS for p in ("validacao", "teste")}
    if (par.get("ok") is not True or par.get("publicavel") is not True
            or len(registros) != len(esperado)
            or {(r.get("tarefa"), r.get("particao")) for r in registros} != esperado
            or not all(r.get("observacoes_e_datas_iguais") is True for r in registros)):
        raise ValueError("Auditoria pareada incompleta ou com amostras diferentes.")
    for p, digest in par["fontes_sha256"].items():
        if sha256(Path(p)) != digest:
            raise ValueError("Fonte do pareamento foi alterada.")
    if any(str(Path(p).resolve()) not in par["fontes_sha256"] for p in auditorias):
        raise ValueError("Pareamento de outros experimentos.")
    return par


def fontes_relatorio(diretorio_windows=None):
    """Prefere Arial e usa o par Vera distribuido pelo ReportLab como reserva."""
    import reportlab

    diretorio_windows = (Path(diretorio_windows) if diretorio_windows is not None
                         else Path("C:/Windows/Fonts"))
    arial = (diretorio_windows / "arial.ttf", diretorio_windows / "arialbd.ttf")
    if all(fonte.is_file() for fonte in arial):
        return arial
    diretorio_pacote = Path(reportlab.__file__).resolve().parent / "fonts"
    return diretorio_pacote / "Vera.ttf", diretorio_pacote / "VeraBd.ttf"


def gerar(auditorias, saida, manifesto, pareamento=None):
    saida = caminho_pdf_logico(saida)
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

    carregadas = [carregar_auditoria(p) for p in auditorias]
    regimes = [a["regime"] for a, _ in carregadas]
    if len(set(regimes)) != len(regimes):
        raise ValueError("Regime repetido.")
    if "atual" in regimes and len(regimes) != 1:
        raise ValueError("A base atual tem PDF separado do estudo historico.")
    if "atual" not in regimes and set(regimes) != {"historico_1998_2022", "historico_curto_pareado"}:
        raise ValueError("PDF historico exige os dois historicos pareados auditados.")
    if "atual" not in regimes:
        if pareamento is None:
            raise ValueError("PDF historico exige auditoria pareada das mesmas observacoes.")
        validar_pareamento(pareamento, auditorias)
    fonte, fonte_bold = fontes_relatorio()
    pdfmetrics.registerFont(TTFont("Relatorio", str(fonte)))
    pdfmetrics.registerFont(TTFont("RelatorioBold", str(fonte_bold)))
    pdfmetrics.registerFontFamily("Relatorio", normal="Relatorio", bold="RelatorioBold",
                                  italic="Relatorio", boldItalic="RelatorioBold")
    largura, altura = landscape(A4)
    margem = 34
    util = largura - 2 * margem
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("CorpoGHI", fontName="Relatorio", fontSize=10, leading=14, spaceAfter=9))
    styles.add(ParagraphStyle("TituloGHI", fontName="RelatorioBold", fontSize=21, leading=26, spaceAfter=16,
                              textColor=colors.HexColor("#172D45")))
    styles.add(ParagraphStyle("SubtituloGHI", fontName="RelatorioBold", fontSize=13, leading=17, spaceAfter=9))
    styles.add(ParagraphStyle("NotaGHI", fontName="Relatorio", fontSize=8.4, leading=11, spaceAfter=7))
    styles.add(ParagraphStyle("CelulaGHI", fontName="Relatorio", fontSize=8.2, leading=10))
    corpo, titulo, subtitulo, nota = (styles[x] for x in ("CorpoGHI", "TituloGHI", "SubtituloGHI", "NotaGHI"))
    story = []
    P = lambda txt, sty=corpo: Paragraph(txt, sty)
    story.append(P("Quantização de GHI<br/>Comparação de todos os modelos", titulo))
    story.append(P("Teste de 2024 - base 2019-2024" if regimes == ["atual"] else
                   "Estudo histórico 1998-2022 e comparação pareada", subtitulo))
    story.append(P("Quatro casos, onze modelos e quatro condições de entrada: min-max sem quantização, "
                   "64, 128 e 256 níveis. As tabelas agrupam todos os modelos por nível, mantendo os mesmos "
                   "alvos e origens de previsão dentro de cada caso."))
    if regimes == ["atual"]:
        story.append(P("<b>Divisão temporal.</b> Ajuste com dados anteriores a 2023; validação em 2023; "
                       "treinamento final com dados até 2023; teste em 2024. As escolhas usam a validação. "
                       "O teste de 2024 já havia sido consultado em estudos anteriores; esta avaliação é retrospectiva."))
        story.append(P("<b>Controles.</b> A TimesNet pura otimizada reutiliza os experimentos completos previamente auditados. "
                       "Os concorrentes têm seus próprios controles. LSTM, GRU e DilatedRNN nos casos horário e diário "
                       "usam novos controles na GPU, no mesmo dispositivo das variantes quantizadas. A climatologia horária "
                       "foi acrescentada nesta etapa. O ARIMA horário utiliza um novo controle de validação reproduzido "
                       "e auditado; a pequena divergência numérica frente ao ajuste histórico está documentada."))
        if any(r.get('controle_teste_suplementar') for r in carregadas[0][0]['resultados']):
            story.append(P('<b>XGBoost horário.</b> O treinamento final utiliza um novo controle sem quantização, '
                           'repetido integralmente e auditado. A execução antiga apresentou divergência cuja causa '
                           'não foi identificada. A seleção dos níveis permaneceu congelada; as variantes são '
                           'comparadas ao controle reexecutado desta rodada. A diferença frente ao controle antigo '
                           'não é atribuída à quantização.'))
    else:
        story.append(P("<b>Divisão temporal.</b> Teste de abril de 2019 a dezembro de 2022, equivalente aos últimos "
                       "45 dos 300 meses (15%). Validação de abril de 2018 a março de 2019. O histórico longo começa "
                       "em janeiro de 1998; o curto começa em abril de 2014. Ambos usam as mesmas datas de validação e teste. "
                       "Os cortes usam fuso local fixo. No horário, há 1.368 origens de teste por localidade; a última é "
                       "28/12/2022, com alvos até 30/12 às 23h locais. A disponibilidade da fonte exclui a origem "
                       "seguinte em ambos os históricos, sem imputação nem dados de 2023."))
        story.append(P("<b>Interpretação.</b> As dez localidades são as do nosso projeto, diferentes das do artigo do Luís. "
                       "A comparação pareada avalia a diferença de histórico mantendo o teste fixo. Uma mudança de MAE "
                       "não demonstra, por si só, que a causa seja variação climática."))
    story.append(P("<b>Leitura.</b> MAE e RMSE em W/m²; MSE em (W/m²)²; nRMSE em %. "
                   "Cada métrica é calculada por localidade e depois promediada. Os horizontes são cumulativos. "
                   "Delta positivo indica piora em relação ao mesmo modelo sem quantização."))
    story.append(P("Os resultados abaixo passaram por conferência de amostras, recálculo independente das métricas e "
                   "reprodução dos novos checkpoints. Pequenas diferenças numéricas não constituem teste de significância.", nota))
    story.append(PageBreak())
    story.append(P("Como a quantização foi aplicada", titulo))
    story.append(P("O min-max é ajustado por localidade usando somente os dados permitidos para treino em cada fase. "
                   "Depois, os valores são limitados a [0, 1] e arredondados para N níveis uniformes, incluindo os extremos. "
                   "O controle preserva o min-max sem clipping ou arredondamento."))
    story.append(P("<b>Redes e XGBoost.</b> Quantização das entradas de GHI no treinamento e na previsão. Alvos de treinamento, "
                   "pesos dos modelos e saídas permanecem contínuos. Identificadores das localidades não são quantizados."))
    story.append(P("<b>ARIMA.</b> Quantização da série histórica endógena usada no ajuste e dos contextos usados na previsão. "
                   "A ordem é escolhida por localidade pelo MSE normalizado na validação do controle e mantida entre "
                   "os níveis; os coeficientes são reajustados. "
                   "Os valores reais usados na avaliação permanecem contínuos."))
    story.append(P("<b>Referências simples.</b> Persistência, sazonal ingênuo e climatologia usam o histórico quantizado "
                   "antes de aplicar suas regras. A climatologia utiliza somente dados anteriores ao corte de ajuste."))
    story.append(P("As métricas usam previsões em W/m². Nas referências simples, o histórico é reconvertido antes da regra; "
                   "nos modelos ajustados, a saída é reconvertida após a previsão. Nas redes com várias sementes, a média das previsões "
                   "brutas precede o piso zero. No horário também é aplicada a mesma máscara noturna. A configuração escolhida "
                   "pela validação é assinalada por asterisco nas tabelas, considerando o horizonte completo de cada caso."))
    story.append(P("<b>Limites.</b> O experimento mede conjuntamente arredondamento e clipping, sem um controle separado "
                   "de clipping. Os diagnósticos contam posições em janelas sobrepostas; no ARIMA há também contagem da série "
                   "de ajuste. Essas contagens não são observações independentes nem cobrem automaticamente todo o histórico "
                   "usado por cada referência."))
    if regimes != ["atual"]:
        story.append(P("<b>Agregação histórica.</b> O horário usa médias de duas amostras de 30 minutos. O diário mantém "
                       "a definição da coleta original da API: amostras no meio da hora, com fuso fixo local e tratamento "
                       "da fronteira anual registrado na auditoria. O mensal é a média dos valores diários. A sobreposição "
                       "com a base anterior foi conferida. O tratamento anual original foi preservado e difere de "
                       "uma agregação física contínua em algumas fronteiras de ano, conforme a auditoria de dados."))
    story.append(P("<b>Sementes.</b> No horário, as redes usam a semente 42. Nos casos diário e mensais, "
                   "usam 11, 23, 42, 67 e 89, com média das previsões. As referências aplicam regras fixas; "
                   "o ARIMA estima coeficientes numericamente. Eles não usam sementes ou épocas de redes neurais."))
    if regimes != ["atual"]:
        story.append(P("As configurações dos modelos foram definidas anteriormente no projeto. "
                       "O estudo histórico também é retrospectivo e não representa um teste inteiramente inédito.", nota))
    fontes_manifesto, tabelas_manifesto = [], []
    story.append(P('<b>Normalização da métrica.</b> O nRMSE divide o RMSE pela média observada de GHI em cada localidade; a tabela apresenta a média dessas razões em porcentagem.', nota))
    story.append(P('<b>Execução numérica.</b> Transformer e Informer nos casos horário e diário usam novos controles com determinismo estrito, mantendo arquitetura, parâmetros e dados entre os níveis. Os controles antigos são preservados. Diferenças causadas pela execução numérica não são atribuídas à quantização. A mesma política é aplicada aos dois históricos.', nota))
    if pareamento is not None:
        fontes_manifesto.append({"path": str(Path(pareamento).resolve()), "sha256": sha256(Path(pareamento))})
    for audit_path, (a, df) in zip(auditorias, carregadas, strict=True):
        regime = a["regime"]
        escolhas = {(r["tarefa"], r["modelo"]): r["vencedor_validacao"] for r in a["resultados"]}
        teste = df[df.particao == "teste"].copy()
        controles = teste[teste.variante == "sem_quantizacao"].set_index(["tarefa", "modelo", "horizonte"])
        fontes_manifesto += [{"path": str(Path(audit_path).resolve()), "sha256": sha256(Path(audit_path))}, a["metricas"]]
        for tarefa in TAREFAS:
            for variante in VARIANTES:
                story.append(PageBreak())
                nome_tabela = f"{ROTULOS[tarefa]} - {NIVEIS[variante]}"
                quadro = teste[(teste.tarefa == tarefa) & (teste.variante == variante)].copy()
                quadro = quadro.sort_values(["horizonte", "MAE_wm2", "modelo"], kind="stable")
                linhas = [[P(nome_tabela, subtitulo)] + [""] * 7,
                          [P(REGIMES[regime], nota)] + [""] * 7,
                          ["Horizonte", "Modelo", "MAE\nW/m²", "MSE\n(W/m²)²", "RMSE\nW/m²", "nRMSE\n%", "R²", "Delta MAE\n%"]]
                registros = []
                for r in quadro.itertuples():
                    controle = float(controles.loc[(tarefa, r.modelo, r.horizonte), "MAE_wm2"])
                    delta = 100 * (r.MAE_wm2 - controle) / controle if controle else np.nan
                    escolhido = escolhas[tarefa, r.modelo] == variante
                    nome = r.modelo + (" *" if escolhido else "")
                    unidade = "mês" if tarefa.startswith("monthly") and r.horizonte == 1 else UNIDADES[tarefa]
                    linhas.append([f"{r.horizonte} {unidade}", nome, numero(r.MAE_wm2),
                                   numero(r.MSE_w2m4, 2), numero(r.RMSE_wm2), numero(100*r.nRMSE, 3),
                                   numero(r.R2), ("+" if delta > 0 else "") + numero(delta, 4)])
                    registros.append({"modelo": r.modelo, "horizonte": int(r.horizonte),
                                      "valores_exibidos": linhas[-1], "escolhido_validacao": escolhido})
                larguras = np.array([52, 140, 80, 88, 80, 79, 65, 88], float)
                larguras *= util / larguras.sum()
                tabela = Table(linhas, colWidths=larguras.tolist(), repeatRows=3, hAlign="LEFT")
                regras = [("SPAN", (0,0), (-1,0)), ("SPAN", (0,1), (-1,1)),
                          ("FONTNAME", (0,0), (-1,-1), "Relatorio"), ("FONTSIZE", (0,2), (-1,-1), 8.2),
                          ("LEADING", (0,2), (-1,-1), 10), ("FONTNAME", (0,2), (-1,2), "RelatorioBold"),
                          ("BACKGROUND", (0,2), (-1,2), colors.HexColor("#DCE7F0")),
                          ("TEXTCOLOR", (0,2), (-1,-1), colors.HexColor("#172D45")),
                          ("ALIGN", (2,2), (-1,-1), "RIGHT"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                          ("TOPPADDING", (0,3), (-1,-1), 4), ("BOTTOMPADDING", (0,3), (-1,-1), 4),
                          ("LINEBELOW", (0,2), (-1,2), .6, colors.HexColor("#7991A8")),
                          ("ROWBACKGROUNDS", (0,3), (-1,-1), [colors.white, colors.HexColor("#F4F7FA")])]
                for i, registro in enumerate(registros, start=3):
                    if registro["escolhido_validacao"]:
                        regras.append(("FONTNAME", (1,i), (1,i), "RelatorioBold"))
                tabela.setStyle(TableStyle(regras))
                story += [tabela, Spacer(1,7), P("* Nível escolhido pela validação no horizonte completo. "
                            "Ordenação pelo MAE observado no teste é descritiva. Delta comparado ao controle do mesmo modelo.", nota)]
                tabelas_manifesto.append({"regime": regime, "tarefa": tarefa, "variante": variante,
                                         "titulo": nome_tabela, "linhas": registros})
    if set(regimes) == {"historico_1998_2022", "historico_curto_pareado"}:
        longo = next(df for a,df in carregadas if a["regime"] == "historico_1998_2022")
        curto = next(df for a,df in carregadas if a["regime"] == "historico_curto_pareado")
        chaves = ["tarefa", "modelo", "variante", "horizonte"]
        pares = longo[longo.particao == "teste"].merge(curto[curto.particao == "teste"], on=chaves,
                    validate="one_to_one", suffixes=("_longo", "_curto"))
        for col in ("N_localidades", "N_origens", "N_pontos"):
            if not np.array_equal(pares[col+"_longo"], pares[col+"_curto"]):
                raise ValueError("Comparacao historica com amostras de tamanhos diferentes.")
        story += [PageBreak(), P("Histórico longo versus curto no mesmo teste", titulo),
                  P("Diferença do MAE no horizonte completo. Valores negativos favorecem o histórico longo. "
                    "A comparação mantém modelo, nível e datas de avaliação; não estabelece causa climática.")]
        linhas = [["Caso", "Modelo", "Nível", "MAE curto", "MAE longo", "Delta W/m²"]]
        for r in pares.sort_values(chaves).itertuples():
            if r.horizonte == max(TAREFAS[r.tarefa]):
                linhas.append([ROTULOS[r.tarefa], r.modelo, NIVEIS[r.variante], numero(r.MAE_wm2_curto),
                               numero(r.MAE_wm2_longo), numero(r.MAE_wm2_longo-r.MAE_wm2_curto)])
        tabela = Table(linhas, colWidths=[220,140,115,95,95,util-665], repeatRows=1)
        tabela.setStyle(TableStyle([("FONTNAME",(0,0),(-1,-1),"Relatorio"), ("FONTSIZE",(0,0),(-1,-1),8),
                                   ("FONTNAME",(0,0),(-1,0),"RelatorioBold"),
                                   ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#DCE7F0")),
                                   ("ALIGN",(3,0),(-1,-1),"RIGHT"),
                                   ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F4F7FA")])]))
        story.append(tabela)

    def rodape(canvas, doc):
        canvas.setFont("Relatorio", 8)
        canvas.setFillColor(colors.HexColor("#53677C"))
        canvas.drawString(margem, 19, "Projeto GHI | Quantização de todos os modelos | Resultados auditados")
        canvas.drawRightString(largura-margem, 19, str(doc.page))

    saida.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(saida), pagesize=landscape(A4), rightMargin=margem, leftMargin=margem,
                            topMargin=30, bottomMargin=35, title="Quantização de GHI - todos os modelos",
                            author="Projeto TCC - previsão de GHI")
    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    import pymupdf
    with pymupdf.open(saida) as pdf:
        paginas = len(pdf)
        texto = "\n".join(p.get_text() for p in pdf)
        if any(nome not in texto for nome in MODELOS) or any(n not in texto for n in NIVEIS.values()):
            raise ValueError("PDF omite algum modelo ou nivel.")
    manifesto.parent.mkdir(parents=True, exist_ok=True)
    manifesto.write_text(json.dumps({"gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "pdf": {"path": str(saida), "sha256": sha256(saida), "paginas": paginas},
        "fontes": fontes_manifesto, "tabelas": tabelas_manifesto, "revisao_visual_pendente": True,
        "gerador_sha256": sha256(Path(__file__))}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pdf": str(saida), "paginas": paginas, "tabelas": len(tabelas_manifesto)}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--auditorias", type=Path, nargs="+", required=True)
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--manifesto", type=Path, required=True)
    ap.add_argument("--pareamento", type=Path)
    args = ap.parse_args()
    gerar(args.auditorias, args.saida, args.manifesto, args.pareamento)
