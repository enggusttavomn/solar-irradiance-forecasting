"""Ferramentas pequenas para tornar uma execucao cientifica auditavel.

O modulo evita importar bibliotecas pesadas durante a criacao do manifesto.
As versoes sao consultadas pelos metadados da instalacao e os arquivos sao
identificados por SHA-256. Assim, um resultado pode ser associado exatamente
aos dados, a configuracao e ao ambiente que o produziram.

Exemplo de integracao no inicio de um treinamento::

    seed = 42
    definir_seed_global(seed)
    salvar_manifesto(
        "resultados/manifesto_execucao.json",
        arquivos_entrada=["dados/brutos/local.csv", "requirements.txt"],
        configuracao={"frequencia": "mensal", "horizonte": 1},
        seed=seed,
        raiz_projeto=".",
    )

O ``random_state`` dos estimadores scikit-learn/XGBoost ainda deve receber a
mesma semente explicitamente; a semente global nao substitui esse parametro.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import platform
import random
import sys
import warnings
from datetime import date, datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


VERSAO_ESQUEMA_MANIFESTO = 1

# Nome exibido no manifesto -> nome da distribuicao no Python Package Index.
# Manter a lista explicita torna o arquivo compacto e focado nas dependencias
# que podem mudar os resultados numericos ou a geracao dos artefatos.
DEPENDENCIAS_CIENTIFICAS: Mapping[str, str] = {
    "numpy": "numpy",
    "pandas": "pandas",
    "scipy": "scipy",
    "pvlib": "pvlib",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "scikit-learn": "scikit-learn",
    "xgboost": "xgboost",
    "joblib": "joblib",
    "tensorflow": "tensorflow",
    "keras": "keras",
    "torch": "torch",
    "gluonts": "gluonts",
    "lightning": "lightning",
    "pytorch-lightning": "pytorch-lightning",
}


def _valor_json(valor: Any) -> Any:
    """Converte tipos cientificos/comuns para uma representacao JSON estavel."""

    if dataclasses.is_dataclass(valor) and not isinstance(valor, type):
        return dataclasses.asdict(valor)
    if isinstance(valor, Path):
        return valor.as_posix()
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, set):
        return sorted(valor, key=str)

    # NumPy e opcional para este conversor. A verificacao por protocolo evita
    # importa-lo apenas para serializar uma configuracao simples.
    if hasattr(valor, "item") and callable(valor.item):
        try:
            return valor.item()
        except (TypeError, ValueError):
            pass
    if hasattr(valor, "tolist") and callable(valor.tolist):
        try:
            return valor.tolist()
        except (TypeError, ValueError):
            pass

    raise TypeError(
        f"Objeto do tipo {type(valor).__name__!r} nao e serializavel em JSON"
    )


def json_canonico(valor: Any) -> str:
    """Serializa sem ambiguidades para comparacao e calculo de hash.

    Chaves ordenadas e ausencia de espacos fazem configuracoes equivalentes
    produzir a mesma sequencia de bytes, independentemente da ordem de criacao
    dos dicionarios.
    """

    return json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_valor_json,
    )


def sha256_configuracao(configuracao: Any) -> str:
    """Retorna o SHA-256 da representacao canonica de uma configuracao."""

    return hashlib.sha256(json_canonico(configuracao).encode("utf-8")).hexdigest()


def sha256_arquivo(caminho: str | Path, tamanho_bloco: int = 1024 * 1024) -> str:
    """Calcula SHA-256 em blocos, inclusive para arquivos grandes de dados."""

    if tamanho_bloco <= 0:
        raise ValueError("tamanho_bloco deve ser positivo")

    arquivo = Path(caminho)
    if not arquivo.is_file():
        raise FileNotFoundError(f"Arquivo de entrada inexistente: {arquivo}")

    digest = hashlib.sha256()
    with arquivo.open("rb") as fluxo:
        for bloco in iter(lambda: fluxo.read(tamanho_bloco), b""):
            digest.update(bloco)
    return digest.hexdigest()


def versoes_dependencias(
    dependencias: Mapping[str, str] | None = None,
) -> dict[str, str | None]:
    """Consulta versoes instaladas sem importar TensorFlow, XGBoost etc.

    Uma dependencia ausente aparece como ``None`` em vez de impedir que o
    diagnostico do ambiente seja gravado.
    """

    selecionadas = (
        DEPENDENCIAS_CIENTIFICAS if dependencias is None else dependencias
    )
    versoes: dict[str, str | None] = {}
    for nome_exibido, distribuicao in selecionadas.items():
        try:
            versoes[nome_exibido] = version(distribuicao)
        except PackageNotFoundError:
            versoes[nome_exibido] = None
    return dict(sorted(versoes.items()))


def definir_seed_global(
    seed: int = 42,
    *,
    configurar_tensorflow: bool = True,
    operacoes_tensorflow_deterministicas: bool = True,
    configurar_pytorch: bool = False,
    operacoes_pytorch_deterministicas: bool = True,
) -> dict[str, Any]:
    """Configura fontes usuais de aleatoriedade e informa o que foi aplicado.

    ``PYTHONHASHSEED`` so controla integralmente a ordem dos hashes se estiver
    definido antes de iniciar o interpretador. Ele e registrado aqui para os
    subprocessos; a execucao principal deve ser iniciada, idealmente, com
    ``PYTHONHASHSEED=<seed>``. TensorFlow e PyTorch sao importados apenas quando
    solicitados. ``configurar_pytorch`` permanece desativado por padrao para
    nao carregar o PyTorch em rotinas exclusivamente tabulares/Keras.
    """

    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or not 0 <= seed < 2**32
    ):
        raise ValueError("seed deve ser um inteiro no intervalo [0, 2**32)")

    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)

    import numpy as np

    np.random.seed(seed)
    estado: dict[str, Any] = {
        "seed": seed,
        "python_random": True,
        "numpy": True,
        "tensorflow": False,
        "tensorflow_deterministico": False,
        "pytorch": False,
        "pytorch_deterministico": False,
    }

    if configurar_tensorflow:
        if operacoes_tensorflow_deterministicas:
            # A variavel precisa existir antes da importacao da biblioteca.
            os.environ["TF_DETERMINISTIC_OPS"] = "1"

        try:
            import tensorflow as tf
        except ImportError:
            warnings.warn(
                "TensorFlow nao esta instalado; sua semente nao foi configurada.",
                RuntimeWarning,
                stacklevel=2,
            )
        else:
            tf.keras.utils.set_random_seed(seed)
            estado["tensorflow"] = True

            if operacoes_tensorflow_deterministicas:
                try:
                    tf.config.experimental.enable_op_determinism()
                    estado["tensorflow_deterministico"] = True
                except (AttributeError, RuntimeError) as erro:
                    warnings.warn(
                        "Nao foi possivel ativar determinismo no TensorFlow: "
                        f"{erro}",
                        RuntimeWarning,
                        stacklevel=2,
                    )

    if configurar_pytorch:
        try:
            import torch
        except ImportError:
            warnings.warn(
                "PyTorch nao esta instalado; sua semente nao foi configurada.",
                RuntimeWarning,
                stacklevel=2,
            )
        else:
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
            estado["pytorch"] = True

            if operacoes_pytorch_deterministicas:
                try:
                    torch.use_deterministic_algorithms(True)
                    if hasattr(torch.backends, "cudnn"):
                        torch.backends.cudnn.benchmark = False
                        torch.backends.cudnn.deterministic = True
                    estado["pytorch_deterministico"] = True
                except (AttributeError, RuntimeError) as erro:
                    warnings.warn(
                        "Nao foi possivel ativar determinismo no PyTorch: "
                        f"{erro}",
                        RuntimeWarning,
                        stacklevel=2,
                    )
    return estado


def _nome_portavel(caminho: Path, raiz_projeto: Path | None) -> str:
    """Produz caminho relativo ao projeto quando isso for possivel."""

    if raiz_projeto is not None:
        try:
            return caminho.resolve().relative_to(raiz_projeto.resolve()).as_posix()
        except ValueError:
            pass
    return caminho.as_posix()


def metadados_arquivos(
    caminhos: Iterable[str | Path],
    *,
    raiz_projeto: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Retorna nome, tamanho e SHA-256 de cada entrada em ordem deterministica."""

    raiz = Path(raiz_projeto) if raiz_projeto is not None else None
    arquivos: list[dict[str, Any]] = []
    for caminho_original in caminhos:
        caminho = Path(caminho_original)
        if not caminho.is_file():
            raise FileNotFoundError(f"Arquivo de entrada inexistente: {caminho}")
        arquivos.append(
            {
                "caminho": _nome_portavel(caminho, raiz),
                "tamanho_bytes": caminho.stat().st_size,
                "sha256": sha256_arquivo(caminho),
            }
        )
    return sorted(arquivos, key=lambda item: item["caminho"])


def construir_manifesto(
    *,
    arquivos_entrada: Sequence[str | Path] = (),
    configuracao: Any | None = None,
    seed: int = 42,
    raiz_projeto: str | Path | None = None,
    metadados: Mapping[str, Any] | None = None,
    dependencias: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Constroi um manifesto completo, pronto para ser salvo junto ao resultado."""

    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or not 0 <= seed < 2**32
    ):
        raise ValueError("seed deve ser um inteiro no intervalo [0, 2**32)")

    config = {} if configuracao is None else configuracao
    manifesto: dict[str, Any] = {
        "versao_esquema": VERSAO_ESQUEMA_MANIFESTO,
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "ambiente": {
            "python": platform.python_version(),
            "implementacao_python": platform.python_implementation(),
            "plataforma": platform.platform(),
            "executavel": Path(sys.executable).name,
            "dependencias": versoes_dependencias(dependencias),
        },
        "configuracao": config,
        "configuracao_sha256": sha256_configuracao(config),
        "arquivos_entrada": metadados_arquivos(
            arquivos_entrada,
            raiz_projeto=raiz_projeto,
        ),
    }
    if metadados:
        manifesto["metadados"] = dict(metadados)
    return manifesto


def salvar_json(valor: Any, caminho: str | Path) -> Path:
    """Salva JSON UTF-8 de forma atomica, com formatacao legivel e estavel."""

    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(f".{destino.name}.tmp")
    try:
        conteudo = json.dumps(
            valor,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
            default=_valor_json,
        )
        temporario.write_text(f"{conteudo}\n", encoding="utf-8")
        os.replace(temporario, destino)
    finally:
        if temporario.exists():
            temporario.unlink()
    return destino


def salvar_manifesto(
    caminho: str | Path,
    **parametros: Any,
) -> dict[str, Any]:
    """Constroi e salva um manifesto; retorna o dicionario persistido."""

    manifesto = construir_manifesto(**parametros)
    # O round-trip normaliza tuplas, escalares NumPy, ``Path`` etc. para os
    # mesmos tipos que ``json.load`` devolvera. Assim, o retorno corresponde
    # literalmente ao conteudo persistido, como promete a API.
    manifesto_persistido = json.loads(json_canonico(manifesto))
    salvar_json(manifesto_persistido, caminho)
    return manifesto_persistido
