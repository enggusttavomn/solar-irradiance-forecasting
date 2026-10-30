"""Compara somente leitura previsoes canonicas/consolidadas e metadados historicos."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
SAIDA=Path(__file__).resolve().parent

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

out={"gerado_em_utc":datetime.now(timezone.utc).isoformat(),"tarefas":{},"codigo_final":{}}
for task in ("monthly_1","monthly_6"):
    pasta=ROOT/"resultados/avaliacao_multirresolucao_corrigida_v2"/task
    registro={"previsoes":{}}
    for part in ("validacao","teste"):
        p=pasta/f"previsoes_{part}.csv.gz"
        q=ROOT/"resultados/avaliacao_baselines_revisao_20260912/consolidado"/task/f"previsoes_{part}.csv.gz"
        a,b=pd.read_csv(p),pd.read_csv(q)
        keys=["localidade_id","localidade","origem","data_alvo","passo"]
        nums=["ghi_real_wm2"]+[c for c in a.columns if "timesnet" in c]
        for df in (a,b):
            for c in ("origem","data_alvo"):
                df[c]=pd.to_datetime(df[c],utc=True).astype("datetime64[ns, UTC]")
        a=a.sort_values(keys).reset_index(drop=True)
        b=b.sort_values(keys).reset_index(drop=True)
        pd.testing.assert_frame_equal(a[keys],b[keys],check_dtype=False)
        erros={c:float(np.max(np.abs(a[c].to_numpy()-b[c].to_numpy()))) for c in nums}
        assert max(erros.values())<1e-10
        registro["previsoes"][part]={"chaves_e_datas_equivalentes":True,
            "erro_maximo_por_coluna_wm2":erros,"linhas":len(a),
            "sha256_canonico":sha(p),"sha256_consolidado":sha(q)}
    contrato=json.loads((pasta/"contrato_execucao.json").read_text(encoding="utf-8"))
    metodo=json.loads((pasta/"hiperparametros_e_metodo.json").read_text(encoding="utf-8"))
    assert contrato["configuracao"]==metodo["configuracao"]
    assert contrato["tarefa"]==metodo["tarefa"]
    for caminho,esperado in contrato["entradas_sha256"].items():
        assert sha(Path(caminho))==esperado
    registro["contrato_atual_configuracao_e_tarefa_iguais_metodo_historico"]=True
    registro["contrato_atual_entradas_sha256_integras"]=len(contrato["entradas_sha256"])
    registro["limite_origem_divergencia_contrato"]="Nao foi localizada copia do contrato com hash esperado no manifesto. Sem ela, nao e possivel afirmar que a diferenca se limita aos caminhos. Os campos configuracao e tarefa do contrato atual coincidem integralmente com hiperparametros_e_metodo.json, arquivo historico conforme manifesto."
    out["tarefas"][task]=registro
for nome in ("experimento_multirresolucao.py","otimizacao_timesnet_mensal.py","timesnet_horario.py","treinamento_timesnet_otimizacao.py"):
    out["codigo_final"][nome]=sha(ROOT/"codigo_fonte"/nome)
out["script_sha256"]=sha(Path(__file__))
(SAIDA/"equivalencia_mensal_canonico_consolidado.json").write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print(json.dumps(out,indent=2,ensure_ascii=False))
