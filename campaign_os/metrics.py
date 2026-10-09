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
    """Dzielenie zwracające NaN zamiast inf/błędu przy zerowym mianowniku.

    Obsługuje kombinacje Series/skalar bez wyrównywania indeksów skalara.
    """
    if isinstance(num, np.ndarray):
        num = pd.Series(num, dtype=float)
    if isinstance(den, np.ndarray):
        den = pd.Series(den, dtype=float)
    if isinstance(den, pd.Series):
        den = den.astype(float)
        num = num.astype(float) if isinstance(num, pd.Series) else float(num)
        return num / den.where(den != 0)
    den = float(den)
    if isinstance(num, pd.Series):
        return num.astype(float) / den if den else pd.Series(np.nan, index=num.index)
    num = float(num)
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


# --------------------------------------------------------------------------- agregacja ogólna


def aggregate(df: pd.DataFrame, keys: list[str] | tuple) -> pd.DataFrame:
    """Agreguje dowolny raport SEM po kluczach, szanując typ metryk.

    * metryki sumowalne – suma,
    * udziały w wyświetleniach (Search IS, Lost IS) – średnia ważona wyświetleniami
      kwalifikującymi się (impressions / Search IS),
    * pozostałe udziały i oceny (Quality Score) – średnia ważona wyświetleniami
      (lub zwykła średnia, gdy raport nie ma wyświetleń),
    * wymiary i kategorie – ostatnia niepusta wartość (dane są sortowane po dacie).
    Kolumna ``date`` spoza kluczy jest pomijana.
    """
    from campaign_os.schema import ADDITIVE, IS_SHARES, SCORES, SHARES

    keys = [k for k in keys if k in df.columns]
    work = df.copy()
    if "date" in work.columns and "date" not in keys:
        work = work.sort_values("date").drop(columns=["date"])
    dummy = not keys
    if dummy:
        work["_all"] = 0
        keys = ["_all"]
    cols = [c for c in work.columns if c not in keys]
    additive = [c for c in ADDITIVE if c in cols]
    weighted = [c for c in SHARES + SCORES if c in cols]
    others = [c for c in cols if c not in additive + weighted]

    base_w = work["impressions"].astype(float) if "impressions" in work.columns else pd.Series(1.0, index=work.index)
    if "search_impression_share" in work.columns:
        is_ = work["search_impression_share"].astype(float)
        eligible = (base_w / is_.where(is_ > 0)).fillna(base_w)
    else:
        eligible = base_w
    tmp_cols = []
    for c in weighted:
        w = eligible if c in IS_SHARES else base_w
        if w.sum() == 0:
            w = pd.Series(1.0, index=work.index)
        v = work[c].astype(float)
        work[f"_{c}_vw"] = (v * w).where(v.notna(), 0.0)
        work[f"_{c}_w"] = w.where(v.notna(), 0.0)
        tmp_cols += [f"_{c}_vw", f"_{c}_w"]
    text_cols = [c for c in others if not pd.api.types.is_numeric_dtype(work[c])
                 and not pd.api.types.is_datetime64_any_dtype(work[c])]
    for c in text_cols:
        col = work[c].astype(object)
        work[c] = col.where(col != "", np.nan)

    agg = {c: "sum" for c in additive + tmp_cols}
    agg.update({c: "last" for c in others})
    out = work.groupby(keys, as_index=False, sort=True, dropna=False).agg(agg)
    for c in weighted:
        out[c] = out[f"_{c}_vw"] / out[f"_{c}_w"].where(out[f"_{c}_w"] > 0)
    out = out.drop(columns=tmp_cols)
    for c in text_cols:
        out[c] = out[c].fillna("").astype(str)
    if dummy:
        out = out.drop(columns=["_all"])
    order = [c for c in df.columns if c in out.columns]
    return out[order].reset_index(drop=True)
