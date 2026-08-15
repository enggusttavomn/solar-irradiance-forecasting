"""CLI do protocolo mensal global canonico dos artigos.

A execucao completa exige ``--confirmar-execucao-longa`` e pode ser retomada
com ``--retomar`` sem repetir modelos ja persistidos.
"""

from codigo_fonte.experimento_mensal_canonico import main


if __name__ == "__main__":
    main()
