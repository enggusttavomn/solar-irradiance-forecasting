"""Coleta contexto meteorologico diario para os casos do artigo unificado."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from codigo_fonte.contexto_meteorologico import (
    LIMIAR_CHUVA_MM_DIA,
    LIMIAR_MUITO_NUBLADO_PERCENTUAL,
    PARAMETROS_POWER,
    coletar_contexto_meteorologico,
)


def executar(
    *,
    inicio: str,
    fim: str,
    pasta_cache: str | Path,
    saida: str | Path,
    atualizar: bool = False,
) -> tuple[Path, Path]:
    tabela, proveniencia = coletar_contexto_meteorologico(
        inicio=inicio,
        fim=fim,
        pasta_cache=pasta_cache,
        atualizar=atualizar,
    )
    destino = Path(saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(destino, index=False, date_format="%Y-%m-%d")
    manifesto = destino.with_name(f"{destino.stem}_manifesto.json")
    manifesto.write_text(
        json.dumps(
            {
                "gerado_utc": datetime.now(timezone.utc).isoformat(),
                "periodo": {"inicio": inicio, "fim": fim},
                "parametros": list(PARAMETROS_POWER),
                "criterios_predeclarados": {
                    "chuva_relevante_mm_dia": LIMIAR_CHUVA_MM_DIA,
                    "muito_nublado_percentual": LIMIAR_MUITO_NUBLADO_PERCENTUAL,
                    "adverso": "chuva_relevante OU muito_nublado",
                },
                "uso_no_modelo": False,
                "uso": "contexto pos-hoc da analise de erros",
                "linhas": int(len(tabela)),
                "sha256_csv": hashlib.sha256(destino.read_bytes()).hexdigest(),
                "consultas": proveniencia,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return destino, manifesto


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Coleta precipitação e nebulosidade diárias da NASA POWER."
    )
    parser.add_argument("--inicio", default="2024-01-01")
    parser.add_argument("--fim", default="2024-12-31")
    parser.add_argument(
        "--cache", type=Path, default=Path("dados/externos/nasa_power")
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path(
            "resultados/artigo_revista_unificado/contexto_meteorologico_2024.csv"
        ),
    )
    parser.add_argument("--atualizar", action="store_true")
    args = parser.parse_args()
    for caminho in executar(
        inicio=args.inicio,
        fim=args.fim,
        pasta_cache=args.cache,
        saida=args.saida,
        atualizar=args.atualizar,
    ):
        print(caminho)


if __name__ == "__main__":
    main()
