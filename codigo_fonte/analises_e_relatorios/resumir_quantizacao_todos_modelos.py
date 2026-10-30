"""Produz feedback a partir das metricas completas que passaram pela auditoria."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from codigo_fonte.analises_e_relatorios.gerar_pdf_quantizacao_todos_modelos import carregar_auditoria as carregar, ROTULOS, NIVEIS
from codigo_fonte.acompanhamento.metricas_quantizacao_todos import TAREFAS, sha256


def n(valor, casas=4):
    return f"{valor:.{casas}f}".replace(".", ",")


def resumir(auditoria, destino):
    audit, df = carregar(auditoria)
    escolhido = {(r["tarefa"], r["modelo"]): r["vencedor_validacao"] for r in audit["resultados"]}
    teste = df[df.particao == "teste"]
    linhas = []
    for (tarefa, modelo), grupo in teste.groupby(["tarefa", "modelo"]):
        grupo = grupo[grupo.horizonte == max(TAREFAS[tarefa])].set_index("variante")
        controle = float(grupo.loc["sem_quantizacao", "MAE_wm2"])
        variante = escolhido[tarefa, modelo]
        erro = float(grupo.loc[variante, "MAE_wm2"])
        linhas.append({"tarefa": tarefa, "modelo": modelo, "escolhido": variante,
                       "controle": controle, "MAE": erro, "delta": erro - controle,
                       "delta_percentual": 100 * (erro - controle) / controle if controle else 0.0})
    resumo = pd.DataFrame(linhas)
    quantizados = resumo[resumo.escolhido != "sem_quantizacao"]
    melhorias = int((quantizados.delta < -1e-7).sum())
    pioras = int((quantizados.delta > 1e-7).sum())
    empates = len(quantizados) - melhorias - pioras
    controles = len(resumo) - len(quantizados)
    texto = ["# Resultados da quantização de todos os modelos", "",
             "Fonte: auditoria completa das previsões e dos checkpoints. Contagem no horizonte completo de cada caso.", "",
             "> Bom dia, Thales! Concluí os testes de todos os modelos nos quatro casos, mantendo o min-max e comparando 64, 128 e 256 níveis com o controle sem quantização. As tabelas do PDF estão separadas por nível, com todos os modelos juntos.", ">",
             f"> Considerando as escolhas feitas pela validação, {melhorias} combinações de modelo e caso melhoraram no teste, {pioras} pioraram e {empates} ficaram praticamente iguais. Em outras {controles}, a validação manteve a opção sem quantização. Esses números descrevem os erros observados; não foi realizado teste de significância estatística.", "",
             "| Caso | Modelo | Escolha na validação | MAE sem quantização | MAE da escolha | Diferença (%) |",
             "|---|---|---|---:|---:|---:|"]
    for r in resumo.itertuples():
        texto.append(f"| {ROTULOS[r.tarefa]} | {r.modelo} | {NIVEIS[r.escolhido]} | {n(r.controle)} | {n(r.MAE)} | {n(r.delta_percentual)} |")
    texto += ["", "Diferença negativa indica menor MAE. Resultados de 2024 e experimentos históricos são retrospectivos. A comparação com o artigo do Luís continua limitada pelas diferenças de locais, agregação e divisão dos dados.", ""]
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto += ['Empate numérico neste resumo: diferença absoluta de MAE até 0,0000001 W/m². Esse critério não é um teste de significância.', '']
    if any(r.get('controle_teste_suplementar') for r in audit['resultados']):
        texto += ['O XGBoost horário usa um novo controle de treinamento final, repetido integralmente e auditado. '
                  'A execução antiga apresentou divergência de causa ainda não identificada. As escolhas da validação '
                  'foram preservadas; os efeitos da quantização são comparados ao controle desta rodada.', '']
    destino.write_text("\n".join(texto), encoding="utf-8")
    destino.with_suffix(".json").write_text(json.dumps({"regime": audit["regime"],
        "auditoria": {"path": str(auditoria.resolve()), "sha256": sha256(auditoria)},
        "comparacoes": linhas, "melhorias": melhorias, "pioras": pioras, "empates": empates,
        "controle_escolhido": controles}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Feedback salvo em {destino}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--auditoria", type=Path, required=True)
    ap.add_argument("--saida", type=Path, required=True)
    args = ap.parse_args()
    resumir(args.auditoria, args.saida)
