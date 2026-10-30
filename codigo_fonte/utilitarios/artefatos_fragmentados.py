"""Fragmentacao auditavel de artefatos binarios grandes.

Os fragmentos sao apenas uma representacao de transporte. A concatenacao
binaria, na ordem declarada, recompõe exatamente o arquivo original e e
validada por tamanho e SHA-256 antes de o artefato ser materializado.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


TAMANHO_PARTE_PADRAO = 6 * 1024 * 1024


class ArtefatoFragmentadoError(ValueError):
    """Indica metadados, partes ou materializacao inconsistentes."""


def sha256_arquivo(caminho: str | Path, *, bloco: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        while pedaco := arquivo.read(bloco):
            digest.update(pedaco)
    return digest.hexdigest()


def _resolver_relativo_seguro(raiz: Path, relativo: object) -> Path:
    texto = str(relativo).replace("\\", "/")
    caminho_relativo = Path(texto)
    if not texto or caminho_relativo.is_absolute() or ".." in caminho_relativo.parts:
        raise ArtefatoFragmentadoError(f"Caminho fragmentado inseguro: {texto!r}.")
    raiz_resolvida = raiz.resolve()
    caminho = (raiz / caminho_relativo).resolve()
    if caminho != raiz_resolvida and raiz_resolvida not in caminho.parents:
        raise ArtefatoFragmentadoError(f"Caminho fragmentado fora da raiz: {texto!r}.")
    return caminho


def _gravar_bytes_atomico(caminho: Path, conteudo: bytes) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.parent / f".{caminho.name}.tmp-{uuid.uuid4().hex}"
    try:
        temporario.write_bytes(conteudo)
        os.replace(temporario, caminho)
    finally:
        if temporario.exists():
            temporario.unlink()


def _gravar_json_atomico(caminho: Path, valor: Mapping[str, object]) -> None:
    conteudo = (
        json.dumps(valor, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _gravar_bytes_atomico(caminho, conteudo)


def fragmentar_arquivo(
    caminho: str | Path,
    *,
    raiz: str | Path,
    tamanho_parte: int = TAMANHO_PARTE_PADRAO,
) -> dict[str, object]:
    """Divide um arquivo em partes ordenadas e retorna metadados auditaveis."""

    if tamanho_parte < 1:
        raise ValueError("tamanho_parte deve ser positivo.")
    raiz_path = Path(raiz)
    origem = Path(caminho)
    if not origem.is_file():
        raise FileNotFoundError(origem)
    try:
        relativo = origem.resolve().relative_to(raiz_path.resolve()).as_posix()
    except ValueError as erro:
        raise ArtefatoFragmentadoError(
            f"Arquivo fora da raiz de fragmentacao: {origem}."
        ) from erro

    pasta_partes = raiz_path / "fragmentos"
    partes: list[dict[str, object]] = []
    with origem.open("rb") as arquivo:
        indice = 1
        while conteudo := arquivo.read(tamanho_parte):
            nome = f"{origem.name}.part{indice:03d}"
            destino = pasta_partes / nome
            _gravar_bytes_atomico(destino, conteudo)
            partes.append(
                {
                    "arquivo": destino.relative_to(raiz_path).as_posix(),
                    "bytes": len(conteudo),
                    "sha256": hashlib.sha256(conteudo).hexdigest(),
                }
            )
            indice += 1
    if not partes:
        raise ArtefatoFragmentadoError(f"Arquivo vazio nao pode ser fragmentado: {origem}.")
    return {
        "arquivo": relativo,
        "bytes": origem.stat().st_size,
        "sha256": sha256_arquivo(origem),
        "algoritmo_reconstrucao": "concatenacao_binaria_ordenada",
        "partes": partes,
    }


def preparar_manifesto_fragmentado(
    pasta: str | Path,
    nomes_arquivos: Sequence[str],
    *,
    tamanho_parte: int = TAMANHO_PARTE_PADRAO,
) -> dict[str, object]:
    """Fragmenta alvos e substitui suas entradas no manifesto da tarefa."""

    raiz = Path(pasta)
    caminho_manifesto = raiz / "manifesto_artefatos.json"
    manifesto = json.loads(caminho_manifesto.read_text(encoding="utf-8"))
    especificacoes = [
        fragmentar_arquivo(
            raiz / nome,
            raiz=raiz,
            tamanho_parte=tamanho_parte,
        )
        for nome in nomes_arquivos
    ]
    alvos = {str(item["arquivo"]) for item in especificacoes}
    prefixos_partes = {
        f"fragmentos/{Path(alvo).name}.part" for alvo in alvos
    }
    arquivos = [
        item
        for item in manifesto.get("arquivos", [])
        if str(item.get("arquivo")) not in alvos
        and not any(
            str(item.get("arquivo", "")).startswith(prefixo)
            for prefixo in prefixos_partes
        )
    ]
    for especificacao in especificacoes:
        arquivos.extend(especificacao["partes"])
    arquivos.sort(key=lambda item: str(item["arquivo"]))
    manifesto["gerado_em_utc"] = datetime.now(timezone.utc).isoformat()
    manifesto["N_arquivos"] = len(arquivos)
    manifesto["arquivos"] = arquivos
    manifesto["arquivos_fragmentados"] = especificacoes
    _gravar_json_atomico(caminho_manifesto, manifesto)
    return manifesto


def materializar_arquivo_fragmentado(
    raiz: str | Path,
    especificacao: Mapping[str, object],
) -> Path:
    """Valida as partes e materializa o arquivo completo quando ausente."""

    raiz_path = Path(raiz)
    destino = _resolver_relativo_seguro(raiz_path, especificacao.get("arquivo"))
    partes = especificacao.get("partes")
    if (
        not isinstance(partes, list)
        or not partes
        or especificacao.get("algoritmo_reconstrucao")
        != "concatenacao_binaria_ordenada"
    ):
        raise ArtefatoFragmentadoError(
            f"Especificacao fragmentada invalida para {destino}."
        )
    tamanho_esperado = especificacao.get("bytes")
    hash_esperado = especificacao.get("sha256")
    if not isinstance(tamanho_esperado, int) or tamanho_esperado < 1:
        raise ArtefatoFragmentadoError(f"Tamanho fragmentado invalido para {destino}.")
    if not isinstance(hash_esperado, str) or len(hash_esperado) != 64:
        raise ArtefatoFragmentadoError(f"SHA-256 fragmentado invalido para {destino}.")

    if destino.is_file():
        if destino.stat().st_size != tamanho_esperado:
            raise ArtefatoFragmentadoError(f"Tamanho do artefato materializado diverge: {destino}.")
        if sha256_arquivo(destino) != hash_esperado:
            raise ArtefatoFragmentadoError(f"SHA-256 do artefato materializado diverge: {destino}.")
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.parent / f".{destino.name}.tmp-{uuid.uuid4().hex}"
    digest_total = hashlib.sha256()
    bytes_total = 0
    try:
        with temporario.open("xb") as saida:
            for parte in partes:
                if not isinstance(parte, Mapping):
                    raise ArtefatoFragmentadoError(f"Parte invalida para {destino}.")
                caminho_parte = _resolver_relativo_seguro(
                    raiz_path, parte.get("arquivo")
                )
                if not caminho_parte.is_file():
                    raise ArtefatoFragmentadoError(
                        f"Parte fragmentada ausente: {caminho_parte}."
                    )
                conteudo = caminho_parte.read_bytes()
                if parte.get("bytes") != len(conteudo):
                    raise ArtefatoFragmentadoError(
                        f"Tamanho da parte diverge: {caminho_parte}."
                    )
                if parte.get("sha256") != hashlib.sha256(conteudo).hexdigest():
                    raise ArtefatoFragmentadoError(
                        f"SHA-256 da parte diverge: {caminho_parte}."
                    )
                saida.write(conteudo)
                digest_total.update(conteudo)
                bytes_total += len(conteudo)
        if bytes_total != tamanho_esperado or digest_total.hexdigest() != hash_esperado:
            raise ArtefatoFragmentadoError(
                f"Reconstrucao fragmentada diverge do artefato declarado: {destino}."
            )
        os.replace(temporario, destino)
    finally:
        if temporario.exists():
            temporario.unlink()
    return destino


__all__ = [
    "ArtefatoFragmentadoError",
    "TAMANHO_PARTE_PADRAO",
    "fragmentar_arquivo",
    "materializar_arquivo_fragmentado",
    "preparar_manifesto_fragmentado",
]
