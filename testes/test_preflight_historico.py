import json
from pathlib import Path

import pytest

from scripts import coordenar_quantizacao_historica as c
from scripts.auditar_pareamento_historicos import QUANTIDADES_FONTES, hash_obj
from scripts.metricas_quantizacao_todos import sha256


def gravar(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding='utf-8')


def preparar(tmp_path, monkeypatch):
    def arquivo(nome):
        path = tmp_path / nome
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(nome)
        return {'arquivo': nome, 'bytes': path.stat().st_size, 'sha256': sha256(path)}

    entradas = {grupo: [arquivo(f'dados/{grupo}/{i}.csv') for i in range(n)]
                for grupo, n in QUANTIDADES_FONTES.items()}
    manifesto = arquivo('manifesto.json')
    motor = arquivo('codigo_fonte/experimento_quantizacao_concorrentes.py')
    contrato = {'ok': True, 'aprovado': True, 'entradas': entradas,
                'manifesto_horario': manifesto, 'auditorias': {}}
    contrato['sha256_contrato'] = hash_obj(contrato)
    cp = tmp_path / 'contrato.json'
    gravar(cp, contrato)
    audit = {'ok': True, 'aprovado': True, 'motor_sha256': motor['sha256'],
             'contrato': {'arquivo': str(cp), 'sha256_arquivo': sha256(cp),
                          'sha256_contrato': contrato['sha256_contrato']}}
    ap = tmp_path / 'audit.json'
    gravar(ap, audit)
    protocolos = {}
    for regime in c.REGIMES:
        path = tmp_path / (regime + '.json')
        gravar(path, {'regime': regime, 'carregador_historico': True, 'contrato_preparacao_dados': str(cp),
                      'sha256_arquivo_contrato_preparacao': sha256(cp),
                      'sha256_contrato_preparacao': contrato['sha256_contrato']})
        protocolos[regime] = path
    monkeypatch.setattr(c, 'HASH_PROTOCOL', {r: sha256(p) for r, p in protocolos.items()})
    monkeypatch.setattr(c, 'HASH_AUDITORIA_DADOS', sha256(ap))
    return protocolos, ap, entradas


def test_preflight_confere70_arquivos_sem_contratos_treinados(tmp_path, monkeypatch):
    protocolos, ap, entradas = preparar(tmp_path, monkeypatch)
    resultado = c.preflight_historico(protocolos, ap, raiz=tmp_path)
    assert resultado['ok'] and resultado['aprovado']
    assert resultado['arquivos_coleta_verificados'] == 70
    item = next(iter(entradas.values()))[0]
    path = tmp_path / item['arquivo']
    path.write_text('x' * item['bytes'])
    with pytest.raises(ValueError, match='Fonte alterada'):
        c.preflight_historico(protocolos, ap, raiz=tmp_path)


def test_preflight_exige_hash_fisico_aprovacao_e_motor(tmp_path, monkeypatch):
    protocolos, ap, entradas = preparar(tmp_path, monkeypatch)
    audit = json.loads(ap.read_text())
    audit['aprovado'] = False
    gravar(ap, audit)
    with pytest.raises(ValueError, match='Fonte alterada'):
        c.preflight_historico(protocolos, ap, raiz=tmp_path)
    monkeypatch.setattr(c, 'HASH_AUDITORIA_DADOS', sha256(ap))
    with pytest.raises(ValueError, match='nao aprovada'):
        c.preflight_historico(protocolos, ap, raiz=tmp_path)
    audit['aprovado'] = True
    gravar(ap, audit)
    monkeypatch.setattr(c, 'HASH_AUDITORIA_DADOS', sha256(ap))
    (tmp_path / 'codigo_fonte/experimento_quantizacao_concorrentes.py').write_text('outro motor')
    with pytest.raises(ValueError, match='Fonte alterada'):
        c.preflight_historico(protocolos, ap, raiz=tmp_path)
