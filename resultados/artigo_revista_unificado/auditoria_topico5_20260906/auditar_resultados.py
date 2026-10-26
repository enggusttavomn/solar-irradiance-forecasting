"""Independent audit of saved predictions, without importing experiment code.

Run from the repository root with Python plus numpy and pandas.
Only writes files beside this script; never retrains or modifies source results.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BASE = ROOT / "resultados/avaliacao_multirresolucao_corrigida_v2"
ART = ROOT / "resultados/artigo_revista_unificado/artefatos_resultados_corrigidos_FINAL"
METRICS = ["MAE_wm2", "RMSE_wm2", "nRMSE", "R2"]
KEYS = ["tarefa", "particao", "modelo", "tipo_estimativa", "semente", "localidade", "tipo_horizonte", "horizonte"]
SLUGS = {"Persistencia": "persistencia", "Sazonal ingenuo": "sazonal_ingenuo", "Climatologia": "climatologia", "XGBoost": "xgboost", "LSTM": "lstm", "TimesNet": "timesnet", "DilatedRNN": "dilatedrnn"}
report: dict = {"method": "Independent NumPy recalculation from gzip prediction CSVs; no experiment or artifact-generator imports.", "tolerance": 1e-8, "checks": [], "tasks": {}}


def check(name, value, detail=None):
    item = {"check": name, "passed": bool(value)}
    if detail is not None:
        item["detail"] = detail
    report["checks"].append(item)


def compare(name, calculated, saved, keys, columns):
    calculated = calculated.copy()
    saved = saved.copy()
    for f in (calculated, saved):
        if "semente" in keys:
            f["semente"] = pd.to_numeric(f["semente"], errors="coerce").fillna(-1).astype(int)
    check(name + ": unique keys", not calculated.duplicated(keys).any() and not saved.duplicated(keys).any())
    joint = calculated.merge(saved, on=keys, how="outer", suffixes=("_calc", "_saved"), indicator=True, validate="one_to_one")
    check(name + ": matching keys", joint["_merge"].eq("both").all(), {"calculated_rows": len(calculated), "saved_rows": len(saved)})
    deltas = {}
    for c in columns:
        a = pd.to_numeric(joint[c + "_calc"], errors="coerce").to_numpy(dtype=float)
        b = pd.to_numeric(joint[c + "_saved"], errors="coerce").to_numpy(dtype=float)
        finite = np.isfinite(a) & np.isfinite(b)
        delta = float(np.max(np.abs(a[finite] - b[finite]))) if finite.any() else 0.0
        deltas[c] = delta
        check(name + ": " + c, np.allclose(a, b, rtol=0, atol=1e-8, equal_nan=True), {"max_abs_difference": delta})
    return deltas


def prediction_column(row, hourly):
    slug = SLUGS[row.modelo]
    if hourly:
        return f"previsao_pos_{slug}_wm2"
    suffix = f"seed{int(row.semente)}" if row.tipo_estimativa == "semente" else row.tipo_estimativa
    return f"previsao_pos_{slug}_{suffix}_wm2"


def calc_metrics(y, p):
    error = y - p
    mse = np.mean(error * error)
    rmse = np.sqrt(mse)
    mean = np.mean(y)
    total = np.sum((y - mean) ** 2)
    return [float(np.mean(np.abs(error))), float(rmse), float(rmse / mean) if not np.isclose(mean, 0) else np.nan, float(1 - np.sum(error * error) / total) if len(y) > 1 and not np.isclose(total, 0) else np.nan]


all_local = []
all_contrasts = []
for task in ["daily_30", "monthly_1", "monthly_6", "hourly_72_extension"]:
    print("Auditing", task, flush=True)
    folder = BASE / task
    saved_local = pd.read_csv(folder / "metricas_por_localidade.csv")
    hourly = task.startswith("hourly")
    contract = json.loads((folder / "contrato_execucao.json").read_text(encoding="utf-8"))
    spec = contract["tarefa"]
    task_rows = []
    report["tasks"][task] = {}
    for partition, fname in [("validacao_2023", "previsoes_validacao.csv.gz"), ("teste_2024", "previsoes_teste.csv.gz")]:
        data = pd.read_csv(folder / fname)
        origin, lead = ("origem_utc", "passo_h") if hourly else ("origem", "passo")
        date_target = "timestamp_alvo_local_fixo" if hourly else "data_alvo"
        target_dates = pd.to_datetime(data[date_target])
        check(f"{task}/{partition}: unique forecast keys", not data.duplicated(["localidade", origin, lead]).any())
        check(f"{task}/{partition}: target year", target_dates.dt.year.eq(2024 if partition == "teste_2024" else 2023).all())
        check(f"{task}/{partition}: sites", data["localidade"].nunique() == 10)
        positions = data.groupby(["localidade", origin])[lead].agg(["min", "max", "count"])
        check(f"{task}/{partition}: complete lead sequence", (positions["min"].eq(1) & positions["max"].eq(spec["pred_len"]) & positions["count"].eq(spec["pred_len"])).all())
        counts = data.groupby("localidade")[origin].nunique()
        expected = spec["teste" if partition == "teste_2024" else "validacao"]["origens_esperadas_por_localidade"]
        check(f"{task}/{partition}: contracted origin count", counts.eq(expected).all(), counts.to_dict())
        report["tasks"][task][partition] = {"prediction_rows": len(data), "sites": data["localidade"].nunique(), "origins_per_site": counts.to_dict(), "first_target": str(target_dates.min()), "last_target": str(target_dates.max())}
        post = [c for c in data if c.startswith("previsao_pos_")]
        check(f"{task}/{partition}: finite forecasts/targets", np.isfinite(data[post + ["ghi_real_wm2"]].to_numpy(dtype=float)).all())
        check(f"{task}/{partition}: nonnegative postprocessed forecasts", data[post].ge(-1e-8).all().all())
        if not hourly:
            for slug in ("xgboost", "lstm", "timesnet", "dilatedrnn"):
                seedcols = [f"previsao_bruta_{slug}_seed{s}_wm2" for s in (11, 23, 42, 67, 89)]
                arithmetic = data[seedcols].mean(axis=1).clip(lower=0)
                stored = data[f"previsao_pos_{slug}_ensemble_wm2"]
                check(f"{task}/{partition}: five-seed {slug} ensemble", np.allclose(arithmetic, stored, atol=1e-5, rtol=0), {"max_abs_difference": float(np.max(np.abs(arithmetic - stored)))})
        for site, group in data.groupby("localidade"):
            for row in saved_local.loc[(saved_local.particao == partition) & (saved_local.localidade == site)].itertuples(index=False):
                selected = group[group[lead] <= row.horizonte] if row.tipo_horizonte == "cumulativo" else group[group[lead] == row.horizonte]
                values = calc_metrics(selected.ghi_real_wm2.to_numpy(), selected[prediction_column(row, hourly)].to_numpy())
                record = {k: getattr(row, k) for k in KEYS}
                record.update(zip(METRICS, values))
                record.update(N_origens=selected[origin].nunique(), N_pontos=len(selected))
                task_rows.append(record)
        if partition == "teste_2024":
            tn = "previsao_pos_timesnet_wm2" if hourly else "previsao_pos_timesnet_ensemble_wm2"
            dr = "previsao_pos_dilatedrnn_wm2" if hourly else "previsao_pos_dilatedrnn_ensemble_wm2"
            data["MAE_timesnet_wm2"] = np.abs(data.ghi_real_wm2 - data[tn])
            data["MAE_dilatedrnn_wm2"] = np.abs(data.ghi_real_wm2 - data[dr])
            for horizon in spec["horizontes"]:
                contrast = data.loc[data[lead] <= horizon].groupby(["localidade", origin], as_index=False)[["MAE_timesnet_wm2", "MAE_dilatedrnn_wm2"]].mean().rename(columns={origin: "origem"})
                contrast["tarefa"] = task
                contrast["horizonte"] = horizon
                contrast["ganho_timesnet_vs_dilatedrnn_wm2"] = contrast.MAE_dilatedrnn_wm2 - contrast.MAE_timesnet_wm2
                all_contrasts.append(contrast)
    calculated_local = pd.DataFrame(task_rows)
    compare(task + ": saved site metrics", calculated_local, saved_local, KEYS, METRICS + ["N_origens", "N_pontos"])
    all_local.append(calculated_local)

local = pd.concat(all_local, ignore_index=True)
macro_keys = [c for c in KEYS if c != "localidade"]
macro = local.groupby(macro_keys, dropna=False, as_index=False).agg(**{c: (c, "mean") for c in METRICS}, N_localidades=("localidade", "nunique"), N_origens=("N_origens", "sum"), N_pontos=("N_pontos", "sum"))
saved_macro = pd.concat([pd.read_csv(BASE / task / "metricas_macro.csv") for task in report["tasks"]], ignore_index=True)
compare("All saved macro metrics", macro, saved_macro, macro_keys, METRICS + ["N_localidades", "N_origens", "N_pontos"])
test_macro = macro.loc[macro.particao == "teste_2024"]
published = test_macro.loc[(test_macro.tipo_estimativa != "semente") | (test_macro.tarefa == "hourly_72_extension")].copy()
article = pd.read_csv(ART / "desempenho_macro.csv")
compare("Article full benchmark", published, article, [c for c in macro_keys if c != "particao"], METRICS + ["N_localidades", "N_origens", "N_pontos"])
ranking_keys = ["tarefa", "tipo_horizonte", "horizonte"]
published = published.sort_values(ranking_keys + ["MAE_wm2", "RMSE_wm2", "modelo"])
published["posicao_MAE"] = published.groupby(ranking_keys)["MAE_wm2"].rank(method="min").astype(int)
compare("Article ranking positions", published, article, [c for c in macro_keys if c != "particao"], ["posicao_MAE"])
winners = published.loc[(published.tipo_horizonte == "cumulativo") & (published.posicao_MAE == 1)]
winners.to_csv(OUT / "vencedores_recalculados.csv", index=False)

paired_local = local.loc[(local.particao == "teste_2024") & ((local.tipo_estimativa == "ensemble") | (local.tarefa == "hourly_72_extension")) & local.modelo.isin(["TimesNet", "DilatedRNN"])]
pivot = paired_local.pivot(index=ranking_keys + ["localidade"], columns="modelo", values="MAE_wm2").reset_index()
pivot["delta"] = pivot.TimesNet - pivot.DilatedRNN
pairs = pivot.groupby(ranking_keys, as_index=False).agg(N_localidades=("localidade", "nunique"), diferenca_MAE_media_wm2=("delta", "mean"), diferenca_MAE_mediana_wm2=("delta", "median"), vitorias_locais_timesnet=("delta", lambda s: (s < -1e-9).sum()), vitorias_locais_dilatedrnn=("delta", lambda s: (s > 1e-9).sum()), empates_locais=("delta", lambda s: (s.abs() <= 1e-9).sum()))
compare("Article paired comparisons", pairs, pd.read_csv(ART / "comparacao_timesnet_dilatedrnn_resumo.csv"), ranking_keys, [c for c in pairs if c not in ranking_keys])
pairs.to_csv(OUT / "comparacao_pareada_recalculada.csv", index=False)

seed_keys = ranking_keys + ["modelo"]
seed_summary = test_macro.loc[test_macro.tipo_estimativa == "semente"].groupby(seed_keys, as_index=False).agg(N_sementes=("semente", "nunique"), **{f"{metric}_{label}": (metric, op) for metric in METRICS for label, op in (("media", "mean"), ("desvio_padrao", "std"), ("minimo", "min"), ("maximo", "max"))})
compare("Article seed variability", seed_summary, pd.read_csv(ART / "variabilidade_sementes.csv"), seed_keys, [c for c in seed_summary if c not in seed_keys])
seed_summary.to_csv(OUT / "variabilidade_recalculada.csv", index=False)
terminal = {"daily_30": 30, "monthly_1": 1, "monthly_6": 6, "hourly_72_extension": 72}
seed_terminal = seed_summary.loc[(seed_summary.tipo_horizonte == "cumulativo") & (seed_summary.horizonte == seed_summary.tarefa.map(terminal)) & seed_summary.modelo.isin(["TimesNet", "DilatedRNN"])]
report["terminal_seed_statistics"] = seed_terminal.to_dict(orient="records")
seed_pairs = test_macro.loc[(test_macro.tipo_estimativa == "semente") & test_macro.modelo.isin(["TimesNet", "DilatedRNN"])].pivot(index=ranking_keys + ["semente"], columns="modelo", values="MAE_wm2").reset_index()
seed_pairs["delta_MAE_timesnet_menos_dilatedrnn"] = seed_pairs.TimesNet - seed_pairs.DilatedRNN
seed_pairs["vencedor"] = np.where(seed_pairs.delta_MAE_timesnet_menos_dilatedrnn < -1e-9, "TimesNet", np.where(seed_pairs.delta_MAE_timesnet_menos_dilatedrnn > 1e-9, "DilatedRNN", "Empate"))
seed_pairs.to_csv(OUT / "comparacao_por_semente.csv", index=False)

contrasts = pd.concat(all_contrasts, ignore_index=True)
contrast_keys = ["tarefa", "localidade", "origem", "horizonte"]
contrast_values = ["MAE_timesnet_wm2", "MAE_dilatedrnn_wm2", "ganho_timesnet_vs_dilatedrnn_wm2"]
compare("Article origin/horizon cases", contrasts, pd.read_csv(ART / "contrastes_por_origem_horizonte.csv"), contrast_keys, contrast_values)
check("Article case universe count", len(contrasts) == json.loads((ART / "regra_selecao_casos.json").read_text())["N_origens_horizontes_avaliados"], len(contrasts))
for kind, ascending in [("maior_ganho_timesnet", False), ("maior_deficit_timesnet", True)]:
    selected = contrasts.sort_values(["ganho_timesnet_vs_dilatedrnn_wm2"] + contrast_keys, ascending=[ascending] + [True] * 4).head(1)
    saved_case = pd.read_csv(ART / ("caso_" + kind + ".csv"))
    compare("Global selected " + kind, selected, saved_case, contrast_keys, contrast_values)
    report[kind] = selected.to_dict(orient="records")[0]

weather = pd.read_csv(ROOT / "resultados/artigo_revista_unificado/contexto_meteorologico_2024.csv")
for kind in ["maior_ganho_timesnet", "maior_deficit_timesnet"]:
    case = pd.read_csv(ART / ("caso_" + kind + ".csv")).iloc[0]
    context = weather.loc[(weather.localidade == case.localidade) & (weather.data_local >= case.datas_contexto_inicio) & (weather.data_local <= case.datas_contexto_fim)]
    check("Weather " + kind + ": count", len(context) == case.N_dias_contexto)
    check("Weather " + kind + ": precipitation", np.isclose(context.precipitacao_corrigida_mm_dia.sum(), case.precipitacao_total_mm))
    check("Weather " + kind + ": cloud", np.isclose(context.nebulosidade_percentual.mean(), case.nebulosidade_media_percentual))
    check("Weather " + kind + ": adverse days", context.condicao_adversa_independente.sum() == case.dias_com_condicao_adversa)
independent = weather.loc[weather.condicao_adversa_independente].sort_values(["precipitacao_corrigida_mm_dia", "nebulosidade_percentual", "localidade", "data_local"], ascending=[False, False, True, True]).head(1)
compare("Independent maximum-rainfall example", independent, pd.read_csv(ART / "caso_meteorologico_independente.csv"), ["localidade", "data_local"], ["precipitacao_corrigida_mm_dia", "nebulosidade_percentual"])
report["hourly_exact_lead_caveat"] = "Exact leads 24, 48 and 72 are nighttime targets under the retained daily-origin hourly protocol: all models have MAE=RMSE=0 after night masking; nRMSE and R2 are undefined. Architecture comparisons must use the reported cumulative scopes."

manifest = json.loads((ART / "manifesto_sha256.json").read_text())
for entry in manifest["arquivos"]:
    path = ART / entry["arquivo"]
    check("Artifact SHA-256: " + entry["arquivo"], hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"])
for entry in json.loads((ART / "proveniencia_entradas.json").read_text())["tarefas"]:
    folder = ROOT / entry["pasta"]
    source_contract = json.loads((folder / "contrato_execucao.json").read_text())
    declared = source_contract.pop("sha256_contrato")
    canonical = json.dumps(source_contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    check("Source canonical contract SHA-256: " + entry["tarefa"], hashlib.sha256(canonical).hexdigest() == declared == entry["sha256_contrato"])
    for key, name in [("sha256_manifesto", "manifesto_artefatos.json"), ("sha256_status", "status_execucao.json")]:
        check("Source SHA-256: " + entry["tarefa"] + "/" + name, hashlib.sha256((folder / name).read_bytes()).hexdigest() == entry[key])
    source_manifest = json.loads((folder / "manifesto_artefatos.json").read_text())
    for source in source_manifest["arquivos"]:
        if source["arquivo"] in {"previsoes_teste.csv.gz", "previsoes_validacao.csv.gz", "metricas_por_localidade.csv", "metricas_macro.csv"}:
            check("Audited input SHA-256: " + entry["tarefa"] + "/" + source["arquivo"], hashlib.sha256((folder / source["arquivo"]).read_bytes()).hexdigest() == source["sha256"])
def latex_rows(path):
    """Read table cells while ignoring layout, captions and bold decoration."""
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "&" not in line or not line.rstrip().endswith(r"\\"):
            continue
        clean = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", line)
        cells = [c.strip() for c in clean.rstrip().removesuffix(r"\\").split("&")]
        rows.append(cells)
    return rows


def macro_latex_frame(path):
    rows = latex_rows(path)
    expected_header = ["Task", "Horizon", "Climatology", "DilatedRNN", "LSTM", "Persistence", "Seasonal naive", "TimesNet", "XGBoost", "Seeds"]
    check("Macro LaTeX column labels/order: " + str(path.relative_to(ROOT)), bool(rows) and rows[0] == expected_header)
    records = []
    for cells in rows[1:]:
        if len(cells) != len(expected_header):
            raise ValueError("Unexpected macro LaTeX row width in " + str(path))
        horizon = re.fullmatch(r"(\d+)(?:\s+(?:h|d|months?))?", cells[1])
        if not horizon:
            raise ValueError("Unexpected macro LaTeX horizon: " + cells[1])
        record = {"task_label": cells[0], "horizonte": int(horizon.group(1))}
        record.update({label: np.nan if value == "NA" else float(value) for label, value in zip(expected_header[2:], cells[2:])})
        records.append(record)
    return pd.DataFrame(records)


for source in ART.glob("*.tex"):
    published_path = ROOT / "artigos/revista_unificado/tables" / source.name
    if source.name == "desempenho_macro.tex":
        compare("Article macro LaTeX numerical equivalence", macro_latex_frame(published_path), macro_latex_frame(source), ["task_label", "horizonte"], ["Climatology", "DilatedRNN", "LSTM", "Persistence", "Seasonal naive", "TimesNet", "XGBoost", "Seeds"])
    elif source.name in {"metricas_terminais.tex", "comparacao_timesnet_dilatedrnn_resumo.tex"}:
        def normalized_numeric_rows(path):
            rows = []
            for cells in latex_rows(path):
                if not cells[0].startswith(("Hourly", "Daily", "Monthly")):
                    continue
                cells[1] = re.sub(r"\s+(h|d|mo)$", "", cells[1])
                rows.append(cells)
            return sorted(rows)
        expected_rows = normalized_numeric_rows(source)
        actual_rows = normalized_numeric_rows(published_path)
        check("Article table numerical cells preserved: " + source.name, bool(expected_rows) and actual_rows == expected_rows)
    else:
        check("Article copied table: " + source.name, published_path.exists() and source.read_bytes() == published_path.read_bytes())

architecture_path = ROOT / "artigos/revista_unificado/tables/vencedores_por_horizonte.tex"
architecture_rows = latex_rows(architecture_path)
check("Focused architecture LaTeX column labels/order", architecture_rows[0] == ["Task", "Cumulative horizon", "TimesNet", "DilatedRNN", r"$\Delta$", "Lower MAE"])
task_labels = {"Hourly": "hourly_72_extension", "Daily": "daily_30", "Monthly 12--1": "monthly_1", "Monthly 12--6": "monthly_6"}
architecture_records = []
for cells in architecture_rows[1:]:
    if len(cells) != 6 or cells[0] not in task_labels:
        raise ValueError("Unexpected focused architecture LaTeX row: " + str(cells))
    horizon = re.fullmatch(r"(\d+)\s+(h|d|mo)", cells[1])
    if not horizon:
        raise ValueError("Unexpected architecture LaTeX horizon: " + cells[1])
    architecture_records.append({"tarefa": task_labels[cells[0]], "horizonte": int(horizon.group(1)), "TimesNet": float(cells[2]), "DilatedRNN": float(cells[3]), "delta": float(cells[4]), "vencedor": cells[5]})
architecture_table = pd.DataFrame(architecture_records)
architecture_expected = published.loc[(published.tipo_horizonte == "cumulativo") & published.modelo.isin(["TimesNet", "DilatedRNN"])].pivot(index=["tarefa", "horizonte"], columns="modelo", values="MAE_wm2").reset_index()
architecture_expected["delta"] = architecture_expected.TimesNet - architecture_expected.DilatedRNN
architecture_expected["vencedor"] = np.where(architecture_expected.delta < 0, "TimesNet", "DilatedRNN")
architecture_expected[["TimesNet", "DilatedRNN", "delta"]] = architecture_expected[["TimesNet", "DilatedRNN", "delta"]].round(2)
compare("Focused architecture LaTeX vs recalculated forecasts", architecture_table, architecture_expected, ["tarefa", "horizonte"], ["TimesNet", "DilatedRNN", "delta"])
architecture_winners = architecture_table.merge(architecture_expected, on=["tarefa", "horizonte"], validate="one_to_one", suffixes=("_table", "_expected"))
check("Focused architecture LaTeX winner labels", architecture_winners.vencedor_table.eq(architecture_winners.vencedor_expected).all())
raw_architecture_rows = [line for line in architecture_path.read_text(encoding="utf-8-sig").splitlines() if "&" in line and line.rstrip().endswith(r"\\")][1:]
bold_matches = []
for line, row in zip(raw_architecture_rows, architecture_table.itertuples(index=False)):
    cells = line.split("&")
    expected_column = 2 if row.vencedor == "TimesNet" else 3
    bold_columns = [i for i, cell in enumerate(cells) if r"\textbf{" in cell]
    bold_matches.append(bold_columns == [expected_column])
check("Focused architecture LaTeX highlights correct winner", len(bold_matches) == len(architecture_expected) and all(bold_matches))
report["article_latex_validation"] = {"macro_table": "All task/horizon keys, model column labels/order, seven MAEs and seed counts match the archived table numerically; bold markup and native-unit labels are permitted.", "focused_architecture_table": "All twelve cumulative rows independently match recalculated TimesNet/DilatedRNN macro-MAE, differences rounded only after subtraction, winner names and bold highlights."}

report["local_metric_rows_recalculated"] = len(local)
report["macro_metric_rows_recalculated"] = len(macro)
report["source_prediction_rows"] = sum(p["prediction_rows"] for task in report["tasks"].values() for p in task.values())
report["passed"] = sum(c["passed"] for c in report["checks"])
report["failed"] = sum(not c["passed"] for c in report["checks"])
(OUT / "auditoria_numerica.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(json.dumps({k: report[k] for k in ["source_prediction_rows", "local_metric_rows_recalculated", "macro_metric_rows_recalculated", "passed", "failed"]}, indent=2))
print("WINNERS", winners[["tarefa", "horizonte", "modelo", "MAE_wm2"]].to_string(index=False))
print("FAILED", json.dumps([c for c in report["checks"] if not c["passed"]], ensure_ascii=False, indent=2))
