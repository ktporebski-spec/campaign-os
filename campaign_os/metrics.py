"""KPI, zakresy dat i porównanie z poprzednim analogicznym okresem."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

BASE_METRICS = ["cost", "impressions", "clicks", "conversions", "conversion_value"]
RATIO_METRICS = ["ctr", "cpc", "cvr", "cpa", "roas"]

# Metadane do wyświetlania KPI. better: "up" = wzrost jest dobry, "down" = spadek jest dobry,
# None = neutralna (np. wydatki).
KPI_META = {
    "cost": {"label": "Spend", "fmt": "money", "better": None},
    "impressions": {"label": "Impressions", "fmt": "int", "better": "up"},
    "clicks": {"label": "Clicks", "fmt": "int", "better": "up"},
    "ctr": {"label": "CTR", "fmt": "pct", "better": "up"},
    "cpc": {"label": "CPC", "fmt": "money", "better": "down"},
    "conversions": {"label": "Conversions", "fmt": "num", "better": "up"},
    "cvr": {"label": "CVR", "fmt": "pct", "better": "up"},
    "cpa": {"label": "CPA", "fmt": "money", "better": "down"},
    "conversion_value": {"label": "Conv. value", "fmt": "money", "better": "up"},
    "roas": {"label": "ROAS", "fmt": "ratio", "better": "up"},
}


def safe_div(num, den):
    """Dzielenie zwracające NaN zamiast inf/błędu przy zerowym mianowniku."""
    if isinstance(num, (pd.Series, np.ndarray)) or isinstance(den, (pd.Series, np.ndarray)):
        num_s = pd.Series(num, dtype=float) if not isinstance(num, pd.Series) else num.astype(float)
        den_s = pd.Series(den, dtype=float) if not isinstance(den, pd.Series) else den.astype(float)
        return num_s / den_s.where(den_s != 0)
    num = float(num)
    den = float(den)
    return num / den if den else float("nan")


def add_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Dodaje CTR, CPC, CVR, CPA i ROAS do DataFrame z metrykami bazowymi."""
    out = df.copy()
    out["ctr"] = safe_div(out["clicks"], out["impressions"])
    out["cpc"] = safe_div(out["cost"], out["clicks"])
    out["cvr"] = safe_div(out["conversions"], out["clicks"])
    out["cpa"] = safe_div(out["cost"], out["conversions"])
    out["roas"] = safe_div(out["conversion_value"], out["cost"])
    return out


def totals(df: pd.DataFrame) -> dict[str, float]:
    """Sumy metryk bazowych i wskaźniki pochodne dla całego DataFrame."""
    sums = {m: float(df[m].sum()) if m in df.columns and len(df) else 0.0 for m in BASE_METRICS}
    sums["ctr"] = safe_div(sums["clicks"], sums["impressions"])
    sums["cpc"] = safe_div(sums["cost"], sums["clicks"])
    sums["cvr"] = safe_div(sums["conversions"], sums["clicks"])
    sums["cpa"] = safe_div(sums["cost"], sums["conversions"])
    sums["roas"] = safe_div(sums["conversion_value"], sums["cost"])
    return sums


def pct_change(current: float, previous: float) -> float:
    if previous is None or pd.isna(previous) or previous == 0 or pd.isna(current):
        return float("nan")
    return (current - previous) / abs(previous)


# --------------------------------------------------------------------------- okresy


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def label(self) -> str:
        return f"{self.start:%d.%m.%Y} – {self.end:%d.%m.%Y}"


def previous_period(period: Period) -> Period:
    """Poprzedni analogiczny okres: ta sama liczba dni bezpośrednio przed zakresem."""
    end = period.start - timedelta(days=1)
    start = end - timedelta(days=period.days - 1)
    return Period(start, end)


def filter_period(df: pd.DataFrame, period: Period) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    mask = (df["date"] >= pd.Timestamp(period.start)) & (df["date"] <= pd.Timestamp(period.end))
    return df.loc[mask]


def coverage_days(df: pd.DataFrame, period: Period) -> int:
    """Liczba dni zakresu, dla których istnieją dane."""
    if df is None or df.empty:
        return 0
    return int(filter_period(df, period)["date"].dt.normalize().nunique())


def compare_totals(current: pd.DataFrame, previous: pd.DataFrame) -> pd.DataFrame:
    """Tabela KPI: wartość bieżąca, poprzednia i zmiana procentowa."""
    cur = totals(current)
    prev = totals(previous) if previous is not None and not previous.empty else {k: float("nan") for k in cur}
    rows = []
    for key in KPI_META:
        rows.append({
            "metric": key,
            "current": cur[key],
            "previous": prev[key],
            "change": pct_change(cur[key], prev[key]),
        })
    return pd.DataFrame(rows).set_index("metric")


def daily_series(df: pd.DataFrame, period: Period) -> pd.DataFrame:
    """Dzienne metryki dla zakresu, z uzupełnieniem dni bez danych zerami."""
    idx = pd.date_range(period.start, period.end, freq="D", name="date")
    if df is None or df.empty:
        daily = pd.DataFrame(0.0, index=idx, columns=BASE_METRICS)
    else:
        daily = (
            filter_period(df, period).groupby("date")[BASE_METRICS].sum().reindex(idx, fill_value=0.0)
        )
    daily = add_ratios(daily.reset_index())
    daily["day_index"] = np.arange(1, len(daily) + 1)
    return daily


def entity_comparison(
    current: pd.DataFrame, previous: pd.DataFrame, keys: list[str]
) -> pd.DataFrame:
    """Agregacja po encji (np. kampanii) z metrykami bieżącymi, *_prev i *_change."""
    cur = add_ratios(current.groupby(keys, as_index=False)[BASE_METRICS].sum())
    if previous is None or previous.empty:
        prev = pd.DataFrame(columns=keys + BASE_METRICS)
    else:
        prev = previous.groupby(keys, as_index=False)[BASE_METRICS].sum()
    prev = add_ratios(prev) if not prev.empty else prev.assign(**{r: pd.Series(dtype=float) for r in RATIO_METRICS})
    prev = prev.rename(columns={m: f"{m}_prev" for m in BASE_METRICS + RATIO_METRICS})
    merged = cur.merge(prev, on=keys, how="left")
    for m in BASE_METRICS + RATIO_METRICS:
        prev_col = merged[f"{m}_prev"].astype(float)
        merged[f"{m}_change"] = (merged[m] - prev_col) / prev_col.abs().where(prev_col != 0)
    return merged.sort_values("cost", ascending=False).reset_index(drop=True)
