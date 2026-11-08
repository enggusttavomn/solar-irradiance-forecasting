from pathlib import Path
import ast
import hashlib
import json
import subprocess
import zipfile
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'resultados/quantizacao_todos_modelos_20260929'
OUT = Path(__file__).with_name('reprodutibilidade.json')
ARCHIVE = ROOT / 'documentacao/organizacao/fontes_antes_reorganizacao_20261027.zip'
REGIMES = ['atual', 'historico_1998_2022', 'historico_curto_pareado']
TASKS = [('hourly_72_extension','Horária',336,72),('daily_30','Diária',365,30),
         ('monthly_1','Mensal de um passo',12,1),('monthly_6','Mensal de seis passos',12,6)]
MODELS = ['transformer','informer','lstm']
SOURCE_MEMBERS = ['codigo_fonte/modelos_baselines_adicionais.py',
                  'codigo_fonte/experimento_horario_timesnet.py',
                  'codigo_fonte/experimento_multirresolucao.py',
                  'codigo_fonte/experimento_quantizacao_concorrentes.py']

def digest(data):
    return hashlib.sha256(data).hexdigest()

def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def relative(path):
    return str(path.relative_to(ROOT)).replace('\\','/')

def object_hash(obj):
    return digest(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())

contracts=[]
packages=defaultdict(set)
devices=defaultdict(set)
canonical_python=[]
gpu_records=[]
code_hashes=defaultdict(set)
for regime in REGIMES:
    for task,_,seq_len,pred_len in TASKS:
        for model in MODELS:
            path=BASE/regime/task/model/'contrato_execucao.json'
            c=load(path)
            assert c['tarefa']['seq_len']==seq_len and c['tarefa']['pred_len']==pred_len
            config=c['parametros']['configuracao']
            assert (config['lstm_ocultos'],config['lstm_camadas'],config['embedding_localidade'])==(32,1,8)
            content_hash=object_hash({k:v for k,v in c.items() if k!='sha256_contrato'})
            assert content_hash==c['sha256_contrato']
            packages_key={k:c['pacotes'][k] for k in ['numpy','pandas','torch']}
            for k,v in packages_key.items():
                packages[k].add(v)
            devices[(task,model)].add(c['parametros']['dispositivo'])
            env=c.get('execucao_numerica',{}).get('ambiente',{})
            if env.get('gpu'):
                gpu_records.append({'regime':regime,'tarefa':task,'modelo':model,'gpu':env['gpu'],
                                    'cuda':env.get('cuda'),'cudnn':env.get('cudnn'),
                                    'torch':env.get('torch'),'threads_torch':env.get('threads_torch'),
                                    'algoritmos_deterministicos':c['execucao_numerica'].get('algoritmos_deterministicos'),
                                    'warn_only':c['execucao_numerica'].get('warn_only'),
                                    'cublas_workspace_config':c['execucao_numerica'].get('cublas_workspace_config'),
                                    'path':relative(path)})
            for member in SOURCE_MEMBERS:
                matched=[v for k,v in c['codigo'].items() if k.replace('\\','/').endswith('/'+Path(member).name)]
                assert len(matched)==1
                code_hashes[member].add(matched[0])
            python_keys=[k for k in c if any(s in k.lower() for s in ['python','processor','platform','commit'])]
            if python_keys:
                canonical_python.append({'path':relative(path),'keys':python_keys})
            contracts.append({'regime':regime,'tarefa':task,'modelo':model,'path':relative(path),
                              'sha256_arquivo':digest(path.read_bytes()),'sha256_contrato':c['sha256_contrato'],
                              'hash_conteudo_conferido':True,'dispositivo':c['parametros']['dispositivo'],
                              'cuda':c.get('cuda'),'pacotes':packages_key,
                              'configuracao_treino':{k:c['parametros'][k] for k in ['batch_size','max_epocas','paciencia','sementes']},
                              'taxa_aprendizado':config['taxa_aprendizado'],'weight_decay':config['peso_decay']})

sources=[]
with zipfile.ZipFile(ARCHIVE) as archive:
    for member in SOURCE_MEMBERS:
        raw=archive.read(member)
        sha=digest(raw)
        assert code_hashes[member]=={sha}
        source=raw.decode('utf-8-sig')
        tree=ast.parse(source)
        identifiers={n.name:{'linha':n.lineno,'fim_linha':n.end_lineno} for n in ast.walk(tree)
                     if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in
                     ['LSTMEncoderDireto','TransformerDireto','AtencaoProjetada','BlocoEncoder','BlocoDecoder','Distilacao',
                      'criar_modelo_neural','nova_rede','treinar_rede','treinar_rede_direta','parametros','construir_contrato']}
        sources.append({'arquivo_zip':relative(ARCHIVE),'membro':member,'sha256':sha,
                        'confere_com_36_contratos':True,'localizadores':identifiers})
    lstm_source=archive.read('codigo_fonte/experimento_horario_timesnet.py').decode('utf-8-sig')
    model_source=archive.read('codigo_fonte/modelos_baselines_adicionais.py').decode('utf-8-sig')
    assert 'self.encoder = nn.LSTM(' in lstm_source
    assert 'self.label_len = max(1, seq_len // 2)' in model_source
    assert 'd_model = 16' in model_source
    assert 'for _ in range(2)' in model_source

# Contagem de parâmetros treináveis por construção das camadas, incluindo biases.
linear=lambda n_in,n_out:n_in*n_out+n_out
norm=lambda width:2*width
attention=4*linear(16,16)
ff=linear(16,32)+linear(32,16)
encoder=attention+ff+2*norm(16)
decoder=2*attention+ff+3*norm(16)
base_components={
    'projecoes_entrada_encoder_decoder':2*linear(1,16),
    'embedding_dez_localidades':10*8,
    'projecao_embedding':linear(8,16),
    'dois_blocos_encoder':2*encoder,
    'normalizacoes_finais_encoder_decoder':2*norm(16),
    'bloco_decoder':decoder,
    'projecao_saida_por_passo':linear(16,1)
}
transformer=sum(base_components.values())
distil_components={'Conv1d_pesos':16*16*3,'Conv1d_bias':16,'BatchNorm1d_peso_e_bias':2*16}
informer=transformer+sum(distil_components.values())
assert transformer==8161 and informer==8977
lstm_core=4*32*1+4*32*32+8*32
assert lstm_core==4480
parameter_table=[]
for task,label,c,h in TASKS:
    parameter_table.append({'tarefa':label,'slug':task,'C':c,'H':h,'LSTM':lstm_core+10*8+linear(40,h),
                            'Transformer':transformer,'Informer':informer,'label_len_transformer_informer':max(1,c//2)})

git_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
git_date=subprocess.check_output(['git','show','-s','--format=%cI','HEAD'],cwd=ROOT,text=True).strip()

result={
    'escopo':'Somente LSTM, Transformer e Informer. Leitura de36contratos canônicos (três regimes × quatro tarefas × três modelos) e fontes executadas arquivadas. Sem novos treinamentos ou instalação de pacotes.',
    'runtime_auditoria':'C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',
    'tabela_parametros':parameter_table,
    'tabela_arquiteturas':[
        {'modelo':'LSTM','configuracao_compacta':'Uma camada recorrente com 32 unidades; embedding de 8 dimensões; último estado de 32 dimensões concatenado ao embedding, seguido de camada linear de 40 para H.',
         'input_size':1,'hidden_size':32,'camadas_recorrentes':1,'dropout_recorrente':0.0,'embedding_localidade':8,
         'd_model':None,'cabecas':None,'d_ff':None,'label_len':None,'factor':None,
         'saida':'Direta para H valores contínuos; sem realimentação das previsões.'},
        {'modelo':'Transformer','configuracao_compacta':'d_model = 16; duas cabeças; d_ff = 32; dois encoders e um decoder; dropout de 0,1; embedding de 8 dimensões projetado para 16.',
         'd_model':16,'cabecas':2,'d_ff':32,'camadas_encoder':2,'camadas_decoder':1,'dropout':0.1,'embedding_localidade':8,
         'label_len':'max(1, floor(C/2))','factor':None,
         'saida':'Uma projeção linear de 16 para 1 compartilhada entre os H passos.'},
        {'modelo':'Informer','configuracao_compacta':'Mesmas dimensões do Transformer; ProbSparse com fator 5 no encoder e autoatenção causal do decoder; atenção cruzada completa; uma etapa de destilação entre encoders.',
         'd_model':16,'cabecas':2,'d_ff':32,'camadas_encoder':2,'camadas_decoder':1,'dropout':0.1,'embedding_localidade':8,
         'label_len':'max(1, floor(C/2))','factor':5,
         'destilacao':'Conv1d de 16 para 16, kernel 3 e padding circular de 1; BatchNorm1d com 16 canais; ELU; MaxPool1d com kernel 3, stride 2 e padding 1.',
         'atencao_probsparse_dropout':'A implementação não aplica dropout aos pesos ProbSparse; mantém dropout nas conexões residuais e no bloco feedforward.',
         'saida':'Uma projeção linear de 16 para 1 compartilhada entre os H passos.'}
    ],
    'contagem_parametros':{
        'tipo':'Contagem algébrica exata dos parâmetros treináveis definidos pelas fontes arquivadas cujo SHA256 coincide com os36contratos; inclui pesos e biases. Não exige carregar pesos nem executar inferência/treinamento.',
        'numero_localidades':10,'transformer_componentes':base_components,'attention_por_bloco':attention,'feedforward_por_bloco':ff,
        'encoder_por_bloco':encoder,'decoder':decoder,'informer_adicional_destilacao':distil_components,
        'lstm_core':lstm_core,'lstm_embedding':80,'lstm_cabeca':'40H + H = 41H','lstm_formula_total':'4560 + 41H',
        'exclusoes':['Buffers de posições senoidais','Médias e variâncias móveis de BatchNorm','Contadores não treináveis'],
        'nota_para_tabela':'Parâmetros treináveis das implementações auditadas, para dez localidades. Pesos e biases estão incluídos; buffers não treináveis estão excluídos. Transformer e Informer compartilham a projeção de saída entre passos, enquanto a cabeça da LSTM depende de H. A contagem é a mesma nas quatro condições de entrada e nos três regimes; não representa igualdade de capacidade efetiva ou de custo computacional.'
    },
    'tabela_ambiente':[
        {'tarefa':'Horária e diária','modelos':'Transformer e Informer','dispositivo':'CUDA','GPU_registrada':'NVIDIA GeForce GTX1650 with Max-Q Design',
         'CUDA':'12.6','cuDNN':91002,'PyTorch':'2.12.0+cu126','fonte':'execucao_numerica.ambiente nos contratos canônicos dessas arquiteturas e tarefas.'},
        {'tarefa':'Horária e diária','modelos':'LSTM','dispositivo':'CUDA','GPU_registrada':'Não especificada no contrato canônico','CUDA':'12.6','cuDNN':None,'PyTorch':'2.12.0+cu126',
         'fonte':'parametros.dispositivo, cuda e pacotes.torch nos contratos canônicos; não inferir modelo da GPU a partir dos contratos de outras arquiteturas.'},
        {'tarefa':'Mensais de um e seis passos','modelos':'LSTM, Transformer e Informer','dispositivo':'CPU','CPU_registrada':'Modelo não especificado no contrato canônico','CUDA':None,'PyTorch':'2.12.0+cu126',
         'fonte':'parametros.dispositivo e pacotes.torch nos contratos canônicos. O sufixo cu126 identifica a distribuição instalada, sem indicar uso de CUDA nessa tarefa.'}
    ],
    'pacotes_comuns_verificados':{k:sorted(v) for k,v in packages.items()},
    'python_cpu_commit_nos_contratos_canonicos':{'campos_encontrados':canonical_python,'Python':'Não registrado diretamente nos36contratos canônicos inspecionados.','CPU_modelo':'Não registrado nos36contratos canônicos inspecionados.','commit_execucao':'Não registrado diretamente nos36contratos canônicos inspecionados.'},
    'ambiente_antecedente_qualificado':{'Python':'3.14.4','fontes':['resultados/avaliacao_baselines_revisao_20260912/hourly_72_extension/informer/contrato.json:python',
        'resultados/avaliacao_multirresolucao_corrigida_v2/hourly_72_extension/contrato_execucao.json:dependencias.python'],
        'uso':'Registro de etapas antecedentes, não garantia da versão de Python de todas as reexecuções de quantização. Recomenda-se não preencher a lacuna do contrato canônico com esse valor sem outra evidência.'},
    'repositorio':{'url':'https://github.com/enggusttavomn/solar-irradiance-forecasting','snapshot_consultado_commit':git_sha,'snapshot_consultado_data_commit':git_date,
                  'snapshot_anterior_documentado':'6c465a6161899f458fde9a062efeb7117c4ef5de',
                  'distincao':'O commit consultado identifica o retrato atual do repositório, posterior aos experimentos, e não é apresentado como commit das execuções. As fontes efetivamente utilizadas são identificadas pelos hashes dos contratos e conferidas no arquivo ZIP de preservação.'},
    'textos_prontos':{
        'metodologia_arquiteturas':'A Tabela de configuração apresenta as dimensões das implementações utilizadas. A LSTM contém uma camada recorrente de32unidades e combina o último estado oculto com uma representação aprendida de8dimensões da localidade antes de produzir os H valores futuros. Transformer e Informer utilizam dimensão interna16, duas cabeças de atenção, bloco feedforward de32unidades, dois encoders, um decoder e dropout de0,1. O decoder recebe os últimos floor(C/2) valores observados seguidos de H zeros, usados como marcadores das posições futuras. No Informer, o fator de amostragem ProbSparse é5 e uma etapa convolucional de destilação conecta os encoders; a atenção cruzada permanece completa.',
        'apendice_contagem':'As quantidades de parâmetros treináveis foram obtidas pela soma das dimensões dos pesos e biases das camadas definidas nas fontes arquivadas, cujos hashes coincidem com os contratos das execuções. A contagem inclui a representação das dez localidades e exclui os buffers de posições senoidais e as estatísticas móveis de normalização. Transformer e Informer têm8.161 e8.977parâmetros, respectivamente, em todas as tarefas, pois compartilham a projeção de saída entre passos. A LSTM tem4.560 +41H parâmetros, devido à cabeça linear que produz todo o horizonte. As quatro condições de entrada mantêm essas quantidades.',
        'apendice_ambiente':'Os36contratos canônicos consultados registram NumPy2.4.4, pandas3.0.3 e PyTorch2.12.0+cu126. As tarefas horária e diária utilizam CUDA12.6; as mensais utilizam CPU. Para Transformer e Informer nas tarefas horária e diária, o ambiente numérico também identifica a GPU NVIDIA GeForce GTX1650 with Max-Q Design e o código de versão cuDNN91002. Os contratos da LSTM informam o uso de CUDA, mas não especificam o modelo da GPU. O modelo da CPU e a versão de Python não foram registrados diretamente nesses contratos; esses campos não são inferidos do computador utilizado nesta revisão. A distribuição de PyTorch com suporte a CUDA também aparece nos contratos mensais, o que não altera o dispositivo CPU declarado para essas tarefas.',
        'apendice_proveniencia':f'O código é disponibilizado em https://github.com/enggusttavomn/solar-irradiance-forecasting. O retrato do repositório consultado nesta revisão corresponde ao commit {git_sha}, de29outubro2026. Esse identificador é posterior aos experimentos e não é atribuído às execuções. A identificação das fontes utilizadas em cada execução é feita pelos hashes SHA256 registrados em contrato_execucao.json, juntamente com hashes das entradas e dos arquivos de configuração. Os arquivos preservados em documentacao/organizacao/fontes_antes_reorganizacao_20261027.zip foram conferidos e coincidem com esses registros. Os metadados de seleção e reajuste referenciam o hash de conteúdo do contrato, ligando cada resultado às fontes e configurações correspondentes. A reorganização posterior das pastas pode alterar caminhos e imports sem substituir essa identificação do código auditado.'
    },
    'verificacao_fontes':sources,
    'sha256_zip_fontes':digest(ARCHIVE.read_bytes()),
    'contratos':contracts,
    'registros_gpu_explicitos':gpu_records,
    'checagens':{'contratos_lidos':len(contracts),'hashes_conteudo_contratos_conferem':True,'quatro_fontes_arquivadas_conferem_em_todos_contratos':True,
                 'config_lstm32_1_embedding8_comum':True,'sem_treinamento_ou_instalacao':True}
}

# Formatar os textos prontos com espaços convencionais entre palavras e numerais.
replacements={'de32':'de 32','de8':'de 8','de0,1':'de 0,1','é5':'é 5','interna16':'interna 16',
              'de8.161':'de 8.161','têm8.161':'têm 8.161','e8.977':'e 8.977','8.977parâmetros':'8.977 parâmetros',
              'tem4.560':'tem 4.560','+41H':'+ 41H','Os36':'Os 36','36contratos':'36 contratos','NumPy2.4.4':'NumPy 2.4.4',
              'pandas3.0.3':'pandas 3.0.3','PyTorch2.12.0':'PyTorch 2.12.0','CUDA12.6':'CUDA 12.6',
              'GTX1650':'GTX 1650','cuDNN91002':'cuDNN 91002','de29outubro2026':'de 29 de outubro de 2026',
              '32unidades':'32 unidades','8dimensões':'8 dimensões'}
for k,text in result['textos_prontos'].items():
    for old,new in replacements.items():
        text=text.replace(old,new)
    result['textos_prontos'][k]=text

OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'path':relative(OUT),'tabela_parametros':parameter_table,'packages':result['pacotes_comuns_verificados'],
                  'devices':{task+'/'+model:sorted(v) for (task,model),v in devices.items()},
                  'gpu_records':len(gpu_records),'canonical_python':canonical_python,
                  'snapshot':result['repositorio'],'checagens':result['checagens']},ensure_ascii=False,indent=2))
