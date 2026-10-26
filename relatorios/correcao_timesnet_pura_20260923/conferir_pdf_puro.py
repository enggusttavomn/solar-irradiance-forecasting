"""QA independente do PDF TimesNet pura; nao gera nem substitui PDFs.

Confere CSV, fontes, 705 celulas e geometria; renderiza quatro PNGs somente
depois de passar as verificacoes. A inspecao visual humana permanece separada.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
METRICAS = ("MAE_wm2", "MSE_w2m4", "RMSE_wm2", "nRMSE", "R2")
TAREFAS = {"hourly_72_extension": (24, 48, 72), "daily_30": (1, 3, 7, 14, 30),
           "monthly_1": (1,), "monthly_6": (1, 3, 6)}
QUANTIDADES = (33, 60, 12, 36)
NOVO_MODELO = "TimesNet (otimizada)"
BENCHMARK = ROOT / "resultados/avaliacao_baselines_revisao_20260912/consolidado"
MENSAL = ROOT / "resultados/busca_timesnet_mensal_20260920"
RESOLUCOES = ROOT / "resultados/busca_timesnet_resolucoes_20260922"
ANTERIOR = ROOT / "relatorios/tabela_resultados_ghi_20260922"


def exigir(condicao, mensagem):
    if not condicao:
        raise ValueError(mensagem)


def sha256(path):
    with Path(path).open("rb") as arquivo:
        return hashlib.file_digest(arquivo, "sha256").hexdigest()


def ler_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ler_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def chave(row):
    return row["tarefa"], row["modelo"], int(row["horizonte"])


def otimizada(row):
    exigir(row["otimizada"] in ("True", "False"), "Indicador otimizada invalido.")
    return row["otimizada"] == "True"


def texto_normalizado(texto):
    return " ".join(unicodedata.normalize("NFKC", texto).split())


def sem_hibridos(texto, origem):
    normalizado = texto_normalizado(texto).lower()
    exigir(not re.search(r"timesnet\s*\+\s*climatologia|anomalia", normalizado),
           f"Referencia a TimesNet hibrida encontrada em {origem}.")


def verificar_fontes(pdf, csv_path, manifesto):
    fontes = manifesto["fontes"]
    caminhos = [Path(x["path"]).resolve() for x in fontes]
    exigir(len(caminhos) == len(set(caminhos)), "Fontes duplicadas.")
    obrigatorias = {BENCHMARK / "metricas_macro.csv", ROOT / "scripts/gerar_tabela_resultados_ghi_otimizada.py"}
    for tarefa in TAREFAS:
        pasta = (MENSAL if tarefa.startswith("monthly") else RESOLUCOES) / tarefa
        previsao = "previsoes_teste.csv" if tarefa.startswith("monthly") else "previsoes_teste.csv.gz"
        obrigatorias.update(pasta / nome for nome in ("contrato_execucao.json", "selecao_congelada.json", "status_execucao.json", previsao))
        obrigatorias.add(BENCHMARK / tarefa / "previsoes_teste.csv.gz")
        if tarefa.startswith("monthly"):
            contrato = ler_json(pasta / "contrato_execucao.json")
            exigir(contrato["quantizacao"] is False, "Contrato mensal deve ser sem quantizacao.")
            exigir(not contrato.get("climatologia") and not contrato.get("climatologia_anomalia"), "Contrato mensal hibrido.")
            for candidato in [*contrato["candidatos"], manifesto["tarefas"][tarefa]["selecao"]["vencedor"]]:
                exigir(candidato.get("alvo", "bruto") == "bruto", "Candidato mensal nao preve alvo bruto.")
                sem_hibridos(json.dumps(candidato), tarefa)
    exigir({p.resolve() for p in obrigatorias}.issubset(set(caminhos)), "Manifesto omite fontes obrigatorias.")
    for registro in fontes:
        path = Path(registro["path"]).resolve()
        exigir("busca_timesnet_mensal_v2" not in str(path).lower(), "Fonte mensal V2 indevida.")
        exigir(path.is_file() and sha256(path) == registro["sha256"], f"Hash divergente: {path}")
    for nome, path in (("pdf", pdf), ("metricas", csv_path)):
        exigir(Path(manifesto[nome]["path"]).resolve() == path.resolve(), f"Caminho {nome} divergente.")
        exigir(sha256(path) == manifesto[nome]["sha256"], f"Hash {nome} divergente.")
    return fontes


def verificar_preservacao(linhas):
    antigo_manifesto = ler_json(ANTERIOR / "manifesto.json")
    antigo_csv = ANTERIOR / "metricas_tabela.csv"
    exigir(sha256(antigo_csv) == antigo_manifesto["metricas"]["sha256"], "CSV anterior alterado.")
    backup_pdf = ROOT / "relatorios/correcao_timesnet_pura_20260923/antes_correcao/tabela_resultados_ghi_2024.pdf"
    exigir(sha256(backup_pdf) == antigo_manifesto["pdf"]["sha256"], "Backup PDF anterior alterado.")
    antigos = ler_csv(antigo_csv)
    exigir(len(linhas) == 141 and len({chave(r) for r in linhas}) == 141, "Esperadas 141 linhas sem duplicatas.")
    exigir(sum(otimizada(r) for r in linhas) == 12, "Esperadas 12 linhas otimizadas.")
    indice = {chave(r): r for r in linhas}
    preservadas = originais = resolucoes = 0
    for antigo in antigos:
        eh_novo = otimizada(antigo)
        if eh_novo and antigo["tarefa"].startswith("monthly"):
            continue
        esperado = dict(antigo)
        if eh_novo:
            esperado["modelo"] = NOVO_MODELO
        atual = indice.get(chave(esperado))
        exigir(atual == esperado, f"Linha anterior nao preservada exatamente: {chave(esperado)}")
        preservadas += 1
        originais += not eh_novo
        resolucoes += eh_novo
    exigir((preservadas, originais, resolucoes) == (137, 129, 8), "Preservacao nao cobre 129 originais + 8 hora/dia.")
    for (tarefa, horizontes), quantidade in zip(TAREFAS.items(), QUANTIDADES):
        quadro = [r for r in linhas if r["tarefa"] == tarefa]
        exigir(len(quadro) == quantidade, f"Numero de linhas incorreto: {tarefa}")
        exigir({int(r["horizonte"]) for r in quadro} == set(horizontes), f"Horizontes incorretos: {tarefa}")
        for h in horizontes:
            novos = [r for r in quadro if int(r["horizonte"]) == h and otimizada(r)]
            exigir(len(novos) == 1 and novos[0]["modelo"] == NOVO_MODELO, f"Linha nova incorreta: {tarefa}, {h}")
    exigir(all(math.isfinite(float(r[m])) for r in linhas for m in METRICAS), "Metrica nao finita.")
    sem_hibridos(json.dumps(linhas), "CSV")
    return {"originais_exatas": originais, "hora_dia_otimizadas_exatas": resolucoes,
            "unica_alteracao_de_rotulo_permitida": "TimesNet otimizada -> TimesNet (otimizada)",
            "csv_anterior_sha256": sha256(antigo_csv), "pdf_anterior_sha256": sha256(backup_pdf)}


def conferir_metricas_fontes(linhas):
    relatos = []
    for tarefa, horizontes in TAREFAS.items():
        pasta = (MENSAL if tarefa.startswith("monthly") else RESOLUCOES) / tarefa
        mensal = tarefa.startswith("monthly")
        df = pd.read_csv(pasta / ("previsoes_teste.csv" if mensal else "previsoes_teste.csv.gz"))
        df = df.rename(columns={"origem_utc": "origem", "passo_h": "passo"})
        coluna = "previsao_pos_timesnet_ensemble_wm2" if mensal else "previsao_pos_timesnet_otimizada_wm2"
        exigir(df.localidade.nunique() == 10, f"Numero de localidades: {tarefa}")
        exigir(np.isfinite(df[["ghi_real_wm2", coluna]].to_numpy()).all(), f"Previsoes nao finitas: {tarefa}")
        for h in horizontes:
            local = []
            n_origens = n_pontos = 0
            for _, grupo in df[df.passo <= h].groupby("localidade"):
                real, previsto = grupo.ghi_real_wm2.to_numpy(float), grupo[coluna].to_numpy(float)
                erro = previsto - real
                mse = float(np.mean(erro ** 2))
                rmse = math.sqrt(mse)
                local.append([float(np.mean(abs(erro))), mse, rmse, rmse / float(np.mean(real)),
                              1 - float(np.sum(erro ** 2)) / float(np.sum((real - np.mean(real)) ** 2))])
                n_origens += grupo.origem.nunique()
                n_pontos += len(grupo)
            esperado = np.mean(local, axis=0)
            row = next(r for r in linhas if r["tarefa"] == tarefa and int(r["horizonte"]) == h and otimizada(r))
            erro = float(np.max(abs(esperado - [float(row[m]) for m in METRICAS])))
            exigir(erro <= 1e-7, f"Metricas novas diferem das previsoes: {tarefa}, {h}, {erro}")
            exigir((int(row["N_localidades"]), int(row["N_origens"]), int(row["N_pontos"])) == (10, n_origens, n_pontos), "Contagens novas divergentes.")
            relatos.append({"tarefa": tarefa, "horizonte": h, "erro_maximo": erro})
    return relatos


def numero(valor, metrica):
    fator = 100 if metrica == "nRMSE" else 1
    casas = 3 if metrica == "R2" else 2
    return f"{float(valor) * fator:,.{casas}f}".replace(",", " ").replace(".", ",")


def verificar_pagina(page, tarefa, horizontes, linhas, quantidade):
    spans = [s for b in page.get_text("dict")["blocks"] if b["type"] == 0 for l in b["lines"] for s in l["spans"] if s["text"].strip()]
    exigir(all(-0.1 <= s["bbox"][0] < s["bbox"][2] <= page.rect.width + 0.1 and
               -0.1 <= s["bbox"][1] < s["bbox"][3] <= page.rect.height + 0.1 for s in spans), f"Texto fora da pagina: {tarefa}")
    texto = page.get_text()
    sem_hibridos(texto, tarefa)
    if tarefa.startswith("monthly"):
        texto_unido = texto_normalizado(texto)
        for trecho in ("TimesNet prevê diretamente o GHI", "sem quantização", "sem mistura com climatologia"):
            exigir(trecho in texto_unido, f"Descricao mensal pura ausente: {trecho}")
    # Limites da tabela A4: horizonte, posicao, modelo e cinco metricas.
    limites = [35, 84, 110, 249, 306, 375, 433, 486, page.rect.width - 35]
    ancoras = sorted([s for s in spans if 84 <= s["bbox"][0] < 110 and s["text"].isdigit()], key=lambda s: s["origin"][1])
    exigir(len(ancoras) == quantidade, f"Linhas PDF: {tarefa}: {len(ancoras)} != {quantidade}")
    esperado = []
    for h in horizontes:
        sub = sorted([r for r in linhas if r["tarefa"] == tarefa and int(r["horizonte"]) == h], key=lambda r: (float(r["MAE_wm2"]), r["modelo"]))
        for indice, row in enumerate(sub):
            esperado.append((h, indice == 0, 1 + sum(float(r["MAE_wm2"]) < float(row["MAE_wm2"]) for r in sub), row))
    azul = np.array([237, 244, 251]) / 255
    fundos = [d["rect"] for d in page.get_drawings() if d.get("fill") is not None and np.max(abs(np.array(d["fill"]) - azul)) < 1e-5]
    exigir(len(fundos) == len(horizontes), f"Quantidade de linhas azuis: {tarefa}")
    valores = 0
    for ancora, (h, primeiro, posicao, row) in zip(ancoras, esperado):
        y = ancora["origin"][1]
        mesma_linha = [s for s in spans if abs(s["origin"][1] - y) < 0.3]
        celulas = []
        for esquerda, direita in zip(limites, limites[1:]):
            conteudo = sorted([s for s in mesma_linha if esquerda <= s["origin"][0] < direita], key=lambda s: s["origin"][0])
            exigir(all(s["bbox"][0] >= esquerda - 0.1 and s["bbox"][2] <= direita + 0.1 for s in conteudo), f"Texto cruza borda de celula: {tarefa}, {h}, {row['modelo']}")
            celulas.append(texto_normalizado(" ".join(s["text"] for s in conteudo)))
        nome = {"TimesNet": "TimesNet (original)", "Persistencia": "Persistência", "Sazonal ingenuo": "Sazonal ingênuo"}.get(row["modelo"], row["modelo"])
        unidade = ("mês" if h == 1 else "meses") if tarefa.startswith("monthly") else ("h" if tarefa.startswith("hourly") else "d")
        alvo = [f"{h} {unidade}" if primeiro else "", str(posicao), nome, *[numero(row[m], m) for m in METRICAS]]
        exigir(celulas == alvo, f"Celulas divergentes: {tarefa}, {h}, {nome}: {celulas!r} != {alvo!r}")
        exigir(any(r.y0 < y < r.y1 for r in fundos) == otimizada(row), f"Destaque azul incoerente: {tarefa}, {h}, {nome}")
        valores += 5
    return {"task": tarefa, "rows": quantidade, "new_rows": len(horizontes), "metric_values_checked": valores,
            "blue_rows": len(fundos), "text_within_page": True, "numeric_columns_within_cells": True,
            "all_cells_match_csv": True, "rankings_match_unrounded_mae": True}


def renderizar(pdf, saida):
    pasta = saida / "renderizacao"
    pasta.mkdir(parents=True, exist_ok=True)
    poppler = shutil.which("pdftoppm")
    arquivos = []
    if poppler:
        subprocess.run([poppler, "-png", "-r", "160", str(pdf), str(pasta / "pagina")], check=True, capture_output=True)
        for indice in range(1, 5):
            original = pasta / f"pagina-{indice}.png"
            destino = pasta / f"pagina_{indice}.png"
            original.replace(destino)
            arquivos.append(destino)
        motor = "Poppler pdftoppm, 160 dpi"
    else:
        with pymupdf.open(pdf) as doc:
            for indice, page in enumerate(doc, 1):
                destino = pasta / f"pagina_{indice}.png"
                page.get_pixmap(dpi=160, alpha=False).save(destino)
                arquivos.append(destino)
        motor = "PyMuPDF, 160 dpi; Poppler nao disponivel no PATH"
    return motor, [{"path": str(p.resolve()), "sha256": sha256(p)} for p in arquivos]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=ROOT / "tmp/pdfs/timesnet_pura_20260923.pdf")
    parser.add_argument("--dados", type=Path, default=ROOT / "relatorios/tabela_resultados_ghi_pura_20260923")
    parser.add_argument("--saida", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    relatorio = {"gerado_em_utc": datetime.now(timezone.utc).isoformat(), "ok": False, "escopo": "QA automatico; inspecao visual das quatro imagens deve ser registrada separadamente."}
    try:
        csv_path, manifesto_path = args.dados / "metricas_tabela.csv", args.dados / "manifesto.json"
        manifesto = ler_json(manifesto_path)
        fontes = verificar_fontes(args.pdf, csv_path, manifesto)
        congelados = {str(p.resolve()): sha256(p) for p in [args.pdf, csv_path, manifesto_path]}
        linhas = ler_csv(csv_path)
        relatorio["preservacao"] = verificar_preservacao(linhas)
        relatorio["metricas_novas_recalculadas"] = conferir_metricas_fontes(linhas)
        with pymupdf.open(args.pdf) as doc:
            exigir(len(doc) == 4, "PDF deve conter quatro paginas.")
            relatorio["pages"] = [dict(page=i + 1, **verificar_pagina(doc[i], tarefa, hs, linhas, n))
                                  for i, ((tarefa, hs), n) in enumerate(zip(TAREFAS.items(), QUANTIDADES))]
        relatorio["row_count"] = sum(p["rows"] for p in relatorio["pages"])
        relatorio["new_rows"] = sum(p["new_rows"] for p in relatorio["pages"])
        relatorio["metric_values_checked"] = sum(p["metric_values_checked"] for p in relatorio["pages"])
        exigir((relatorio["row_count"], relatorio["new_rows"], relatorio["metric_values_checked"]) == (141, 12, 705), "Contagem final divergente.")
        relatorio["renderer"], relatorio["renderizacao"] = renderizar(args.pdf, args.saida)
        exigir(all(sha256(path) == digest for path, digest in congelados.items()), "Artefato mudou durante QA.")
        exigir(all(sha256(f["path"]) == f["sha256"] for f in fontes), "Fonte mudou durante QA.")
        relatorio.update(pdf=str(args.pdf.resolve()), pdf_sha256=sha256(args.pdf), metricas_sha256=sha256(csv_path),
                         manifesto_sha256=sha256(manifesto_path), source_hashes_ok=True, fontes_verificadas=len(fontes),
                         ausencia_timesnet_hibrida=True, visual_inspection="pendente: quatro PNGs gerados para inspecao", ok=True)
    except Exception as erro:
        relatorio["erro"] = f"{type(erro).__name__}: {erro}"
    args.saida.mkdir(parents=True, exist_ok=True)
    destino = args.saida / "qa_pdf_puro.json"
    destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in relatorio.items() if k in ("ok", "erro", "row_count", "new_rows", "metric_values_checked", "renderizacao")}, ensure_ascii=True), flush=True)
    return 0 if relatorio["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
