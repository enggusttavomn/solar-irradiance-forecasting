"""Regressões de proveniência e leitura de objetos após a reorganização."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import pickle
import subprocess
import sys
import zipfile

import pytest

from codigo_fonte.utilitarios import migracao
from codigo_fonte.utilitarios.compatibilidade import instalar_aliases


RAIZ = Path(__file__).resolve().parents[1]


def test_fonte_cientifica_antiga_continua_conferindo_apos_mudar_codigo_ativo():
    registro = json.loads(migracao.REGISTRO_MIGRACAO.read_text(encoding="utf-8"))
    origem = "codigo_fonte/configuracao.py"
    esperado = registro["fontes_antes"][origem]
    original = migracao.ler_fonte_historica(origem, esperado)
    atual = RAIZ / registro["arquivos"][origem]

    assert hashlib.sha256(original).hexdigest() == esperado
    assert original != atual.read_bytes()
    assert migracao.verificar_fonte_historica(origem, esperado)


@pytest.fixture
def fontes_distintas(tmp_path, monkeypatch):
    origem = "codigo_fonte/antes.py"
    destino = "codigo_fonte/depois.py"
    original, atual = b"fonte cientifica original", b"codigo reorganizado"
    registro = tmp_path / "registro.json"
    registro.write_text(json.dumps({
        "arquivos": {origem: destino}, "fontes_arquivadas": "fontes.zip",
    }), encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "fontes.zip", "w") as arquivo:
        arquivo.writestr(origem, original)
    (tmp_path / destino).parent.mkdir(parents=True)
    (tmp_path / destino).write_bytes(atual)
    monkeypatch.setattr(migracao, "RAIZ_PROJETO", tmp_path)
    monkeypatch.setattr(migracao, "REGISTRO_MIGRACAO", registro)
    return origem, destino, original, atual, tmp_path


def test_hash_errado_nao_e_encoberto_por_fonte_atual(fontes_distintas):
    origem, _, _, atual, _ = fontes_distintas
    hash_atual = hashlib.sha256(atual).hexdigest()
    # Mesmo que a cópia ativa combine com o hash informado, ela não pode
    # substituir silenciosamente uma fonte histórica diferente no ZIP.
    with pytest.raises(ValueError, match="SHA-256 divergente"):
        migracao.ler_fonte_historica(origem, hash_atual)


def test_fallback_atual_exige_hash_conferido(fontes_distintas):
    origem, _, _, atual, raiz = fontes_distintas
    (raiz / "fontes.zip").unlink()
    assert migracao.ler_fonte_historica(
        origem, hashlib.sha256(atual).hexdigest()
    ) == atual
    with pytest.raises(ValueError, match="SHA-256 divergente"):
        migracao.ler_fonte_historica(origem, "0" * 64)
    with pytest.raises(FileNotFoundError, match="SHA-256 esperado"):
        migracao.ler_fonte_historica(origem)


def test_caminhos_migrados_preservam_forma_e_localidade(fontes_distintas):
    origem, destino, _, _, raiz = fontes_distintas
    assert migracao.caminho_atual(origem) == Path(destino)
    assert migracao.caminho_atual(raiz / origem) == raiz / destino
    assert migracao.caminho_atual("relatorios/auditoria/a.json") == Path(
        "resultados/relatorios/auditoria/a.json"
    )
    assert migracao.caminho_atual("output/pdf/analise.pdf") == Path(
        "resultados/pdf/analise.pdf"
    )
    externo = raiz.parent / "outra_pesquisa/fonte.py"
    assert migracao.caminho_atual(externo) == externo


def test_alias_antigo_e_modulo_atual_possuem_a_mesma_identidade():
    atual = importlib.import_module("codigo_fonte.utilitarios.json_atomico")
    antigo = importlib.import_module("scripts.json_atomico")

    assert antigo is atual
    assert antigo.__name__ == "codigo_fonte.utilitarios.json_atomico"
    assert antigo.__spec__.name == "codigo_fonte.utilitarios.json_atomico"
    assert importlib.import_module(atual.__name__) is atual


def test_pickle_com_referencia_historica_encontra_a_funcao_atual():
    atual = importlib.import_module("codigo_fonte.utilitarios.json_atomico")
    # Referência GLOBAL do protocolo pickle 0, como um objeto antigo que
    # registrou a função antes de scripts/ ser incorporado ao código.
    referencia_antiga = b"cscripts.json_atomico\nsalvar_json\n."
    assert pickle.loads(referencia_antiga) is atual.salvar_json


def test_namespaces_historicos_nao_substituem_pacotes_reais():
    for nome in ("scripts.apresentacoes", "executaveis"):
        virtual = importlib.import_module(nome)
        # Diretórios antigos vazios podem ser reconhecidos pelo Python como
        # namespaces; sem diretório físico, o finder cria o mesmo namespace.
        assert getattr(virtual, "__file__", None) is None
        assert virtual.__spec__.submodule_search_locations is not None
    real = importlib.import_module("codigo_fonte.utilitarios")
    assert real.__spec__.submodule_search_locations is not None
    assert Path(real.__file__).name == "__init__.py"
    assert instalar_aliases() is instalar_aliases()


def test_importar_pacote_nao_importa_bibliotecas_de_modelos():
    programa = """
import codigo_fonte
import sys
carregados = sorted(set(sys.modules) & {'torch', 'tensorflow', 'numpy', 'pandas'})
assert not carregados, carregados
"""
    processo = subprocess.run(
        [sys.executable, "-c", programa], cwd=RAIZ,
        capture_output=True, text=True, check=False,
    )
    assert processo.returncode == 0, processo.stdout + processo.stderr
