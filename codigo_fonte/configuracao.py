"""Configuracoes de caminhos usadas pelo pipeline de treinamento."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PASTA_DADOS = PROJECT_ROOT / "dados"
PASTA_DADOS_BRUTOS = PASTA_DADOS / "brutos"
PASTA_DADOS_INTERMEDIARIOS = PASTA_DADOS / "intermediarios"
PASTA_DADOS_PROCESSADOS = PASTA_DADOS / "processados"

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
    """Cria os diretorios padrao do projeto, caso ainda nao existam."""
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
    """Alias mantido para compatibilidade com a primeira versao do pipeline."""
    criar_pastas()
