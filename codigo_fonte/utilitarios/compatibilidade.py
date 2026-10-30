"""Aliases preguiçosos para módulos usados por objetos pickle/joblib antigos.

As implementações atuais continuam tendo uma única identidade e um único
arquivo. O finder entra depois dos finders normais: pacotes reais, como
``codigo_fonte.utilitarios``, sempre têm prioridade sobre nomes históricos.
"""

from __future__ import annotations

import importlib
from importlib.abc import Loader, MetaPathFinder
from importlib.util import spec_from_loader
import json
from pathlib import Path
import sys


REGISTRO_MIGRACAO = (
    Path(__file__).resolve().parents[2]
    / "documentacao/organizacao/reorganizacao_codigo_20261027.json"
)


class _CarregadorAlias(Loader):
    def __init__(self, origem: str, destino: str) -> None:
        self.origem = origem
        self.destino = destino
        self.atributos = {}

    def create_module(self, spec):
        modulo = importlib.import_module(self.destino)
        # module_from_spec prepara metadados usando o nome do alias. Restaurar
        # estes atributos evita modificar a identidade canônica do módulo.
        self.atributos = {
            atributo: getattr(modulo, atributo, None)
            for atributo in ("__spec__", "__loader__", "__package__", "__name__")
        }
        return modulo

    def exec_module(self, modulo) -> None:
        for atributo, valor in self.atributos.items():
            setattr(modulo, atributo, valor)
        sys.modules[self.origem] = modulo


class _CarregadorPacoteVirtual(Loader):
    def create_module(self, spec):
        return None

    def exec_module(self, modulo) -> None:
        modulo.__doc__ = "Namespace histórico virtual; sem implementação duplicada."


class _AliasesHistoricos(MetaPathFinder):
    def __init__(self, registro: Path, aliases: dict[str, str]) -> None:
        self._registro_aliases_codigo_fonte = str(registro.resolve())
        self.aliases = {origem: destino for origem, destino in aliases.items()
                        if origem != destino}
        self.pacotes = set()
        for nome in self.aliases:
            partes = nome.split(".")
            self.pacotes.update(".".join(partes[:i]) for i in range(1, len(partes)))

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.aliases:
            return spec_from_loader(
                fullname, _CarregadorAlias(fullname, self.aliases[fullname]),
                origin="alias histórico", is_package=False,
            )
        if fullname in self.pacotes:
            return spec_from_loader(
                fullname, _CarregadorPacoteVirtual(),
                origin="namespace histórico virtual", is_package=True,
            )
        return None


def instalar_aliases() -> _AliasesHistoricos | None:
    """Registra a compatibilidade uma vez, sem importar módulos de destino."""
    if not REGISTRO_MIGRACAO.is_file():
        return None
    identificador = str(REGISTRO_MIGRACAO.resolve())
    for finder in sys.meta_path:
        if getattr(finder, "_registro_aliases_codigo_fonte", None) == identificador:
            return finder
    registro = json.loads(REGISTRO_MIGRACAO.read_text(encoding="utf-8"))
    aliases = registro.get("modulos", {})
    if not isinstance(aliases, dict) or any(
        not isinstance(origem, str) or not isinstance(destino, str)
        for origem, destino in aliases.items()
    ):
        raise ValueError("Registro de migração contém aliases inválidos.")
    finder = _AliasesHistoricos(REGISTRO_MIGRACAO, aliases)
    sys.meta_path.append(finder)
    return finder
