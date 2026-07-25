"""Gera as quatro paginas do site a partir dos resultados canonicos."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
RESULTADOS = RAIZ / "resultados" / "avaliacao_mensal_canonica"
PASTA_SITE = RAIZ / "site"

NOMES_LOCALIDADES = {
    "BMW San Luis Potosi": "BMW San Luis Potosí",
    "BYD Camacari": "BYD Camaçari",
    "Ford Rouge Electric Vehicle Center": "Ford Rouge",
    "GM Factory Zero": "GM Factory Zero",
    "Hyundai Metaplant Georgia": "Hyundai Georgia",
    "Lucid AMP 1 Casa Grande": "Lucid Casa Grande",
    "Rivian Normal": "Rivian Normal",
    "Tesla Fremont Factory": "Tesla Fremont",
    "Tesla Gigafactory Nevada": "Tesla Nevada",
    "Tesla Gigafactory Texas": "Tesla Texas",
}
NOMES_MODELOS = {
    "Persistencia": "Persistência",
    "Sazonal ingenuo": "Sazonal ingênuo",
}
MODELOS_ESPERADOS = {
    "Persistencia", "Sazonal ingenuo", "Climatologia", "XGBoost", "MLP",
    "RNN", "LSTM", "DilatedRNN", "DeepAR", "DeepNPTS",
}


def ler_csv(nome: str) -> list[dict[str, str]]:
    with (RESULTADOS / nome).open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def valor(linha: dict[str, str], chave: str) -> float:
    return float(linha[chave])


def carregar_dados() -> dict[str, object]:
    status = json.loads((RESULTADOS / "status_execucao.json").read_text(encoding="utf-8"))
    detalhes = status.get("detalhes", {})
    if (
        status.get("etapa") != "concluido"
        or detalhes.get("protocolo_canonico") is not True
        or detalhes.get("fonte_artigos_atuais") is not True
    ):
        raise RuntimeError("A avaliacao canonica nao esta concluida ou autorizada.")

    locais_csv = ler_csv("metricas_por_localidade.csv")
    medias_csv = ler_csv("metricas_medias_modelos.csv")
    auditoria_csv = ler_csv("auditoria_dados.csv")
    prob_csv = ler_csv("metricas_probabilisticas_medias.csv")
    pares = {(linha["Localidade"], linha["Modelo"]) for linha in locais_csv}
    if (
        len(locais_csv) != 100
        or len(pares) != 100
        or {linha["Localidade"] for linha in locais_csv} != set(NOMES_LOCALIDADES)
        or {linha["Modelo"] for linha in locais_csv} != MODELOS_ESPERADOS
        or any(int(linha["N_teste"]) != 12 for linha in locais_csv)
    ):
        raise RuntimeError("A grade canonica deve conter 10 modelos x 10 localidades.")

    ordem_modelos = [
        linha["Modelo"]
        for linha in sorted(medias_csv, key=lambda item: valor(item, "MAE_media_wm2"))
    ]
    metricas_locais = [
        {
            "localidade": linha["Localidade"],
            "modelo": linha["Modelo"],
            "mae": valor(linha, "MAE_wm2"),
            "mse": valor(linha, "MSE_wm4"),
            "rmse": valor(linha, "RMSE_wm2"),
            "r2": valor(linha, "R2"),
            "nrmse": valor(linha, "nRMSE_percentual"),
        }
        for linha in locais_csv
    ]
    ranking = []
    for posicao, linha in enumerate(
        sorted(medias_csv, key=lambda item: valor(item, "MAE_media_wm2")), start=1
    ):
        ranking.append(
            {
                "posicao": posicao,
                "modelo": linha["Modelo"],
                "modelo_exibicao": NOMES_MODELOS.get(linha["Modelo"], linha["Modelo"]),
                "mae": valor(linha, "MAE_media_wm2"),
                "dp": valor(linha, "MAE_dp_sementes_wm2"),
                "mse": valor(linha, "MSE_media_wm4"),
                "rmse": valor(linha, "RMSE_media_wm2"),
                "r2": valor(linha, "R2_medio"),
                "nrmse": valor(linha, "nRMSE_medio_percentual"),
            }
        )
    auditoria = [
        {
            "localidade": NOMES_LOCALIDADES[linha["Localidade"]],
            "inicio": linha["data_inicial"],
            "fim": linha["data_final"],
            "linhas": int(linha["linhas_brutas"]),
            "ausentes": int(linha["dias_ausentes"]),
            "duplicadas": int(linha["datas_duplicadas"]),
            "invalidas": int(linha["ghi_invalidas"]),
        }
        for linha in auditoria_csv
    ]
    probabilisticas = [
        {
            "modelo": linha["Modelo"],
            "crps": valor(linha, "CRPS_medio_wm2"),
            "picp": valor(linha, "PICP_medio_percentual"),
            "mpiw": valor(linha, "MPIW_medio_wm2"),
        }
        for linha in prob_csv
    ]
    return {
        "ordemModelos": ordem_modelos,
        "ordemLocalidades": list(NOMES_LOCALIDADES),
        "nomesLocalidades": NOMES_LOCALIDADES,
        "nomesModelos": {m: NOMES_MODELOS.get(m, m) for m in ordem_modelos},
        "metricasLocais": metricas_locais,
        "ranking": ranking,
        "auditoria": auditoria,
        "probabilisticas": probabilisticas,
        "statusAtualizado": status.get("atualizado_em_utc"),
    }


def navegacao(ativa: str) -> str:
    itens = (
        ("home", "index.html", "HOME"),
        ("data", "data.html", "DATA"),
        ("modelos", "modelos.html", "ML MODELS"),
        ("resultados", "resultados.html", "RESULTADOS"),
    )
    links_partes = []
    for chave, arquivo, rotulo in itens:
        atual = ' aria-current="page"' if chave == ativa else ""
        links_partes.append(f'<a href="{arquivo}"{atual}>{rotulo}</a>')
    links = "".join(links_partes)
    return f"""
<header class="topbar">
  <div class="nav-shell">
    <a class="brand" href="index.html"><span class="brand-mark">GHI</span><span>Monthly Forecast Study</span></a>
    <nav class="nav-links" aria-label="Navegação principal">{links}</nav>
  </div>
</header>"""


def pagina(*, titulo: str, descricao: str, ativa: str, kicker: str, chamada: str, corpo: str) -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{html.escape(descricao)}">
  <title>{html.escape(titulo)} · GHI Forecast</title>
  <link rel="stylesheet" href="assets/estilo.css">
</head>
<body>
{navegacao(ativa)}
<header class="page-hero{' compact' if ativa != 'home' else ''}">
  <span class="eyebrow">{html.escape(kicker)}</span>
  <h1>{chamada}</h1>
  <p>{html.escape(descricao)}</p>
</header>
<main>{corpo}</main>
<footer class="page-footer"><div class="container footer-inner"><span>Avaliação mensal canônica de GHI</span><span>Fonte oficial: <a href="../resultados/avaliacao_mensal_canonica/README.md">resultados canônicos</a></span></div></footer>
</body>
</html>"""


def pagina_home() -> str:
    corpo = """
<section><div class="container">
  <div class="section-head"><span class="kicker">Pergunta central</span><h2>O DeepNPTS supera alternativas mais simples?</h2><p class="lead">O projeto compara o DeepNPTS com seis modelos aprendidos e três referências temporais na previsão da GHI média do mês seguinte.</p></div>
  <div class="grid-2">
    <div class="card"><span class="card-number">OBJETIVO</span><h3>Previsão mensal de GHI</h3><p>Dez séries associadas a localidades de fábricas de veículos elétricos. As fábricas definem somente os pontos geográficos.</p></div>
    <div class="card dark-card"><span class="card-number">RESULTADO PRINCIPAL</span><h3>A climatologia obteve o menor erro</h3><p>Macro-MAE de 12,07 W/m². O DeepNPTS obteve 17,70 W/m² e ficou em 9º lugar entre dez métodos.</p></div>
  </div>
</div></section>
<section class="alt"><div class="container">
  <div class="section-head"><span class="kicker">Fluxo do projeto</span><h2>Da API ao artigo</h2></div>
  <div class="flow">
    <div class="flow-step"><span class="card-number">01</span><h3>Dados</h3><p>NSRDB, auditoria e agregação mensal.</p><small>Veja DATA</small></div>
    <div class="flow-step"><span class="card-number">02</span><h3>Preparação</h3><p>Contexto, quantização e atributos temporais.</p><small>Veja DATA</small></div>
    <div class="flow-step"><span class="card-number">03</span><h3>Modelos</h3><p>Dez métodos globais e referências simples.</p><small>Veja ML MODELS</small></div>
    <div class="flow-step"><span class="card-number">04</span><h3>Avaliação</h3><p>Walk-forward, métricas e comparação.</p><small>Veja RESULTADOS</small></div>
  </div>
</div></section>
<section><div class="container">
  <div class="section-head"><span class="kicker">Números do estudo</span><h2>Escopo em uma leitura</h2></div>
  <div class="grid-4">
    <div class="card"><strong style="font-size:2rem">10</strong><p>localidades</p></div>
    <div class="card"><strong style="font-size:2rem">72</strong><p>meses por série</p></div>
    <div class="card"><strong style="font-size:2rem">10</strong><p>métodos</p></div>
    <div class="card"><strong style="font-size:2rem">120</strong><p>alvos de teste</p></div>
  </div>
  <div class="button-row"><a class="button" href="data.html">Explorar os dados</a><a class="button secondary" href="resultados.html">Abrir resultados</a></div>
</div></section>"""
    return pagina(
        titulo="Home", ativa="home", kicker="TCC · previsão de séries temporais",
        chamada="Previsão mensal de irradiância solar.",
        descricao="Visão geral do projeto, do problema científico e do caminho entre dados, modelos e resultados.",
        corpo=corpo,
    )


def pagina_data(dados: dict[str, object]) -> str:
    linhas = "".join(
        f"<tr><td>{linha['localidade']}</td><td>{linha['inicio']} — {linha['fim']}</td><td>{linha['linhas']:,}</td><td>{linha['ausentes']}</td><td>{linha['duplicadas']}</td><td>{linha['invalidas']}</td></tr>".replace(",", ".")
        for linha in dados["auditoria"]
    )
    corpo = f"""
<section><div class="container">
  <div class="section-head"><span class="kicker">Fonte</span><h2>NLR / NSRDB</h2><p class="lead">Produto modelado GOES Aggregated PSM v4. Não são medições de solo nem dados internos das fábricas.</p></div>
  <div class="grid-3">
    <div class="card"><span class="card-number">RESOLUÇÃO DA API</span><h3>60 minutos</h3><p>Consulta anual da GHI para cada coordenada.</p></div>
    <div class="card"><span class="card-number">DADO PRESERVADO</span><h3>Média diária</h3><p>As 24 horas são agregadas, mantendo a unidade W/m².</p></div>
    <div class="card"><span class="card-number">COBERTURA</span><h3>2019–2024</h3><p>2.192 dias completos por localidade.</p></div>
  </div>
</div></section>
<section class="alt"><div class="container">
  <div class="section-head"><span class="kicker">Divisão temporal</span><h2>Contexto, treino e teste</h2></div>
  <div class="timeline"><div class="time"><strong>2019</strong><span>contexto inicial</span></div><div class="time train"><strong>2020–2023</strong><span>48 alvos de treinamento por localidade</span></div><div class="time"><strong>2024</strong><span>12 alvos de teste</span></div></div>
  <div class="notice" style="margin-top:20px"><strong>Sem vazamento:</strong> os parâmetros da transformação são estimados antes do teste. O valor real de cada mês de 2024 entra apenas no contexto da origem seguinte.</div>
</div></section>
<section><div class="container">
  <div class="section-head"><span class="kicker">Auditoria</span><h2>Integridade das dez séries</h2></div>
  <div class="table-wrap"><table><thead><tr><th>Localidade</th><th>Período</th><th>Dias</th><th>Ausentes</th><th>Duplicados</th><th>GHI inválida</th></tr></thead><tbody>{linhas}</tbody></table></div>
</div></section>
<section class="alt"><div class="container">
  <div class="section-head"><span class="kicker">Preparação</span><h2>Como as entradas são construídas</h2></div>
  <div class="grid-2">
    <div class="card"><h3>Transformação</h3><p>Média por mês civil, min–max por localidade, saturação em [0,1] e quantização uniforme em 128 níveis.</p></div>
    <div class="card"><h3>Atributos</h3><p>12 defasagens, médias de 3, 6 e 12 meses, seno/cosseno do mês-alvo e identificação da localidade.</p></div>
  </div>
  <div class="grid-2" style="margin-top:18px">
    <div class="code-card"><div class="code-head"><span>Coleta</span><a href="../codigo_fonte/coleta/api_nsrdb.py">abrir código</a></div><pre>coletar_ghi(
    lat=local["lat"],
    lon=local["lon"],
    start_year=2019,
    end_year=2024,
    inter=60,
)</pre></div>
    <div class="code-card"><div class="code-head"><span>Base mensal</span><a href="../codigo_fonte/preparacao/base_mensal.py">abrir código</a></div><pre>base = carregar_base_mensal(
    contexto=12,
    train_ratio=0.8,
    niveis_quantizacao=128,
)</pre></div>
  </div>
</div></section>"""
    return pagina(
        titulo="Data", ativa="data", kicker="Dados e preparação",
        chamada="Da NSRDB à base mensal.",
        descricao="Origem, cobertura, auditoria, divisão temporal e construção das entradas utilizadas pelos modelos.",
        corpo=corpo,
    )


def pagina_modelos() -> str:
    modelos = (
        ("Referência", "Persistência", "Repete o último mês observado.", "referencias_simples/persistencia.py"),
        ("Referência", "Sazonal ingênuo", "Usa o mesmo mês do ano anterior.", "referencias_simples/sazonal_ingenuo.py"),
        ("Referência", "Climatologia", "Média histórica do mês e da localidade.", "referencias_simples/climatologia.py"),
        ("Tabular", "XGBoost", "Árvores impulsionadas sobre atributos temporais.", "tabulares/xgboost.py"),
        ("Tabular", "MLP", "Rede densa aplicada à representação tabular.", "tabulares/mlp.py"),
        ("Recorrente", "RNN", "Recorrência simples sobre 12 meses.", "recorrentes/rnn.py"),
        ("Recorrente", "LSTM", "Recorrência com mecanismos de memória.", "recorrentes/lstm.py"),
        ("Recorrente", "DilatedRNN", "Saltos recorrentes de 1, 2 e 4 meses.", "recorrentes/dilated_rnn.py"),
        ("Probabilístico", "DeepAR", "Distribuição Student-t autorregressiva.", "probabilisticos/deepar.py"),
        ("Modelo principal", "DeepNPTS", "Distribuição discreta sobre valores do contexto.", "probabilisticos/deepnpts.py"),
    )
    cards = "".join(
        f'<article class="card model-card"><span class="model-type">{tipo}</span><h3>{nome}</h3><p>{descricao}</p><a href="../codigo_fonte/modelos/{arquivo}"><code>{arquivo}</code></a></article>'
        for tipo, nome, descricao, arquivo in modelos
    )
    corpo = f"""
<section><div class="container">
  <div class="section-head"><span class="kicker">Comparação</span><h2>Um arquivo para cada método</h2><p class="lead">O DeepNPTS é o objeto principal. Os demais métodos mostram se sua complexidade produz ganho sobre alternativas conhecidas.</p></div>
  <div class="grid-3">{cards}</div>
</div></section>
<section class="alt"><div class="container">
  <div class="section-head"><span class="kicker">Treinamento</span><h2>O que todos compartilham</h2></div>
  <div class="grid-4">
    <div class="card"><span class="card-number">GLOBAL</span><h3>Dez séries</h3><p>Um modelo por arquitetura e semente.</p></div>
    <div class="card"><span class="card-number">SEMENTES</span><h3>Cinco execuções</h3><p>11, 23, 42, 67 e 89.</p></div>
    <div class="card"><span class="card-number">HORIZONTE</span><h3>Um mês</h3><p>Uma previsão em cada origem.</p></div>
    <div class="card"><span class="card-number">TESTE</span><h3>Sem reajuste</h3><p>Pesos fixos durante 2024.</p></div>
  </div>
  <div class="notice" style="margin-top:20px"><strong>Importante:</strong> o DeepNPTS atual é o estimador discreto do GluonTS. Ele não é o antigo VHP baseado em uma regra manual de vizinhança.</div>
</div></section>"""
    return pagina(
        titulo="ML Models", ativa="modelos", kicker="Modelos de previsão",
        chamada="Dez métodos, uma comparação controlada.",
        descricao="Referências simples, modelos tabulares, redes recorrentes e previsores probabilísticos.",
        corpo=corpo,
    )


def pagina_resultados(dados: dict[str, object]) -> str:
    dados_json = html.escape(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), quote=False)
    corpo = """
<section><div class="container">
  <div class="section-head"><span class="kicker">Resultado principal</span><h2>A climatologia liderou o ranking.</h2><p class="lead">O DeepNPTS ficou em 9º lugar, com alta variação entre sementes. O ranking descreve esta janela retrospectiva; não estabelece superioridade universal.</p></div>
  <div class="grid-3">
    <div class="card dark-card"><span class="card-number">1º LUGAR</span><h3>Climatologia</h3><p>MAE de 12,07 W/m².</p></div>
    <div class="card"><span class="card-number">DEEP NPTS</span><h3>17,70 W/m²</h3><p>9º entre dez métodos.</p></div>
    <div class="card"><span class="card-number">VARIABILIDADE</span><h3>DP de 9,22 W/m²</h3><p>Forte sensibilidade às sementes.</p></div>
  </div>
</div></section>
<section class="alt"><div class="container">
  <div class="section-head"><span class="kicker">Tabela completa</span><h2>Todos os modelos × todas as localidades</h2><p class="lead">Selecione uma métrica. A borda preta marca o melhor método de cada localidade.</p></div>
  <div class="controls"><label>Métrica<select id="metric-select"><option value="mae">MAE (W/m²)</option><option value="rmse">RMSE (W/m²)</option><option value="mse">MSE (W²/m⁴)</option><option value="r2">R²</option><option value="nrmse">nRMSE (%)</option></select></label><div class="legend"><span>melhor</span><span class="gradient"></span><span>pior</span></div></div>
  <div class="table-wrap"><table id="results-table"><thead></thead><tbody></tbody></table></div>
  <p id="metric-note" class="lead" style="margin-top:13px"></p>
</div></section>
<section><div class="container">
  <div class="grid-2">
    <div class="card"><h3>Ranking por macro-MAE</h3><div id="ranking" class="rank-list"></div></div>
    <div class="card"><h3>Modelos probabilísticos</h3><div id="probabilistic"></div><div class="notice" style="margin-top:15px">A cobertura próxima de 90% do DeepNPTS veio com intervalos 4,10 vezes mais largos que os do DeepAR.</div></div>
  </div>
</div></section>
<section class="alt"><div class="container">
  <div class="section-head"><span class="kicker">Figuras oficiais</span><h2>Leitura visual</h2></div>
  <div class="figure-grid">
    <figure><img src="../resultados/avaliacao_mensal_canonica/figuras/mae_medio_modelos.png" alt="Ranking por MAE"><figcaption>Ranking geral por macro-MAE.</figcaption></figure>
    <figure><img src="../resultados/avaliacao_mensal_canonica/figuras/mae_deepnpts_por_localidade.png" alt="DeepNPTS por localidade"><figcaption>MAE do DeepNPTS nas dez localidades.</figcaption></figure>
    <figure><img src="../resultados/avaliacao_mensal_canonica/figuras/previsao_mensal_byd_camacari.png" alt="Previsão BYD Camaçari"><figcaption>Referência, climatologia e DeepNPTS em Camaçari.</figcaption></figure>
    <figure><img src="../resultados/avaliacao_mensal_canonica/figuras/intervalo_deepnpts_byd_camacari.png" alt="Intervalo DeepNPTS"><figcaption>Intervalo preditivo do DeepNPTS.</figcaption></figure>
  </div>
</div></section>
<script id="project-data" type="application/json">__DADOS__</script>
<script>
const data=JSON.parse(document.getElementById('project-data').textContent);
const config={
  mae:{label:'MAE (W/m²)',lower:true,digits:2,note:'Erro absoluto médio. Menor é melhor.'},
  mse:{label:'MSE (W²/m⁴)',lower:true,digits:2,note:'Erro quadrático médio. Menor é melhor.'},
  rmse:{label:'RMSE (W/m²)',lower:true,digits:2,note:'Raiz do erro quadrático médio. Menor é melhor.'},
  r2:{label:'R²',lower:false,digits:3,note:'Variação explicada. Maior é melhor.'},
  nrmse:{label:'nRMSE (%)',lower:true,digits:2,note:'RMSE relativo à GHI média local. Menor é melhor.'}
};
const fmt=(v,d=2)=>Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
const pair=new Map(data.metricasLocais.map(r=>[`${r.localidade}|||${r.modelo}`,r]));
const model=m=>data.nomesModelos[m]||m;
function color(value,min,max,lower){const raw=max===min?.5:(value-min)/(max-min);const q=lower?1-raw:raw;const s=Math.round(249-q*31);return `rgb(${s} ${s} ${s})`;}
function render(metric){
  const cfg=config[metric],table=document.getElementById('results-table');
  table.tHead.innerHTML=`<tr><th>Localidade</th>${data.ordemModelos.map(m=>`<th>${model(m)}</th>`).join('')}</tr>`;
  table.tBodies[0].innerHTML=data.ordemLocalidades.map(local=>{
    const values=data.ordemModelos.map(m=>pair.get(`${local}|||${m}`)[metric]);
    const best=cfg.lower?Math.min(...values):Math.max(...values),min=Math.min(...values),max=Math.max(...values);
    return `<tr><td>${data.nomesLocalidades[local]}</td>${values.map((v,i)=>`<td class="${Math.abs(v-best)<1e-10?'best-cell':''}" style="background:${color(v,min,max,cfg.lower)}" title="${model(data.ordemModelos[i])}">${Math.abs(v-best)<1e-10?'★ ':''}${fmt(v,cfg.digits)}</td>`).join('')}</tr>`;
  }).join('');
  document.getElementById('metric-note').textContent=cfg.note;
}
function ranking(){const max=Math.max(...data.ranking.map(r=>r.mae));document.getElementById('ranking').innerHTML=data.ranking.map(r=>`<div class="rank-row ${r.modelo==='DeepNPTS'?'deep':''}" title="DP entre sementes: ${fmt(r.dp)}"><span class="rank-pos">${r.posicao}</span><strong>${r.modelo_exibicao}</strong><span class="bar-track"><span class="bar" style="width:${Math.max(5,r.mae/max*100)}%"></span></span><span class="rank-value">${fmt(r.mae)}</span></div>`).join('');}
function probabilistic(){document.getElementById('probabilistic').innerHTML=data.probabilisticas.map(r=>`<div style="padding:12px 0;border-bottom:1px solid #ddd"><strong>${r.modelo}</strong><br><span>CRPS ${fmt(r.crps)} · cobertura ${fmt(r.picp)}% · largura ${fmt(r.mpiw)} W/m²</span></div>`).join('');}
document.getElementById('metric-select').addEventListener('change',e=>render(e.target.value));render('mae');ranking();probabilistic();
</script>""".replace("__DADOS__", dados_json)
    return pagina(
        titulo="Resultados", ativa="resultados", kicker="Avaliação e comparação",
        chamada="O que os modelos realmente entregaram.",
        descricao="Ranking geral, resultados por localidade, métricas probabilísticas e figuras oficiais.",
        corpo=corpo,
    )


def escrever(nome: str, conteudo: str) -> None:
    destino = PASTA_SITE / nome
    temporario = destino.with_suffix(destino.suffix + ".tmp")
    temporario.write_text(conteudo, encoding="utf-8")
    temporario.replace(destino)


def main() -> None:
    dados = carregar_dados()
    PASTA_SITE.mkdir(parents=True, exist_ok=True)
    escrever("index.html", pagina_home())
    escrever("data.html", pagina_data(dados))
    escrever("modelos.html", pagina_modelos())
    escrever("resultados.html", pagina_resultados(dados))
    for nome in ("index.html", "data.html", "modelos.html", "resultados.html"):
        print(PASTA_SITE / nome)


if __name__ == "__main__":
    main()
