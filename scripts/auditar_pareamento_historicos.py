"""Exige as mesmas observacoes em historico longo/curto antes de compara-los."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.metricas_quantizacao_todos import MODELOS, TAREFAS, comparar_amostras, sha256

RAIZ = Path(__file__).resolve().parents[1]
REGIMES = ("historico_1998_2022", "historico_curto_pareado")
REL_HISTORICO = RAIZ / "relatorios/quantizacao_todos_modelos_20260929/historico"
QUANTIDADES_FONTES = {"horario": 25, "amostras_30min": 25, "diario": 10, "mensal": 10}
PARES_CUDA_AUTORIZADOS = {(t, m) for t in ("hourly_72_extension", "daily_30")
                         for m in ("GRU", "LSTM", "DilatedRNN")}


def ler(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def exigir(valor, mensagem):
    if not valor:
        raise ValueError(mensagem)


def caminho(path, raiz):
    p = Path(path)
    return (p if p.is_absolute() else raiz / p).resolve()


def hash_obj(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def conferir_hash_interno(obj, nome):
    exigir(obj.get("sha256_contrato") == hash_obj({k: v for k, v in obj.items()
                                                  if k != "sha256_contrato"}),
           f"Hash interno invalido: {nome}")


def registrar_fonte(fontes, path, esperado=None):
    p = Path(path).resolve()
    exigir(p.is_file(), f"Fonte ausente: {p}")
    atual = sha256(p)
    exigir(esperado is None or atual == esperado, f"Fonte alterada: {p}")
    exigir(str(p) not in fontes or fontes[str(p)] == atual,
           f"Fonte mudou durante a auditoria: {p}")
    fontes[str(p)] = atual
    return atual


def conferir_fontes_finais(fontes):
    # Nao publicar uma auditoria antiga caso os arquivos mudem durante a leitura.
    for path, esperado in fontes.items():
        exigir(Path(path).is_file() and sha256(Path(path)) == esperado,
               f"Fonte alterada antes da publicacao: {path}")


def conferir_protocolo_treinamento(protocolo, contrato, tarefa, modelo):
    if contrato.get("protocolo") == protocolo:
        return {"tipo": "protocolo_cli_inalterado"}
    if (tarefa, modelo) in PARES_CUDA_AUTORIZADOS:
        esperado = copy.deepcopy(protocolo)
        esperado.setdefault("dispositivos", {})[modelo] = "cuda"
        if contrato.get("protocolo") == esperado:
            exigir(contrato.get("parametros", {}).get("dispositivo") == "cuda",
                   "Sobrescrita CUDA diverge dos parametros efetivos do treinamento.")
            return {"tipo": "sobrescrita_cuda_autorizada_por_par", "tarefa": tarefa,
                    "modelo": modelo, "campo": f"dispositivos.{modelo}", "valor": "cuda",
                    "fonte": "CLI --dispositivo cuda aplica a mudanca em memoria somente ao par"}
    raise ValueError(f"Protocolo do treinamento diverge do CLI: {tarefa}/{modelo}")


def conferir_politica_atencao(contrato, referencias, fontes, raiz):
    chave = (contrato['tarefa']['slug'], contrato['modelo'])
    if chave[0] not in ('daily_30', 'hourly_72_extension') or chave[1] not in ('Transformer', 'Informer'):
        exigir(contrato.get('execucao_numerica') is None, 'Politica numerica fora do escopo historico.')
        return
    politica = contrato.get('execucao_numerica', {})
    exigir(politica.get('id') == 'atencao_cuda_deterministica_v1'
           and politica.get('algoritmos_deterministicos') is True
           and politica.get('warn_only') is False and politica.get('sdpa') == 'automatico',
           'Atencao historica sem politica deterministica estrita.')
    adaptador = (Path(raiz) / 'codigo_fonte/experimento_atencao_deterministica_v1.py').resolve()
    digest = contrato.get('codigo', {}).get(str(adaptador))
    exigir(bool(digest), 'Contrato historico sem fonte do adaptador.')
    registrar_fonte(fontes, adaptador, digest)
    atual = {'politica': politica, 'adaptador_sha256': digest}
    if chave in referencias:
        exigir(referencias[chave] == atual, 'Historicos usam politicas numericas diferentes.')
    else:
        referencias[chave] = atual


def auditar_integridade_historica(protocolo_longo, protocolo_curto, auditoria_dados,
                                  saida_experimentos, auditorias_experimentos, *, raiz=RAIZ):
    """Liga a coleta imutavel aos protocolos e aos 88 contratos usados.

    Hash fisico atual sozinho nao prova origem: ele precisa coincidir tambem
    com o hash esperado registrado na coleta e no contrato de treinamento.
    O mensal e reconstituido a partir dos CSVs diarios pelo motor, por isso
    suas dez entradas de treinamento sao diarias; os dez CSVs mensais da
    coleta tambem sao verificados, embora nao sejam carregados pelo motor.
    """
    raiz = Path(raiz).resolve()
    fontes, protocolos = {}, {}
    contrato_path = None
    contrato = None
    for regime, arquivo in zip(REGIMES, (protocolo_longo, protocolo_curto), strict=True):
        arquivo = caminho(arquivo, raiz)
        registrar_fonte(fontes, arquivo)
        p = ler(arquivo)
        exigir(p.get("regime") == regime, f"Protocolo de outro regime: {arquivo}")
        exigir(p.get("carregador_historico") is True, "Protocolo nao usa carregador historico.")
        exigir(p.get("contrato_preparacao_dados"), "Protocolo sem contrato de preparacao.")
        fonte = caminho(p["contrato_preparacao_dados"], raiz)
        exigir(p.get("sha256_arquivo_contrato_preparacao"), "Protocolo sem hash fisico da preparacao.")
        registrar_fonte(fontes, fonte, p["sha256_arquivo_contrato_preparacao"])
        coleta = ler(fonte)
        conferir_hash_interno(coleta, fonte)
        exigir(coleta.get("ok") is True and coleta.get("aprovado") is True,
               "Contrato de preparacao nao aprovado.")
        exigir(p.get("sha256_contrato_preparacao") == coleta["sha256_contrato"],
               "Hash de preparacao declarado no protocolo diverge.")
        exigir(contrato_path is None or fonte == contrato_path,
               "Perfis historicos usam contratos de coleta diferentes.")
        contrato_path, contrato = fonte, coleta
        protocolos[regime] = {"objeto": p, "arquivo": arquivo, "sha256": fontes[str(arquivo)]}
    exigir(set(contrato.get("entradas", {})) == set(QUANTIDADES_FONTES),
           "Grupos de fontes da coleta incompletos.")
    grupos, fontes_dados, registro_dados = {}, {}, []
    for grupo, quantidade in QUANTIDADES_FONTES.items():
        itens = contrato["entradas"][grupo]
        exigir(len(itens) == quantidade, f"Quantidade de fontes invalida em {grupo}.")
        if grupo in ("horario", "amostras_30min"):
            exigir({e.get("ano") for e in itens} == set(range(1998, 2023)),
                   f"Anos da coleta incompletos em {grupo}.")
        grupos[grupo] = {}
        for item in itens:
            p = caminho(item["arquivo"], raiz)
            exigir(str(p) not in fontes_dados, f"Fonte duplicada no contrato de coleta: {p}")
            exigir(item.get("sha256"), f"Fonte sem hash esperado: {p}")
            atual = registrar_fonte(fontes, p, item["sha256"])
            exigir(item.get("bytes") == p.stat().st_size, f"Tamanho da fonte diverge: {p}")
            grupos[grupo][str(p)] = atual
            fontes_dados[str(p)] = atual
            registro_dados.append({"grupo": grupo, "arquivo": str(p), "sha256_coleta": item["sha256"],
                                   "sha256_fisico": atual, "bytes": p.stat().st_size})
    exigir(len(fontes_dados) == 70, "A coleta deve conter 70 fontes distintas.")
    manifesto = contrato["manifesto_horario"]
    manifesto_path = caminho(manifesto["arquivo"], raiz)
    registrar_fonte(fontes, manifesto_path, manifesto["sha256"])
    metadados_autorizados = {str(contrato_path): fontes[str(contrato_path)],
                            str(manifesto_path): fontes[str(manifesto_path)]}
    for item in contrato["auditorias"].values():
        p = caminho(item["arquivo"], raiz)
        metadados_autorizados[str(p)] = registrar_fonte(fontes, p, item["sha256"])
    audit_path = caminho(auditoria_dados, raiz)
    registrar_fonte(fontes, audit_path)
    dados = ler(audit_path)
    aprovacoes = [dados[k] for k in ("ok", "aprovado") if k in dados]
    exigir(aprovacoes and all(v is True for v in aprovacoes),
           "Auditoria da base historica nao aprovada.")
    # Aceita o proprio contrato, auditoria incluida nele ou parecer posterior
    # que declare exatamente o contrato fisico e interno vigente.
    ligacao = dados.get("contrato", {})
    ligada = str(audit_path) in metadados_autorizados
    if not ligada and ligacao.get("arquivo"):
        ligada = (caminho(ligacao["arquivo"], raiz) == contrato_path
                  and ligacao.get("sha256_arquivo") == fontes[str(contrato_path)]
                  and ligacao.get("sha256_contrato") == contrato["sha256_contrato"])
    exigir(ligada, "Auditoria dos dados sem ligacao ao contrato de coleta vigente.")
    registros_contratos = []
    politicas_numericas = {}
    pares_esperados = {(t, m) for t in TAREFAS for m in MODELOS}
    for regime, info in protocolos.items():
        p = info["objeto"]
        pasta_diaria = caminho(p["pasta_diaria"], raiz)
        exigir({Path(x).parent for x in grupos["diario"]} == {pasta_diaria},
               "Pasta diaria do protocolo diverge da coleta.")
        lista = [str(caminho(x, raiz)) for x in p.get("arquivos_historicos", [])]
        exigir(len(lista) == len(set(lista)), "Protocolo tem fontes historicas duplicadas.")
        exigir(set(grupos["horario"]) <= set(lista), "Protocolo omite fontes horarias da coleta.")
        exigir(set(lista) <= set(grupos["horario"]) | set(metadados_autorizados),
               "Protocolo historico referencia fonte nao declarada na coleta.")
        exigir(str(contrato_path) in lista and str(manifesto_path) in lista,
               "Protocolo horario omite contrato de coleta ou manifesto.")
        carregador = raiz / "codigo_fonte/historico_nsrdb_expandido.py"
        registrar_fonte(fontes, carregador)
        fontes_horarias = {x: fontes[x] for x in lista}
        fontes_horarias[str(carregador.resolve())] = fontes[str(carregador.resolve())]
        audit = auditorias_experimentos[regime]
        exigir(audit.get("ok") is True and audit.get("publicavel") is True
               and audit.get("regime") == regime, "Auditoria do experimento incompleta.")
        resultados = audit.get("resultados", [])
        exigir(all(r.get("ok") is True for r in resultados), "Auditoria contem par reprovado.")
        pares = [(r["tarefa"], r["modelo"]) for r in resultados]
        exigir(len(pares) == len(pares_esperados) and set(pares) == pares_esperados,
               "Auditoria nao contempla os 44 pares tarefa/modelo historicos.")
        for r in resultados:
            tarefa, modelo = r["tarefa"], r["modelo"]
            pasta = Path(saida_experimentos) / regime / tarefa / modelo.lower().replace(" ", "_")
            cp = pasta / "contrato_execucao.json"
            registrar_fonte(fontes, cp)
            ct = ler(cp)
            conferir_hash_interno(ct, cp)
            conferir_politica_atencao(ct, politicas_numericas, fontes, raiz)
            exigir(ct.get("modelo") == modelo and ct.get("tarefa", {}).get("slug") == tarefa
                   and ct.get("modo") == "completa", f"Contrato de outro experimento: {cp}")
            transformacao = conferir_protocolo_treinamento(p, ct, tarefa, modelo)
            esperadas = fontes_horarias if tarefa == "hourly_72_extension" else grupos["diario"]
            entradas = {}
            for path, digest in ct.get("entradas", {}).items():
                canonico = str(caminho(path, raiz))
                exigir(canonico not in entradas, f"Fonte duplicada no contrato de treinamento: {cp}")
                entradas[canonico] = digest
            exigir(entradas == esperadas, f"Entradas do treinamento divergem da coleta: {cp}")
            for path, digest in entradas.items():
                registrar_fonte(fontes, Path(path), digest)
            sp = pasta / "selecao_congelada.json"
            exigir(r.get("selecao_sha256"), f"Auditoria sem hash da selecao: {pasta}")
            registrar_fonte(fontes, sp, r["selecao_sha256"])
            exigir(ler(sp).get("contrato_sha256") == ct["sha256_contrato"],
                   f"Selecao auditada pertence a outro contrato: {pasta}")
            registros_contratos.append({"regime": regime, "tarefa": tarefa, "modelo": modelo,
                "contrato": str(cp.resolve()), "sha256_arquivo": fontes[str(cp.resolve())],
                "sha256_contrato": ct["sha256_contrato"], "protocolo_sha256": info["sha256"],
                "protocolo_efetivo_sha256_canonico": hash_obj(ct["protocolo"]),
                "transformacao_protocolo": transformacao,
                "grupo_dados_usado": "horario" if tarefa == "hourly_72_extension" else "diario",
                "fontes_dados_usadas": len(grupos["horario"] if tarefa == "hourly_72_extension" else grupos["diario"]),
                "entradas_conferidas_contra_coleta": True})
    conferir_fontes_finais(fontes)
    return {"ok": True, "contrato_preparacao_dados": str(contrato_path),
            "sha256_arquivo_contrato_preparacao": fontes[str(contrato_path)],
            "sha256_contrato_preparacao": contrato["sha256_contrato"],
            "quantidade_fontes_dados": len(fontes_dados), "fontes_dados": registro_dados,
            "protocolos": {r: {"arquivo": str(v["arquivo"]), "sha256": v["sha256"]}
                           for r, v in protocolos.items()},
            "contratos_treinamento": registros_contratos}, fontes


def auditar(args):
    fontes, auditorias = {}, {}
    for path, regime in ((args.auditoria_longo, REGIMES[0]), (args.auditoria_curto, REGIMES[1])):
        a = ler(path)
        exigir(a.get("ok") is True and a.get("publicavel") is True and a.get("regime") == regime,
               "Auditoria do experimento incompleta.")
        registrar_fonte(fontes, Path(a["metricas"]["path"]), a["metricas"]["sha256"])
        registrar_fonte(fontes, path)
        auditorias[regime] = a
    integridade, fisicos = auditar_integridade_historica(
        args.protocolo_longo, args.protocolo_curto, args.auditoria_dados,
        args.saida_experimentos, auditorias)
    fontes.update(fisicos)
    resultados = []
    # Cada auditoria completa ja exige igualdade de amostras entre todos os
    # modelos e niveis. Aqui ligamos as duas grades pela TimesNet de controle.
    for tarefa in TAREFAS:
        for particao in ("validacao", "teste"):
            paths = [args.saida_experimentos / regime / tarefa / "timesnet" / "sem_quantizacao" /
                     f"previsoes_{particao}.csv.gz" for regime in REGIMES]
            for p in paths:
                registrar_fonte(fontes, p)
            frames = [pd.read_csv(path) for path in paths]
            comparar_amostras(*frames)
            resultados.append({"tarefa": tarefa, "particao": particao, "linhas": len(frames[0]),
                               "observacoes_e_datas_iguais": True})
    conferir_fontes_finais(fontes)
    return {"ok": True, "publicavel": True, "concluido_em_utc": datetime.now(timezone.utc).isoformat(),
            "fontes_sha256": fontes, "integridade_historica": integridade, "resultados": resultados,
            "codigo_auditor_sha256": sha256(Path(__file__)),
            "limite": "Comparacao retrospectiva; nao demonstra causa climatica"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saida-experimentos", type=Path, default=RAIZ / "resultados/quantizacao_todos_modelos_20260929")
    ap.add_argument("--auditoria-longo", type=Path, required=True)
    ap.add_argument("--auditoria-curto", type=Path, required=True)
    ap.add_argument("--auditoria-dados", type=Path, required=True)
    ap.add_argument("--protocolo-longo", type=Path, default=REL_HISTORICO / "protocolo_historico_1998_2022.json")
    ap.add_argument("--protocolo-curto", type=Path, default=REL_HISTORICO / "protocolo_historico_curto_pareado.json")
    ap.add_argument("--relatorio", type=Path, required=True)
    args = ap.parse_args()
    args.relatorio.parent.mkdir(parents=True, exist_ok=True)
    try:
        resultado = auditar(args)
    except Exception as exc:
        args.relatorio.write_text(json.dumps({"ok": False, "publicavel": False,
            "erro": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    args.relatorio.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Pareamento aprovado: {len(resultado['resultados'])} grades; 70 fontes e 88 contratos conferidos.")


if __name__ == "__main__":
    main()
