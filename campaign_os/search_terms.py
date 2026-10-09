"""Analiza wyszukiwanych haseł: agregacja, wasted spend, high performers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from campaign_os.metrics import BASE_METRICS, add_ratios, safe_div

TERM_KEYS = ["campaign", "ad_group", "search_term"]


@dataclass(frozen=True)
class SearchTermThresholds:
    target_cpa: float
    wasted_min_cost: float = 30.0
    wasted_min_clicks: int = 5
    high_performer_min_conversions: float = 2
    high_performer_max_cpa_ratio: float = 0.8

    @classmethod
    def from_settings(cls, thresholds: dict, account_cpa: float) -> "SearchTermThresholds":
        target = float(thresholds.get("target_cpa") or 0)
        if target <= 0:
            target = account_cpa if account_cpa == account_cpa else 0.0  # NaN -> 0
        return cls(
            target_cpa=target,
            wasted_min_cost=float(thresholds.get("wasted_min_cost", 30.0)),
            wasted_min_clicks=int(thresholds.get("wasted_min_clicks", 5)),
            high_performer_min_conversions=float(thresholds.get("high_performer_min_conversions", 2)),
            high_performer_max_cpa_ratio=float(thresholds.get("high_performer_max_cpa_ratio", 0.8)),
        )


def aggregate_terms(df: pd.DataFrame, keys: list[str] | None = None) -> pd.DataFrame:
    """Sumuje metryki haseł w zakresie i dolicza wskaźniki oraz udział w koszcie."""
    keys = keys or TERM_KEYS
    if df is None or df.empty:
        return pd.DataFrame(columns=keys + BASE_METRICS)
    agg = {m: "sum" for m in BASE_METRICS}
    agg["date"] = "nunique"
    extra = {}
    if "match_type" in df.columns and "match_type" not in keys:
        extra["match_type"] = lambda s: ", ".join(sorted({v for v in s if v}))
    out = df.groupby(keys, as_index=False).agg({**agg, **extra}).rename(columns={"date": "active_days"})
    out = add_ratios(out)
    out["cost_share"] = safe_div(out["cost"], out["cost"].sum())
    return out.sort_values("cost", ascending=False).reset_index(drop=True)


def classify_terms(terms: pd.DataFrame, th: SearchTermThresholds) -> pd.DataFrame:
    """Dodaje flagi is_wasted / is_high_performer oraz kolumnę segment."""
    out = terms.copy()
    if out.empty:
        for col in ("is_wasted", "is_high_performer"):
            out[col] = pd.Series(dtype=bool)
        out["segment"] = pd.Series(dtype=str)
        return out
    out["is_wasted"] = (
        (out["conversions"] <= 0)
        & (out["cost"] >= th.wasted_min_cost)
        & (out["clicks"] >= th.wasted_min_clicks)
    )
    max_cpa = th.target_cpa * th.high_performer_max_cpa_ratio if th.target_cpa > 0 else float("inf")
    out["is_high_performer"] = (
        (out["conversions"] >= th.high_performer_min_conversions)
        & (out["cpa"].fillna(float("inf")) <= max_cpa)
    )
    out["segment"] = "Neutral"
    out.loc[out["conversions"] <= 0, "segment"] = "Bez konwersji"
    out.loc[out["is_wasted"], "segment"] = "Wasted spend"
    out.loc[out["is_high_performer"], "segment"] = "High performer"
    return out


def summary(classified: pd.DataFrame) -> dict[str, float]:
    if classified.empty:
        return {"terms": 0, "wasted_terms": 0, "wasted_cost": 0.0, "wasted_share": float("nan"),
                "hp_terms": 0, "hp_conversions": 0.0, "hp_conv_share": float("nan")}
    total_cost = classified["cost"].sum()
    total_conv = classified["conversions"].sum()
    wasted = classified[classified["is_wasted"]]
    hp = classified[classified["is_high_performer"]]
    return {
        "terms": int(len(classified)),
        "wasted_terms": int(len(wasted)),
        "wasted_cost": float(wasted["cost"].sum()),
        "wasted_share": safe_div(wasted["cost"].sum(), total_cost),
        "hp_terms": int(len(hp)),
        "hp_conversions": float(hp["conversions"].sum()),
        "hp_conv_share": safe_div(hp["conversions"].sum(), total_conv),
    }


def ngram_analysis(terms: pd.DataFrame, n: int = 1, min_terms: int = 2) -> pd.DataFrame:
    """Agregacja metryk po n-gramach słów występujących w hasłach."""
    if terms.empty:
        return pd.DataFrame(columns=["ngram", "terms"] + BASE_METRICS)
    rows = []
    for rec in terms[["search_term"] + BASE_METRICS].itertuples(index=False):
        words = str(rec.search_term).split()
        grams = {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}
        for g in grams:
            rows.append((g, *[getattr(rec, m) for m in BASE_METRICS]))
    if not rows:
        return pd.DataFrame(columns=["ngram", "terms"] + BASE_METRICS)
    grams = pd.DataFrame(rows, columns=["ngram"] + BASE_METRICS)
    out = grams.groupby("ngram").agg(terms=("cost", "size"), **{m: (m, "sum") for m in BASE_METRICS})
    out = add_ratios(out.reset_index())
    out = out[out["terms"] >= min_terms]
    return out.sort_values("cost", ascending=False).reset_index(drop=True)
