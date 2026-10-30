
"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch]));
let state = null, timer = null, loading = false;
const pct = (a,b) => b ? Math.round(100*a/b) : 0;
function progress(label,value,total){
  const p=pct(value,total);
  return '<div class="bar-label"><span>'+esc(label)+'</span><strong>'+value+' / '+total+' · '+p+'%</strong></div><div class="track" role="progressbar" aria-label="'+esc(label)+'" aria-valuemin="0" aria-valuemax="'+total+'" aria-valuenow="'+value+'"><div class="fill" style="width:'+p+'%"></div></div>';
}
function duration(seconds){
  if(seconds==null)return "—";
  const minutes=Math.floor(seconds/60);
  return minutes<1?"menos de 1 min":minutes<60?minutes+" min":Math.floor(minutes/60)+" h "+minutes%60+" min";
}
function approximate(seconds){
  if(!Number.isFinite(seconds))return "—";
  const minutes=Math.max(1,Math.round(seconds/300)*5);
  if(minutes<60)return minutes+" min";
  if(minutes<1440)return Math.floor(minutes/60)+" h"+(minutes%60?" "+minutes%60+" min":"");
  const hours=Math.round(minutes/60);
  return Math.floor(hours/24)+" d"+(hours%24?" "+hours%24+" h":"");
}
function interval(e){
  const a=approximate(e.min_s), b=approximate(e.max_s);
  return a===b?"cerca de "+b:a+" a "+b;
}
function endWindow(e,now){
  if(e.min_s==null||e.max_s==null)return "";
  const start=new Date(now), a=new Date(start.getTime()+e.min_s*1000), b=new Date(start.getTime()+e.max_s*1000);
  const format=t=>t.toLocaleString("pt-BR",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});
  return "Término aproximado: "+format(a)+" a "+format(b)+".";
}
function etaJob(j,now){
  const e=j.estimativa||{status:"sem_base"};
  if(j.fase==="verificacao_controle")return '<div class="job-eta">Auditoria do controle<strong>Verificando os resultados salvos</strong>Esta conferência não possui estimativa baseada nas durações de treinamento.</div>';
  if(e.status==="finalizando")return '<div class="job-eta">Repetições concluídas<strong>Conferindo e salvando os resultados</strong>O encerramento desta execução ainda está em andamento.</div>';
  if(e.min_s==null||e.max_s==null)return '<div class="job-eta">Tempo restante deste modelo<strong>Medindo as primeiras repetições</strong>A previsão aparece quando houver duração registrada nesta fase.</div>';
  return '<div class="job-eta">Tempo restante deste modelo<strong>'+esc(interval(e))+'</strong>'+esc(endWindow(e,now))+'<br>Base: '+e.amostras+' repetições concluídas.'+(e.recalibrado?' O treino atual está mais lento; faixa recalculada.':'')+'</div>';
}
function renderEstimates(s){
  const e=s.estimativa||{status:"sem_base"};
  let value="Medindo as primeiras execuções", note="Acompanhe abaixo a estimativa de cada modelo em execução.";
  if(e.status==="suspensa"){value="Previsão suspensa";note="Há um aviso nas filas. A estimativa será atualizada quando a execução estiver confirmada.";}
  else if(e.status==="concluido"){value="Concluída";note="Treinos e auditorias concluídos, com registros de entrega dos PDFs.";}
  else if(e.min_s!=null&&e.max_s!=null){
    value=(e.status==="parcial"?"Parte medida: ":"")+interval(e);
    note=e.status==="parcial"?"Cobre "+e.medidos+" de "+e.pendentes+" combinações restantes. As demais ainda não têm medição; esta faixa NÃO é o prazo da etapa inteira.":"Cobre as "+e.pendentes+" combinações restantes, considerando as duas filas em paralelo. "+endWindow(e,s.gerado_em_utc);
  }
  $("eta-stage").textContent=value;$("eta-stage-note").textContent=note;
  $("eta-total").textContent=s.concluido?"PDFs entregues":"Ainda sem prazo confiável";
  if(s.concluido)$("eta-total-note").textContent="Os dois PDFs têm registros de entrega e os três conjuntos passaram pela auditoria.";
}
function activity(line){
  const m=line.match(/\/(sem_quantizacao|q64|q128|q256)\/(selecao|refit) seed=(\d+) (inicio|fim)(?: epocas=(\d+))?/);
  if(!m)return line;
  const level=m[1]==="sem_quantizacao"?"Sem quantização":m[1].slice(1)+" níveis";
  return level+" · semente "+m[3]+(m[4]==="inicio"?" em execução":" concluída"+(m[5]?" · "+m[5]+" épocas":""));
}
function renderTable(){
  if(!state)return;
  const group=state.regimes.find(g=>g.id===$("regime-select").value)||state.regimes[0];
  $("models").querySelector("thead").innerHTML="<tr><th>Modelo</th>"+Object.values(state.tarefas).map(t=>"<th>"+esc(t)+"</th>").join("")+"</tr>";
  $("models").querySelector("tbody").innerHTML=state.modelos.map(model=>{
    return "<tr><td>"+esc(model)+"</td>"+Object.keys(state.tarefas).map(task=>{
      const pair=group.pares.find(p=>p.tarefa===task&&p.modelo===model);
      const active=state.ativos.some(a=>a.regime===group.id&&a.tarefa===task&&a.modelo===model);
      let text="Aguardando", cls="";
      if(pair.refit){text="Treino final pronto";cls="done";}
      else if(active){text="Em execução";cls="running";}
      else if(pair.selecao){text="Seleção pronta";cls="selected";}
      return '<td><span class="cell '+cls+'">'+text+"</span></td>";
    }).join("")+"</tr>";
  }).join("");
}
function render(s){
  state=s;renderEstimates(s);
  document.body.classList.remove("offline");$("offline").hidden=true;
  const warnings=s.alertas.length>0;
  $("connection").className="pill"+(warnings?" warn":"");
  $("connection").innerHTML='<i class="dot"></i>'+(warnings?"Atenção às filas":s.concluido?"Entrega concluída":"Monitor conectado");
  $("alerts").hidden=!warnings;
  $("alerts").innerHTML=s.alertas.map(t=>"<p>"+esc(t)+"</p>").join("");
  const f=s.foco, group=s.regimes.find(g=>g.id===f.regime), quantified=f.total!=null;
  $("focus-regime").textContent=group?group.rotulo:"Etapa de entrega";
  $("focus-title").textContent=f.titulo;
  $("focus-count").textContent=quantified?f.feito+" de "+f.total+" combinações concluídas":s.concluido?"Os dois PDFs têm registros de entrega.":"Esta etapa não possui percentual por treinamento.";
  const globalDone=s.regimes.reduce((sum,g)=>sum+g.selecao+g.refit,0);
  const globalTotal=s.regimes.reduce((sum,g)=>sum+2*g.total,0);
  const globalPercent=pct(globalDone,globalTotal);
  $("global-count").textContent=globalDone+" de "+globalTotal+" etapas de treinamento concluídas nas três bases.";
  $("percent").innerHTML=globalPercent+'<span>%</span>';
  $("hero-fill").style.width=globalPercent+"%";
  $("hero-track").setAttribute("aria-valuenow",globalPercent);
  $("phase-percent").textContent=quantified?pct(f.feito,f.total)+"%":"—";
  $("phase-fill").style.width=quantified?pct(f.feito,f.total)+"%":"0%";
  $("phase-track").hidden=!quantified;
  if(quantified)$("phase-track").setAttribute("aria-valuenow",pct(f.feito,f.total));
  else $("phase-track").removeAttribute("aria-valuenow");
  $("active-count").textContent=s.ativos.length+" treinamento"+(s.ativos.length===1?"":"s")+" ativo"+(s.ativos.length===1?"":"s");
  $("focus-note").textContent="Etapas concluídas, não percentual de horas. Auditorias e PDFs são acompanhados separadamente.";
  document.title=(s.concluido?"PDFs entregues":globalPercent+"% dos treinamentos")+" · Treinamentos GHI";
  $("regimes").innerHTML=s.regimes.map((g,i)=>'<article class="card '+(g.id===f.regime?"active":"")+'"><div class="card-head"><h3>'+esc(g.rotulo)+'</h3><span class="step">0'+(i+1)+'</span></div>'+progress("Escolha das configurações",g.selecao,g.total)+progress("Treinamento final",g.refit,g.total)+'<div class="audit '+(g.auditoria?"good":"")+'">'+(g.auditoria?"✓ Auditoria aprovada":"○ Auditoria do conjunto pendente")+"</div></article>").join("");
  $("jobs").innerHTML=s.ativos.length?s.ativos.map(j=>'<article class="card job"><div class="job-heading"><div><h3>'+esc(j.modelo)+'</h3><p>'+esc(j.caso)+'</p></div><span class="pill">'+(j.fase==="refit"?"Treino final":j.fase==="verificacao_controle"?"Verificação do controle":"Seleção")+'</span></div><div class="activity">'+esc(activity(j.atividade))+'</div>'+(j.sementes_total?progress("Repetições salvas nesta fase",j.sementes_concluidas,j.sementes_total):j.fase==="verificacao_controle"?'<p>Auditoria dos checkpoints, dados e configuração do controle.</p>':'<p>O progresso deste modelo é registrado ao concluir cada nível.</p>')+'<div class="job-meta"><span>'+esc(s.regimes.find(g=>g.id===j.regime)?.rotulo||j.regime)+'</span><span>Execução há '+duration(j.decorrido_s)+'</span></div></article>').join(""):'<div class="empty">'+(warnings?"Consulte o aviso acima: não foi confirmado treinamento ativo.":"Nenhum treinamento ativo nesta leitura. Os coordenadores podem estar conferindo arquivos, preparando a próxima fase ou aguardando revisão.")+"</div>";
  $("updated").textContent="Leitura em "+new Date(s.gerado_em_utc).toLocaleTimeString("pt-BR");
  $("jobs").querySelectorAll(".job").forEach((card,i)=>card.insertAdjacentHTML("beforeend",etaJob(s.ativos[i],s.gerado_em_utc)));
  $("deliveries").innerHTML=s.entregas.map(e=>{
    const label=e.etapa==="entregue"?"PDF entregue":e.etapa==="revisao_pendente"?"PDF gerado · revisão pendente":"Aguardando resultados";
    return '<article class="card delivery"><div><h3>'+esc(e.nome)+'</h3><small>'+esc(e.arquivo)+'</small></div><span class="pill '+(e.etapa==="entregue"?"": "warn")+'">'+label+"</span></article>";
  }).join("");
  if(!$("regime-select").options.length)$("regime-select").innerHTML=s.regimes.map(g=>'<option value="'+esc(g.id)+'">'+esc(g.rotulo)+"</option>").join("");
  $("note").textContent=s.nota;renderTable();
}
async function refresh(){
  if(loading)return;
  loading=true;clearTimeout(timer);$("refresh").disabled=true;
  const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),15000);
  try{
    const response=await fetch("/api/status",{cache:"no-store",signal:controller.signal});
    if(!response.ok)throw new Error("HTTP "+response.status);
    const s=await response.json();if(s.app!=="tcc-progresso-quantizacao-v1")throw new Error("Servidor inesperado");
    render(s);
  }catch(error){
    document.body.classList.add("offline");$("offline").hidden=false;
    $("connection").className="pill error";$("connection").innerHTML='<i class="dot"></i>Sem conexão';
    document.title="Sem conexão · Treinamentos GHI";
  }finally{
    clearTimeout(timeout);loading=false;$("refresh").disabled=false;timer=setTimeout(refresh,10000);
  }
}
$("refresh").addEventListener("click",refresh);
$("regime-select").addEventListener("change",renderTable);
document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
refresh();
