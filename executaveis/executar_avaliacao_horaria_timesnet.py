"""CLI do protocolo horário de GHI com TimesNet."""


# Permite executar este arquivo diretamente a partir de ``executaveis/``,
# mantendo a raiz do repositorio disponivel para importar ``codigo_fonte``.
import sys as _sys
from pathlib import Path as _Path

_RAIZ_REPOSITORIO = _Path(__file__).resolve().parents[1]
if str(_RAIZ_REPOSITORIO) not in _sys.path:
    _sys.path.insert(0, str(_RAIZ_REPOSITORIO))

from codigo_fonte.experimento_horario_timesnet import main


if __name__ == "__main__":
    main()
