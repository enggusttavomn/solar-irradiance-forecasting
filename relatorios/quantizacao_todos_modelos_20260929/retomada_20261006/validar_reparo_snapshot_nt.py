"""Fixtures e 30 mapas NT nativos; nenhum treinamento ou watcher e iniciado."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys
import unittest
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from scripts import retomar_historico_apos_calendario as h

def save(name,value):
    with (OUT/name).open('w',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2); stream.write('\n')

archive = OUT / 'nativa59_anterior'
preservacao = json.loads((archive/'preservacao.json').read_text(encoding='utf-8'))
assert len(preservacao['arquivos']) == 5
for item in preservacao['arquivos']:
    assert h.digest(item['copia']) == item['sha256']
recibo59 = json.loads((archive/'testes_snapshot_nt.json').read_text(encoding='utf-8'))
assert recibo59['aprovado'] and recibo59['testes_executados'] == 59

manifest_path = ROOT / h.REL / 'aceleracao_local_20261005_2335/manifesto_recuperacao.json'
manifest_bytes = manifest_path.read_bytes(); manifest = json.loads(manifest_bytes)
i = manifest['antigos']['coordenador']
journal_path = ROOT / h.REL / 'retomadas_apos_calendario' / f"{i['pid']}_{i['creation_time']}" / 'journal.json'
journal_bytes = journal_path.read_bytes(); journal = json.loads(journal_bytes)
assert journal['etapa'] == 'BLOCKED' and journal['tentativas_popen'] == 0 and journal['lancamento_pode_ter_ocorrido'] is False
started = datetime.now(timezone.utc).isoformat()
log_path = OUT / 'testes_snapshot_nt.log'
with log_path.open('w',encoding='utf-8',newline='\n') as log:
    suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_retomar_historico_apos_calendario')
    result = unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
native = h.Windows()
old = h.Instancia(2964,'134356484788665740')
real = {'identidade_antiga':h.asdict(old)}
try:
    try:
        atual = native.identificar(old.pid)
        real['identificar_atual'] = h.asdict(atual) if atual else None
    except OSError as exc:
        real['identificar_winerror'] = getattr(exc,'winerror',None)
    real['instancia_antiga_viva'] = native.vivo(old)
    real['snapshot_nt_certificado_registros_atual'] = native._snapshot_nt().get(old.pid,[])
finally:
    native.fechar()
assert real['instancia_antiga_viva'] is False
sources = {str(ROOT/path):h.digest(ROOT/path) for path in ('scripts/retomar_historico_apos_calendario.py','tests/test_retomar_historico_apos_calendario.py')}
receipt = {'versao':1,'aprovado':result.wasSuccessful(),'exitcode':0 if result.wasSuccessful() else 1,
           'testes_executados':result.testsRun,'falhas':len(result.failures),'erros':len(result.errors),'ignorados':len(result.skipped),
           'comando':[sys.executable,'-X','utf8',str(Path(__file__).resolve())],
           'modulo_unittest':'tests.test_retomar_historico_apos_calendario','fontes_sha256':sources,
           'log':str(log_path),'log_sha256':h.digest(log_path),'iniciado_em_utc':started,
           'concluido_em_utc':datetime.now(timezone.utc).isoformat(),
           'consultas_nativas_repetidas':30,'teste_nativo':'test_snapshot_nativo_30_consultas_certificam_pid_filetime_ppid',
           'guard_vivo_win5_real':real,'provas59_preservadas':str(archive/'preservacao.json'),
           'escopo':'Fixtures isoladas e consultas NT somente leitura. Nenhum treinamento/watcher iniciado ou encerrado, nenhuma pausa ou prioridade alterada.'}
save('testes_snapshot_nt.json',receipt)
changes = []
for source in manifest['hashes']:
    current = h.digest(source['path'])
    if current != source['sha256']: changes.append({**source,'sha256_atual':current})
assert len(changes)==2 and {s['papel'] for s in changes}=={'helper','tests_helper'}
assert manifest_path.read_bytes()==manifest_bytes and journal_path.read_bytes()==journal_bytes
diag_path = OUT/'diagnostico_snapshot_original.json'; diag = json.loads(diag_path.read_text(encoding='utf-8'))
dups = []
for sample in diag['tentativas']:
    trace = sample.get('toolhelp_trace',[])
    if trace and trace[-1]['repeated']:
        last = trace[-1]
        first = next(r for r in trace[:-1] if r['pid']==last['pid'])
        evidence = {'pid':last['pid'],'primeiro':first,'repetido':last}
        if evidence not in dups: dups.append(evidence)
review = {'versao':1,'aprovado_para_reconciliacao':result.wasSuccessful(),
          'revisado_em_utc':datetime.now(timezone.utc).isoformat(),
          'manifesto_atual':str(manifest_path),'manifesto_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
          'fontes_vinculadas':len(manifest['hashes']),'fontes_divergentes':changes,
          'fontes_demais_preservadas':len(manifest['hashes'])-2,
          'journal_canonico':str(journal_path),'journal_sha256':hashlib.sha256(journal_bytes).hexdigest(),
          'journal_etapa':journal['etapa'],'tentativas_popen':journal['tentativas_popen'],
          'lancamento_pode_ter_ocorrido':journal['lancamento_pode_ter_ocorrido'],
          'manifesto_e_journal_preservados':True,
          'recibo_testes':str(OUT/'testes_snapshot_nt.json'),'recibo_testes_sha256':h.digest(OUT/'testes_snapshot_nt.json'),
          'diagnostico_original':str(diag_path),'diagnostico_original_sha256':h.digest(diag_path),
          'toolhelp_abi':{'size':diag['entrada_size'],'offsets':diag['entrada_offsets']},
          'toolhelp_amostras':len(diag['tentativas']),
          'toolhelp_amostras_inconclusivas':sum('toolhelp_erro' in s for s in diag['tentativas']),
          'nt_original_amostras_inconclusivas':sum('nt_erro' in s for s in diag['tentativas']),
          'duplicacoes_toolhelp_observadas':dups,
          'diagnostico_adicional_nt':str(OUT/'diagnostico_reuso_pid_nt.json'),
          'causa_observada':'ABI Toolhelp correto; o mesmo PID aparece com executavel e PPID diferentes numa captura, e o parser NT legado tambem rejeita duplicacao de PID. Reciclagem durante enumeracao e a inferencia suportada; camada subjacente nao foi atribuida.',
          'correcao':'Snapshot NT integral com ABI/PID/FILETIME/PPID proprio certificados. Grupos de PID com FILETIMEs diferentes exigem match unico com handle vivo. Mesmo PID+FILETIME repetido, acesso negado, buffer truncado, certificado invalido ou nova troca de instancia bloqueiam. PID realmente morto e removido somente depois de certificar snapshot inteiro; edges de filhos permanecem.',
          'regra_fallback_vivo_win5':'Somente vivo(i) sem handle retido, apos identificar gerar WinError5, consulta snapshot integral certificado. Ausencia de PID ou registro unico com FILETIME positivo diferente confirma instancia antiga morta. Mesmo FILETIME continua aguardando conservadoramente. Multiplos registros, FILETIMEzero, snapshot/certificado invalidos ou qualquer outro erro bloqueiam. identificar() e selecao geral de handles permanecem estritos.',
          'guard_vivo_win5_real':real,'provas59_preservadas':str(archive/'preservacao.json'),
          'fontes_primarias':['https://learn.microsoft.com/windows/win32/api/winternl/nf-winternl-ntqueryinformationprocess',
                              'https://learn.microsoft.com/windows/win32/api/winternl/nf-winternl-ntquerysysteminformation'],
          'limites_preservados':'Guardas de identidade, parentesco temporal, orfaos, travas, fontes congeladas e tentativa unica permanecem intactos.',
          'ativacao':'Nenhuma ativacao feita. Root coordenara renovacao dos bindings e reconciliacao preservando journal BLOCKED.'}
save('revisao_reparo_snapshot_nt.json',review)
print(json.dumps({'aprovado':receipt['aprovado'],'testes':receipt['testes_executados'],'falhas':receipt['falhas'],'erros':receipt['erros'],
                  'fontes_vinculadas':review['fontes_vinculadas'],'fontes_divergentes':changes,
                  'recibo_sha256':review['recibo_testes_sha256'],'revisao':str(OUT/'revisao_reparo_snapshot_nt.json')},ensure_ascii=False))
raise SystemExit(receipt['exitcode'])
