"""Valida o helper com fixtures e consultas Windows; nunca inicia treinamentos."""
from pathlib import Path
import hashlib
import json
import os
import sys
import time
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts import retomar_historico_apos_calendario as h


def sha(path):
    return h.digest(path)


def save(name, value):
    target = OUT / name
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


manifest_path = ROOT / h.REL / 'retomada_local_20261005_1715/manifesto_recuperacao.json'
manifest_bytes = manifest_path.read_bytes()
manifest = json.loads(manifest_bytes)
coordenador = manifest['antigos']['coordenador']
journal_path = ROOT / h.REL / 'retomadas_apos_calendario' / (str(coordenador['pid']) + '_' + coordenador['creation_time']) / 'journal.json'
journal_bytes = journal_path.read_bytes()
journal = json.loads(journal_bytes)
assert journal['etapa'] == 'BLOCKED'
assert journal['tentativas_popen'] == 0
assert journal['lancamento_pode_ter_ocorrido'] is False

log_path = OUT / 'testes_reparo_watcher.log'
started = datetime.now(timezone.utc).isoformat()
with log_path.open('x', encoding='utf-8', newline='\n') as log:
    suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_retomar_historico_apos_calendario')
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)

sources = {str(ROOT / 'scripts/retomar_historico_apos_calendario.py'): sha(ROOT / 'scripts/retomar_historico_apos_calendario.py'),
           str(ROOT / 'tests/test_retomar_historico_apos_calendario.py'): sha(ROOT / 'tests/test_retomar_historico_apos_calendario.py')}
receipt = {'versao':1, 'aprovado':result.wasSuccessful(), 'exitcode':0 if result.wasSuccessful() else 1,
           'testes_executados':result.testsRun, 'falhas':len(result.failures), 'erros':len(result.errors),
           'ignorados':len(result.skipped), 'iniciado_em_utc':started,
           'concluido_em_utc':datetime.now(timezone.utc).isoformat(),
           'comando':[sys.executable, '-X', 'utf8', str(Path(__file__).resolve())],
           'modulo_unittest':'tests.test_retomar_historico_apos_calendario',
           'fontes_sha256':sources, 'log':str(log_path), 'log_sha256':sha(log_path),
           'escopo':'Fixtures isoladas e snapshots somente leitura; nenhum treinamento iniciado, parado ou alterado.'}
save('testes_reparo_watcher.json', receipt)

changes = []
for binding in manifest['hashes']:
    current = sha(Path(binding['path']))
    if current != binding['sha256']:
        changes.append({**binding, 'sha256_atual':current})
assert {entry['papel'] for entry in changes} == {'helper','tests_helper'}
assert len(changes) == 2
assert manifest_path.read_bytes() == manifest_bytes
assert journal_path.read_bytes() == journal_bytes
review = {'versao':1, 'revisado_em_utc':datetime.now(timezone.utc).isoformat(),
          'aprovado_para_reconciliacao':result.wasSuccessful(),
          'manifesto_atual':str(manifest_path), 'manifesto_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
          'fontes_vinculadas':len(manifest['hashes']), 'fontes_divergentes':changes,
          'fontes_demais_preservadas':len(manifest['hashes'])-len(changes),
          'journal_canonico':str(journal_path), 'journal_sha256':hashlib.sha256(journal_bytes).hexdigest(),
          'journal_etapa':journal['etapa'], 'tentativas_popen':journal['tentativas_popen'],
          'lancamento_pode_ter_ocorrido':journal['lancamento_pode_ter_ocorrido'],
          'manifesto_e_journal_preservados':True,
          'recibo_testes':str(OUT / 'testes_reparo_watcher.json'),
          'recibo_testes_sha256':sha(OUT / 'testes_reparo_watcher.json'),
          'correcao':'Tipo ctypes de PROCESSENTRY32 estavel; ate tres snapshots completos para PID duplicado. Cada snapshot parcial e descartado e fechado. Persistencia, falha de acesso, mapa vazio ou proprio PID ausente bloqueiam antes de Popen.',
          'limites_preservados':'Identidades PID/FILETIME, vinculo SHA256 de fontes, locks originais, journal canonico e tentativa unica permanecem estritos.',
          'ativacao':'Nenhum watcher relancado. Requer reconciliacao explicita do journal BLOCKED e novo binding de helper/testes/recibo antes da ativacao.'}
save('revisao_reparo_watcher.json', review)
print(json.dumps({'testes':receipt, 'revisao':review}, ensure_ascii=False))
raise SystemExit(receipt['exitcode'])
