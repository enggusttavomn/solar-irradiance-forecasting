"""Caminhos PDF logicos e guardas de entrega, com NASCA/IO simulados.

Nenhum PDF, manifesto de experimento ou registro de entrega real e criado.
"""
from contextlib import ExitStack
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import unittest

from scripts import entregar_pdf_quantizacao_todos_modelos as entrega
from scripts import gerar_pdf_quantizacao_todos_modelos as gerador


class _AmbientePDF(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(dir='tmp')
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name).resolve()
        self.doc = self.raiz / 'documentacao'
        self.doc.mkdir()
        self.real_resolve = Path.resolve
        self.resolucoes_pdf = []

    def resolver_nasca(self, path, *args, **kwargs):
        if path.suffix.casefold() == '.pdf':
            self.resolucoes_pdf.append(path)
            return self.raiz / 'drmtmp' / 'transitorio.nsc'
        return self.real_resolve(path, *args, **kwargs)

class CaminhosLogicos(_AmbientePDF):
    def test_gerador_e_entregador_preservam_folha_logica_sem_resolve_pdf(self):
        esperado = self.doc / 'relatorio.pdf'
        with mock.patch.object(Path, 'resolve', lambda path, *a, **kw: self.resolver_nasca(path, *a, **kw)):
            for modulo in (gerador, entrega):
                with self.subTest(modulo=modulo.__name__):
                    self.assertEqual(modulo.caminho_pdf_logico(esperado), esperado)
                    self.assertTrue(modulo.caminho_pdf_logico(esperado).is_absolute())
        self.assertEqual(self.resolucoes_pdf, [])

    def test_pai_relativo_e_normalizado_mas_nome_pdf_preservado(self):
        path = Path(self.temp.name) / 'documentacao' / '..' / 'documentacao' / 'relatorio.pdf'
        for modulo in (gerador, entrega):
            with self.subTest(modulo=modulo.__name__):
                self.assertEqual(modulo.caminho_pdf_logico(path), self.doc / 'relatorio.pdf')

    def test_ambos_rejeitam_caminho_temporario_nsc_em_vez_de_pdf(self):
        for modulo in (gerador, entrega):
            with self.subTest(modulo=modulo.__name__):
                with self.assertRaisesRegex(ValueError, 'extensao .pdf'):
                    modulo.caminho_pdf_logico(self.raiz / 'drmtmp' / 'temporario.nsc')

    def test_dois_destinos_permitidos_com_pdf_redirecionado_pelo_provedor(self):
        with mock.patch.object(entrega, 'RAIZ', self.raiz), mock.patch.object(Path, 'resolve', lambda path, *a, **kw: self.resolver_nasca(path, *a, **kw)):
            for nome in entrega.NOMES_ENTREGA:
                with self.subTest(nome=nome):
                    self.assertEqual(entrega.validar_destino(self.doc / nome), self.doc / nome)
        self.assertEqual(self.resolucoes_pdf, [])

    def test_destinos_fora_do_diretorio_nome_ou_extensao_sao_rejeitados(self):
        nome = 'tabela_resultados_ghi_2024.pdf'
        casos = [self.raiz / nome, self.raiz / 'documentacao_backup' / nome,
                 self.doc / '..' / 'fora' / nome, self.doc / 'outro.pdf',
                 self.doc / 'tabela_resultados_ghi_2024.pdf.nsc']
        with mock.patch.object(entrega, 'RAIZ', self.raiz):
            for path in casos:
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        entrega.validar_destino(path)

    def test_pai_redirecionado_para_fora_e_rejeitado_mesmo_com_nome_correto(self):
        def resolver_pai(path, *args, **kwargs):
            if path == self.doc:
                return self.raiz.parent / 'fora_do_projeto'
            return self.real_resolve(path, *args, **kwargs)
        with mock.patch.object(entrega, 'RAIZ', self.raiz), mock.patch.object(Path, 'resolve', resolver_pai):
            with self.assertRaisesRegex(ValueError, 'Destino fora'):
                entrega.validar_destino(self.doc / 'tabela_resultados_ghi_2024.pdf')


class EntregaSimulada(_AmbientePDF):
    def setUp(self):
        super().setUp()
        self.origem = self.raiz / 'staged' / 'tabela_resultados_ghi_2024.pdf'
        self.destino = self.doc / 'tabela_resultados_ghi_2024.pdf'
        self.backup = self.raiz / 'backup' / 'tabela_resultados_ghi_2024_anterior.pdf'
        self.manifesto_path = self.raiz / 'manifesto.json'
        self.visual_path = self.raiz / 'visual.json'
        self.rel = self.raiz / 'relatorios'
        self.registro_path = self.rel / 'entrega.json'
        self.digest = '1' * 64
        self.digest_anterior = '2' * 64
        self.manifesto = {'pdf': {'path': str(self.origem), 'sha256': self.digest, 'paginas': 2}, 'fontes': []}
        self.visual = {'aprovado': True, 'pdf_sha256': self.digest, 'paginas_verificadas': [1, 2]}
        self.snapshot = {'backup_pdf': str(self.backup), 'arquivos': {str(self.destino): self.digest_anterior}}
        self.digests_extras = {}
        self.hashes_lidos = []
        self.replaced = False
        self.write_calls = []
        self.copy = mock.Mock()
        self.read = mock.Mock(side_effect=self.ler_simulado)

    def ler_simulado(self, path):
        return {self.manifesto_path: self.manifesto, self.visual_path: self.visual,
                self.rel / 'snapshot_anteriores.json': self.snapshot}[Path(path)]

    def sha_simulado(self, path):
        path = Path(path)
        self.hashes_lidos.append(path)
        if path in self.digests_extras:
            return self.digests_extras[path]
        if path == self.backup:
            return self.digest_anterior
        if path == self.destino and not self.replaced:
            return self.digest_anterior
        return self.digest

    def substituir_simulado(self, path, destino):
        self.assertEqual(destino, self.destino)
        self.assertEqual(path, self.destino.with_name(self.destino.stem + '.novo.pdf'))
        self.replaced = True
        return destino

    def escrever_simulado(self, path, texto, *args, **kwargs):
        self.write_calls.append((path, texto))
        return len(texto)

    def executar_simulado(self):
        argv = ['entregar', '--manifesto', str(self.manifesto_path), '--visual', str(self.visual_path),
                '--destino', str(self.destino), '--registro', str(self.registro_path)]
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(entrega, 'RAIZ', self.raiz))
            stack.enter_context(mock.patch.object(entrega, 'REL', self.rel))
            stack.enter_context(mock.patch.object(Path, 'resolve', lambda path, *a, **kw: self.resolver_nasca(path, *a, **kw)))
            stack.enter_context(mock.patch.object(entrega, 'ler', self.read))
            stack.enter_context(mock.patch.object(entrega, 'sha256', side_effect=self.sha_simulado))
            stack.enter_context(mock.patch.object(entrega.shutil, 'copyfile', self.copy))
            stack.enter_context(mock.patch.object(Path, 'replace', autospec=True, side_effect=self.substituir_simulado))
            stack.enter_context(mock.patch.object(Path, 'mkdir', autospec=True))
            stack.enter_context(mock.patch.object(Path, 'write_text', autospec=True, side_effect=self.escrever_simulado))
            stack.enter_context(mock.patch.object(Path, 'exists', autospec=True,
                                                  side_effect=lambda path: path == self.destino))
            stack.enter_context(mock.patch('sys.argv', argv))
            stack.enter_context(mock.patch('builtins.print'))
            entrega.main()

    def test_entrega_preserva_chave_snapshot_backup_copy_e_registro_logicos(self):
        self.executar_simulado()
        self.copy.assert_called_once_with(self.origem, self.destino.with_name(self.destino.stem + '.novo.pdf'))
        self.assertIn(self.backup, self.hashes_lidos)
        self.assertEqual(self.resolucoes_pdf, [])
        self.assertTrue(self.replaced)
        self.assertEqual(len(self.write_calls), 1)
        registro = json.loads(self.write_calls[0][1])
        self.assertEqual(registro['pdf']['path'], str(self.destino))
        self.assertEqual(registro['backup_pdf_2024'], str(self.backup))
        self.assertEqual(registro['pdf_anterior_sha256'], self.digest_anterior)
        self.assertTrue(all(path.suffix.casefold() == '.pdf' for path in self.hashes_lidos
                            if path not in (self.manifesto_path, self.visual_path)))

    def test_destino_ja_atualizado_e_validado_e_registrado_sem_copia_ou_rename(self):
        self.digests_extras[self.destino] = self.digest
        self.executar_simulado()
        self.copy.assert_not_called()
        self.assertFalse(self.replaced)
        self.assertIn(self.backup, self.hashes_lidos)
        self.assertIn(self.origem, self.hashes_lidos)
        self.assertGreaterEqual(self.hashes_lidos.count(self.destino), 2)
        self.assertEqual(len(self.write_calls), 1)
        registro = json.loads(self.write_calls[0][1])
        self.assertEqual(registro['pdf']['sha256'], self.digest)
        self.assertEqual(registro['pdf_anterior_sha256'], self.digest)

    def test_idempotencia_nao_dispensa_validacao_do_backup(self):
        self.digests_extras[self.destino] = self.digest
        self.digests_extras[self.backup] = '3' * 64
        with self.assertRaisesRegex(ValueError, 'Copia anterior diverge'):
            self.executar_simulado()
        self.copy.assert_not_called()
        self.assertEqual(self.write_calls, [])

    def test_snapshot_temporario_nsc_nao_substitui_chave_logica_obrigatoria(self):
        self.snapshot['arquivos'] = {str(self.raiz / 'drmtmp' / 'transitorio.nsc'): self.digest_anterior}
        with self.assertRaisesRegex(ValueError, 'chave logica'):
            self.executar_simulado()
        self.copy.assert_not_called()

    def test_backup_divergente_continua_barrando_entrega(self):
        self.digests_extras[self.backup] = '3' * 64
        with self.assertRaisesRegex(ValueError, 'Copia anterior diverge'):
            self.executar_simulado()
        self.copy.assert_not_called()

    def test_origem_divergente_continua_barrando_entrega(self):
        self.digests_extras[self.origem] = '3' * 64
        with self.assertRaisesRegex(ValueError, 'PDF mudou'):
            self.executar_simulado()
        self.copy.assert_not_called()

    def test_original_modificado_continua_barrando_entrega(self):
        self.digests_extras[self.destino] = '3' * 64
        with self.assertRaisesRegex(ValueError, 'PDF atual modificado'):
            self.executar_simulado()
        self.copy.assert_not_called()

    def test_manifesto_nsc_rejeitado_antes_de_ler_conteudo_transitorio(self):
        self.manifesto['pdf']['path'] = str(self.raiz / 'drmtmp' / 'transitorio.nsc')
        with self.assertRaisesRegex(ValueError, 'extensao .pdf'):
            self.executar_simulado()
        self.assertEqual(self.hashes_lidos, [])
        self.copy.assert_not_called()

    def test_path_traversal_rejeitado_antes_de_metadados_ou_copia(self):
        self.destino = self.doc / '..' / 'fora' / 'tabela_resultados_ghi_2024.pdf'
        with self.assertRaisesRegex(ValueError, 'Destino fora'):
            self.executar_simulado()
        self.read.assert_not_called()
        self.copy.assert_not_called()

    def test_revisao_visual_incompleta_continua_barrando_entrega(self):
        self.visual['paginas_verificadas'] = [1]
        with self.assertRaisesRegex(ValueError, 'Faltam paginas'):
            self.executar_simulado()
        self.copy.assert_not_called()


class EsperaCompartilhamentoWindows(TestCase):
    def setUp(self):
        self.agora = 0.0
        self.esperas = []
        self.temporario = Path('tmp/somente_simulado.novo.pdf')
        self.destino = Path('tmp/somente_simulado.pdf')

    def erro(self, winerror=None):
        exc = PermissionError('Arquivo em uso no teste simulado')
        if winerror is not None:
            exc.winerror = winerror
        return exc

    def dormir(self, segundos):
        self.esperas.append(segundos)
        self.agora += segundos

    def executar(self, efeito):
        with mock.patch.object(Path, 'replace', autospec=True, side_effect=efeito) as substituir, \
                mock.patch.object(entrega.time, 'monotonic', side_effect=lambda: self.agora), \
                mock.patch.object(entrega.time, 'sleep', side_effect=self.dormir):
            self.substituir = substituir
            return entrega.substituir_pdf_com_espera(self.temporario, self.destino)

    def test_32_e_33_transitorios_sao_repetidos_ate_substituir(self):
        resultado = self.executar([self.erro(32), self.erro(33), self.destino])
        self.assertEqual(resultado, self.destino)
        self.assertEqual(self.substituir.call_count, 3)
        self.assertEqual(self.esperas, [0.25, 0.25])
        self.assertTrue(all(c.args == (self.temporario, self.destino) for c in self.substituir.call_args_list))

    def test_bloqueio_persistente_para_em_dez_segundos_e_preserva_erro(self):
        exc = self.erro(32)
        with self.assertRaises(PermissionError) as captura:
            self.executar(exc)
        self.assertIs(captura.exception, exc)
        self.assertEqual(sum(self.esperas), 10.0)
        self.assertEqual(self.substituir.call_count, 41)

    def test_outros_oserrors_nao_sao_repetidos_ou_suprimidos(self):
        for winerror in (5, None):
            with self.subTest(winerror=winerror):
                exc = self.erro(winerror)
                with self.assertRaises(PermissionError) as captura:
                    self.executar(exc)
                self.assertIs(captura.exception, exc)
                self.assertEqual(self.substituir.call_count, 1)
                self.assertEqual(self.esperas, [])

    def test_erro_fora_de_oserror_propaga_imediatamente(self):
        exc = RuntimeError('Falha diferente de compartilhamento')
        with self.assertRaises(RuntimeError) as captura:
            self.executar(exc)
        self.assertIs(captura.exception, exc)
        self.assertEqual(self.substituir.call_count, 1)
        self.assertEqual(self.esperas, [])


if __name__ == '__main__':
    unittest.main()
