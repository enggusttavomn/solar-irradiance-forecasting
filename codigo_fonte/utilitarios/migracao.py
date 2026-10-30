"""Resolução de caminhos migrados e leitura das fontes históricas preservadas.

O registro e o ZIP são dados locais; importar este módulo não carrega modelos.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import posixpath
import zipfile


RAIZ_PROJETO = Path(__file__).resolve().parents[2]
REGISTRO_MIGRACAO = (
    RAIZ_PROJETO / "documentacao/organizacao/reorganizacao_codigo_20261027.json"
)


def _normalizar(caminho: str | os.PathLike[str]) -> str:
    return posixpath.normpath(os.fspath(caminho).replace("\\", "/"))


def _registro() -> dict:
    registro = json.loads(REGISTRO_MIGRACAO.read_text(encoding="utf-8"))
    if not isinstance(registro.get("arquivos"), dict):
        raise ValueError("Registro de migração sem o dicionário 'arquivos'.")
    if not isinstance(registro.get("fontes_arquivadas"), str):
        raise ValueError("Registro de migração sem o caminho 'fontes_arquivadas'.")
    return registro


def _relativo_local(caminho: str | os.PathLike[str]) -> tuple[str | None, bool]:
    """Identifica caminhos relativos ou absolutos sob a raiz deste projeto."""
    texto = _normalizar(caminho)
    raiz = _normalizar(RAIZ_PROJETO)
    comparar = str.casefold if os.name == "nt" else lambda s: s
    texto_comparado, raiz_comparada = comparar(texto), comparar(raiz)
    if texto_comparado == raiz_comparada:
        return ".", True
    if texto_comparado.startswith(raiz_comparada + "/"):
        return texto[len(raiz) + 1 :], True
    if Path(os.fspath(caminho)).is_absolute() or PureWindowsPath(texto).is_absolute():
        return None, True
    return texto, False


def _mapear_relativo(relativo: str, registro: dict) -> str:
    arquivos = {_normalizar(antigo): _normalizar(novo)
                for antigo, novo in registro["arquivos"].items()}
    if relativo in arquivos:
        return arquivos[relativo]
    # Os dois diretórios de produtos foram incorporados aos resultados.
    for antigo, novo in (("relatorios", "resultados/relatorios"),
                         ("output/pdf", "resultados/pdf")):
        if relativo == antigo:
            return novo
        if relativo.startswith(antigo + "/"):
            return novo + relativo[len(antigo) :]
    return relativo


def caminho_atual(caminho: str | os.PathLike[str]) -> Path:
    """Retorna o destino atual, conservando a forma relativa ou absoluta local.

    Caminhos absolutos externos ao projeto permanecem intactos. Entradas
    relativas continuam relativas: quem precisa de um absoluto usa
    ``RAIZ_PROJETO / caminho_atual(caminho)``.
    """
    relativo, absoluto = _relativo_local(caminho)
    if relativo is None:
        return Path(caminho)
    destino = Path(_mapear_relativo(relativo, _registro()))
    return RAIZ_PROJETO / destino if absoluto else destino


def _membros_historicos(relativo: str | None, registro: dict) -> list[str]:
    if relativo is None:
        return []
    # O nome original é prioritário. A busca inversa permite consultar pelo
    # caminho novo; todos os candidatos encontrados ainda precisam do hash.
    candidatos = [relativo]
    for antigo, novo in registro["arquivos"].items():
        if _normalizar(novo) == relativo and _normalizar(antigo) not in candidatos:
            candidatos.append(_normalizar(antigo))
    return candidatos


def _validar_hash(conteudo: bytes, esperado: str | None, origem: str) -> bytes:
    if esperado is not None:
        esperado = esperado.lower()
        if len(esperado) != 64 or any(c not in "0123456789abcdef" for c in esperado):
            raise ValueError("SHA-256 esperado deve conter 64 caracteres hexadecimais.")
        obtido = hashlib.sha256(conteudo).hexdigest()
        if obtido != esperado:
            raise ValueError(
                f"SHA-256 divergente em {origem}: esperado {esperado}, obtido {obtido}."
            )
    return conteudo


def ler_fonte_historica(
    caminho: str | os.PathLike[str], sha256_esperado: str | None = None
) -> bytes:
    """Lê os bytes antigos no ZIP, sem extrair ou modificar qualquer arquivo.

    Sem membro arquivado, aceita o arquivo atual somente se um SHA-256 foi
    informado e coincide. Um ZIP corrompido ou um membro com hash divergente
    produz erro: não se substitui silenciosamente a evidência histórica.
    """
    registro = _registro()
    relativo, _ = _relativo_local(caminho)
    arquivo_zip = Path(registro["fontes_arquivadas"])
    if not arquivo_zip.is_absolute():
        arquivo_zip = RAIZ_PROJETO / arquivo_zip
    if arquivo_zip.is_file():
        with zipfile.ZipFile(arquivo_zip) as arquivo:
            nomes = set(arquivo.namelist())
            divergencias = []
            for membro in _membros_historicos(relativo, registro):
                if membro in nomes:
                    try:
                        return _validar_hash(
                            arquivo.read(membro), sha256_esperado,
                            f"{arquivo_zip.name}:{membro}",
                        )
                    except ValueError as erro:
                        divergencias.append(str(erro))
            if divergencias:
                raise ValueError("; ".join(divergencias))
    if sha256_esperado is None:
        raise FileNotFoundError(
            f"Fonte histórica não encontrada no ZIP: {caminho}. "
            "Para consultar um arquivo atual é necessário informar o SHA-256 esperado."
        )
    atual = caminho_atual(caminho)
    if relativo is not None and not atual.is_absolute():
        atual = RAIZ_PROJETO / atual
    return _validar_hash(atual.read_bytes(), sha256_esperado, str(atual))


def verificar_fonte_historica(
    caminho: str | os.PathLike[str], sha256_esperado: str
) -> bool:
    """Retorna True quando os bytes conferem; ausência ou divergência gera erro."""
    ler_fonte_historica(caminho, sha256_esperado)
    return True
