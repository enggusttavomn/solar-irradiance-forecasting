"""Funcoes auxiliares compartilhadas pelos scripts do projeto."""

from __future__ import annotations

from pathlib import Path

from codigo_fonte.configuracao import (
    PASTA_DADOS_BRUTOS,
    PASTA_DADOS_PROCESSADOS,
    criar_pastas,
)


def localizar_arquivo_dados(
    diretorios: tuple[Path, ...] = (PASTA_DADOS_BRUTOS, PASTA_DADOS_PROCESSADOS),
    extensoes: tuple[str, ...] = ("*.csv", "*.xlsx", "*.xls", "*.parquet"),
) -> Path | None:
    """Localiza automaticamente um arquivo tabular de GHI no projeto.

    Args:
        diretorios: Pastas onde a busca sera realizada.
        extensoes: Padroes de arquivos aceitos.

    Returns:
        Caminho do arquivo encontrado ou ``None`` quando nao ha dados locais.

    Notes:
        A busca e recursiva. Quando existem varios arquivos, a chave de
        ordenacao favorece dados brutos e nomes relacionados a GHI diario.
        Ainda assim, informar ``--data-path`` e a opcao mais explicita.
    """
    candidatos: list[Path] = []

    # Reune todos os formatos tabulares aceitos em todas as pastas informadas.
    for diretorio in diretorios:
        if not diretorio.exists():
            continue
        for extensao in extensoes:
            candidatos.extend(diretorio.rglob(extensao))

    if not candidatos:
        return None

    # Cada expressao booleana vale False (0) ou True (1). Como False vem
    # primeiro, arquivos brutos, diarios e de localidades recebem prioridade.
    return sorted(
        candidatos,
        key=lambda path: (
            "brutos" not in str(path.parent).lower(),
            "ghi_diario" not in path.name.lower(),
            "localidades_ev" not in str(path.parent).lower(),
            "ghi_features" in path.name.lower(),
            "ghi" not in path.name.lower(),
            path.name.lower(),
        ),
    )[0]


# Define a interface publica esperada quando este modulo e importado.
__all__ = ["criar_pastas", "localizar_arquivo_dados"]
