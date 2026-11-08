"""Audit and plot frozen selection losses. Never loads models or forecasts."""
from pathlib import Path
import csv
import hashlib
import json
import math
import sys
import html
import subprocess
import os

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=ROOT/'resultados/quantizacao_todos_modelos_20260929'
MODELS=('Transformer','Informer','LSTM')
REGIMES=('atual','historico_1998_2022','historico_curto_pareado')
TASKS=('hourly_72_extension','daily_30','monthly_1','monthly_6')
COLORS={'Transformer':'#245B86','Informer':'#B55B36','LSTM':'#337A71'}
LINESTYLES={'Transformer':'','Informer':'12 7','LSTM':'14 6 3 6'}
TITLES={'atual':('A  Atual','Validação: 2023'),
        'historico_1998_2022':('B  Histórico longo','Validação: abr/2018–mar/2019'),
        'historico_curto_pareado':('C  Histórico curto pareado','Validação: abr/2018–mar/2019')}

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def relative(p):return str(p.relative_to(ROOT)).replace('\\','/')
def load_json(p):return json.loads(p.read_text(encoding='utf-8'))
def load_log(p):
    with p.open(encoding='utf-8-sig',newline='') as stream:
        f=[{k.lower():float(v) for k,v in row.items()} for row in csv.DictReader(stream)]
    needed=['epoca','mse_treino_normalizado','mse_validacao_normalizado']
    assert f and set(needed).issubset(f[0]),p
    assert all(math.isfinite(r[k]) for r in f for k in needed),p
    assert [int(r['epoca']) for r in f]==list(range(1,len(f)+1)),p
    assert all(r['mse_validacao_normalizado']>0 for r in f),p
    return f

def save_rows(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)

def recorded_csv_hash(meta,p):
    matching=[v for k,v in meta['arquivos_sha256'].items() if k.replace('\\','/').endswith('/'+p.name)]
    assert len(matching)==1,(p,matching)
    return matching[0]

curves=[];curve_frames=[]
for regime in REGIMES:
    for model in MODELS:
        folder=BASE/regime/'hourly_72_extension'/model.lower()
        selected=load_json(folder/'selecao_congelada.json')
        control=next(v for v in selected['ranking'] if v['nome']=='sem_quantizacao')
        epoch=int(control['epocas']['42'])
        csv_path=folder/'sem_quantizacao/selecao/seed42.csv'
        json_path=csv_path.with_suffix('.json')
        meta=load_json(json_path)
        frame=load_log(csv_path)
        assert meta['fase']=='selecao' and meta['variante']=='sem_quantizacao' and meta['seed']==42
        assert meta['epocas']==epoch,(json_path,epoch)
        assert int(min(frame,key=lambda r:r['mse_validacao_normalizado'])['epoca'])==epoch
        assert digest(csv_path)==recorded_csv_hash(meta,csv_path),csv_path
        best=next(r for r in frame if int(r['epoca'])==epoch)
        curves.append({'regime':regime,'task':'hourly_72_extension','model':model,'variant':'sem_quantizacao','phase':'selecao','seed':42,'selected_epoch':epoch,'epochs_logged':len(frame),'first_validation_mse':frame[0]['mse_validacao_normalizado'],'selected_validation_mse':best['mse_validacao_normalizado'],'last_validation_mse':frame[-1]['mse_validacao_normalizado'],'selected_train_mse':best['mse_treino_normalizado'],'selection_csv':relative(csv_path),'selection_csv_sha256':digest(csv_path),'selection_json':relative(json_path),'selection_json_sha256':digest(json_path),'recorded_csv_hash_matches':True,'selection_frozen_json':relative(folder/'selecao_congelada.json'),'selection_frozen_json_sha256':digest(folder/'selecao_congelada.json')})
        for row in frame:curve_frames.append({'regime':regime,'modelo':model,'variante':'sem_quantizacao','semente':42,**row,'epoca_escolhida':int(row['epoca'])==epoch})
combined=curve_frames
save_rows(HERE/'dados_curvas_selecao_horaria.csv',combined)

# Read all loss logs for the three report models to distinguish reaching the
# budget from having the selected epoch at its upper boundary.
cap_rows=[];cap_summary=[]
for regime in REGIMES:
    for task in TASKS:
        for model in MODELS:
            folder=BASE/regime/task/model.lower()
            frozen=load_json(folder/'selecao_congelada.json')
            contract=load_json(folder/'contrato_execucao.json')
            cap=int(contract['parametros']['max_epocas'])
            subset=[]
            for variant in frozen['ranking']:
                for seed,epoch in variant['epocas'].items():
                    p=folder/variant['nome']/'selecao'/f'seed{seed}.csv'
                    f=load_log(p)
                    chosen=int(epoch)
                    assert chosen==int(min(f,key=lambda r:r['mse_validacao_normalizado'])['epoca']),(p,chosen)
                    row={'regime':regime,'tarefa':task,'modelo':model,'variante':variant['nome'],'semente':int(seed),'limite_epocas':cap,'epoca_escolhida':chosen,'epocas_registradas':len(f),'escolhida_no_teto':chosen==cap,'execucao_atingiu_teto':len(f)==cap,'fonte':relative(p),'sha256':digest(p)}
                    cap_rows.append(row);subset.append(row)
            cap_summary.append({'regime':regime,'task':task,'model':model,'max_epochs':cap,'n_variant_seed_runs':len(subset),'selected_epoch_at_cap':sum(x['escolhida_no_teto'] for x in subset),'logged_to_cap':sum(x['execucao_atingiu_teto'] for x in subset)})
save_rows(HERE/'auditoria_tetos_epocas.csv',cap_rows)

# SVG authored directly; bundled sharp rasterizes it. No package installation,
# repository environment, matplotlib, forecasts or trained models are used.
elements=['<svg xmlns="http://www.w3.org/2000/svg" width="17cm" height="10.3cm" viewBox="0 0 1700 1030">',
          '<title>Seleção horária: controles contínuos</title>',
          '<desc>MSE de validação normalizado dos registros canônicos de seleção. Somente Transformer, Informer e LSTM; semente 42; sem novos treinamentos.</desc>',
          '<rect width="1700" height="1030" fill="white"/>',
          '<g font-family="DejaVu Sans,Arial,sans-serif" fill="#26323B">']
def text(x,y,s,size=30,fill='#26323B',anchor='start',weight='normal',extra=''):
    elements.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" font-weight="{weight}" {extra}>{html.escape(s)}</text>')
def line(x1,y1,x2,y2,stroke='#DDE3E8',width=2,dash=''):
    elements.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{width}"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
text(850,56,'Seleção horária: controles contínuos',size=40,anchor='middle',weight='bold')
text(850,105,'MSE de validação normalizado · semente 42 · saída de 72 horas',size=30,fill='#56636E',anchor='middle')
for xpos,model in zip([350,760,1120],MODELS):
    line(xpos,160,xpos+85,160,COLORS[model],5,LINESTYLES[model]);text(xpos+105,170,model,size=31)
text(42,508,'MSE normalizado (escala log)',size=30,anchor='middle',extra='transform="rotate(-90 42 508)"')
def ymap(value):return 700-(math.log(value)-math.log(.0085))/(math.log(.09)-math.log(.0085))*400
for i,regime in enumerate(REGIMES):
    left=140+i*530;right=left+450
    def xmap(epoch):return left+(epoch-.5)/30.5*450
    text(left,236,TITLES[regime][0],size=31,weight='bold')
    text(left,277,TITLES[regime][1],size=25.5,fill='#56636E')
    for value in [.01,.02,.04,.08]:
        y=ymap(value);line(left,y,right,y)
        text(left-14,y+9,f'{value:.2f}'.replace('.',','),size=28,anchor='end',fill='#56636E')
    line(left,300,left,700,'#B7C1C9',2);line(left,700,right,700,'#B7C1C9',2)
    for epoch in [1,10,20,30]:
        x=xmap(epoch);line(x,700,x,711,'#93A1AC',2);text(x,748,str(epoch),size=28,anchor='middle',fill='#56636E')
    text((left+right)/2,790,'Época',size=30,anchor='middle')
    for j,model in enumerate(MODELS):
        rows=[r for r in combined if r['regime']==regime and r['modelo']==model]
        info=next(c for c in curves if c['regime']==regime and c['model']==model)
        points=' '.join(f'{xmap(r["epoca"]):.3f},{ymap(r["mse_validacao_normalizado"]):.3f}' for r in rows)
        dash=LINESTYLES[model]
        elements.append(f'<polyline points="{points}" fill="none" stroke="{COLORS[model]}" stroke-width="5" stroke-linejoin="round"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
        elements.append(f'<circle cx="{xmap(info["selected_epoch"]):.3f}" cy="{ymap(info["selected_validation_mse"]):.3f}" r="9" fill="white" stroke="{COLORS[model]}" stroke-width="4"/>')
        text(left,846+38*j,f'{model}: época {info["selected_epoch"]}',size=28,fill=COLORS[model])
text(850,976,'○ Época escolhida na validação · curvas completas até a parada ou o teto',size=28,fill='#3E4B56',anchor='middle')
text(850,1015,'Escalas próprias por regime; longo e curto compartilham a validação histórica.',size=26,fill='#56636E',anchor='middle')
elements.extend(['</g>','</svg>'])
stem=HERE/'diagnostico_treinamento_horario_controles'
stem.with_suffix('.svg').write_text('\n'.join(elements),encoding='utf-8')
node=Path('C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
sharp='C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp'
renderer=HERE/'rasterizar_diagnostico.cjs'
renderer.write_text("const sharp = require("+json.dumps(sharp)+");\nconst fs = require('fs');\nconst svg = fs.readFileSync(process.argv[2], 'utf8').replace('width=\"17cm\" height=\"10.3cm\"', 'width=\"3012\" height=\"1825\"');\nsharp(Buffer.from(svg), {density:72}).resize({width:3012,height:1825}).flatten({background:'#ffffff'}).png().withMetadata({density:450}).toFile(process.argv[3]).then(info => console.log(JSON.stringify(info))).catch(error => { console.error(error); process.exit(1); });\n",encoding='utf-8')
render_env=dict(os.environ)
render_env['XDG_CACHE_HOME']=str(HERE/'cache')
(HERE/'cache').mkdir(exist_ok=True)
subprocess.run([str(node),str(renderer),str(stem.with_suffix('.svg')),str(stem.with_suffix('.png'))],check=True,env=render_env)

caption=('Figura — Trajetórias de validação na seleção horária dos controles contínuos. '
         'Fonte: elaboração própria a partir dos registros canônicos de seleção de Transformer, Informer e LSTM, semente 42. '
         'Cada painel apresenta o MSE de validação na escala normalizada do respectivo regime, em eixo vertical logarítmico; '
         'os círculos marcam as épocas escolhidas. As curvas incluem todas as épocas registradas até a parada antecipada ou o teto de 30 épocas. '
         'As escalas são ajustadas separadamente; os históricos longo e curto compartilham a validação, enquanto o regime atual usa 2023. '
         'As trajetórias não isolam o efeito do tamanho do histórico. '
         'Não foram utilizados registros de refit nem executados novos treinamentos.')
interpretation=('Nas execuções horárias dos controles contínuos, o Informer apresentou uma trajetória de validação diferente das demais redes nos regimes atual e histórico curto pareado. '
                'No histórico longo, sua perda diminuiu ao longo das épocas registradas. Esses registros ajudam a caracterizar diferenças na otimização sob as configurações executadas, '
                'mas não demonstram uma causa isolada do erro de teste nem estabelecem uma conclusão formal de convergência. '
                'A tarefa horária dispõe de uma única semente, e os valores normalizados utilizam as escalas de cada regime. '
                'Os históricos longo e curto compartilham os mesmos alvos de validação; o regime atual avalia outro período.')
budget=('A época escolhida coincidiu com o teto de 30 em quatro das quatro condições de entrada do Transformer horário no regime atual. '
        'Na tarefa diária atual, isso ocorreu em oito de 20 combinações de condição e semente do Transformer e em cinco de 20 da LSTM; '
        'na tarefa diária do histórico curto pareado, ocorreu em onze de 20 combinações da LSTM. '
        'Esses casos indicam que a busca por épocas terminou na fronteira do orçamento estabelecido. '
        'Não demonstram, por si só, que as redes ficaram subtreinadas ou que ampliar o orçamento reduziria o erro de teste; essa hipótese exigiria outra avaliação.')
text={'caption':caption,'short_discussion':interpretation,'epoch_budget_paragraph':budget,'scope_note':'The figure shows only continuous controls. Main report rankings using validation-selected quantization variants must remain unchanged.'}
(HERE/'sugestao_caption_treinamento.json').write_text(json.dumps(text,ensure_ascii=False,indent=2),encoding='utf-8')
manifest={'scope':'Frozen canonical hourly SELECTION logs only; continuous controls of Transformer, Informer and LSTM, seed 42, in three regimes. No refit logs, model loading, forecast generation or new training.','curves':curves,'combined_log_rows':len(combined),'epoch_budget_summary':cap_summary,'epoch_budget_runs':len(cap_rows),'figure_size_cm':[17,10.3],'vertical_axis':'logarithmic MSE in each regime normalization','sources_csv_hashes_verified':True,'outputs':{p.name:digest(p) for p in [stem.with_suffix('.png'),stem.with_suffix('.svg'),HERE/'dados_curvas_selecao_horaria.csv',HERE/'auditoria_tetos_epocas.csv']}}
(HERE/'manifesto_diagnostico_treinamento.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'figure':relative(stem.with_suffix('.png')),'curves':len(curves),'combined_log_rows':len(combined),'budget_runs':len(cap_rows),'nonzero_cap_counts':[r for r in cap_summary if r['selected_epoch_at_cap']]},ensure_ascii=True,indent=2))
