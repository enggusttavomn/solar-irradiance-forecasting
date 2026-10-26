"""Painel local, somente leitura, dos experimentos de quantizacao.

Nao importa motores, nao treina modelos e nao substitui a auditoria cientifica.
As barras contam pares modelo/caso. A ETA usa duracoes do mesmo contrato/fase.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit

from scripts.processos_quantizacao import mesma_instancia
from scripts.estimativa_tempo_quantizacao import estimar_restante

RAIZ = Path(__file__).resolve().parents[1]
BASE = Path("relatorios/quantizacao_todos_modelos_20260929")
RESULTADOS = Path("resultados/quantizacao_todos_modelos_20260929")
APP_ID = "tcc-progresso-quantizacao-v1"
TAREFAS = {
    "hourly_72_extension": "Horário · até 72 h",
    "daily_30": "Diário · até 30 dias",
    "monthly_1": "Mensal · 1 mês",
    "monthly_6": "Mensal · 6 meses",
}
MODELOS = ("TimesNet", "XGBoost", "LSTM", "DilatedRNN", "GRU", "Transformer",
           "Informer", "ARIMA", "Persistencia", "Sazonal ingenuo", "Climatologia")
REGIMES = {
    "atual": "Base atual · 2019–2024",
    "historico_1998_2022": "Histórico longo · 1998–2022",
    "historico_curto_pareado": "Histórico curto · comparação pareada",
}
VARIANTES = ("sem_quantizacao", "q64", "q128", "q256")
TERMINAIS = {"concluida", "selecao_concluida", "erro", "interrompida",
             "pronto_para_revisao_visual"}
RUNNERS = (
    "fila_aprendidos/atual/completa/runner.json",
    "fila_atencao/atual/completa/runner.json",
    "fila_estatisticos/atual/completa/runner.json",
    "fila_integral_atual/atual/completa/runner.json",
    "fila_historica/historico_1998_2022/completa/runner.json",
    "fila_historica/historico_curto_pareado/completa/runner.json",
    "recuperacao_20261001/runner.json",
    "recuperacao_xgboost_20261001/runner.json",
)
RECUPERACAO = "recuperacao_20261001/runner.json"
RECUPERACAO_XGBOOST = "recuperacao_xgboost_20261001/runner.json"


def slug(modelo):
    return modelo.lower().replace(" ", "_")


def idade(instante, agora):
    try:
        return max(0, (agora - datetime.fromisoformat(instante)).total_seconds())
    except (ValueError, TypeError):
        return None


class Leitor:
    def __init__(self):
        self.cache = {}
        self.avisos = set()

    def json(self, path):
        path = Path(path)
        try:
            stat = path.stat()
            assinatura = (stat.st_mtime_ns, stat.st_size)
            anterior = self.cache.get(path)
            if anterior and anterior[0] == assinatura:
                return anterior[1]
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("Registro deve ser um objeto.")
            self.cache[path] = (assinatura, data)
            return data
        except FileNotFoundError:
            self.cache.pop(path, None)
            return {}
        except (OSError, ValueError) as exc:
            # Nunca reutilizar um valor antigo como se fosse leitura atual.
            self.cache.pop(path, None)
            self.avisos.add(f"Não foi possível ler {path.name}: {type(exc).__name__}")
            return {}


def contar_par(pasta, leitor):
    status = leitor.json(pasta / "status.json")
    selecao = leitor.json(pasta / "selecao_congelada.json")
    contrato = leitor.json(pasta / "contrato_execucao.json")
    modos = [obj["modo"] for obj in (status, contrato) if "modo" in obj]
    completa = bool(modos) and all(modo == "completa" for modo in modos)
    pronta = completa and (
        selecao.get("selecao_concluida_antes_refit") is True
        or selecao.get("selecao_concluida_antes_do_teste") is True
    )
    # A conclusao local nao significa que a auditoria global foi aprovada.
    refit = pronta and status.get("etapa") == "concluida"
    return {"selecao": bool(pronta), "refit": bool(refit),
            "reutilizado": status.get("reutilizado") is True}


def situacao_processo(estado, agora, checar=mesma_instancia):
    etapa = estado.get("etapa", "")
    if etapa in TERMINAIS:
        return etapa
    registro = estado.get("identidade_runner") or estado.get("identidade_coordenador")
    atraso = idade(estado.get("atualizado_em_utc"), agora)
    if not registro or atraso is None or atraso > 90:
        return "sem_atualizacao"
    try:
        return "ativo" if checar(registro) else "parado"
    except (OSError, ValueError, KeyError):
        return "processo_nao_confirmado"


def mais_recente(novo, anterior):
    """A recuperacao so substitui um registro anterior, nunca uma nova fila."""
    try:
        return (datetime.fromisoformat(novo["iniciado_em_utc"])
                > datetime.fromisoformat(anterior["atualizado_em_utc"]))
    except (KeyError, TypeError, ValueError):
        return False


def falhas_pendentes(raiz, estado, leitor, *, ignorar=()):
    """Falhas de pares continuam visiveis enquanto outros jobs executam."""
    regime = estado.get("regime")
    if regime not in REGIMES:
        return []
    falhas = []
    for registro in estado.get("falhas", []):
        tarefa, modelo = registro.get("tarefa"), registro.get("modelo")
        if tarefa not in TAREFAS or modelo not in MODELOS or (tarefa, modelo) in ignorar:
            continue
        fase = registro.get("fase") or estado.get("etapa") or "execucao"
        par = contar_par(raiz / RESULTADOS / regime / tarefa / slug(modelo), leitor)
        if par["refit"] or (fase == "selecao" and par["selecao"]):
            continue
        falhas.append({"regime": regime, "tarefa": tarefa, "modelo": modelo,
                       "fase": fase, "returncode": registro.get("returncode")})
    return falhas


def registros_sementes(pasta, fase, leitor):
    """Metadados leves: mesmo contrato/fase, nunca checkpoints ou dados."""
    contrato = leitor.json(pasta / "contrato_execucao.json")
    if contrato.get("modo") != "completa":
        return 0, []
    sementes = contrato.get("parametros", {}).get("sementes", [])
    registros = []
    for variante in VARIANTES:
        for seed in sementes:
            meta = leitor.json(pasta / variante / fase / f"seed{seed}.json")
            if (meta.get("concluido_em_utc") and meta.get("fase") == fase
                    and meta.get("seed") == seed and meta.get("variante") == variante
                    and meta.get("contrato_sha256") == contrato.get("sha256_contrato")
                    and (pasta / variante / fase / f"seed{seed}.npz").is_file()):
                registros.append(meta)
    return 4 * len(sementes), registros


def estimativa_modelo(pasta, fase, leitor, agora, **kwargs):
    total, registros = (registros_sementes(pasta, fase, leitor)
                       if fase in ("selecao", "refit") else (0, []))
    if not total:
        return {"status": "sem_base", "min_s": None, "max_s": None,
                "amostras": 0, "restantes": None}
    kwargs.setdefault("encerrando", len(registros) == total)
    return estimar_restante(registros, total, agora, **kwargs)


def detalhe_job(raiz, estado, job, leitor, agora):
    regime = estado["regime"]
    tarefa, modelo = job["tarefa"], job["modelo"]
    fase = job.get("fase", estado.get("etapa", "selecao"))
    pasta = raiz / RESULTADOS / regime / tarefa / slug(modelo)
    total, registros = (registros_sementes(pasta, fase, leitor)
                       if fase in ("selecao", "refit") else (0, []))
    prontas = len(registros)
    ultima = ("Conferindo a reproducao do controle CPU/CUDA"
              if fase == "verificacao_controle" else "Preparando dados ou conferindo resultados salvos")
    log = Path(job.get("log", ""))
    if not log.is_absolute():
        log = raiz / log
    try:
        # Os logs vem dos runners locais; nenhum caminho fornecido pelo navegador.
        log.resolve().relative_to(raiz.resolve())
        with log.open("rb") as stream:
            stream.seek(max(0, log.stat().st_size - 32768))
            trecho = stream.read().decode("utf-8", errors="replace")
        linhas = trecho.rsplit("\nInicio ", 1)[-1].splitlines()
        progressos = [x for x in linhas if re.search(r"(?:seed=|localidade|niveis=|/q(?:64|128|256)/)", x)
                      and not x.startswith((" ", "Traceback"))]
        if progressos:
            ultima = progressos[-1][:240]
    except (OSError, ValueError):
        pass
    iniciou_unidade = bool(re.search(r"/(?:selecao|refit)(?: seed=-?\d+)? inicio$", ultima))
    if total:
        eta = estimar_restante(registros, total, agora, inicio=job.get("inicio"),
                              executando=iniciou_unidade, encerrando=prontas == total)
    else:
        eta = {"status": "sem_base", "min_s": None, "max_s": None,
               "amostras": 0, "restantes": None}
    return {"regime": regime, "modelo": modelo, "tarefa": tarefa,
            "caso": TAREFAS.get(tarefa, tarefa), "fase": fase,
            "inicio": job.get("inicio"), "decorrido_s": idade(job.get("inicio"), agora),
            "sementes_concluidas": prontas, "sementes_total": total,
            "atividade": ultima, "estimativa": eta}


def estimativa_fila(raiz, estado, path, ativos, leitor, agora):
    """Duas filas iniciais conhecidas: um worker GPU em cada fila, em paralelo.

    Outras filas podem misturar CPU/GPU; sem capacidade registrada nao se
    inventa uma soma sequencial. As ETAs individuais seguem disponiveis.
    """
    if path not in RUNNERS[:2] or estado.get("etapa") != "selecao":
        return None
    pares = {tuple(p) for p in estado.get("pendentes", [])}
    pares.update((j["tarefa"], j["modelo"]) for j in estado.get("processos", []))
    detalhes = []
    for tarefa, modelo in sorted(pares):
        pasta = raiz / RESULTADOS / estado["regime"] / tarefa / slug(modelo)
        if contar_par(pasta, leitor)["selecao"]:
            continue
        job = next((j for j in ativos if j["regime"] == estado["regime"]
                    and j["tarefa"] == tarefa and j["modelo"] == modelo), None)
        eta = job["estimativa"] if job else estimativa_modelo(pasta, "selecao", leitor, agora)
        detalhes.append({"tarefa": tarefa, "modelo": modelo, **eta})
    medidas = [d for d in detalhes if d.get("min_s") is not None
               and d.get("max_s") is not None]
    return {"pares": [[d["tarefa"], d["modelo"]] for d in detalhes],
            "medidos": len(medidas), "pendentes": len(detalhes),
            "min_s": sum(d["min_s"] for d in medidas),
            "max_s": sum(d["max_s"] for d in medidas)}


def resumir_estimativa(foco, filas, alertas, concluido):
    base = {"status": "sem_base", "min_s": None, "max_s": None,
            "medidos": 0, "pendentes": None, "escopo": "etapa_atual"}
    if concluido:
        return {**base, "status": "concluido"}
    if alertas:
        return {**base, "status": "suspensa"}
    if foco.get("regime") != "atual" or foco.get("titulo") != "Escolha das configurações":
        return base
    estimativas = [f["estimativa"] for f in filas if f.get("estimativa")]
    medidos = sum(e["medidos"] for e in estimativas)
    pendentes = foco["total"] - foco["feito"]
    pares = {tuple(p) for e in estimativas for p in e["pares"]}
    if not medidos:
        return {**base, "pendentes": pendentes}
    completa = len(pares) == pendentes == medidos
    # Filas GPU paralelas: usar o caminho mais longo, nao somar as duas filas.
    return {**base, "status": "estimado" if completa else "parcial",
            "min_s": max(e["min_s"] for e in estimativas),
            "max_s": max(e["max_s"] for e in estimativas),
            "medidos": medidos, "pendentes": pendentes}


def auditoria_pronta(data, regime):
    return (data.get("ok") is True and data.get("publicavel") is True
            and data.get("escopo_completo") is True
            and data.get("replay_novo_executado") is True
            and data.get("modo") == "completa" and data.get("regime") == regime
            and data.get("pares_verificados") == 44)


def montar_estado(raiz=RAIZ, leitor=None, agora=None, checar=mesma_instancia):
    raiz = Path(raiz)
    leitor = leitor or Leitor()
    leitor.avisos.clear()
    agora = agora or datetime.now(timezone.utc)
    rel = raiz / BASE
    grupos, alertas, ativos, filas, falhas = [], [], [], [], []
    for regime, rotulo in REGIMES.items():
        pares = []
        for tarefa in TAREFAS:
            for modelo in MODELOS:
                par = contar_par(raiz / RESULTADOS / regime / tarefa / slug(modelo), leitor)
                pares.append({"tarefa": tarefa, "modelo": modelo, **par})
        audit_path = rel / ("auditoria_final_atual" if regime == "atual"
                            else "auditoria_" + regime) / "auditoria.json"
        grupos.append({"id": regime, "rotulo": rotulo, "total": 44,
                       "selecao": sum(p["selecao"] for p in pares),
                       "refit": sum(p["refit"] for p in pares),
                       "auditoria": auditoria_pronta(leitor.json(audit_path), regime),
                       "pares": pares})

    # Uma fila integral nova substitui os erros antigos das filas iniciais.
    integral = leitor.json(rel / RUNNERS[3])
    recuperacoes = {path: leitor.json(rel / path)
                   for path in (RECUPERACAO, RECUPERACAO_XGBOOST)}
    recuperacoes_ativas = {path: registro for path, registro in recuperacoes.items()
                          if registro.get("modo") == "completa"
                          and registro.get("regime") == "atual"
                          and situacao_processo(registro, agora, checar) == "ativo"}
    recuperacao_ativa = bool(recuperacoes_ativas)
    recuperacao = max(recuperacoes_ativas.values(),
                     key=lambda r: r.get("iniciado_em_utc", ""), default={})
    escopo = (leitor.json(rel / "recuperacao_20261001/escopo.json")
              if RECUPERACAO in recuperacoes_ativas else {})
    pares_recuperacao = {tuple(par) for par in escopo.get("pares", [])
                        if isinstance(par, (list, tuple)) and len(par) == 2}
    if RECUPERACAO_XGBOOST in recuperacoes_ativas:
        pares_recuperacao.add(("hourly_72_extension", "XGBoost"))
    for path in (RECUPERACAO, RECUPERACAO_XGBOOST, *RUNNERS[:-2]):
        if integral and path in RUNNERS[:3]:
            continue
        estado = leitor.json(rel / path)
        if not estado or estado.get("modo") != "completa":
            continue
        situacao = situacao_processo(estado, agora, checar)
        substituida = (path == RUNNERS[3] and recuperacao_ativa
                       and situacao != "ativo" and mais_recente(recuperacao, estado))
        if substituida:
            situacao = "substituida_pela_recuperacao"
        fila = {"arquivo": path, "etapa": estado.get("etapa"),
                "situacao": situacao, "atualizado_em_utc": estado.get("atualizado_em_utc")}
        filas.append(fila)
        falhas.extend(falhas_pendentes(raiz, estado, leitor,
                                     ignorar=pares_recuperacao if substituida else ()))
        if situacao in ("erro", "interrompida", "parado", "sem_atualizacao", "processo_nao_confirmado"):
            alertas.append(f"{REGIMES.get(estado.get('regime'), 'Fila')} · {situacao.replace('_', ' ')}")
        if situacao == "ativo":
            for job in estado.get("processos", []):
                ativos.append(detalhe_job(raiz, estado, job, leitor, agora))
            fila["estimativa"] = estimativa_fila(raiz, estado, path, ativos, leitor, agora)

    for falha in falhas:
        alertas.append(f"{TAREFAS[falha['tarefa']]} · {falha['modelo']} · "
                       f"falha em {falha['fase'].replace('_', ' ')}; execucao ainda pendente")

    coords = []
    for nome in ("atual", "historica"):
        estado = leitor.json(rel / f"coordenacao_{nome}/status.json")
        if not estado:
            continue
        situacao = situacao_processo(estado, agora, checar)
        if (nome == "atual" and recuperacao_ativa and situacao != "ativo"
                and mais_recente(recuperacao, estado)):
            situacao = "em_recuperacao"
        coords.append({"id": nome, "etapa": estado.get("etapa"), "situacao": situacao,
                       "atualizado_em_utc": estado.get("atualizado_em_utc")})
        if situacao in ("erro", "interrompida", "parado", "sem_atualizacao", "processo_nao_confirmado"):
            alertas.append(f"Coordenação {nome} · {situacao.replace('_', ' ')}"
                           + (f": {estado['erro'][:180]}" if estado.get("erro") else ""))

    # O PDF antigo ja existe: sua presenca nunca significa nova entrega pronta.
    entregas = []
    for nome, destino, pasta_pdf in (
        ("Base atual", "tabela_resultados_ghi_2024.pdf", "pdf_atual"),
        ("Históricos comparados", "tabela_resultados_ghi_1998_2022.pdf", "pdf_historico"),
    ):
        etapa = "aguardando"
        manifesto = leitor.json(rel / pasta_pdf / "manifesto.json")
        pdf_meta = manifesto.get("pdf", {})
        if pdf_meta.get("sha256") and pdf_meta.get("paginas"):
            etapa = "revisao_pendente"
        # Registro exclusivo produzido pelo script de entrega; busca restrita aos
        # pequenos registros do diretorio principal e da pasta PDF, sem rglob.
        recibos = list((rel / pasta_pdf).glob("*.json")) + list(rel.glob("*entrega*.json"))
        for path in recibos:
            recibo = leitor.json(path)
            pdf = recibo.get("pdf", {})
            if (recibo.get("entregue_em_utc") and recibo.get("evidencias")
                    and pdf.get("sha256") == pdf_meta.get("sha256")
                    and pdf.get("sha256")
                    and Path(pdf.get("path", "")).resolve() == (raiz / "documentacao" / destino).resolve()):
                etapa = "entregue"
                break
        entregas.append({"nome": nome, "arquivo": destino, "etapa": etapa})

    foco = None
    for grupo in grupos:
        if grupo["selecao"] < 44:
            foco = {"regime": grupo["id"], "titulo": "Escolha das configurações",
                    "feito": grupo["selecao"], "total": 44}
            break
        if grupo["refit"] < 44:
            foco = {"regime": grupo["id"], "titulo": "Treinamento final",
                    "feito": grupo["refit"], "total": 44}
            break
        if not grupo["auditoria"]:
            foco = {"regime": grupo["id"], "titulo": "Conferência dos resultados",
                    "feito": None, "total": None}
            break
    concluido = (all(e["etapa"] == "entregue" for e in entregas)
                 and all(g["selecao"] == 44 and g["refit"] == 44
                         and g["auditoria"] for g in grupos))
    if foco is None:
        foco = {"regime": None, "titulo": "PDFs entregues" if concluido else "Preparação e revisão dos PDFs",
                "feito": None, "total": None}
    avisos = sorted(set(alertas) | leitor.avisos)
    return {"app": APP_ID, "interface_versao": 2,
            "gerado_em_utc": agora.isoformat(), "intervalo_s": 10,
            "foco": foco, "regimes": grupos, "tarefas": TAREFAS, "modelos": list(MODELOS),
            "ativos": ativos, "filas": filas, "coordenadores": coords,
            "falhas": falhas,
            "alertas": avisos,
            "estimativa": resumir_estimativa(foco, filas, avisos, concluido),
            "entregas": entregas, "concluido": concluido,
            "nota": "Percentuais por combinações modelo/caso concluídas; não representam tempo restante. "
                    "Cada combinação inclui sem quantização, 64, 128 e 256 níveis. "
                    "O painel lê os registros; as auditorias científicas são executadas separadamente."}


class Painel:
    def __init__(self, raiz):
        self.raiz = Path(raiz)
        self.leitor = Leitor()
        self.lock = threading.Lock()
        self.cache = None
        self.em = 0.0

    def estado(self):
        with self.lock:
            if self.cache is None or time.monotonic() - self.em >= 8:
                self.cache = montar_estado(self.raiz, self.leitor)
                self.em = time.monotonic()
            return self.cache


def handler(painel):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            host = self.headers.get("Host", "").split(":")[0].lower()
            if host not in ("127.0.0.1", "localhost"):
                self.send_error(403)
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/status":
                    body = json.dumps(painel.estado(), ensure_ascii=False).encode("utf-8")
                    tipo = "application/json; charset=utf-8"
                elif path == "/health":
                    body = json.dumps({"app": APP_ID}).encode()
                    tipo = "application/json"
                elif path in ("/", "/index.html"):
                    body = (painel.raiz / "relatorios/painel_treinamentos.html").read_bytes()
                    tipo = "text/html; charset=utf-8"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; "
                                 "style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; "
                                 "frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                print(f"Erro ao ler painel: {type(exc).__name__}: {exc}", flush=True)
                self.send_error(503, "Leitura indisponivel; tentar novamente.")

        def log_message(self, fmt, *args):
            if len(args) > 1 and str(args[1]) not in ("200", "304"):
                super().log_message(fmt, *args)
    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--json", action="store_true", help="Uma leitura, sem iniciar servidor")
    args = ap.parse_args()
    if args.json:
        print(json.dumps(montar_estado(), ensure_ascii=False, indent=2))
        return
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(Painel(RAIZ)))
    print(f"Painel: http://127.0.0.1:{args.port} · somente leitura", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
