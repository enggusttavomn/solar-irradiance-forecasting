'''Sonda flags de determinismo apenas em forward/backward, sem optimizer.step.'''
from __future__ import annotations
import copy
from pathlib import Path
import time
from contextlib import nullcontext

from codigo_fonte.analises_e_relatorios.investigar_controles_atencao import x, e, m, torch, REL, TAREFAS, MODELOS, rede_gpu
from torch.nn.attention import sdpa_kernel, SDPBackend


def main():
    linhas = []
    for tarefa in TAREFAS:
        ctx = x.preparar_contexto(tarefa, 'selecao', 'completa')
        j = ctx.janelas['ajuste']
        xn, yn = j.normalizar(ctx.escalas['selecao'])
        for modelo in MODELOS:
            seed = 42 if ctx.tarefa.resolucao == 'horaria' else 11
            lote = next(iter(m._carregador(xn, yn, j.localidade_id, batch_size=128, embaralhar=True, semente=seed)))
            xb, yb, ids = lote
            rede = rede_gpu(ctx, modelo, seed)
            estado = copy.deepcopy(rede.state_dict())
            for backend in ('automatico_estrito', 'math_estrito'):
                registros, vetores = [], []
                try:
                    for n in range(3):
                        rede.load_state_dict(estado, strict=True)
                        rede.zero_grad(set_to_none=True)
                        rede.train()
                        m.fixar_semente(seed, 1)
                        torch.use_deterministic_algorithms(True, warn_only=False)
                        with sdpa_kernel(SDPBackend.MATH) if backend=='math_estrito' else nullcontext():
                            torch.cuda.synchronize()
                            inicio = time.perf_counter()
                            saida = rede(xb, ids)
                            loss = ((saida-yb)**2).mean()
                            loss.backward()
                            torch.cuda.synchronize()
                            segundos = time.perf_counter() - inicio
                        grad = torch.cat([p.grad.detach().cpu().reshape(-1) for p in rede.parameters() if p.grad is not None])
                        vetores.append((saida.detach().clone(),grad))
                        registros.append({'repeticao':n,'segundos_lote':segundos,
                            'saida_max_delta':float((vetores[0][0]-vetores[-1][0]).abs().max()),
                            'gradiente_max_delta':float((vetores[0][1]-vetores[-1][1]).abs().max())})
                    r = {'tarefa':tarefa,'modelo':modelo,'backend':backend,'ok':True,
                         'bitexato_repeticoes':all(z['saida_max_delta']==0 and z['gradiente_max_delta']==0 for z in registros),
                         'repeticoes':registros}
                except RuntimeError as exc:
                    r = {'tarefa':tarefa,'modelo':modelo,'backend':backend,'ok':False,'erro':str(exc),'repeticoes':registros}
                linhas.append(r)
                print(tarefa,modelo,backend,r.get('bitexato_repeticoes'),flush=True)
            del rede
            torch.cuda.empty_cache()
    destino=REL/'sonda_determinismo_estrito.json'
    m.salvar_json_atomico({'sem_optimizer_step':True,'resultados':linhas,
        'limite':'Paridade em um lote real repetido; nao comprova ainda reproducao do treinamento completo.',
        'codigo_sha256':x.hashes([Path(__file__),Path(x.__file__),Path(e.redes.__file__),Path(m.__file__)])},destino)
    print(destino,flush=True)


if __name__=='__main__':main()
