"""Guardas de escopo, fonte e narrativa do controle XGBoost complementar."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, mock
import json
import unittest
from scripts import rodar_quantizacao_todos_modelos as runner
from scripts import auditar_quantizacao_todos_modelos as auditor
from scripts import gerar_pdf_quantizacao_todos_modelos as pdf

class Encaminhamento(TestCase):
 def args(self, **kw):
  d=dict(regime='atual',smoke=False,saida=Path('tmp/teste_integracao_sem_resultados'),protocolo=None)
  d.update(kw)
  return SimpleNamespace(**d)
 def test_somente_refit_xgboost_horario_atual_completo(self):
  a=self.args()
  esperado='codigo_fonte.experimento_xgboost_horario_controle_auditado_v1'
  self.assertIn(esperado,runner.comando(a,'hourly_72_extension','XGBoost','refit'))
  for fase in ('selecao','congelar'):
   with self.subTest(fase=fase):
    self.assertNotIn(esperado,runner.comando(a,'hourly_72_extension','XGBoost',fase))
  for a,t,m in [(self.args(smoke=True),'hourly_72_extension','XGBoost'),
                (self.args(regime='historico_1998_2022'),'hourly_72_extension','XGBoost'),
                (self.args(regime='historico_curto_pareado'),'hourly_72_extension','XGBoost'),
                (self.args(),'monthly_6','XGBoost'),(self.args(),'daily_30','XGBoost'),
                (self.args(),'hourly_72_extension','GRU')]:
   with self.subTest(regime=a.regime,tarefa=t,modelo=m):
    self.assertNotIn(esperado,runner.comando(a,t,m,'refit'))

class Auditoria(TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
  self.pasta=Path(self.temp.name)
 def gravar(self,nome,dados):
  p=self.pasta/nome; p.write_text(json.dumps(dados),encoding='utf-8'); return p
 def call(self,**kw):
  a=dict(regime='atual',tarefa='hourly_72_extension',modelo='XGBoost',modo='completa'); a.update(kw)
  return auditor.auditar_controle_suplementar(self.pasta,**a)
 def test_controle_legado_aprovado_sem_suplemento(self):
  self.gravar('controle_teste.json',{'aprovado':True})
  self.assertIsNone(self.call())
 def test_controle_reprovado_ou_recibo_novo_sem_suplemento_rejeitado(self):
  for dados in ({'aprovado':False},{'aprovado':True,'novo_controle_refit_xgboost_reexecutado':True}):
   with self.subTest(dados=dados):
    self.gravar('controle_teste.json',dados)
    with self.assertRaises(AssertionError): self.call()
 def test_suplemento_fora_escopo_rejeitado(self):
  self.gravar('contrato_complementar_controle_teste_xgboost_v1.json',{})
  for kw in ({'regime':'historico_1998_2022'},{'modelo':'GRU'},{'tarefa':'daily_30'},{'modo':'smoke'}):
   with self.subTest(kw=kw):
    with self.assertRaises(AssertionError): self.call(**kw)
 def test_fontes_validas_vinculadas_ao_relatorio_e_mutacao_rejeitada(self):
  from codigo_fonte import experimento_xgboost_horario_controle_auditado_v1 as a
  fonte=self.gravar('fonte.json',{'valor':1})
  fontes={str(fonte.resolve()):pdf.sha256(fonte)}
  evidencia=self.gravar('evidencia.json',{'fontes_sha256':fontes})
  self.gravar('contrato_complementar_controle_teste_xgboost_v1.json',{})
  self.gravar('controle_teste.json',{'aprovado':True,'fontes_sha256':fontes})
  with mock.patch.object(a,'validar_controle_adaptado',return_value={'fontes_sha256':fontes}) as validar, mock.patch.object(a,'EVIDENCIA',evidencia):
   resultado=self.call()
   validar.assert_called_once_with(self.pasta)
   self.assertFalse(resultado['metricas_usadas_como_criterio'])
   self.assertFalse(resultado['selecao_alterada'])
   self.assertEqual(resultado['causa_divergencia_legada'],'nao determinada')
   self.gravar('fonte.json',{'valor':2})
   with self.assertRaises(AssertionError): self.call()
 def test_pdf_rejeita_fonte_suplementar_alterada_apos_auditoria(self):
  fonte=self.gravar('fonte.json',{})
  audit=self.gravar('audit.json',{'ok':True,'publicavel':True,'escopo_completo':True,
          'modo':'completa','replay_novo_executado':True,
          'fontes_controles_suplementares_sha256':{str(fonte):'0'*64}})
  with self.assertRaisesRegex(ValueError,'controle complementar alterada'):
   pdf.carregar_auditoria(audit)

class FontesPortateis(TestCase):
 def test_preserva_arial_quando_o_par_esta_disponivel(self):
  with TemporaryDirectory() as td:
   pasta=Path(td)
   fontes=(pasta/'arial.ttf',pasta/'arialbd.ttf')
   for fonte in fontes: fonte.touch()
   self.assertEqual(pdf.fontes_relatorio(pasta),fontes)
   fontes[1].unlink()
   self.assertEqual([p.name for p in pdf.fontes_relatorio(pasta)],['Vera.ttf','VeraBd.ttf'])
 def test_sem_arial_usa_vera_real_com_glifos_portugueses(self):
  from io import BytesIO
  import reportlab
  from reportlab.pdfbase import pdfmetrics
  from reportlab.pdfbase.ttfonts import TTFont
  from reportlab.pdfgen.canvas import Canvas
  texto='Quantização — Horário, previsão, mês, ação e R² (W/m²).'
  pacote=Path(reportlab.__file__).resolve().parent/'fonts'
  with TemporaryDirectory() as td:
   fontes=pdf.fontes_relatorio(Path(td)/'windows_ausente')
   self.assertEqual(fontes,(pacote/'Vera.ttf',pacote/'VeraBd.ttf'))
   memoria=BytesIO()
   documento=Canvas(memoria)
   for indice,fonte in enumerate(fontes):
    nome=f'TesteVeraPortatil{indice}'
    registrada=TTFont(nome,str(fonte))
    self.assertTrue(all(registrada.face.charToGlyph.get(ord(c),0) for c in texto if not c.isspace()))
    pdfmetrics.registerFont(registrada)
    documento.setFont(nome,12)
    documento.drawString(30,750-indice*24,texto)
   documento.save()
   self.assertTrue(memoria.getvalue().startswith(b'%PDF-'))
   self.assertIn(b'/FontFile2',memoria.getvalue())

class Narrativa(TestCase):
 def test_gerador_usa_auditoria_carregada_e_identifica_controle_novo(self):
  import pandas as pd
  from reportlab.platypus import SimpleDocTemplate
  # Captura a estrutura antes de escrever um PDF; estes valores sao sintéticos de teste.
  cols=dict(MAE_wm2=1.,MSE_w2m4=1.,RMSE_wm2=1.,nRMSE=1.,R2=0.,N_localidades=10,N_origens=1,N_pontos=1)
  rows=[dict(tarefa=t,modelo=m,variante=v,particao=p,horizonte=h,regime='atual',**cols)
        for t,hs in pdf.TAREFAS.items() for m in pdf.MODELOS for v in pdf.VARIANTES
        for p in ('validacao','teste') for h in hs]
  frame=pd.DataFrame(rows)
  resultados=[{'tarefa':t,'modelo':m,'vencedor_validacao':'q64',
               'controle_teste_suplementar':{'id':'teste'} if t=='hourly_72_extension' and m=='XGBoost' else None}
              for t in pdf.TAREFAS for m in pdf.MODELOS]
  audit={'regime':'atual','resultados':resultados,
         'metricas':{'path':'sintetico.csv','sha256':'0'*64}}
  historias=[]
  def capturar(self,story,**kw):
   historias.extend(story)
   raise RuntimeError('fim da captura antes de escrever PDF')
  with TemporaryDirectory() as td:
   path=Path(td)/'audit.json'; path.write_text('{}',encoding='utf-8')
   with mock.patch.object(pdf,'carregar_auditoria',return_value=(audit,frame)), mock.patch.object(SimpleDocTemplate,'build',capturar):
    with self.assertRaisesRegex(RuntimeError,'fim da captura'):
     pdf.gerar([path],Path(td)/'nao_escrito.pdf',Path(td)/'nao_escrito.json')
   self.assertFalse((Path(td)/'nao_escrito.pdf').exists())
  texto=' '.join(getattr(p,'text','') for p in historias)
  self.assertIn('XGBoost horário.',texto)
  self.assertIn('não foi identificada',texto)
  self.assertIn('controle reexecutado desta rodada',texto)

if __name__=='__main__': unittest.main()
