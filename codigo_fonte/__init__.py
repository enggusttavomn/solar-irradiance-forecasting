"""Código da pesquisa organizado por finalidade.

O registro de aliases permite carregar objetos antigos sem recriar os
arquivos removidos. Nenhum modelo é importado ao registrar a compatibilidade.
"""

from .utilitarios.compatibilidade import instalar_aliases as _instalar_aliases

_instalar_aliases()
del _instalar_aliases
