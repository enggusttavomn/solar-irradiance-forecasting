from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.gerar_comparacao_focal_artigo import select_week


SITE = "Factory under test"
EVENT_DATE = "2024-03-31"
EVENT = pd.Timestamp(EVENT_DATE)
START = EVENT - pd.Timedelta(days=3)


@pytest.fixture
def forecasts() -> pd.DataFrame:
    """Overlapping 72-hour forecasts include context outside the requested week."""
    rows = []
    origins = pd.date_range(EVENT - pd.Timedelta(days=6), periods=11, freq="D")
    for site in (SITE, "Another factory"):
        for origin in origins:
            for lead in range(1, 73):
                target = origin + pd.Timedelta(hours=lead - 1)
                rows.append({
                    "localidade": site,
                    "semente": 42,
                    "origem_local_fixa": origin,
                    "timestamp_alvo_local_fixo": target,
                    "passo_h": lead,
                    "ghi_real_wm2": float(target.hour * 10),
                    "previsao_pos_timesnet_wm2": float(lead),
                    "previsao_pos_dilatedrnn_wm2": float(lead + 2),
                })
    return pd.DataFrame(rows).sample(frac=1, random_state=42).reset_index(drop=True)


def _first_daily_prefix(forecasts: pd.DataFrame) -> pd.Series:
    return (
        forecasts["localidade"].eq(SITE)
        & forecasts["origem_local_fixa"].eq(START)
        & forecasts["passo_h"].le(24)
    )


def test_week_stitches_seven_daily_24_hour_prefixes_without_repeated_targets(
    forecasts: pd.DataFrame,
) -> None:
    original = forecasts.copy(deep=True)
    week = select_week(forecasts, SITE, EVENT_DATE)
    expected_targets = pd.date_range(START, periods=168, freq="h")

    assert len(week) == 168
    assert week["timestamp_alvo_local_fixo"].is_unique
    pd.testing.assert_index_equal(
        pd.DatetimeIndex(week["timestamp_alvo_local_fixo"]),
        expected_targets,
        check_names=False,
    )
    assert week["localidade"].unique().tolist() == [SITE]
    assert week["origem_local_fixa"].nunique() == 7
    for origin, daily in week.groupby("origem_local_fixa"):
        assert len(daily) == 24
        assert daily["passo_h"].tolist() == list(range(1, 25))
        assert daily["timestamp_alvo_local_fixo"].dt.normalize().eq(origin).all()
    np.testing.assert_array_equal(
        week["previsao_pos_timesnet_wm2"], np.tile(np.arange(1, 25), 7)
    )
    assert week.iloc[0]["timestamp_alvo_local_fixo"] == START
    assert week.iloc[-1]["timestamp_alvo_local_fixo"] == EVENT + pd.Timedelta(
        days=3, hours=23
    )
    pd.testing.assert_frame_equal(forecasts, original)


@pytest.mark.parametrize("lead", [1, 12, 24])
def test_week_rejects_missing_target_even_when_longer_forecasts_cover_it(
    forecasts: pd.DataFrame, lead: int,
) -> None:
    remove = _first_daily_prefix(forecasts) & forecasts["passo_h"].eq(lead)
    incomplete = forecasts.loc[~remove]
    missing_target = START + pd.Timedelta(hours=lead - 1)
    assert incomplete.loc[
        incomplete["localidade"].eq(SITE)
        & incomplete["timestamp_alvo_local_fixo"].eq(missing_target),
        "passo_h",
    ].gt(24).any()

    with pytest.raises(ValueError, match="Incomplete or duplicated"):
        select_week(incomplete, SITE, EVENT_DATE)


@pytest.mark.parametrize("keep_count", [False, True])
def test_week_rejects_duplicate_targets_even_when_total_is_168(
    forecasts: pd.DataFrame, keep_count: bool,
) -> None:
    daily_indices = forecasts.index[_first_daily_prefix(forecasts)]
    duplicate = forecasts.loc[[daily_indices[0]]]
    broken = forecasts.drop(index=daily_indices[1]) if keep_count else forecasts
    broken = pd.concat([broken, duplicate], ignore_index=True)

    with pytest.raises(ValueError, match="Incomplete or duplicated"):
        select_week(broken, SITE, EVENT_DATE)


@pytest.mark.parametrize("problem", ["non_midnight", "swapped_days"])
def test_week_rejects_origins_inconsistent_with_daily_target_prefixes(
    forecasts: pd.DataFrame, problem: str,
) -> None:
    broken = forecasts.copy()
    first_day = _first_daily_prefix(broken)
    if problem == "non_midnight":
        broken.loc[first_day, "origem_local_fixa"] = START + pd.Timedelta(hours=1)
    else:
        next_day = (
            broken["localidade"].eq(SITE)
            & broken["origem_local_fixa"].eq(START + pd.Timedelta(days=1))
            & broken["passo_h"].le(24)
        )
        broken.loc[first_day, "origem_local_fixa"] = START + pd.Timedelta(days=1)
        broken.loc[next_day, "origem_local_fixa"] = START

    with pytest.raises(ValueError, match="seven daily midnight issuances"):
        select_week(broken, SITE, EVENT_DATE)


@pytest.mark.parametrize("invalid_lead", [0.0, 11.5, 12.0])
def test_week_rejects_lead_inconsistent_with_target_hour(
    forecasts: pd.DataFrame, invalid_lead: float,
) -> None:
    broken = forecasts.astype({"passo_h": float})
    row = _first_daily_prefix(broken) & broken["passo_h"].eq(11)
    broken.loc[row, "passo_h"] = invalid_lead

    with pytest.raises(ValueError, match="Inconsistent hourly lead indexing"):
        select_week(broken, SITE, EVENT_DATE)


def test_week_rejects_unavailable_site(forecasts: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="Incomplete or duplicated"):
        select_week(forecasts, "Unavailable factory", EVENT_DATE)
