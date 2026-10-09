"""Pipeline analizy: od znormalizowanych danych do KPI, haseł i rekomendacji."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from campaign_os import metrics, recommendations, search_terms
from campaign_os.metrics import Period
from campaign_os.rules import RuleSet


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


def campaign_daily_from_terms(terms: pd.DataFrame) -> pd.DataFrame:
    """Gdy brak raportu kampanii – przybliżenie z raportu search terms."""
    return terms.groupby(["date", "campaign"], as_index=False)[metrics.BASE_METRICS].sum()


def run_analysis(
    campaign_df: pd.DataFrame | None,
    terms_df: pd.DataFrame | None,
    period: Period,
    thresholds: dict[str, Any],
    ruleset: RuleSet,
    currency: str = "PLN",
    campaigns_filter: list[str] | None = None,
) -> AnalysisResult:
    notes: list[str] = []
    if campaign_df is None or campaign_df.empty:
        if terms_df is None or terms_df.empty:
            raise ValueError("Brak danych do analizy.")
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

    context = recommendations.build_context(account, target_cpa, thresholds, period.days, currency)
    recs, rule_errors = recommendations.generate(ruleset, campaigns, terms, context)

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
    )
