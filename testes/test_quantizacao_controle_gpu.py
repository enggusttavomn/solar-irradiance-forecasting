import json
from pathlib import Path
import pytest
from codigo_fonte import experimento_quantizacao_concorrentes as x


def aceite(tmp_path):
    evidencia=tmp_path/'replay.json'
    evidencia.write_text('{"aprovado":true}')
    registro={'contrato_sha256':'contrato','fonte_sha256':'fonte',
        'relatorio_divergencia_sha256':'diferencas','replay_checkpoint_original_aprovado':True,
        'arquitetura_e_loop_aprovados':True,'justificativa':'Novo controle GPU auditado.',
        'auditoria_arquivos_sha256':x.hashes([evidencia])}
    arquivo=tmp_path/'aceite_controle_gpu_validacao.json'
    arquivo.write_text(json.dumps(registro))
    return arquivo,registro,evidencia


def test_aceite_gpu_exige_evidencia(tmp_path):
    p,a,_=aceite(tmp_path)
    assert x.validar_aceite_gpu(p,'contrato','fonte','diferencas')==a


@pytest.mark.parametrize('campo',['contrato_sha256','fonte_sha256','relatorio_divergencia_sha256',
    'replay_checkpoint_original_aprovado','arquitetura_e_loop_aprovados',
    'justificativa','auditoria_arquivos_sha256'])
def test_aceite_gpu_nao_aprova_excecao_sem_requisitos(tmp_path,campo):
    p,a,_=aceite(tmp_path)
    a.pop(campo)
    p.write_text(json.dumps(a))
    with pytest.raises(ValueError):x.validar_aceite_gpu(p,'contrato','fonte','diferencas')


def test_aceite_gpu_rejeita_evidencia_alterada(tmp_path):
    p,_,e=aceite(tmp_path)
    e.write_text('alterado')
    with pytest.raises(ValueError):x.validar_aceite_gpu(p,'contrato','fonte','diferencas')


def test_aceite_gpu_ausente_nao_e_aprovacao(tmp_path):
    with pytest.raises(ValueError):
        x.validar_aceite_gpu(tmp_path/'nao_existe.json','contrato','fonte','diferencas')
