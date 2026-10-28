"""Contratos temporais, reproducao e isolamento de quantizacao/targets."""
from dataclasses import asdict, replace
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import torch

from codigo_fonte import experimento_quantizacao_concorrentes as x
from codigo_fonte import experimento_multirresolucao as m


@pytest.fixture
def fontes_configuracao_sinteticas(tmp_path, monkeypatch):
    """Contratos locais de teste, sem depender de resultados nao publicados."""
    raiz_original = x.RAIZ
    raiz = tmp_path / "projeto"
    tarefa = m.TAREFAS_CANONICAS["monthly_1"]
    configuracao = m.ConfiguracaoMultirresolucao(modo_execucao="smoke", sementes=(42,))

    def gravar(relativo, contrato):
        arquivo = raiz / relativo
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(contrato, ensure_ascii=False), encoding="utf-8")

    gravar("resultados/avaliacao_multirresolucao_corrigida_v2/monthly_1/contrato_execucao.json",
           m.construir_contrato(tarefa=tarefa, configuracao=configuracao, arquivos_entrada=()))
    for modelo in ("GRU", "Transformer", "Informer"):
        contrato = {"schema": 1, "modelo": modelo, "tarefa": asdict(tarefa),
                    "configuracao_canonica": asdict(configuracao),
                    "execucao": {"dispositivo": "cpu"}}
        contrato["sha256_contrato"] = x.hash_obj(contrato)
        gravar(f"resultados/avaliacao_baselines_revisao_20260912/monthly_1/{modelo.lower()}/contrato.json",
               contrato)

    # O contrato continua calculando hashes reais das fontes usadas na execucao.
    for nome in ("dilated_rnn_direta.py", "timesnet_horario.py",
                 "treinamento_timesnet_otimizacao.py", "treinamento_timesnet_quantizado_resolucoes.py",
                 "treinamento_timesnet_resolucoes.py"):
        relativo = Path("codigo_fonte") / nome
        destino = raiz / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes((raiz_original / relativo).read_bytes())
    monkeypatch.setattr(x, "RAIZ", raiz)
    return raiz


def contexto_sintetico(fase="selecao"):
    t = m.TAREFAS_CANONICAS["monthly_1"]
    rng = np.random.default_rng(7)
    def janela(n, ano, part):
        datas = pd.date_range(f"{ano}-01-31", periods=n, freq="ME")
        return m.JanelasDiretas(rng.uniform(10, 80, (n,12)).astype(np.float32),
            rng.uniform(10, 80, (n,1)).astype(np.float32), np.zeros(n,dtype=np.int64),
            np.full(n,"A",dtype=object), datas, datas.to_numpy()[:,None],12,1,part)
    c = m.ConfiguracaoMultirresolucao(modo_execucao="smoke", sementes=(42,))
    escalas = pd.DataFrame([{"localidade_id":0,"minimo_treino_wm2":10.,"amplitude_escala_wm2":70.}])
    a,b = ("ajuste","validacao") if fase == "selecao" else ("refit","teste")
    return SimpleNamespace(tarefa=t,config=c,series=[None],janelas={a:janela(6,2020,a),b:janela(3,2023,b)},
          escalas={fase:escalas},elevacoes={},entradas=[],fase=fase,protocolo=x.protocolo_padrao())


@pytest.mark.parametrize("slug", list(x.e.TAREFAS))
def test_protocolo_atual_preserva_contrato_temporal(slug):
    assert x.construir_tarefa(slug,x.protocolo_padrao()) == x.e.TAREFAS[slug]


@pytest.mark.parametrize("slug", list(x.e.TAREFAS))
@pytest.mark.parametrize("regime", x.REGIMES[1:])
def test_historico_nao_cruza_cortes(slug,regime):
    p=x.protocolo_padrao(regime)
    t=x.construir_tarefa(slug,p)
    assert pd.Timestamp(t.ajuste.fim_alvo) < pd.Timestamp(p["inicio_validacao"])
    assert pd.Timestamp(t.validacao.fim_alvo) < pd.Timestamp(p["inicio_teste"])
    assert pd.Timestamp(t.refit.fim_alvo) < pd.Timestamp(p["inicio_teste"])
    assert t.teste == x.construir_tarefa(slug,x.protocolo_padrao(x.REGIMES[1])).teste
    assert t.validacao == x.construir_tarefa(slug,x.protocolo_padrao(x.REGIMES[1])).validacao


def test_mensal_historico_45_meses_teste():
    t=x.construir_tarefa("monthly_1",x.protocolo_padrao(x.REGIMES[1]))
    assert t.teste.origens_esperadas_por_localidade == 45
    assert t.ajuste.origens_esperadas_por_localidade == 231
    assert t.validacao.origens_esperadas_por_localidade == 12


@pytest.mark.parametrize("modelo", x.MODELOS[:-1])
def test_quantizacao_so_muda_x_treino_e_inferencia(modelo,monkeypatch,fontes_configuracao_sinteticas):
    ctx=contexto_sintetico()
    par=x.parametros(ctx,modelo)
    par["dispositivo"]="cpu"
    alvo=ctx.janelas["ajuste"].normalizar(ctx.escalas["selecao"])[1]
    visto={}
    class Dummy(torch.nn.Module):
        def forward(self,z,ids):
            return z[:,:1]
    monkeypatch.setattr(x,"nova_rede",lambda *a:Dummy())
    def treinar(rede,**k):
        visto.update(k)
        return rede,1,[]
    monkeypatch.setattr(m,"treinar_rede",treinar)
    class Xgb:
        def fit(self,z,y):
            visto.update(x_treino=z[:,:12],y_treino=y[:,None])
        def predict(self,z):
            visto["x_validacao"]=z[:,:12]
            return z[:,0]
    monkeypatch.setattr(m,"criar_xgboost",lambda *a,**k:Xgb())
    x.treinar_seed(ctx,modelo,64,42,"selecao",par)
    np.testing.assert_array_equal(visto["y_treino"],alvo)
    for k in ("x_treino","x_validacao"):
        z=visto[k].astype(float)*63
        np.testing.assert_allclose(z,np.rint(z),atol=2e-6,rtol=0)


@pytest.mark.parametrize("modelo", ["LSTM","DilatedRNN","GRU","Transformer","Informer"])
def test_noquant_repete_loop_original(modelo,fontes_configuracao_sinteticas):
    ctx=contexto_sintetico()
    par=x.parametros(ctx,modelo)
    par["dispositivo"]="cpu"
    rede,prev,epocas,_=x.treinar_seed(ctx,modelo,None,42,"selecao",par)
    original=x.nova_rede(ctx,modelo,42,par)
    treino,val=ctx.janelas["ajuste"],ctx.janelas["validacao"]
    xt,yt=treino.normalizar(ctx.escalas["selecao"])
    xv,yv=val.normalizar(ctx.escalas["selecao"])
    original,ep0,_=m.treinar_rede(original,x_treino=xt,y_treino=yt,ids_treino=treino.localidade_id,
        x_validacao=xv,y_validacao=yv,ids_validacao=val.localidade_id,batch_size=32,
        taxa_aprendizado=.001,peso_decay=1e-5,semente=42,threads_torch=1,max_epocas=1,paciencia=30)
    esperado=val.inverter(m.prever_rede(original,xv,val.localidade_id,batch_size=32),ctx.escalas["selecao"])
    assert epocas==ep0
    np.testing.assert_array_equal(prev,esperado)
    for k,v in rede.state_dict().items():
        torch.testing.assert_close(v,original.state_dict()[k],atol=0,rtol=0)


def test_inferencia_independente_y(monkeypatch,fontes_configuracao_sinteticas):
    ctx=contexto_sintetico("refit")
    par=x.parametros(ctx,"GRU")
    _,p1,_,_=x.treinar_seed(ctx,"GRU",128,42,"refit",par,1)
    ctx.janelas["teste"].y_bruto[:]=np.nan
    _,p2,_,_=x.treinar_seed(ctx,"GRU",128,42,"refit",par,1)
    np.testing.assert_array_equal(p1,p2)


def test_macro_media_locais_nao_raiz_mse_macro():
    ctx=contexto_sintetico()
    j=ctx.janelas["validacao"]
    ctx.janelas["validacao"]=replace(j,localidade=np.array(["A","A","B"],dtype=object))
    bruto=j.y_bruto.astype(float)+np.array([[1.],[1.],[3.]])
    local,macro=x.metricas(ctx,"validacao",bruto,"GRU","q64")
    assert macro.MAE_wm2.iloc[0]==2
    assert macro.MSE_w2m4.iloc[0]==5
    assert macro.RMSE_wm2.iloc[0]==2


def selecao_fake(tmp_path):
    c={"modelo":"GRU","parametros":{"sementes":[42],"max_epocas":30,"fontes_configuracao":{}},
       "codigo":{},"entradas":{}}
    c["sha256_contrato"]=x.hash_obj(c)
    ranking=[{"nome":n,"niveis":k,"MAE_validacao_wm2":float(i+1),"epocas":{"42":2}}
             for i,(n,k) in enumerate(x.VARIANTES)]
    s={"contrato_sha256":c["sha256_contrato"],"selecao_concluida_antes_refit":True,
       "ranking":ranking,"vencedor":ranking[0],"arquivos_selecao":{}}
    (tmp_path/"contrato_execucao.json").write_text(json.dumps(c))
    (tmp_path/"selecao_congelada.json").write_text(json.dumps(s))
    return c,s


def test_selecao_congelada_valida(tmp_path):
    c,s=selecao_fake(tmp_path)
    assert x.validar_selecao(tmp_path)==(c,s)


@pytest.mark.parametrize("erro", ["nivel","seed","epoca","vencedor","contrato","nan","duplicada"])
def test_selecao_rejeita_tampering(tmp_path,erro):
    c,s=selecao_fake(tmp_path)
    if erro=="nivel":s["ranking"][1]["niveis"]=256
    elif erro=="seed":s["ranking"][1]["epocas"]={"11":2}
    elif erro=="epoca":s["ranking"][1]["epocas"]["42"]=31
    elif erro=="vencedor":s["vencedor"]=s["ranking"][2]
    elif erro=="contrato":s["contrato_sha256"]="x"
    elif erro=="nan":s["ranking"][1]["MAE_validacao_wm2"]=float("nan")
    elif erro=="duplicada":s["ranking"][1]=s["ranking"][0]
    (tmp_path/"selecao_congelada.json").write_text(json.dumps(s))
    with pytest.raises(ValueError):x.validar_selecao(tmp_path)


def test_refit_nao_inicia_sem_congelamento(tmp_path,monkeypatch):
    ctx=contexto_sintetico("refit")
    monkeypatch.setattr(x,"construir_contrato",lambda *a:{"x":1})
    with pytest.raises(FileNotFoundError):x.executar_fase(ctx,"GRU",tmp_path,"refit")


def test_contrato_hash_muda_por_niveis_e_hardware(fontes_configuracao_sinteticas):
    ctx=contexto_sintetico()
    a=x.construir_contrato(ctx,"GRU")
    ctx.config=replace(ctx.config,modo_execucao="completa")
    b=x.construir_contrato(ctx,"GRU")
    assert a["sha256_contrato"] != b["sha256_contrato"]
