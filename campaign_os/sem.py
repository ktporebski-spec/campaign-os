"""Warstwa SEM: pokrycie danych, dostępność analiz i ramki encji dla Rule Engine.

Każda encja (słowo kluczowe, urządzenie, godzina, lokalizacja…) jest budowana WYŁĄCZNIE z raportu,
który ją opisuje. Jeśli raportu nie dostarczono, ramka nie powstaje, a reguły tej encji nie są
uruchamiane – dzięki temu nie powstają diagnozy oparte na brakujących danych.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd

from campaign_os import metrics
from campaign_os.metrics import Period, add_ratios, safe_div
from campaign_os.schema import (
    ADDITIVE, COVERAGE_ORDER, IS_SHARES, MODULES, REPORT_BY_KEY, SCORES, SHARES, TIERS, AnalysisModule,
)

CORE_REPORTS = ("campaign_daily", "search_terms_daily")


# --------------------------------------------------------------------------- pokrycie danych


@dataclass
class CoverageItem:
    key: str
    label: str
    core: bool
    present: bool
    rows: int = 0
    date_from: pd.Timestamp | None = None
    date_to: pd.Timestamp | None = None
    has_date: bool = False
    columns: tuple = ()


def coverage(datasets: dict[str, pd.DataFrame]) -> list[CoverageItem]:
    items = []
    for key in COVERAGE_ORDER:
        spec = REPORT_BY_KEY[key]
        df = datasets.get(key)
        if df is None or df.empty:
            items.append(CoverageItem(key, spec.label, spec.core, False))
            continue
        has_date = "date" in df.columns and df["date"].notna().any()
        items.append(CoverageItem(
            key, spec.label, spec.core, True, rows=len(df),
            date_from=df["date"].min() if has_date else None,
            date_to=df["date"].max() if has_date else None,
            has_date=has_date, columns=tuple(df.columns),
        ))
    return items


@dataclass
class ModuleStatus:
    module: AnalysisModule
    available: bool
    reason: str = ""


def _has_any(df: pd.DataFrame, alternatives: tuple) -> bool:
    return any(c in df.columns and df[c].notna().any() and (df[c] != "").any() for c in alternatives)


def module_status(datasets: dict[str, pd.DataFrame]) -> list[ModuleStatus]:
    out = []
    for m in MODULES:
        missing = [REPORT_BY_KEY[r].label for r in m.reports if datasets.get(r) is None or datasets[r].empty]
        if missing:
            out.append(ModuleStatus(m, False, "Brak raportu: " + ", ".join(missing)))
            continue
        lacking = [f"{REPORT_BY_KEY[r].label}: {' / '.join(alts)}" for r, alts in m.columns
                   if not _has_any(datasets[r], alts)]
        if lacking:
            out.append(ModuleStatus(m, False, "Raport nie zawiera kolumn – " + "; ".join(lacking)))
            continue
        out.append(ModuleStatus(m, True))
    return out


def analysis_level(statuses: list[ModuleStatus]) -> dict[str, dict]:
    """Status poziomów BASIC / ADVANCED / FULL. Poziom jest osiągnięty, gdy dostępne są
    wszystkie moduły tego poziomu i poziomów niższych."""
    result = {}
    reached_prev = True
    for tier, (title, desc) in TIERS.items():
        mods = [s for s in statuses if s.module.tier == tier]
        available = sum(s.available for s in mods)
        complete = available == len(mods)
        result[tier] = {
            "title": title, "description": desc, "available": available, "total": len(mods),
            "complete": complete, "reached": reached_prev and complete, "modules": mods,
        }
        reached_prev = reached_prev and complete
    return result


# --------------------------------------------------------------------------- filtrowanie


def scope(df: pd.DataFrame | None, period: Period, campaigns: list[str] | None) -> pd.DataFrame | None:
    """Zawęża raport do okresu (jeśli ma datę) i wybranych kampanii (jeśli ma kampanię)."""
    if df is None or df.empty:
        return None
    out = df
    if "date" in out.columns and out["date"].notna().any():
        out = metrics.filter_period(out, period)
    if campaigns and "campaign" in out.columns and (out["campaign"] != "").any():
        out = out[out["campaign"].isin(campaigns)]
    return out


def has_date(df: pd.DataFrame) -> bool:
    return "date" in df.columns and df["date"].notna().any()


# --------------------------------------------------------------------------- statystyki segmentów


def two_proportion_z(conv: pd.Series, clicks: pd.Series, conv_rest: pd.Series, clicks_rest: pd.Series) -> pd.Series:
    """Test z dla różnicy dwóch proporcji (dodatni = segment wypada lepiej niż reszta)."""
    conv, clicks, conv_rest, clicks_rest = (pd.Series(x, dtype=float) if not isinstance(x, pd.Series)
                                            else x.astype(float) for x in (conv, clicks, conv_rest, clicks_rest))
    p1 = safe_div(conv, clicks)
    p2 = safe_div(conv_rest, clicks_rest)
    pooled = safe_div(conv + conv_rest, clicks + clicks_rest)
    se = np.sqrt(pooled * (1 - pooled) * (1 / clicks.where(clicks > 0) + 1 / clicks_rest.where(clicks_rest > 0)))
    return (p1 - p2) / se.where(se > 0)


def segment_compare(df: pd.DataFrame, group: str | None = None) -> pd.DataFrame:
    """Porównuje każdy segment z resztą raportu (lub resztą grupy ``group``)."""
    out = add_ratios(df)
    if out.empty:
        return out
    keys = out[group] if group else pd.Series(0, index=out.index)
    tot = out.groupby(keys)[["impressions", "clicks", "cost", "conversions"]].transform("sum")
    rest_clicks = tot["clicks"] - out["clicks"]
    rest_conv = tot["conversions"] - out["conversions"]
    tot_ctr = safe_div(tot["clicks"], tot["impressions"])
    tot_cvr = safe_div(tot["conversions"], tot["clicks"])
    tot_cpa = safe_div(tot["cost"], tot["conversions"])
    out["n_segments"] = out.groupby(keys)["clicks"].transform("size")
    out["cost_share"] = safe_div(out["cost"], tot["cost"])
    out["ctr_index"] = safe_div(out["ctr"], tot_ctr)
    out["cvr_index"] = safe_div(out["cvr"], tot_cvr)
    out["cpa_index"] = safe_div(out["cpa"], tot_cpa)
    out["cvr_rest"] = safe_div(rest_conv, rest_clicks)
    out["cvr_z"] = two_proportion_z(out["conversions"], out["clicks"], rest_conv, rest_clicks)
    out["ctr_z"] = two_proportion_z(out["clicks"], out["impressions"], tot["clicks"] - out["clicks"],
                                    tot["impressions"] - out["impressions"])
    out["expected_conversions"] = out["clicks"] * out["cvr_rest"]
    # Sugerowana korekta stawki: relacja CPA segmentu do CPA całości (zaokrąglona do 5 p.p.).
    adj = (safe_div(tot_cpa, out["cpa"]) - 1).clip(-0.9, 0.5)
    adj = adj.where(out["conversions"] > 0)  # bez konwersji nie sugerujemy konkretnej korekty
    out["bid_adjustment"] = (adj * 20).round() / 20
    return out


# --------------------------------------------------------------------------- budowa encji


def _mark(df: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["has_date"] = has_date(source)
    return df


def _agg(df: pd.DataFrame, keys: list[str], keep: tuple = ()) -> pd.DataFrame:
    """Agregacja po kluczach z zachowaniem tylko metryk i wskazanych atrybutów
    (bez "przypadkowych" wartości innych wymiarów, np. kampanii w raporcie urządzeń)."""
    keys = [k for k in keys if k in df.columns]
    cols = [c for c in df.columns
            if c in keys or c in ADDITIVE or c in SHARES or c in SCORES or c in keep or c == "date"]
    return metrics.aggregate(df[cols], keys)


def build_ad_groups(df: pd.DataFrame) -> pd.DataFrame:
    agg = _agg(df, ["campaign", "ad_group"], keep=("ad_group_status",))
    return _mark(segment_compare(agg), df)


def build_keywords(df: pd.DataFrame) -> pd.DataFrame:
    agg = _agg(df, ["campaign", "ad_group", "keyword", "match_type"],
               keep=("keyword_status", "expected_ctr", "ad_relevance", "landing_page_experience"))
    return _mark(segment_compare(agg), df)


def build_ads(df: pd.DataFrame) -> pd.DataFrame:
    keys = [k for k in ("campaign", "ad_group", "ad_id", "headline_1") if k in df.columns]
    agg = _agg(df, keys, keep=("ad_type", "ad_strength", "ad_status", "headline_2", "final_url"))
    agg["_grp"] = agg["campaign"].astype(str) + "␟" + agg["ad_group"].astype(str)
    out = segment_compare(agg, group="_grp")
    grp = out.groupby("_grp")
    out["ads_in_group"] = grp["clicks"].transform("size")
    out["ctr_group"] = safe_div(grp["clicks"].transform("sum"), grp["impressions"].transform("sum"))
    out["cvr_group"] = safe_div(grp["conversions"].transform("sum"), grp["clicks"].transform("sum"))
    name = out["headline_1"] if "headline_1" in out.columns else pd.Series("", index=out.index)
    ad_id = out["ad_id"] if "ad_id" in out.columns else pd.Series("", index=out.index)
    out["ad_name"] = name.where(name != "", "Reklama " + ad_id.astype(str))
    return _mark(out.drop(columns=["_grp"]), df)


def build_devices(df: pd.DataFrame) -> pd.DataFrame:
    keys = ["device", "device_label"]
    return _mark(segment_compare(_agg(df, keys)), df)


def build_time(df: pd.DataFrame) -> pd.DataFrame:
    parts = []
    if "day_of_week" in df.columns and df["day_of_week"].notna().any():
        dow = _agg(df.dropna(subset=["day_of_week"]), ["day_of_week", "day_of_week_label"])
        dow = dow.assign(slot_type="Dzień tygodnia", slot=dow["day_of_week_label"], slot_order=dow["day_of_week"])
        parts.append(dow)
    if "hour" in df.columns and df["hour"].notna().any():
        hr = _agg(df.dropna(subset=["hour"]), ["hour"])
        hr = hr.assign(slot_type="Godzina", slot=hr["hour"].astype(int).map(lambda h: f"{h:02d}:00–{h:02d}:59"),
                       slot_order=hr["hour"])
        parts.append(hr)
    if not parts:
        return pd.DataFrame()
    cols = ["slot_type", "slot", "slot_order", "impressions", "clicks", "cost", "conversions", "conversion_value"]
    frame = pd.concat([p[cols] for p in parts], ignore_index=True)
    return _mark(segment_compare(frame, group="slot_type"), df)


def build_locations(df: pd.DataFrame) -> pd.DataFrame:
    return _mark(segment_compare(_agg(df, ["location", "location_type"], keep=("country", "region"))), df)


def build_audiences(df: pd.DataFrame) -> pd.DataFrame:
    agg = _agg(df, ["segment_type", "segment"])
    return _mark(segment_compare(agg, group="segment_type"), df)


def build_landing_pages(df: pd.DataFrame) -> pd.DataFrame:
    agg = _agg(df, ["landing_page"])
    if "impressions" not in agg.columns:
        agg["impressions"] = 0.0
    return _mark(segment_compare(agg), df)


def build_conversion_actions(df: pd.DataFrame) -> pd.DataFrame:
    agg = _agg(df, ["conversion_action", "conversion_category", "is_micro"], keep=("include_in_conversions",))
    for col in ("conversions", "conversion_value"):
        if col not in agg.columns:
            agg[col] = 0.0
    agg["conv_share"] = safe_div(agg["conversions"], agg["conversions"].sum())
    agg["value_share"] = safe_div(agg["conversion_value"], agg["conversion_value"].sum())
    agg["value_per_conversion"] = safe_div(agg["conversion_value"], agg["conversions"])
    agg["has_value_column"] = "conversion_value" in df.columns and df["conversion_value"].sum() > 0
    return _mark(agg.sort_values("conversions", ascending=False).reset_index(drop=True), df)


def build_competitors(df: pd.DataFrame, own_is_fallback: float | None) -> pd.DataFrame:
    agg = _agg(df, ["competitor_domain", "is_self"])
    own = agg.loc[agg["is_self"], "impression_share"]
    own_is = float(own.iloc[0]) if len(own) and pd.notna(own.iloc[0]) else own_is_fallback
    agg["own_impression_share"] = own_is if own_is is not None else np.nan
    agg["is_gap"] = agg["impression_share"] - agg["own_impression_share"]
    return _mark(agg.sort_values("impression_share", ascending=False).reset_index(drop=True), df)


def campaign_impression_share(campaign_cur: pd.DataFrame) -> pd.DataFrame | None:
    cols = [c for c in IS_SHARES if c in campaign_cur.columns and campaign_cur[c].notna().any()]
    if not cols:
        return None
    agg = metrics.aggregate(campaign_cur[["campaign", "impressions"] + cols], ["campaign"])
    return agg[["campaign"] + cols]


BUILDERS = {
    "ad_groups": ("ad_group", build_ad_groups),
    "keywords": ("keyword", build_keywords),
    "ads": ("ad", build_ads),
    "devices": ("device", build_devices),
    "time": ("time_slot", build_time),
    "locations": ("location", build_locations),
    "audiences": ("audience", build_audiences),
    "landing_pages": ("landing_page", build_landing_pages),
    "conversion_actions": ("conversion_action", build_conversion_actions),
}


def critical_z(z_threshold: float, n_segments: pd.Series) -> pd.Series:
    """Próg |z| z poprawką Bonferroniego na liczbę porównywanych segmentów.

    ``z_threshold`` to próg dla pojedynczego porównania (1,96 ≈ α = 5%). Przy m segmentach
    porównujemy z progiem dla α/m – dzięki temu 24 godziny czy 16 województw nie dają
    "istotnych" różnic przypadkiem.
    """
    nd = NormalDist()
    alpha = 2 * (1 - nd.cdf(z_threshold))
    return n_segments.clip(lower=1).map(lambda m: nd.inv_cdf(1 - alpha / (2 * m)))


def build_entity_frames(
    datasets: dict[str, pd.DataFrame], period: Period, campaigns: list[str] | None,
    own_is_fallback: float | None = None, z_threshold: float = 1.96,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Buduje ramki encji dla raportów opcjonalnych. Zwraca (ramki, uwagi)."""
    frames: dict[str, pd.DataFrame] = {}
    notes: list[str] = []
    for key, (entity, builder) in BUILDERS.items():
        raw = datasets.get(key)
        if raw is None or raw.empty:
            continue
        label = REPORT_BY_KEY[key].label
        df = scope(raw, period, campaigns)
        if df is None or df.empty:
            notes.append(f"{label}: brak danych w wybranym okresie / kampaniach.")
            continue
        if not has_date(raw):
            notes.append(f"{label}: raport bez daty – analizowany za cały okres eksportu.")
        if campaigns and "campaign" not in raw.columns:
            notes.append(f"{label}: raport na poziomie konta – filtr kampanii nie ma zastosowania.")
        frame = builder(df)
        if frame is not None and not frame.empty:
            if "n_segments" in frame.columns:
                frame["z_crit"] = critical_z(z_threshold, frame["n_segments"])
            frames[entity] = frame
    raw = datasets.get("auction_insights")
    if raw is not None and not raw.empty:
        df = scope(raw, period, campaigns)
        if df is None or df.empty:
            notes.append("Auction Insights: brak danych w wybranym okresie / kampaniach.")
        else:
            if not has_date(raw):
                notes.append("Auction Insights: raport bez daty – analizowany za cały okres eksportu.")
            frames["competitor"] = build_competitors(df, own_is_fallback)
    return frames, notes
