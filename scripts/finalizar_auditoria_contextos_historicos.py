"""Documenta a disponibilidade real sem modificar dados ou o motor congelado.

Preserva a auditoria bruta, inclusive seu alerta de contagem, e emite parecer
separado para a diferenca comprovada entre grade teorica e janelas completas.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

RAIZ = Path(__file__).resolve().parents[1]
REL = RAIZ / "relatorios/quantizacao_todos_modelos_20260929/historico"
MOTOR = RAIZ / "codigo_fonte/experimento_quantizacao_concorrentes.py"
MOTOR_ESPERADO = "ca56d2040cc7c0bb1ec353464b861bf75c690a9330e543272eb58ca26450769a"
CODEX = Path(r"C:\Users\gm.nascimento\.vscode\extensions\openai.chatgpt-26.917.62051-win32-x64\bin\windows-x86_64\codex.exe")
REV = REL / "revisao_documental_fuso_cobertura_20260930"
SEMANTICA = (
    "Arquivos horarios armazenam UTC; origens e cortes dos modelos usam horario "
    "local fixo NSRDB em todas as resolucoes, sem horario de verao. Campos de "
    "IntervaloParticao descrevem a grade teorica de calendario. As metricas usam "
    "somente janelas completas efetivamente disponiveis e construidas."
)
MOTIVO = (
    "A fonte horaria termina em 2022-12-31 23:00 UTC, equivalente a 15:00--20:00 "
    "locais nos fusos de -8 a -3. A origem teorica 2022-12-29 00:00 local exige "
    "72 horas ate 2022-12-31 23:00 local, indisponiveis. Ela e excluida pelo "
    "construtor canonico. Restam 1368 origens por localidade, terminando em "
    "2022-12-28 00:00 local, com ultimo alvo em 2022-12-30 23:00 local. "
    "A grade teorica contem 1369, nao observadas. Nao se incorporou 2023 nem "
    "se imputou dado. Ambos os perfis e todos os modelos usam as mesmas janelas."
)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def hash_obj(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def ler(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def texto_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def salvar(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(texto_json(obj), encoding="utf-8")


def atualizar_com_patch(path, novo):
    velho = path.read_text(encoding="utf-8")
    if velho == novo:
        return
    if path.suffix == ".json":
        # Relatorios gerados, com originais preservados e hashes revisados.
        path.write_text(novo, encoding="utf-8")
        return
    linhas = ["*** Begin Patch", f"*** Update File: {path.as_posix()}", "@@"]
    linhas += ["-" + s for s in velho.splitlines()]
    linhas += ["+" + s for s in novo.splitlines()]
    linhas += ["*** End Patch", ""]
    subprocess.run([str(CODEX), "--codex-run-as-apply-patch", "\n".join(linhas)],
                   cwd=RAIZ, check=True, capture_output=True, text=True, encoding="utf-8")


def main():
    assert digest(MOTOR) == MOTOR_ESPERADO
    contrato_path = REL / "contrato_historico_pareado.json"
    bruto_path = REL / "validacao_contextos_historicos.json"
    contrato = ler(contrato_path)
    bruto = ler(bruto_path)
    assert "revisao_documental" not in contrato, "Revisao ja aplicada; nao sobrescrever evidencia."
    assert bruto["contextos_construidos"] == 32 and len(bruto["resultados"]) == 32
    assert all(p["mesmos_alvos_origens_contextos_brutos_entre_perfis_e_modelos"]
               for p in bruto["comparacoes_pareadas"])
    assert all(p["todas_particoes_iguais_entre_concorrentes_e_TimesNet"]
               for p in bruto["comparacoes_entre_modelos_por_perfil"])
    assert bruto["argumento_modelo_sem_ramo_no_contexto"]
    assert not bruto["treinamentos_iniciados"]
    antigos = {}
    for regime in ("historico_1998_2022", "historico_curto_pareado"):
        p = REL / f"protocolo_{regime}.json"
        antigos[regime] = {"arquivo": p, "objeto": ler(p), "sha256": digest(p)}
    fisicos = []
    for tipo, entradas in contrato["entradas"].items():
        for e in entradas:
            arquivo = RAIZ / e["arquivo"]
            atual = digest(arquivo)
            assert atual == e["sha256"], f"Fonte alterada: {arquivo}"
            assert arquivo.stat().st_size == e["bytes"]
            fisicos.append({"grupo": tipo, "arquivo": e["arquivo"], "sha256": atual,
                            "bytes": arquivo.stat().st_size, "coincide_com_coleta": True})
    assert len(fisicos) == 70
    for e in [contrato["manifesto_horario"], *contrato["auditorias"].values()]:
        assert digest(RAIZ / e["arquivo"]) == e["sha256"]
    assert contrato["sha256_contrato"] == hash_obj({k: v for k, v in contrato.items() if k != "sha256_contrato"})
    cobertura = []
    aceitos = []
    arquivos_contextos = []
    for r in bruto["resultados"]:
        assert r["motor_sha256"] == MOTOR_ESPERADO
        assert r["protocolo_sha256"] == antigos[r["regime"]]["sha256"]
        assert r["escalas_recalculadas_train_only"] and not r["contextos_anteriores_ao_inicio"]
        assert not r["treinamento_iniciado"]
        assert r["seq_len"] == r["seq_len_otimizado_esperado"]
        p = REL / "validacao_estrutural" / r["regime"] / r["tarefa"] / r["fase"] / f'{r["grupo"]}.json'
        assert ler(p) == r
        arquivos_contextos.append({"arquivo": p.relative_to(RAIZ).as_posix(), "sha256": digest(p)})
        conhecidos = []
        for parte, v in r["particoes"].items():
            assert v["alvos_e_contextos_reconstruidos_da_fonte"]
            assert len(v["origens_por_localidade"]) == 10
            assert v["n"] == sum(v["origens_por_localidade"].values())
            for nome, n in v["origens_por_localidade"].items():
                if n != v["origens_declaradas_por_localidade"]:
                    assert r["tarefa"] == "hourly_72_extension" and r["fase"] == "refit" and parte == "teste"
                    assert n == 1368 and v["origens_declaradas_por_localidade"] == 1369
                    conhecidos.append(f"{parte}/{nome}: contrato declara 1369 origens, disponiveis e construidas 1368.")
                    c = next(c for c in v["cobertura"] if c["localidade"] == nome)
                    assert c["origem_final"] == "2022-12-28 00:00:00"
                    assert c["ultimo_alvo"] == "2022-12-30 23:00:00"
            if r["grupo"] == "TimesNet":
                cobertura.append({"regime": r["regime"], "tarefa": r["tarefa"], "fase": r["fase"],
                    "particao": parte, "seq_len": r["seq_len"], "pred_len": r["pred_len"],
                    "origens_teoricas_por_localidade": v["origens_declaradas_por_localidade"],
                    "origens_efetivas_por_localidade": v["origens_por_localidade"],
                    "origens_efetivas_total": v["n"], "cobertura_local": v["cobertura"],
                    "compartilhada_por_todos_os_modelos": True,
                    "diferenca_teorica_efetiva": bool(conhecidos),
                    "motivo_diferenca": MOTIVO if conhecidos else None})
        assert sorted(r["erros"]) == sorted(conhecidos), "Ha erro nao classificado pela disponibilidade."
        assert r["ok"] == (not conhecidos)
        if conhecidos:
            aceitos.append({"regime": r["regime"], "tarefa": r["tarefa"], "fase": r["fase"],
                "grupo": r["grupo"], "alertas_brutos_preservados": conhecidos, "interpretacao": MOTIVO})
    assert len(aceitos) == 4 and len(cobertura) == 32
    hora = datetime.now(timezone.utc).isoformat()
    originais = [contrato_path, bruto_path, REL / "PROVENIENCIA_E_AGREGACAO.md"]
    originais += [v["arquivo"] for v in antigos.values()]
    preservados = []
    for p in originais:
        destino = REV / "originais" / p.name
        assert not destino.exists()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(p.read_bytes())
        preservados.append({"arquivo": destino.relative_to(RAIZ).as_posix(), "sha256": digest(destino)})
    novo = copy.deepcopy(contrato)
    novo["definicoes"]["cortes"] = SEMANTICA
    novo["definicoes"]["horario"] = "Armazenamento em UTC: media dos minutos 00 e 30. Modelagem e cortes em horario local fixo NSRDB."
    novo["revisao_documental"] = {"data_utc": hora, "altera_dados": False, "altera_motor": False,
        "altera_datas_operacionais": False, "contrato_anterior_sha256": contrato["sha256_contrato"],
        "arquivo_contrato_anterior_sha256": digest(contrato_path),
        "motivo": "Precisar fuso dos cortes e distinguir grade teorica de janelas observadas; nenhuma amostra ou janela alterada."}
    novo["cobertura_janelas_modelos"] = cobertura
    novo["auditoria_estrutural"] = {"aprovado": True, "contextos_construidos": 32,
        "relatorio_bruto": {"arquivo": bruto_path.relative_to(RAIZ).as_posix(), "sha256": digest(bruto_path)},
        "ok_bruto": bruto["ok"], "motivo_ok_bruto_false": MOTIVO,
        "limite_disponibilidade_aceito_sem_imputacao": True,
        "mesmos_alvos_entre_perfis_e_modelos": True, "escalas_somente_treino": True,
        "contexto_nunca_anterior_ao_perfil": True,
        "contagem_usada_metricas": "Comprimento dos vetores reais em ctx.janelas; nunca origens_esperadas_por_localidade.",
        "hash_motor_congelado": MOTOR_ESPERADO}
    novo.pop("sha256_contrato")
    novo["sha256_contrato"] = hash_obj(novo)
    atualizar_com_patch(contrato_path, texto_json(novo))
    hash_novo = digest(contrato_path)
    protocolos = []
    for regime, v in antigos.items():
        p = copy.deepcopy(v["objeto"])
        p["sha256_contrato_preparacao"] = novo["sha256_contrato"]
        p["sha256_arquivo_contrato_preparacao"] = hash_novo
        p["semantica_temporal_documental"] = SEMANTICA
        p["cobertura_janelas_documental"] = [c for c in cobertura if c["regime"] == regime]
        excluir = {"sha256_contrato_preparacao", "sha256_arquivo_contrato_preparacao",
                   "semantica_temporal_documental", "cobertura_janelas_documental"}
        operacional_antes = {k: x for k, x in v["objeto"].items() if k not in excluir}
        operacional_depois = {k: x for k, x in p.items() if k not in excluir}
        assert operacional_antes == operacional_depois
        atualizar_com_patch(v["arquivo"], texto_json(p))
        protocolos.append({"regime": regime, "arquivo": v["arquivo"].relative_to(RAIZ).as_posix(),
            "protocolo_sha256_ao_executar_contextos": v["sha256"],
            "protocolo_sha256_documental_atual": digest(v["arquivo"]),
            "operacao_antes_depois_identica": True, "sha256_campos_operacionais": hash_obj(operacional_antes),
            "campos_apenas_documentais_alterados_ou_adicionados": sorted(excluir)})
    proveniencia = REL / "PROVENIENCIA_E_AGREGACAO.md"
    adendo = "\n## Cortes dos modelos e janelas efetivas (auditoria estrutural)\n\n"
    adendo += SEMANTICA + "\n\n" + MOTIVO + "\n\n"
    adendo += ("Foram construidos 32 contextos, sem treinar: quatro tarefas, duas fases, "
        "dois perfis e dois grupos (concorrentes/TimesNet). As oito comparacoes de "
        "avaliacao longo/curto e as 16 comparacoes por perfil entre grupos preservam "
        "origens, entradas brutas e alvos exatos. As escalas foram recalculadas apenas "
        "com o treino de cada fase; nenhum contexto antecede o inicio do perfil.\n\n"
        "A TimesNet conserva contextos de 336 horas, 365 dias e 12 meses, iguais aos "
        "vencedores puros registrados. No perfil curto, o metadado horario da escala "
        "pode indicar janeiro de 2014, mas a serie foi filtrada em abril antes do "
        "ajuste; os valores e a contagem efetiva da escala foram conferidos.\n\n"
        "O relatorio bruto preserva os quatro alertas de contagem teorica. O parecer "
        "final `auditoria_contextos_historicos_aprovada.json` documenta sua "
        "classificacao como limite real de disponibilidade e os hashes anteriores "
        "e atuais dos protocolos. A revisao e apenas documental: nao houve novo "
        "treinamento, alteracao do motor ou dos dados. Antes de qualquer treino, "
        "revalidar os hashes fisicos contra `entradas` do contrato de coleta.\n")
    atualizar_com_patch(proveniencia, proveniencia.read_text(encoding="utf-8") + adendo)
    assert digest(MOTOR) == MOTOR_ESPERADO
    assert ler(bruto_path) == bruto
    assert novo["entradas"] == contrato["entradas"]
    assert all(digest(RAIZ / e["arquivo"]) == e["sha256"] for e in fisicos)
    final = {"ok": True, "aprovado": True, "data_utc": hora,
        "objeto": "Construcao e integridade dos contextos; nenhum modelo historico treinado.",
        "treinamentos_historicos_iniciados": False, "motor_sha256": MOTOR_ESPERADO,
        "contrato": {"arquivo": contrato_path.relative_to(RAIZ).as_posix(),
                     "sha256_arquivo": hash_novo, "sha256_contrato": novo["sha256_contrato"]},
        "relatorio_bruto": {"arquivo": bruto_path.relative_to(RAIZ).as_posix(),
                            "sha256": digest(bruto_path), "ok_original_preservado": bruto["ok"]},
        "contextos_construidos": 32, "arquivos_contextos_brutos": arquivos_contextos,
        "comparacoes_pareadas": bruto["comparacoes_pareadas"],
        "comparacoes_entre_modelos_por_perfil": bruto["comparacoes_entre_modelos_por_perfil"],
        "limites_disponibilidade_documentados": aceitos,
        "cobertura_janelas": cobertura, "protocolos": protocolos,
        "integridade_fisica_reverificada": {"ok": True, "quantidade_arquivos": 70, "entradas": fisicos},
        "evidencia_metricas": {"codigo_fonte/experimento_quantizacao_concorrentes.py":
            {"sha256": MOTOR_ESPERADO, "funcao": "metricas", "linhas": "329-346"},
            "codigo_fonte/experimento_multirresolucao.py":
            {"sha256": digest(RAIZ / "codigo_fonte/experimento_multirresolucao.py"),
             "funcao": "_metricas_vetor", "linhas": "1400-1416"},
            "conclusao": "np.mean sobre vetores reais. N_origens_canonicas e metadado; contagens observadas sao separadas."},
        "proveniencia": {"arquivo": proveniencia.relative_to(RAIZ).as_posix(), "sha256": digest(proveniencia)},
        "originais_preservados": preservados,
        "limites": ["Validacao estrutural nao comprova qualidade preditiva.",
            "Hashes devem ser novamente conferidos antes do treino e da publicacao.",
            "Os hashes executados dos protocolos antigos ficam preservados; somente sua documentacao mudou."]}
    salvar(REL / "auditoria_contextos_historicos_aprovada.json", final)
    print(json.dumps({"ok": True, "contextos": 32, "fontes_hashadas": 70,
        "sha256_contrato": novo["sha256_contrato"], "sha256_arquivo_contrato": hash_novo,
        "protocolos": protocolos}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
