"""Tabela auditavel das quatro tarefas, preservando o benchmark e a nova TimesNet.

As metricas novas sao calculadas das previsoes do vencedor, por localidade.
O script recusa execucoes incompletas e previsoes em origens diferentes.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
TAREFAS = {
    "hourly_72_extension": ("Horaria", (24, 48, 72)),
    "daily_30": ("Diaria", (1, 3, 7, 14, 30)),
    "monthly_1": ("Mensal", (1,)),
    "monthly_6": ("Mensal exploratoria", (1, 3, 6)),
}
METRICAS = ("MAE_wm2", "MSE_w2m4", "RMSE_wm2", "nRMSE", "R2")
CHAVES = ("localidade", "origem", "data_alvo", "passo")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalizar_chaves(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={"origem_utc": "origem", "timestamp_alvo_utc": "data_alvo", "passo_h": "passo"}).copy()
    for col in ("origem", "data_alvo"):
        df[col] = pd.to_datetime(df[col], utc=True, format="mixed")
    if df.duplicated(list(CHAVES)).any():
        raise ValueError("Previsoes possuem chaves duplicadas.")
    return df.sort_values(list(CHAVES)).reset_index(drop=True)


def conferir_observacoes(novas: pd.DataFrame, canonicas: pd.DataFrame) -> None:
    novas = normalizar_chaves(novas)
    canonicas = normalizar_chaves(canonicas)
    if len(novas) != len(canonicas) or not novas[list(CHAVES)].equals(canonicas[list(CHAVES)]):
        raise ValueError("As previsoes novas e canonicas nao possuem as mesmas origens/alvos.")
    if not np.allclose(novas.ghi_real_wm2, canonicas.ghi_real_wm2, rtol=0, atol=1e-6):
        raise ValueError("As observacoes novas diferem das observacoes canonicas.")
    if novas.localidade.nunique() != 10:
        raise ValueError("A tabela exige as dez localidades do benchmark.")


def calcular_macro(previsoes: pd.DataFrame, coluna: str, horizontes: tuple[int, ...]) -> pd.DataFrame:
    """Media aritmetica de cada metrica local; MSE nao e macro-RMSE ao quadrado."""
    previsoes = normalizar_chaves(previsoes)
    if not np.isfinite(previsoes[["ghi_real_wm2", coluna]].to_numpy(dtype=float)).all():
        raise ValueError("Previsoes/observacoes nao finitas.")
    linhas = []
    for horizonte in horizontes:
        locais = []
        recorte = previsoes[previsoes.passo <= horizonte]
        for localidade, grupo in recorte.groupby("localidade"):
            real = grupo.ghi_real_wm2.to_numpy(dtype=float)
            pred = grupo[coluna].to_numpy(dtype=float)
            erro = real - pred
            mse = float(np.mean(erro ** 2))
            rmse = float(np.sqrt(mse))
            media = float(real.mean())
            denominador = float(np.sum((real - media) ** 2))
            locais.append({
                "localidade": localidade,
                "MAE_wm2": float(np.mean(np.abs(erro))), "MSE_w2m4": mse,
                "RMSE_wm2": rmse,
                "nRMSE": np.nan if np.isclose(media, 0) else rmse / media,
                "R2": np.nan if len(real) < 2 or np.isclose(denominador, 0) else 1 - float(np.sum(erro ** 2)) / denominador,
                "N_origens": int(grupo.origem.nunique()), "N_pontos": len(grupo),
            })
        locais_df = pd.DataFrame(locais)
        linhas.append({"horizonte": horizonte, "N_localidades": len(locais),
                       "N_origens": int(locais_df.N_origens.sum()), "N_pontos": int(locais_df.N_pontos.sum()),
                       **{col: float(locais_df[col].mean()) for col in METRICAS}})
    return pd.DataFrame(linhas)


def ler_benchmark(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    mascara = ((df.particao == "teste_2024") & (df.tipo_horizonte == "cumulativo") &
               (df.tipo_estimativa.isin(["ensemble", "deterministica"]) |
                ((df.tarefa == "hourly_72_extension") & (df.tipo_estimativa == "semente") & (df.semente == 42))))
    df = df.loc[mascara].copy()
    df["otimizada"] = False
    for tarefa, (_, horizontes) in TAREFAS.items():
        quadro = df[df.tarefa == tarefa]
        modelos = 10 if tarefa == "hourly_72_extension" else 11
        if len(quadro) != len(horizontes) * modelos or quadro.duplicated(["modelo", "horizonte"]).any():
            raise ValueError(f"Benchmark incompleto ou duplicado: {tarefa}")
        if set(quadro.horizonte) != set(horizontes) or (quadro.N_localidades != 10).any():
            raise ValueError(f"Horizontes/localidades inesperados: {tarefa}")
    return df


def nota_teto_epocas(tarefa: str, selecao: dict, contrato: dict) -> str:
    """Sinaliza selecao no teto real da busca, sem inferir convergencia."""
    if tarefa not in ("hourly_72_extension", "daily_30"):
        return ""
    epocas = selecao["vencedor"].get("epocas", {})
    if not epocas:
        return ""
    limite = int(contrato["configuracao"]["max_epocas_diario"])
    no_teto = [semente for semente, valor in epocas.items() if int(valor) >= limite]
    if not no_teto:
        return ""
    amostra = f"semente {no_teto[0]}" if len(epocas) == 1 else f"{len(no_teto)}/{len(epocas)} sementes"
    return (f"A TimesNet otimizada atingiu o teto de {limite} épocas na seleção ({amostra}); "
            "pode não ter convergido.")


def validar_mensal_pura(tarefa: str, selecao: dict, contrato: dict) -> None:
    """Aceita o contrato legado de alvo bruto e impede misturas com climatologia."""
    if contrato.get("tarefa") != tarefa or selecao.get("tarefa", {}).get("slug") != tarefa:
        raise ValueError(f"Tarefa mensal incoerente no contrato/selecao: {tarefa}")
    if contrato.get("quantizacao") is not False:
        raise ValueError(f"A TimesNet mensal pura exige contrato sem quantizacao: {tarefa}")
    if contrato.get("climatologia_anomalia") or contrato.get("climatologia"):
        raise ValueError(f"Contrato mensal hibrido com climatologia: {tarefa}")
    candidatos = contrato.get("candidatos")
    vencedor = selecao.get("vencedor")
    if not isinstance(candidatos, list) or not candidatos or not isinstance(vencedor, dict):
        raise ValueError(f"Contrato/selecao mensal sem candidatos e vencedor: {tarefa}")
    nomes = []
    for candidato in [*candidatos, vencedor]:
        if not isinstance(candidato, dict) or not isinstance(candidato.get("nome"), str):
            raise ValueError(f"Candidato mensal sem nome: {tarefa}")
        nome = candidato["nome"].lower()
        if (candidato.get("alvo", "bruto") != "bruto" or
                any(termo in nome for termo in ("anomalia", "climatologia")) or
                candidato.get("climatologia") or candidato.get("climatologia_anomalia")):
            raise ValueError(f"A tabela mensal exige todos os candidatos com alvo bruto: {tarefa}")
    nomes = [candidato["nome"] for candidato in candidatos]
    if len(nomes) != len(set(nomes)) or vencedor["nome"] not in nomes:
        raise ValueError(f"Vencedor mensal incoerente com os candidatos declarados: {tarefa}")
    declarado = candidatos[nomes.index(vencedor["nome"])]
    if any(vencedor.get(chave) != valor for chave, valor in declarado.items() if chave != "alvo"):
        raise ValueError(f"Configuracao do vencedor mensal incoerente com o contrato: {tarefa}")
    sementes = contrato.get("configuracao", {}).get("sementes", [])
    if (sorted(sementes) != [11, 23, 42, 67, 89] or
            set(vencedor.get("epocas", {})) != {str(semente) for semente in sementes}):
        raise ValueError(f"A TimesNet mensal pura exige as cinco sementes declaradas: {tarefa}")


def montar_dados(benchmark: Path, mensal: Path, resolucoes: Path) -> tuple[pd.DataFrame, dict]:
    base = ler_benchmark(benchmark / "metricas_macro.csv")
    fontes = [benchmark / "metricas_macro.csv", Path(__file__).resolve()]
    detalhes = {}
    quadros = [base]
    for tarefa, (_, horizontes) in TAREFAS.items():
        pasta = (mensal if tarefa.startswith("monthly") else resolucoes) / tarefa
        status_path = pasta / "status_execucao.json"
        selecao_path = pasta / "selecao_congelada.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status.get("etapa") != "concluida" or status.get("modo") != "completa" or not status.get("teste_avaliado", True):
            raise ValueError(f"Busca incompleta ou de verificacao: {tarefa}")
        selecao = json.loads(selecao_path.read_text(encoding="utf-8"))
        contrato_path = pasta / "contrato_execucao.json"
        contrato = json.loads(contrato_path.read_text(encoding="utf-8"))
        fontes.append(contrato_path)
        if not selecao.get("selecao_concluida_antes_do_teste", False):
            raise ValueError(f"Selecao nao congelada antes do teste: {tarefa}")
        if tarefa.startswith("monthly"):
            validar_mensal_pura(tarefa, selecao, contrato)
        previsoes_path = pasta / ("previsoes_teste.csv" if tarefa.startswith("monthly") else "previsoes_teste.csv.gz")
        canonicas_path = benchmark / tarefa / "previsoes_teste.csv.gz"
        previsoes = pd.read_csv(previsoes_path)
        nomes_chave = set(CHAVES) | {"origem_utc", "timestamp_alvo_utc", "passo_h", "ghi_real_wm2"}
        canonicas = pd.read_csv(canonicas_path, usecols=lambda c: c in nomes_chave)
        conferir_observacoes(previsoes, canonicas)
        coluna = "previsao_pos_timesnet_ensemble_wm2" if tarefa.startswith("monthly") else "previsao_pos_timesnet_otimizada_wm2"
        novas = calcular_macro(previsoes, coluna, horizontes)
        novas["tarefa"] = tarefa
        novas["modelo"] = "TimesNet (otimizada)"
        novas["otimizada"] = True
        novas["tipo_horizonte"] = "cumulativo"
        novas["particao"] = "teste_2024"
        novas["agregacao"] = "media_aritmetica_das_metricas_por_localidade"
        referencia = base[(base.tarefa == tarefa) & (base.modelo == "TimesNet")].set_index("horizonte")
        for row in novas.itertuples():
            for count in ("N_origens", "N_pontos"):
                if getattr(row, count) != referencia.loc[row.horizonte, count]:
                    raise ValueError(f"Contagem diferente: {tarefa}, {count}.")
        quadros.append(novas)
        fontes.extend([status_path, selecao_path, previsoes_path, canonicas_path])
        detalhes[tarefa] = {"selecao": selecao, "status": status, "coluna_previsao": coluna,
                            "nota_teto_epocas": nota_teto_epocas(tarefa, selecao, contrato),
                            "N_origens_por_local": int(novas.N_origens.iloc[0] / 10)}
    dados = pd.concat(quadros, ignore_index=True)
    manifesto = {"criado_em_utc": datetime.now(timezone.utc).isoformat(), "tarefas": detalhes,
                 "agregacao": "Media de cada metrica por localidade; MSE calculado antes da media, independente do macro-RMSE.",
                 "fontes": [{"path": str(p.resolve()), "sha256": sha256(p)} for p in fontes]}
    return dados, manifesto


def numero(valor: float, decimais: int = 2) -> str:
    return f"{valor:,.{decimais}f}".replace(",", " ").replace(".", ",")


def escrever_pdf(dados: pd.DataFrame, manifesto: dict, destino: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph, Table, TableStyle

    destino.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(destino), pagesize=A4)
    c.setTitle("Previsao de GHI - resultados de teste de 2024, com TimesNet otimizada")
    c.setAuthor("Projeto TCC - previsao de GHI")
    largura, altura = A4
    margem = 35
    largura_util = largura - 2 * margem
    azul = colors.HexColor("#edf4fb")
    texto = colors.HexColor("#142435")
    estilo = ParagraphStyle("nota", fontName="Times-Roman", fontSize=9, leading=11, textColor=texto)
    rodape = ParagraphStyle("rodape", parent=estilo, fontSize=8, leading=9.6)

    def paragrafo(txt: str, y: float, style=estilo) -> float:
        p = Paragraph(txt, style)
        _, h = p.wrap(largura_util, altura)
        p.drawOn(c, margem, y - h)
        return y - h

    titulos = {"hourly_72_extension": "Horária", "daily_30": "Diária", "monthly_1": "Mensal - 1 mês", "monthly_6": "Mensal exploratória - até 6 meses"}
    for indice, (tarefa, (_, horizontes)) in enumerate(TAREFAS.items(), 1):
        y = altura - 31
        c.setFillColor(texto)
        c.setFont("Times-Roman", 9)
        c.drawString(margem, y, "Previsão de GHI - teste de 2024 | benchmark e TimesNet otimizada")
        y -= 23
        c.setFont("Times-Bold", 18)
        c.drawString(margem, y, titulos[tarefa])
        y -= 13
        detalhes = manifesto["tarefas"][tarefa]
        vencedor = detalhes["selecao"]["vencedor"]
        seq_len = vencedor.get("seq_len", vencedor.get("contexto"))
        contextos = {"hourly_72_extension": (336, "h", 72), "daily_30": (365, "d", 30), "monthly_1": (12, "meses", 1), "monthly_6": (12, "meses", 6)}
        original, unidade, passos = contextos[tarefa]
        seq_txt = str(seq_len) if seq_len is not None else "registrado na busca"
        unidade_previsao = "mês" if tarefa.startswith("monthly") and passos == 1 else unidade
        resumo = f"Histórico: benchmark {original} {unidade}; otimizada {seq_txt} {unidade}. Previsão direta de {passos} {unidade_previsao}. "
        resumo += "Semente 42. Climatologia não avaliada." if tarefa == "hourly_72_extension" else "Redes: ensemble das sementes 11, 23, 42, 67 e 89."
        if tarefa == "monthly_6":
            resumo += " Sete origens de teste por localidade."
        y = paragrafo(resumo, y) - 8

        quadro = dados[dados.tarefa == tarefa]
        cabecalho = ["Horizonte", "Pos.", "Modelo", "MAE\n(W/m²)", "MSE\n((W/m²)²)", "RMSE\n(W/m²)", "nRMSE\n(%)", "R²"]
        linhas = [cabecalho]
        comandos = [("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
                    ("TEXTCOLOR", (0, 0), (-1, -1), texto),
                    ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                    ("ALIGN", (1, 0), (1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEABOVE", (0, 0), (-1, 0), 0.7, colors.black),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                    ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        fonte = 8.3 if tarefa == "daily_30" else 9
        comandos.append(("FONTSIZE", (0, 0), (-1, -1), fonte))
        comandos.append(("LEADING", (0, 0), (-1, -1), fonte + 1))
        for horizonte in horizontes:
            sub = quadro[quadro.horizonte == horizonte].sort_values(["MAE_wm2", "modelo"], kind="stable")
            primeiro = len(linhas)
            melhores = {col: (sub[col].max() if col == "R2" else sub[col].min()) for col in METRICAS}
            for pos, (_, row) in enumerate(sub.iterrows(), 1):
                nome = {"Persistencia": "Persistência", "Sazonal ingenuo": "Sazonal ingênuo"}.get(row.modelo, row.modelo)
                if row.modelo == "TimesNet":
                    nome = "TimesNet (original)"
                horizonte_txt = f"{horizonte} {('mês' if horizonte == 1 else 'meses') if tarefa.startswith('monthly') else unidade}"
                vals = [numero(row[col] * (100 if col == "nRMSE" else 1), 3 if col == "R2" else 2) for col in METRICAS]
                posicao = int((sub.MAE_wm2 < row.MAE_wm2).sum()) + 1
                linhas.append([horizonte_txt if pos == 1 else "", str(posicao), nome, *vals])
                r = len(linhas) - 1
                if row.otimizada:
                    comandos.append(("BACKGROUND", (0, r), (-1, r), azul))
                    comandos.append(("FONTNAME", (2, r), (2, r), "Times-Bold"))
                for j, col in enumerate(METRICAS, 3):
                    if np.isclose(row[col], melhores[col], rtol=1e-12, atol=1e-12):
                        comandos.append(("FONTNAME", (j, r), (j, r), "Times-Bold"))
            if primeiro > 1:
                comandos.append(("LINEABOVE", (0, primeiro), (-1, primeiro), 0.3, colors.HexColor("#adb7c0")))
        comandos.append(("LINEBELOW", (0, len(linhas) - 1), (-1, len(linhas) - 1), 0.7, colors.black))
        alturas = [25] + [9.5 if tarefa == "daily_30" else 13] * (len(linhas) - 1)
        tabela = Table(linhas, colWidths=[49, 26, 139, 57, 69, 58, 53, largura_util - 451], rowHeights=alturas)
        tabela.setStyle(TableStyle(comandos))
        _, h = tabela.wrap(largura_util, altura)
        tabela.drawOn(c, margem, y - h)
        y -= h + 8
        original_retida = vencedor.get("nome") == "referencia_original"
        metodologia = ("Azul: a busca pelo MAE físico de 2023 reteve a configuração original da TimesNet; os resultados são repetidos para registrar a seleção. "
                       if original_retida else "Azul: nova variante, escolhida pelo MAE físico na validação de 2023 e reestimada até 2023. ")
        if tarefa.startswith("monthly"):
            metodologia += ("TimesNet prevê diretamente o GHI, com normalização min-max e sem quantização. "
                            "A previsão é a média de cinco sementes da própria TimesNet, sem mistura com climatologia. ")
        metodologia += "Os valores anteriores foram preservados."
        y = paragrafo(metodologia, y, rodape) - 5
        notas = {
            "hourly_72_extension": "ARIMA e Informer têm erros altos por não reproduzirem bem o ciclo dia/noite nas configurações avaliadas. Há só uma semente por rede. GRU e Transformer originais atingiram 30 épocas ainda melhorando na validação.",
            "daily_30": "Transformer (2/5 sementes), DilatedRNN (1/5) e LSTM (1/5), nas configurações originais, atingiram 30 épocas ainda melhorando na validação.",
            "monthly_1": "Esta tarefa prevê um mês por origem. É diferente do primeiro passo da tarefa de seis meses, que usa apenas sete origens de teste por localidade.",
            "monthly_6": "Resultados cumulativos: 1, 3 e 6 passos da mesma previsão direta. Os alvos se sobrepõem entre origens; a tarefa não corresponde a uma previsão de cinco anos.",
        }
        nota_tarefa = notas[tarefa]
        if detalhes.get("nota_teto_epocas"):
            nota_tarefa += " " + detalhes["nota_teto_epocas"]
        y = paragrafo(nota_tarefa, y, rodape) - 6
        nota_geral = ("Média simples das métricas calculadas em cada um dos 10 locais (NSRDB). MSE e RMSE são agregados separadamente; nRMSE = RMSE/média observada por local. "
                      "Horizontes cumulativos incluem todos os passos até o limite. Posição pelo MAE sem arredondamento; negrito indica o melhor valor de cada métrica. "
                      "Persistência, sazonal ingênuo, climatologia e ARIMA são determinísticos. "
                      "A otimização é exploratória: 2024 já havia sido consultado. A confirmação requer outro período; não há avaliação da variação entre anos.")
        y = paragrafo(nota_geral, y, rodape)
        if y < 27:
            raise ValueError(f"Conteudo excedeu a area util da pagina: {tarefa}, y={y:.1f}")
        c.setFont("Times-Roman", 8)
        c.setFillColor(colors.HexColor("#596773"))
        c.drawString(margem, 16, "Fontes, hashes e métricas sem arredondamento acompanham a geração na pasta de auditoria.")
        c.drawRightString(largura - margem, 16, f"{indice}/4")
        c.showPage()
    c.save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, default=RAIZ / "resultados/avaliacao_baselines_revisao_20260912/consolidado")
    parser.add_argument("--mensal", type=Path, default=RAIZ / "resultados/busca_timesnet_mensal_20260920")
    parser.add_argument("--resolucoes", type=Path, default=RAIZ / "resultados/busca_timesnet_resolucoes_20260922")
    parser.add_argument("--saida", type=Path, default=RAIZ / "documentacao/tabela_resultados_ghi_2024.pdf")
    parser.add_argument("--pasta-auditoria", type=Path, default=RAIZ / "relatorios/tabela_resultados_ghi_pura_20260923")
    parser.add_argument("--somente-validar", action="store_true", help="Confere entradas e calcula metricas sem escrever arquivos.")
    args = parser.parse_args()
    dados, manifesto = montar_dados(args.benchmark, args.mensal, args.resolucoes)
    if args.somente_validar:
        print(dados[dados.otimizada][["tarefa", "horizonte", *METRICAS]].to_string(index=False))
        return
    escrever_pdf(dados, manifesto, args.saida)
    args.pasta_auditoria.mkdir(parents=True, exist_ok=True)
    csv_path = args.pasta_auditoria / "metricas_tabela.csv"
    dados.to_csv(csv_path, index=False)
    manifesto["pdf"] = {"path": str(args.saida.resolve()), "sha256": sha256(args.saida)}
    manifesto["metricas"] = {"path": str(csv_path.resolve()), "sha256": sha256(csv_path)}
    (args.pasta_auditoria / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.saida.resolve())


if __name__ == "__main__":
    main()
