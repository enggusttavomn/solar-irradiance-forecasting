"""Protecoes operacionais da retomada; nenhum teste inicia treinamento real."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from codigo_fonte.acompanhamento import retomar_historico_apos_calendario as h


class Memoria:
    def __init__(self):
        self.dados = None
        self.falhar_launcher = False
        self.falhar_intento = False

    def ler(self):
        return deepcopy(self.dados)

    def gravar(self, dados):
        if self.falhar_intento and dados['etapa'] == 'LAUNCH_INTENT':
            raise PermissionError('journal inacessivel antes de Popen')
        if self.falhar_launcher and 'launcher' in dados:
            raise PermissionError('queda depois de Popen, antes de persistir launcher')
        self.dados = deepcopy(dados)


class FalsoWindows:
    def __init__(self, fixture, journal):
        self.f, self.journal = fixture, journal
        self.instancias = dict((i.pid, i) for i in fixture.manifesto.roots.values())
        self.pais = {200:100}
        self.lancamentos = 0
        self.bloquear_lock = False
        self.negar_consulta = False
        self.crash_antes_popen = False
        self.confirmar_real = True
        self.mapa_calls = 0
        self.trocar_pai = False

    def identificar(self, pid):
        if self.negar_consulta:
            raise PermissionError('WinError 5: acesso negado, estado desconhecido')
        return self.instancias.get(pid)

    def vivo(self, i):
        return self.identificar(i.pid) == i

    def mapa(self):
        self.mapa_calls += 1
        if self.trocar_pai and self.mapa_calls > 1:
            return {**self.pais, 300:9999}
        return dict(self.pais)

    def programa(self, i):
        return 'C:/Python/python.exe'

    @contextmanager
    def trava_original(self, path):
        if self.bloquear_lock:
            raise h.Bloqueio('lock ocupado')
        yield

    def lancar(self, comando, saida, erro, raiz):
        if self.journal.dados['etapa'] != 'LAUNCH_INTENT':
            raise AssertionError('Popen antes de intent duravel')
        if self.crash_antes_popen:
            raise SystemExit('crash depois de intent e antes de Popen')
        self.lancamentos += 1
        stamp = int(self.journal.dados['intent_filetime']) + 1
        self.instancias[600] = h.Instancia(600, str(stamp))
        if self.confirmar_real:
            i = h.Instancia(650, str(stamp+1))
            self.instancias[i.pid] = i
            self.pais[i.pid] = 600
            self.f.escrever(self.f.coord_status, {'identidade_coordenador':h.asdict(i),
                            'codigo_sha256':self.f.manifesto.codigo_coord_sha,
                            'etapa':'verificando_coleta_historico_1998_2022'})
        return SimpleNamespace(pid=600)


class Fixture:
    def __init__(self, raiz):
        self.raiz = raiz.resolve()
        raiz = self.raiz
        self.coord_status = raiz / h.REL / 'coordenacao_historica/status.json'
        self.runner_status = raiz / h.REL / 'fila_historica/historico_1998_2022/completa/runner.json'
        self.saida = raiz / h.REL / 'prova_helper_isolada'
        hashes = []
        for papel in sorted(h.PAPEIS - {'global'}):
            p = raiz / 'fontes' / (papel + '.py')
            if papel == 'coordenador':
                p = raiz / 'codigo_fonte/acompanhamento/coordenar_quantizacao_historica.py'
            elif papel == 'helper':
                p = raiz / 'codigo_fonte/acompanhamento/retomar_historico_apos_calendario.py'
            elif papel == 'tests_helper':
                p = raiz / 'testes/test_retomar_historico_apos_calendario.py'
            self.escrever(p, 'fixture:' + papel)
            hashes.append({'path':str(p), 'sha256':h.digest(p), 'papel':papel})
        fontes = {}
        for i in range(88):
            p = raiz / 'congelados' / f'fonte{i}.json'
            self.escrever(p, {'fonte':i})
            sha = h.digest(p); fontes[str(p)] = sha
            hashes.append({'path':str(p),'sha256':sha,'papel':'global_fonte'})
        self.global_path = raiz / 'congelados/global.json'
        self.escrever(self.global_path, {'regime':'historico_1998_2022',
                          'pares':[[f'tarefa{i}',f'modelo{i}'] for i in range(44)],
                          'fontes_sha256':fontes})
        hashes.append({'path':str(self.global_path),'sha256':h.digest(self.global_path),'papel':'global'})
        self.exe = raiz / 'python.exe'; self.escrever(self.exe, b'fake executable never invoked')
        locks = [self.coord_status.parent / '.execucao.lock', self.runner_status.parent / '.execucao.lock',
                 raiz / h.REL / 'coordenacao_atual/.execucao.lock',
                 raiz / h.REL / 'fila_atual/.execucao.lock',
                 raiz / h.REL / 'fila_historica/curto/.execucao.lock']
        for p in locks:
            self.escrever(p, b'original lock bytes')
        self.dados = {'versao':1, 'aprovado':True, 'cpu_workers':2,'gpu_workers':2,
                      'antigos':{'coordenador':{'pid':100,'creation_time':'100'},
                                'runner':{'pid':200,'creation_time':'200'}},
                      'coord_status':str(self.coord_status),'runner_status':str(self.runner_status),
                      'global':str(self.global_path),'global_mtime_ns':self.global_path.stat().st_mtime_ns,
                      'hashes':hashes,'locks':[str(p) for p in locks],
                      'comando':[str(self.exe),*h.COMANDO]}
        self.manifesto = h.Manifesto(self.dados, 'a'*64, raiz)
        self.estado_ativo()

    @staticmethod
    def escrever(p, conteudo):
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(conteudo, bytes):
            p.write_bytes(conteudo)
        elif isinstance(conteudo, str):
            p.write_text(conteudo, encoding='utf-8')
        else:
            p.write_text(json.dumps(conteudo), encoding='utf-8')

    def estado_ativo(self):
        self.escrever(self.coord_status, {'identidade_coordenador':self.dados['antigos']['coordenador'],
                                         'etapa':'fila_historico_1998_2022','processos_historico':[]})
        self.escrever(self.runner_status, {'identidade_runner':self.dados['antigos']['runner'],
                                          'etapa':'refit','regime':'historico_1998_2022',
                                          'processos_historico':[]})

    def estado_erro(self, tarefas=('monthly_6',)):
        self.escrever(self.coord_status, {'identidade_coordenador':self.dados['antigos']['coordenador'],
                       'etapa':'erro','erro':f'RuntimeError: Falha fila_historico_1998_2022; consultar {self.coord_status.parent / "fila_historico_1998_2022.log"}',
                       'eventos':[{'etapa':'fila_historico_1998_2022','retorno':1}]})
        self.escrever(self.coord_status.parent/'fila_historico_1998_2022.log','fila antiga encerrou naturalmente com erro sazonal\n')
        jobs = []
        for tarefa in tarefas:
            p = self.runner_status.parent / f'refit_{tarefa}_sazonal_ingenuo.log'
            self.escrever(p, 'Traceback (most recent call last):\nValueError: Referencia anual ausente em BYD Camacari.\n')
            jobs.append({'fase':'refit','tarefa':tarefa,'modelo':'Sazonal ingenuo','returncode':1,'log':str(p)})
        self.escrever(self.runner_status, {'identidade_runner':self.dados['antigos']['runner'],
                      'etapa':'erro','regime':'historico_1998_2022','processos':[],'pendentes':[],
                      'falhas':jobs+[{'tipo':'RuntimeError','mensagem':f'{len(jobs)} execucoes falharam; outras selecoes foram preservadas. Consulte {self.runner_status}'}]})


class TestRetomada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='retomada_calendario_test_')
        cls.fixture = Fixture(Path(cls.temp.name))
        cls.fontes_originais = {Path(x['path']):(Path(x['path']).read_bytes(),Path(x['path']).stat().st_mtime_ns)
                              for x in cls.fixture.dados['hashes']}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.f = self.fixture
        self.f.manifesto = h.Manifesto(deepcopy(self.f.dados),'a'*64,self.f.raiz)
        self.f.estado_ativo()
        self.j = Memoria(); self.b = FalsoWindows(self.f, self.j)
        self.r = h.Retomada(self.f.manifesto, self.f.saida, self.b, self.j)

    def tearDown(self):
        for p,(bruto,mtime) in self.fontes_originais.items():
            if not p.exists() or p.stat().st_mtime_ns != mtime:
                p.write_bytes(bruto); os.utime(p,ns=(p.stat().st_atime_ns,mtime))

    def encerrados(self, tarefas=('monthly_6',)):
        self.f.estado_erro(tarefas); self.b.instancias.clear(); self.b.pais.clear()

    def aprovar_falha_tecnica(self):
        self.encerrados()
        log = self.f.runner_status.parent / 'refit_monthly_1_dilatedrnn.log'
        self.f.escrever(log, 'monthly_1/DilatedRNN/q64/refit seed=42 inicio\n')
        fontes = {}
        raiz = self.f.global_path.parent / 'monthly_1/dilatedrnn'
        for variante, seeds in (('sem_quantizacao', range(40,45)), ('q64', range(40,42))):
            for seed in seeds:
                npz = raiz / variante / 'refit' / f'seed{seed}.npz'
                for p in (npz, npz.with_suffix('.json'), npz.with_suffix('.csv'),
                          raiz / variante / 'modelos' / f'seed{seed}_refit.pt'):
                    self.f.escrever(p, f'artefato isolado {variante}/{seed}/{p.suffix}')
                    fontes[str(p)] = h.digest(p)
        recibo = self.f.saida / 'auditoria_caches_tecnica.json'
        audit = {'versao':1, 'aprovado':True, 'regime':'historico_1998_2022',
                 **h.FALHA_TECNICA, 'log':str(log), 'log_sha256':h.digest(log),
                 'caches_completos_verificados':7, 'fontes_sha256':fontes}
        self.f.escrever(recibo, audit)
        dados = deepcopy(self.f.dados)
        dados['falhas_tecnicas_aprovadas'] = [{**h.FALHA_TECNICA,
            'log':str(log), 'log_sha256':h.digest(log),
            'auditoria_caches':{'path':str(recibo), 'sha256':h.digest(recibo)}}]
        dados['hashes'].extend({'path':p, 'sha256':s, 'papel':'auditoria_tecnica_fonte'}
                               for p,s in fontes.items())
        runner = h.ler(self.f.runner_status)
        runner['falhas'].insert(0, {**h.FALHA_TECNICA, 'log':str(log)})
        runner['falhas'][-1]['mensagem'] = f'2 execucoes falharam; outras selecoes foram preservadas. Consulte {self.f.runner_status}'
        self.f.escrever(self.f.runner_status, runner)
        self.f.manifesto = h.Manifesto(dados, 'a'*64, self.f.raiz)
        self.r = h.Retomada(self.f.manifesto, self.f.saida, self.b, self.j)
        return log, recibo, dados

    def reaprovar_recibo(self, recibo, dados, audit):
        self.f.escrever(recibo, audit)
        dados['falhas_tecnicas_aprovadas'][0]['auditoria_caches']['sha256'] = h.digest(recibo)
        self.f.manifesto = h.Manifesto(dados, 'a'*64, self.f.raiz)
        self.r = h.Retomada(self.f.manifesto, self.f.saida, self.b, self.j)

    def test_falha_tecnica_exata_com_sete_caches_lanca_so_uma_vez(self):
        _, recibo, _ = self.aprovar_falha_tecnica()
        self.assertTrue(self.r.ciclo()); self.assertEqual(self.b.lancamentos,1)
        self.assertEqual(self.j.dados['etapa'],'CONFIRMED')
        self.assertIn(str(recibo), [p['origem'] for p in self.j.dados['preservados']])
        r2 = h.Retomada(self.f.manifesto,self.f.saida,self.b,self.j)
        self.assertTrue(r2.ciclo()); self.assertEqual(self.b.lancamentos,1)

    def test_falha_tecnica_log_alterado_bloqueia(self):
        log, _, _ = self.aprovar_falha_tecnica(); self.f.escrever(log,'log modificado\n')
        with self.assertRaisesRegex(h.Bloqueio,'SHA256 do log tecnico'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_falha_tecnica_recibo_alterado_bloqueia(self):
        _, recibo, _ = self.aprovar_falha_tecnica(); self.f.escrever(recibo,recibo.read_text()+'\n')
        with self.assertRaisesRegex(h.Bloqueio,'SHA256 do recibo tecnico'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_falha_tecnica_sem_recibo_bloqueia(self):
        _, recibo, _ = self.aprovar_falha_tecnica(); recibo.unlink()
        with self.assertRaisesRegex(h.Bloqueio,'ausente ou ilegivel'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_falha_tecnica_outro_job_ou_codigo_bloqueia(self):
        self.aprovar_falha_tecnica(); original=h.ler(self.f.runner_status)
        for campo,valor in (('tarefa','monthly_6'),('modelo','GRU'),('fase','selecao'),('returncode',2),('returncode',True)):
            with self.subTest(campo=campo,valor=valor):
                runner=deepcopy(original); runner['falhas'][0][campo]=valor
                self.f.escrever(self.f.runner_status,runner)
                with self.assertRaisesRegex(h.Bloqueio,'Falha adicional'): self.r.ciclo()
                self.assertEqual(self.b.lancamentos,0)

    def test_manifesto_falha_tecnica_generica_ou_duplicada_bloqueia(self):
        _, _, dados=self.aprovar_falha_tecnica()
        for campo,valor in (('tarefa','monthly_6'),('modelo','GRU'),('fase','selecao'),('returncode',True)):
            with self.subTest(campo=campo):
                d=deepcopy(dados); d['falhas_tecnicas_aprovadas'][0][campo]=valor
                with self.assertRaises(h.Bloqueio): h.Manifesto(d,'a'*64,self.f.raiz)
        d=deepcopy(dados); d['falhas_tecnicas_aprovadas']*=2
        with self.assertRaises(h.Bloqueio): h.Manifesto(d,'a'*64,self.f.raiz)
        self.assertEqual(self.b.lancamentos,0)

    def test_falha_tecnica_recibo_outro_escopo_ou_contagem_bloqueia(self):
        _, recibo, dados=self.aprovar_falha_tecnica(); original=h.ler(recibo)
        for campo,valor in (('modelo','GRU'),('tarefa','monthly_6'),('caches_completos_verificados',6),('aprovado',False)):
            with self.subTest(campo=campo):
                audit=deepcopy(original); audit[campo]=valor
                self.reaprovar_recibo(recibo,dados,audit)
                with self.assertRaisesRegex(h.Bloqueio,'nao cobre'): self.r.ciclo()
                self.assertEqual(self.b.lancamentos,0)

    def test_falha_tecnica_recibo_fontes_fora_manifesto_bloqueia(self):
        _, recibo, dados=self.aprovar_falha_tecnica(); audit=h.ler(recibo)
        audit['fontes_sha256'].pop(next(iter(audit['fontes_sha256'])))
        self.reaprovar_recibo(recibo,dados,audit)
        with self.assertRaisesRegex(h.Bloqueio,'divergem do manifesto'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_falha_tecnica_cache_alterado_bloqueia(self):
        _, recibo, _=self.aprovar_falha_tecnica()
        p=Path(next(iter(h.ler(recibo)['fontes_sha256'])))
        self.f.escrever(p,'cache alterado')
        with self.assertRaisesRegex(h.Bloqueio,'Fonte da auditoria tecnica divergiu'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_falha_tecnica_aprovada_ausente_no_runner_bloqueia(self):
        self.aprovar_falha_tecnica(); self.f.estado_erro()
        with self.assertRaisesRegex(h.Bloqueio,'nao corresponde ao runner'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_falha_tecnica_nao_dispensa_guardas_sazonais_e_resumo(self):
        self.aprovar_falha_tecnica(); original=h.ler(self.f.runner_status)
        runner=deepcopy(original); runner['falhas'].pop(1)
        runner['falhas'][-1]['mensagem']=f'1 execucoes falharam; outras selecoes foram preservadas. Consulte {self.f.runner_status}'
        self.f.escrever(self.f.runner_status,runner)
        with self.assertRaisesRegex(h.Bloqueio,'Quantidade de falhas sazonais'): self.r.ciclo()
        runner=deepcopy(original); runner['falhas'][-1]['mensagem']='resumo generico'
        self.f.escrever(self.f.runner_status,runner)
        with self.assertRaisesRegex(h.Bloqueio,'Resumo de erro'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_aguarda_raizes_vivas_sem_lancar(self):
        self.assertFalse(self.r.ciclo()); self.assertEqual(self.j.dados['etapa'],'WAITING')
        self.assertEqual(self.b.lancamentos,0)

    def test_runner_vivo_com_coordenador_morto_continua_aguardando(self):
        del self.b.instancias[100]
        self.assertFalse(self.r.ciclo()); self.assertEqual(self.b.lancamentos,0)

    def test_filhos_futuros_capturados_persistidos_e_aguardados(self):
        self.b.instancias[300]=h.Instancia(300,'300'); self.b.pais[300]=200
        self.b.instancias[400]=h.Instancia(400,'400'); self.b.pais[400]=300
        self.r.ciclo()
        self.assertIn({'pid':400,'creation_time':'400'},self.j.dados['conhecidos'])
        self.b.instancias.pop(100); self.b.instancias.pop(200)
        self.assertFalse(self.r.ciclo()); self.assertEqual(self.b.lancamentos,0)

    def test_reuso_pid_raiz_bloqueia(self):
        self.b.instancias[100]=h.Instancia(100,'999')
        with self.assertRaises(h.Bloqueio): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_win5_consulta_nao_e_morte(self):
        self.b.negar_consulta=True
        with self.assertRaises(PermissionError): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_race_parentesco_bloqueia(self):
        self.b.instancias[300]=h.Instancia(300,'300'); self.b.pais[300]=200
        self.b.trocar_pai=True
        with self.assertRaises(h.Bloqueio): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_filho_mais_antigo_nao_entra_arvore(self):
        self.b.instancias[300]=h.Instancia(300,'150'); self.b.pais[300]=200
        with self.assertRaises(h.Bloqueio): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_descendente_desconhecido_apos_saida_bloqueia(self):
        self.encerrados(); self.b.pais[888]=200
        self.b.instancias[888]=h.Instancia(888,'300')
        with self.assertRaises(h.Bloqueio): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_pid_conhecido_reutilizado_nao_esconde_orfao(self):
        self.encerrados()
        self.r.conhecidos.add(h.Instancia(300,'250'))
        self.b.instancias[300]=h.Instancia(300,'350'); self.b.pais[300]=200
        with self.assertRaisesRegex(h.Bloqueio,'descendente nao identificado'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_falha_modelo_extra_bloqueia(self):
        self.encerrados(); d=h.ler(self.f.runner_status)
        d['falhas'][0]['modelo']='XGBoost'; self.f.escrever(self.f.runner_status,d)
        with self.assertRaisesRegex(h.Bloqueio,'Falha adicional'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_falha_outro_valueerror_bloqueia(self):
        self.encerrados(); p=Path(h.ler(self.f.runner_status)['falhas'][0]['log'])
        self.f.escrever(p,'ValueError: forma invalida\n')
        with self.assertRaisesRegex(h.Bloqueio,'Erro sazonal difere'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_falha_apos_mensagem_sazonal_bloqueia(self):
        self.encerrados(); p=Path(h.ler(self.f.runner_status)['falhas'][0]['log'])
        self.f.escrever(p,'ValueError: Referencia anual ausente em X.\nPermissionError: status inacessivel\n')
        with self.assertRaises(h.Bloqueio): self.r.ciclo()

    def test_pendentes_no_estado_erro_bloqueia(self):
        self.encerrados(); d=h.ler(self.f.runner_status); d['pendentes']=[['monthly_1','GRU']]
        self.f.escrever(self.f.runner_status,d)
        with self.assertRaises(h.Bloqueio): self.r.ciclo()

    def test_hash_divergente_impede_popen(self):
        self.encerrados(); p=Path(self.f.dados['hashes'][0]['path']); self.f.escrever(p,'mudou')
        with self.assertRaisesRegex(h.Bloqueio,'Fonte divergiu'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_mtime_global_divergente_impede_popen(self):
        self.encerrados(); p=self.f.global_path; stamp=p.stat().st_mtime_ns
        os.utime(p,ns=(p.stat().st_atime_ns,stamp+10_000_000))
        with self.assertRaisesRegex(h.Bloqueio,'mtime do global'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_lock_ocupado_impede_popen(self):
        self.encerrados(); self.b.bloquear_lock=True
        with self.assertRaisesRegex(h.Bloqueio,'lock ocupado'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_dois_sazonais_autorizados_lancam_uma_vez_e_confirmam(self):
        self.encerrados(('monthly_1','monthly_6'))
        self.assertTrue(self.r.ciclo()); self.assertEqual(self.b.lancamentos,1)
        self.assertEqual(self.j.dados['etapa'],'CONFIRMED')
        self.assertGreaterEqual(len(self.j.dados['preservados']),5)
        for registro in self.j.dados['preservados']:
            self.assertEqual(h.digest(registro['copia']),registro['sha256'])
        r2=h.Retomada(self.f.manifesto,self.f.saida,self.b,self.j)
        self.assertTrue(r2.ciclo()); self.assertEqual(self.b.lancamentos,1)

    def test_crash_antes_popen_nao_permite_segunda_tentativa(self):
        self.encerrados(); self.b.crash_antes_popen=True
        with self.assertRaises(SystemExit): self.r.ciclo()
        self.assertEqual(self.j.dados['etapa'],'LAUNCH_INTENT')
        self.assertEqual(self.b.lancamentos,0)
        with self.assertRaises(h.Bloqueio): h.Retomada(self.f.manifesto,self.f.saida,self.b,self.j)

    def test_crash_apos_popen_nao_permite_repeticao(self):
        self.encerrados(); self.j.falhar_launcher=True
        with self.assertRaises(PermissionError): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,1); self.assertEqual(self.j.dados['etapa'],'LAUNCH_INTENT')
        with self.assertRaises(h.Bloqueio): h.Retomada(self.f.manifesto,self.f.saida,self.b,self.j)

    def test_intent_sem_durabilidade_nao_lanca(self):
        self.encerrados(); self.j.falhar_intento=True
        with self.assertRaises(PermissionError): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)

    def test_status_novo_precisa_descender_do_launcher(self):
        self.encerrados(); self.b.confirmar_real=False
        self.assertFalse(self.r.ciclo()); self.assertEqual(self.b.lancamentos,1)
        stamp=int(self.r.estado['intent_filetime'])+10
        i=h.Instancia(999,str(stamp)); self.b.instancias[999]=i; self.b.pais[999]=3333
        self.f.escrever(self.f.coord_status,{'identidade_coordenador':h.asdict(i),
                        'codigo_sha256':self.f.manifesto.codigo_coord_sha,'etapa':'ativa'})
        with self.assertRaises(h.Bloqueio): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,1)

    def test_status_novo_codigo_divergente_nao_confirma(self):
        self.encerrados(); self.b.confirmar_real=False; self.r.ciclo()
        i=h.Instancia(650,str(int(self.r.estado['intent_filetime'])+10))
        self.b.instancias[i.pid]=i; self.b.pais[i.pid]=600
        self.f.escrever(self.f.coord_status,{'identidade_coordenador':h.asdict(i),
                        'codigo_sha256':'0'*64,'etapa':'ativa'})
        with self.assertRaises(h.Bloqueio): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,1)

    def test_parada_antes_lancamento_preserva_processos(self):
        self.f.manifesto.parada=self.f.raiz/'parar'; self.f.escrever(self.f.manifesto.parada,'parar')
        antes=dict(self.b.instancias)
        with self.assertRaises(h.Bloqueio): self.r.ciclo()
        self.assertEqual(self.b.instancias,antes); self.assertEqual(self.b.lancamentos,0)

    def test_saida_diferente_tem_mesmo_lock_e_journal(self):
        outra=h.Retomada(self.f.manifesto,self.f.saida.parent/'outra',self.b)
        self.assertEqual(outra.journal.path,self.f.manifesto.canonico/'journal.json')

    def test_manifesto_sha_divergente_e_comando_adicional_rejeitados(self):
        p=self.f.raiz/'manifesto.json'; self.f.escrever(p,self.f.dados)
        with self.assertRaises(h.Bloqueio): h.Manifesto.carregar(p,'0'*64,self.f.raiz)
        correto=hashlib.sha256(p.read_bytes()).hexdigest()
        h.Manifesto.carregar(p,correto,self.f.raiz)
        d=deepcopy(self.f.dados); d['comando'].append('--somente-planejar')
        with self.assertRaises(h.Bloqueio): h.Manifesto(d,'a'*64,self.f.raiz)

    def test_global_88_correspondencia_estrita(self):
        d=deepcopy(self.f.dados)
        next(x for x in d['hashes'] if x['papel']=='global_fonte')['papel']='fonte_qualquer'
        with self.assertRaises(h.Bloqueio): h.Manifesto(d,'a'*64,self.f.raiz)

    def test_caminho_externo_rejeitado_sem_resolver_folha(self):
        with self.assertRaises(h.Bloqueio): h.local(self.f.raiz.parent/'fora.json',self.f.raiz)
        self.assertEqual(h.local(self.f.raiz/'inexistente.pdf',self.f.raiz),self.f.raiz/'inexistente.pdf')

    @unittest.skipUnless(os.name=='nt','erros nativos Windows')
    def test_backend_win5_nao_retorna_morto(self):
        from unittest.mock import patch
        b=object.__new__(h.Windows)
        b.k=SimpleNamespace(OpenProcess=lambda *args:0); b.handles={}
        with patch.object(h.ctypes,'get_last_error',return_value=5):
            with self.assertRaises(OSError) as caught: b.identificar(777)
        self.assertEqual(caught.exception.winerror,5)

    @unittest.skipUnless(os.name=='nt','erros nativos Windows')
    def test_backend_win87_pid_ausente_retorna_none(self):
        from unittest.mock import patch
        b=object.__new__(h.Windows)
        b.k=SimpleNamespace(OpenProcess=lambda *args:0); b.handles={}
        with patch.object(h.ctypes,'get_last_error',return_value=87):
            self.assertIsNone(b.identificar(777))

    @staticmethod
    def montar_snapshot_nt(linhas):
        partes = []
        for indice, (pid, stamp, ppid) in enumerate(linhas):
            r = h.Windows.ProcessoSistemaPrefixo()
            r.pid, r.ppid, r.creation_time = pid, ppid, stamp
            r.next_offset = h.ctypes.sizeof(r) if indice + 1 < len(linhas) else 0
            partes.append(bytes(r))
        return b''.join(partes)

    def snapshot_nt_falso(self, linhas=None, *, bruto=None, status=0, tamanho_retornado=None,
                          basico_pid=None, basico_ppid=47, basico_status=0, basico_tamanho=None):
        if bruto is None:
            bruto = self.montar_snapshot_nt(linhas if linhas is not None else [(os.getpid(),123,47)])
        b = object.__new__(h.Windows); b.handles = {}
        def sistema(classe, buffer, tamanho, retorno):
            self.assertEqual(classe,5)
            retorno._obj.value = len(bruto) if tamanho_retornado is None else tamanho_retornado
            if status == 0 and len(bruto) <= tamanho:
                h.ctypes.memmove(buffer,bruto,len(bruto))
            return status
        def processo(handle, classe, pointer, tamanho, retorno):
            self.assertEqual(classe,0)
            pointer._obj.pid = os.getpid() if basico_pid is None else basico_pid
            pointer._obj.ppid = basico_ppid
            retorno._obj.value = tamanho if basico_tamanho is None else basico_tamanho
            return basico_status
        b.k = SimpleNamespace(GetCurrentProcess=Mock(return_value=-1))
        b.nt = SimpleNamespace(NtQuerySystemInformation=Mock(side_effect=sistema),
                               NtQueryInformationProcess=Mock(side_effect=processo))
        b._stamp = Mock(return_value='123')
        b.identificar = Mock(return_value=h.Instancia(777,'200'))
        b.vivo = Mock(return_value=True)
        return b

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_pid_reutilizado_escolhe_filetime_e_ppid_do_handle_vivo(self):
        b = self.snapshot_nt_falso([(os.getpid(),123,47),(777,100,6),(777,200,9)])
        self.assertEqual(b.mapa(),{os.getpid():47,777:9})
        b.identificar.assert_called_once_with(777)
        b.vivo.assert_called_once_with(h.Instancia(777,'200'))
        self.assertEqual(b.nt.NtQuerySystemInformation.call_count,1)

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_identidade_duplicada_bloqueia_sem_consultar_handle(self):
        for ppid in (6,9):
            with self.subTest(ppid=ppid):
                b = self.snapshot_nt_falso([(os.getpid(),123,47),(777,100,6),(777,100,ppid)])
                with self.assertRaisesRegex(h.Bloqueio,'PID/FILETIME duplicada'): b.mapa()
                b.identificar.assert_not_called()

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_pid_reutilizado_morto_preserva_edge_do_orfao(self):
        b = self.snapshot_nt_falso([(os.getpid(),123,47),(777,100,6),(777,200,9),(888,300,777)])
        b.identificar.return_value = None
        self.assertEqual(b.mapa(),{os.getpid():47,888:777})
        b.nt.NtQueryInformationProcess.assert_called_once()

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_pid_reutilizado_acesso_negado_nao_confirma_ausencia(self):
        b = self.snapshot_nt_falso([(os.getpid(),123,47),(777,100,6),(777,200,9)])
        b.identificar.side_effect = PermissionError('WinError5: identidade desconhecida')
        with self.assertRaises(PermissionError): b.mapa()

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_pid_reutilizado_novamente_ou_morto_na_revalidacao_bloqueia(self):
        for atual, vivo in ((h.Instancia(777,'300'),True),(h.Instancia(777,'200'),False)):
            with self.subTest(atual=atual,vivo=vivo):
                b = self.snapshot_nt_falso([(os.getpid(),123,47),(777,100,6),(777,200,9)])
                b.identificar.return_value = atual; b.vivo.return_value = vivo
                with self.assertRaisesRegex(h.Bloqueio,'identidade inconclusiva'): b.mapa()

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_certificacao_antecede_descarte_de_pid_morto(self):
        b = self.snapshot_nt_falso([(os.getpid(),124,47),(777,100,6),(777,200,9)])
        b.identificar.return_value = None
        with self.assertRaisesRegex(h.Bloqueio,'proprio processo'): b.mapa()
        b.identificar.assert_not_called()

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_proprio_pid_filetime_ppid_precisam_corresponder(self):
        for linhas in ([(777,123,47)],[(os.getpid(),124,47)],[(os.getpid(),123,48)]):
            with self.subTest(linhas=linhas):
                b = self.snapshot_nt_falso(linhas)
                with self.assertRaisesRegex(h.Bloqueio,'proprio processo'): b.mapa()

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_consulta_certificadora_inconclusiva_bloqueia(self):
        for kwargs in ({'basico_pid':777},{'basico_status':0xc0000001},{'basico_tamanho':1}):
            with self.subTest(kwargs=kwargs):
                b = self.snapshot_nt_falso(**kwargs)
                with self.assertRaisesRegex(h.Bloqueio,'nao certificou'): b.mapa()

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_filetime_proprio_indeterminado_bloqueia(self):
        b = self.snapshot_nt_falso(); b._stamp.return_value = '0'
        with self.assertRaisesRegex(h.Bloqueio,'proprio processo'): b.mapa()

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_vazio_truncado_e_returnlength_invalidos_bloqueiam(self):
        for bruto, retorno in ((b'',None),(b'\0',None),(self.montar_snapshot_nt([(os.getpid(),123,47)]),1),
                               (b'',1024*1024)):
            with self.subTest(tamanho=len(bruto),retorno=retorno):
                b = self.snapshot_nt_falso(bruto=bruto,tamanho_retornado=retorno)
                with self.assertRaises(h.Bloqueio): b.mapa()

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_deslocamento_invalido_nao_oculta_registros(self):
        bruto = self.montar_snapshot_nt([(os.getpid(),123,47),(777,200,9)])
        n = h.ctypes.sizeof(h.Windows.ProcessoSistemaPrefixo)
        for passo in (8,n+1,n*2):
            with self.subTest(passo=passo):
                r = h.Windows.ProcessoSistemaPrefixo.from_buffer_copy(bruto); r.next_offset = passo
                b = self.snapshot_nt_falso(bruto=bytes(r)+bruto[n:])
                with self.assertRaisesRegex(h.Bloqueio,'Deslocamento invalido'): b.mapa()

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_ntstatus_erro_nao_retorna_parcial(self):
        for status in (0xc0000001,-1073741823):
            with self.subTest(status=status):
                b = self.snapshot_nt_falso(status=status)
                with self.assertRaisesRegex(h.Bloqueio,'NTSTATUS'): b.mapa()
                b.nt.NtQueryInformationProcess.assert_not_called()

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_cresce_so_em_buffer_insuficiente(self):
        b = self.snapshot_nt_falso()
        original = b.nt.NtQuerySystemInformation.side_effect
        def consulta(classe,buffer,tamanho,retorno):
            if b.nt.NtQuerySystemInformation.call_count == 1:
                retorno._obj.value = tamanho+1
                return -1073741820
            return original(classe,buffer,tamanho,retorno)
        b.nt.NtQuerySystemInformation.side_effect = consulta
        self.assertEqual(b.mapa(),{os.getpid():47})
        self.assertEqual([call.args[2] for call in b.nt.NtQuerySystemInformation.call_args_list],
                         [256*1024,512*1024])

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_cap_e_resize_persistente_bloqueiam(self):
        for retorno, texto in ((64*1024*1024,'limite de 32 MiB'),(1,'oito vezes')):
            with self.subTest(retorno=retorno):
                b = self.snapshot_nt_falso(status=0xc0000004,tamanho_retornado=retorno)
                with self.assertRaisesRegex(h.Bloqueio,texto): b.mapa()

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_identidade_duplicada_impede_popen_antes_intento(self):
        self.encerrados()
        b = self.snapshot_nt_falso([(os.getpid(),123,47),(777,100,6),(777,100,9)])
        self.b.mapa = b.mapa
        with self.assertRaisesRegex(h.Bloqueio,'PID/FILETIME duplicada'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)
        self.assertEqual(self.r.estado['tentativas_popen'],0)

    @unittest.skipUnless(os.name=='nt','ABI nativo Windows')
    def test_snapshot_acesso_negado_impede_popen_antes_intento(self):
        self.encerrados()
        b = self.snapshot_nt_falso([(os.getpid(),123,47),(777,100,6),(777,200,9)])
        b.identificar.side_effect = PermissionError('WinError5')
        self.b.mapa = b.mapa
        with self.assertRaises(PermissionError): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)
        self.assertEqual(self.r.estado['tentativas_popen'],0)

    def backend_vivo_protegido(self, linhas=None, **kwargs):
        b = self.snapshot_nt_falso(linhas,**kwargs)
        b.vivo = h.Windows.vivo.__get__(b,h.Windows)
        b.identificar.side_effect = h.ctypes.WinError(5)
        return b

    @unittest.skipUnless(os.name=='nt','erros nativos Windows')
    def test_vivo_win5_ausencia_certificada_confirma_instancia_antiga_morta(self):
        b = self.backend_vivo_protegido()
        self.assertFalse(b.vivo(h.Instancia(777,'100')))
        b.nt.NtQueryInformationProcess.assert_called_once()
        self.assertEqual(b.handles,{})

    @unittest.skipUnless(os.name=='nt','erros nativos Windows')
    def test_vivo_win5_filetime_diferente_certificado_confirma_antiga_morta(self):
        b = self.backend_vivo_protegido([(os.getpid(),123,47),(777,200,9)])
        self.assertFalse(b.vivo(h.Instancia(777,'100')))
        self.assertEqual(b.handles,{})

    @unittest.skipUnless(os.name=='nt','erros nativos Windows')
    def test_vivo_win5_mesma_identidade_certificada_continua_aguardando(self):
        b = self.backend_vivo_protegido([(os.getpid(),123,47),(777,100,9)])
        self.assertTrue(b.vivo(h.Instancia(777,'100')))
        self.assertEqual(b.handles,{})

    @unittest.skipUnless(os.name=='nt','erros nativos Windows')
    def test_vivo_win5_snapshot_inconclusivo_nunca_confirma_morto(self):
        for kwargs in ({'bruto':b''},{'linhas':[(os.getpid(),124,47)]},
                       {'basico_ppid':48},{'status':0xc0000001}):
            with self.subTest(kwargs=kwargs):
                b = self.backend_vivo_protegido(**kwargs)
                with self.assertRaises(h.Bloqueio): b.vivo(h.Instancia(777,'100'))

    @unittest.skipUnless(os.name=='nt','erros nativos Windows')
    def test_vivo_win5_pid_ambiguo_certificado_bloqueia(self):
        b = self.backend_vivo_protegido([(os.getpid(),123,47),(777,100,6),(777,200,9)])
        with self.assertRaisesRegex(h.Bloqueio,'PID protegido ambiguo'): b.vivo(h.Instancia(777,'100'))

    @unittest.skipUnless(os.name=='nt','erros nativos Windows')
    def test_vivo_win5_filetime_zero_do_protegido_bloqueia(self):
        b = self.backend_vivo_protegido([(os.getpid(),123,47),(777,0,9)])
        with self.assertRaisesRegex(h.Bloqueio,'FILETIME'): b.vivo(h.Instancia(777,'100'))

    @unittest.skipUnless(os.name=='nt','erros nativos Windows')
    def test_vivo_outro_erro_de_identificar_nao_usa_snapshot(self):
        b = self.backend_vivo_protegido(); b.identificar.side_effect = h.ctypes.WinError(6)
        with self.assertRaises(OSError) as caught: b.vivo(h.Instancia(777,'100'))
        self.assertEqual(caught.exception.winerror,6)
        b.nt.NtQuerySystemInformation.assert_not_called()

    @unittest.skipUnless(os.name=='nt','erros nativos Windows')
    def test_vivo_handle_retido_erro_de_stamp_nao_usa_fallback(self):
        b = self.backend_vivo_protegido(); i = h.Instancia(777,'100'); b.handles[i] = 12345
        b._stamp.side_effect = h.ctypes.WinError(5)
        with self.assertRaises(OSError) as caught: b.vivo(i)
        self.assertEqual(caught.exception.winerror,5)
        b.identificar.assert_not_called(); b.nt.NtQuerySystemInformation.assert_not_called()

    @unittest.skipUnless(os.name=='nt','erros nativos Windows')
    def test_vivo_win5_ambiguo_impede_popen_antes_intento(self):
        self.encerrados()
        b = self.backend_vivo_protegido([(os.getpid(),123,47),(100,99,6),(100,100,9)])
        self.b.vivo = b.vivo
        with self.assertRaisesRegex(h.Bloqueio,'PID protegido ambiguo'): self.r.ciclo()
        self.assertEqual(self.b.lancamentos,0)
        self.assertEqual(self.r.estado['tentativas_popen'],0)

    @unittest.skipUnless(os.name=='nt','snapshot nativo Windows somente leitura')
    def test_snapshot_nativo_30_consultas_certificam_pid_filetime_ppid(self):
        b = h.Windows()
        try:
            for _ in range(30):
                self.assertIn(os.getpid(),b.mapa())
        finally: b.fechar()

    @unittest.skipUnless(os.name=='nt','lock nativo Windows')
    def test_lock_exclusivo_nativo_so_fixture(self):
        b=h.Windows()
        try:
            with b.lock_observador(self.f.raiz/'lock_isolado'):
                with self.assertRaises(h.Bloqueio):
                    with b.lock_observador(self.f.raiz/'lock_isolado'): pass
        finally: b.fechar()

    @unittest.skipUnless(os.name=='nt','trava nativa Windows')
    def test_probe_original_nativo_preserva_bytes_e_mtime(self):
        p=Path(self.f.dados['locks'][0]); before=(p.read_bytes(),p.stat().st_mtime_ns)
        b=h.Windows()
        try:
            with b.trava_original(p):
                with self.assertRaises(h.Bloqueio):
                    with b.trava_original(p): pass
        finally: b.fechar()
        self.assertEqual((p.read_bytes(),p.stat().st_mtime_ns),before)


if __name__=='__main__':
    unittest.main()
