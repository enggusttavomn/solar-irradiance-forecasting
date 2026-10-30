import json
import sys
import time

from codigo_fonte.acompanhamento.processos_quantizacao import ProcessoProprio


def test_jobs_aninhados_coordenador_runner_treino(tmp_path):
    treino = tmp_path / 'treino.json'
    runner = tmp_path / 'runner.json'
    codigo_treino = "import os,json;from pathlib import Path;Path(" + repr(str(treino)) + ").write_text(json.dumps({'pid':os.getpid(),'ok':True}))"
    codigo_runner = (
        'import sys,time,json;from pathlib import Path\n'
        'from codigo_fonte.acompanhamento.processos_quantizacao import ProcessoProprio\n'
        'p=ProcessoProprio([sys.executable,\'-c\',' + repr(codigo_treino) + '])\n'
        'try:\n'
        ' while p.poll() is None: time.sleep(.05)\n'
        ' assert p.returncode == 0\n'
        ' Path(' + repr(str(runner)) + ').write_text(json.dumps({\'ok\':True,\'identidade\':p.registro}))\n'
        'finally: p.fechar()\n')
    coordenador = ProcessoProprio([sys.executable, '-c', codigo_runner])
    try:
        limite = time.monotonic() + 40
        while coordenador.poll() is None and time.monotonic() < limite:
            time.sleep(.05)
        assert coordenador.poll() == 0
        assert json.loads(runner.read_text())['ok']
        assert json.loads(treino.read_text())['ok']
    finally:
        coordenador.fechar()
