"""Regenerate the BTSym'26 DilatedRNN temporal figure from canonical CSVs."""

from __future__ import annotations

import csv
import os
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "btsym26-matplotlib"))

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "resultados" / "avaliacao_mensal_canonica"
OUTPUT = Path(__file__).resolve().parent / "figures" / "dilatedrnn_forecast_byd_camacari.png"
LOCATION = "BYD Camacari"


def read_consolidated() -> list[dict[str, str]]:
    with (RESULTS / "previsoes_consolidadas.csv").open(encoding="utf-8", newline="") as stream:
        return [row for row in csv.DictReader(stream) if row["Localidade"] == LOCATION]


def read_seed_forecasts() -> dict[str, list[float]]:
    forecasts: dict[str, list[float]] = defaultdict(list)
    with (RESULTS / "previsoes_por_modelo_seed.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["Localidade"] == LOCATION and row["Modelo"] == "DilatedRNN":
                forecasts[row["data_alvo"]].append(float(row["y_pred_wm2"]))
    return forecasts


def main() -> None:
    rows = sorted(read_consolidated(), key=lambda row: row["data_alvo"])
    seeds = read_seed_forecasts()
    if len(rows) != 12 or any(len(seeds[row["data_alvo"]]) != 5 for row in rows):
        raise RuntimeError("Expected 12 monthly targets and five DilatedRNN seeds per target")

    months = [datetime.strptime(row["data_alvo"], "%Y-%m-%d").strftime("%b") for row in rows]
    reference = np.array([float(row["y_wm2"]) for row in rows])
    dilated = np.array([float(row["DilatedRNN"]) for row in rows])
    seed_matrix = np.array([seeds[row["data_alvo"]] for row in rows])

    plt.rcParams.update(
        {
            "font.size": 8.0,
            "axes.labelsize": 8.5,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7.0,
        }
    )

    x = np.arange(12)
    fig, ax = plt.subplots(figsize=(7.2, 3.00))
    band = ax.fill_between(
        x,
        seed_matrix.min(axis=1),
        seed_matrix.max(axis=1),
        facecolor="#9ECAE1",
        edgecolor="#3565A8",
        linewidth=0.55,
        alpha=0.35,
        label="DilatedRNN min--max across 5 seeds",
    )
    reference_line, = ax.plot(
        x,
        reference,
        color="#202124",
        marker="o",
        markersize=4.2,
        linewidth=1.55,
        label="Modeled GHI reference",
    )
    dilated_line, = ax.plot(
        x,
        dilated,
        color="#3565A8",
        marker="s",
        markersize=4.0,
        linewidth=1.55,
        label="DilatedRNN (5-seed mean)",
    )
    ax.set_xticks(x, months)
    ax.set_xlabel("Month in 2024")
    ax.set_ylabel("Monthly mean GHI (W/m$^2$)")
    ax.grid(axis="y", color="#d9d9d9", linewidth=0.50)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_linewidth(0.65)
    ax.tick_params(width=0.65, length=3.0)
    ax.legend(
        [reference_line, dilated_line, band],
        [
            "Modeled GHI reference",
            "DilatedRNN (5-seed mean)",
            "DilatedRNN min--max across 5 seeds",
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.20),
        ncol=3,
        frameon=False,
        columnspacing=1.6,
        handlelength=2.4,
    )
    fig.subplots_adjust(bottom=0.29, left=0.105, right=0.99, top=0.98)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
