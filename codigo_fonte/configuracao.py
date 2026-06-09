"""Centralizacao dos caminhos usados em todo o projeto.

Os caminhos sao calculados a partir da posicao deste arquivo. Dessa forma, os
scripts continuam funcionando mesmo quando o comando e executado fora da raiz
do repositorio.
"""

from pathlib import Path


# ``configuracao.py`` fica em ``codigo_fonte/``; subir um nivel encontra a raiz.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Pastas de dados seguem a separacao bruto -> intermediario -> processado.
PASTA_DADOS = PROJECT_ROOT / "dados"
PASTA_DADOS_BRUTOS = PASTA_DADOS / "brutos"
PASTA_DADOS_INTERMEDIARIOS = PASTA_DADOS / "intermediarios"
PASTA_DADOS_PROCESSADOS = PASTA_DADOS / "processados"

# Pastas de documentacao, resultados e apoio.
PASTA_CADERNOS = PROJECT_ROOT / "cadernos_jupyter"
PASTA_RESULTADOS = PROJECT_ROOT / "resultados"
PASTA_FIGURAS = PASTA_RESULTADOS / "figuras"
PASTA_METRICAS = PASTA_RESULTADOS / "metricas"
PASTA_MODELOS = PASTA_RESULTADOS / "modelos"
PASTA_RELATORIOS = PROJECT_ROOT / "relatorios"
PASTA_TESTES = PROJECT_ROOT / "testes"
PASTA_TOOLS = PROJECT_ROOT / "tools"

# Aliases em ingles para reduzir atrito com bibliotecas e codigo legado.
DATA_DIR = PASTA_DADOS
RAW_DATA_DIR = PASTA_DADOS_BRUTOS
INTERIM_DATA_DIR = PASTA_DADOS_INTERMEDIARIOS
PROCESSED_DATA_DIR = PASTA_DADOS_PROCESSADOS
OUTPUTS_DIR = PASTA_RESULTADOS
FIGURES_DIR = PASTA_FIGURAS
METRICS_DIR = PASTA_METRICAS
MODELS_DIR = PASTA_MODELOS
REPORTS_DIR = PASTA_RELATORIOS
TOOLS_DIR = PASTA_TOOLS


def criar_pastas() -> None:
    """Cria os diretorios padrao do projeto, caso ainda nao existam.

    ``parents=True`` cria tambem os diretorios pais ausentes. ``exist_ok=True``
    torna a funcao idempotente: ela pode ser chamada varias vezes sem erro.
    """
    for directory in [
        PASTA_DADOS_BRUTOS,
        PASTA_DADOS_INTERMEDIARIOS,
        PASTA_DADOS_PROCESSADOS,
        PASTA_CADERNOS,
        PASTA_FIGURAS,
        PASTA_METRICAS,
        PASTA_MODELOS,
        PASTA_RELATORIOS,
        PASTA_TESTES,
        PASTA_TOOLS,
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def garantir_diretorios() -> None:
    """Alias mantido para codigo antigo que usava este nome de funcao."""
    criar_pastas()
