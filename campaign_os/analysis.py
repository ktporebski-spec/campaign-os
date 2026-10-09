"""Pipeline analizy: od znormalizowanych raportów do KPI, encji SEM i rekomendacji.

Dane żyją wyłącznie w pamięci na czas bieżącej analizy (brak warstwy persistence).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from campaign_os import metrics, recommendations, search_terms, sem
from campaign_os.metrics import Period, safe_div
from campaign_os.rules import RuleSet, RuleStat
from campaign_os.schema import IS_SHARES


@dataclass
class AnalysisResult:
    period: Period
    prev_period: Period
    kpis: pd.DataFrame
    daily: pd.DataFrame
    daily_prev: pd.DataFrame
    campaigns: pd.DataFrame
    terms: pd.DataFrame | None
    terms_summary: dict[str, float]
    thresholds: search_terms.SearchTermThresholds
    target_cpa_source: str
    recommendations: pd.DataFrame
    rule_errors: list[str]
    context: dict[str, Any]
    prev_coverage_days: int
    notes: list[str] = field(default_factory=list)
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    coverage: list[sem.CoverageItem] = field(default_factory=list)
    modules: list[sem.ModuleStatus] = field(default_factory=list)
    levels: dict[str, dict] = field(default_factory=dict)
    rule_stats: dict[str, RuleStat] = field(default_factory=dict)
    sem_notes: list[str] = field(default_factory=list)


def campaign_daily_from_terms(terms: pd.DataFrame) -> pd.DataFrame:
    """Gdy brak raportu kampanii – przybliżenie z raportu search terms."""
    return terms.groupby(["date", "campaign"], as_index=False)[metrics.BASE_METRICS].sum()


def _add_impression_share(campaigns: pd.DataFrame, cur_c: pd.DataFrame) -> pd.DataFrame:
    is_frame = sem.campaign_impression_share(cur_c)
    if is_frame is None:
        return campaigns
    out = campaigns.merge(is_frame, on="campaign", how="left")
    if "search_lost_is_budget" in out.columns and "search_impression_share" in out.columns:
        # Szacunek konwersji utraconych przez budżet przy niezmienionym CVR.
        out["lost_budget_conversions"] = out["conversions"] * safe_div(
            out["search_lost_is_budget"], out["search_impression_share"])
    return out


def run_analysis(
    campaign_df: pd.DataFrame | None,
    terms_df: pd.DataFrame | None,
    period: Period,
    thresholds: dict[str, Any],
    ruleset: RuleSet,
    currency: str = "PLN",
    campaigns_filter: list[str] | None = None,
    extra: dict[str, pd.DataFrame] | None = None,
) -> AnalysisResult:
    """``extra`` – raporty opcjonalne {klucz_raportu: DataFrame} (ad_groups, keywords, ads…)."""
    notes: list[str] = []
    datasets = {k: v for k, v in (extra or {}).items() if v is not None and not v.empty}
    if campaign_df is not None and not campaign_df.empty:
        datasets["campaign_daily"] = campaign_df
    if terms_df is not None and not terms_df.empty:
        datasets["search_terms_daily"] = terms_df
    coverage_items = sem.coverage(datasets)
    module_statuses = sem.module_status(datasets)

    if campaign_df is None or campaign_df.empty:
        if terms_df is None or terms_df.empty:
            raise ValueError("Brak danych do analizy: wgraj co najmniej raport kampanii lub search terms.")
        campaign_df = campaign_daily_from_terms(terms_df)
        notes.append(
            "Brak raportu campaign_daily – KPI policzono z raportu search terms "
            "(nie obejmuje ruchu bez haseł, np. PMax/Display)."
        )

    if campaigns_filter:
        campaign_df = campaign_df[campaign_df["campaign"].isin(campaigns_filter)]
        if terms_df is not None:
            terms_df = terms_df[terms_df["campaign"].isin(campaigns_filter)]

    prev = metrics.previous_period(period)
    cur_c = metrics.filter_period(campaign_df, period)
    prev_c = metrics.filter_period(campaign_df, prev)
    prev_cov = metrics.coverage_days(campaign_df, prev)
    if prev_cov == 0:
        notes.append(f"Brak danych dla poprzedniego okresu ({prev.label()}) – porównanie niedostępne.")
        prev_c = prev_c.iloc[0:0]
    elif prev_cov < prev.days:
        notes.append(
            f"Poprzedni okres ({prev.label()}) ma dane tylko dla {prev_cov} z {prev.days} dni – "
            "porównanie może być zaniżone."
        )

    kpis = metrics.compare_totals(cur_c, prev_c)
    account = metrics.totals(cur_c)
    daily = metrics.daily_series(cur_c, period)
    daily_prev = metrics.daily_series(prev_c, prev)
    campaigns = metrics.entity_comparison(cur_c, prev_c, ["campaign"])
    campaigns = _add_impression_share(campaigns, cur_c)
    # Istotność zmiany CVR vs poprzedni okres (test z dla dwóch proporcji).
    campaigns["cvr_change_z"] = sem.two_proportion_z(
        campaigns["conversions"], campaigns["clicks"],
        campaigns["conversions_prev"].astype(float).fillna(0), campaigns["clicks_prev"].astype(float).fillna(0))

    target_cpa = float(thresholds.get("target_cpa") or 0)
    target_source = "ustawienia"
    if target_cpa <= 0:
        target_cpa = account["cpa"] if pd.notna(account["cpa"]) else 0.0
        target_source = "średni CPA konta"
    th = search_terms.SearchTermThresholds.from_settings({**thresholds, "target_cpa": target_cpa}, account["cpa"])

    terms = None
    terms_sum: dict[str, float] = search_terms.summary(pd.DataFrame())
    if terms_df is not None and not terms_df.empty:
        cur_t = metrics.filter_period(terms_df, period)
        terms = search_terms.classify_terms(search_terms.aggregate_terms(cur_t), th)
        terms_sum = search_terms.summary(terms)

    # Udział w wyświetleniach konta (do porównań w Auction Insights, gdy brak wiersza "Ty").
    own_is = None
    if "search_impression_share" in cur_c.columns and cur_c["search_impression_share"].notna().any():
        acc_is = metrics.aggregate(cur_c[["impressions"] + [c for c in IS_SHARES if c in cur_c.columns]], [])
        own_is = float(acc_is["search_impression_share"].iloc[0])

    frames, sem_notes = sem.build_entity_frames(
        datasets, period, campaigns_filter, own_is_fallback=own_is,
        z_threshold=float(thresholds.get("z_threshold", 1.96)))
    frames["campaign"] = campaigns
    if terms is not None:
        frames["search_term"] = terms

    context = recommendations.build_context(account, target_cpa, thresholds, period.days, currency)
    context["period_label"] = period.label()
    context["account_search_is"] = own_is if own_is is not None else float("nan")
    stats: dict[str, RuleStat] = {}
    recs, rule_errors = recommendations.generate(ruleset, frames, context, stats)
    frames["campaign"] = recommendations.prepare_campaign_frame(campaigns, target_cpa)

    return AnalysisResult(
        period=period,
        prev_period=prev,
        kpis=kpis,
        daily=daily,
        daily_prev=daily_prev,
        campaigns=campaigns,
        terms=terms,
        terms_summary=terms_sum,
        thresholds=th,
        target_cpa_source=target_source,
        recommendations=recs,
        rule_errors=rule_errors,
        context=context,
        prev_coverage_days=prev_cov,
        notes=notes,
        frames=frames,
        coverage=coverage_items,
        modules=module_statuses,
        levels=sem.analysis_level(module_statuses),
        rule_stats=stats,
        sem_notes=sem_notes,
    )
