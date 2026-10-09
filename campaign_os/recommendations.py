"""Budowa kontekstu dla Rule Engine i priorytetyzacja rekomendacji."""

from __future__ import annotations

from typing import Any

import pandas as pd

from campaign_os.metrics import safe_div
from campaign_os.rules import SEVERITIES, RuleSet, run_rules

CATEGORY_LABELS = {
    "wasted_spend": "Wasted spend",
    "high_performer": "High performers",
    "efficiency": "Efektywność (CPA)",
    "trend": "Zmiany vs poprzedni okres",
    "growth": "Możliwości wzrostu",
    "relevance": "Trafność",
    "other": "Inne",
}


def build_context(
    account: dict[str, float],
    target_cpa: float,
    thresholds: dict[str, Any],
    period_days: int,
    currency: str,
) -> dict[str, Any]:
    return {
        "account_cost": account["cost"],
        "account_cpa": account["cpa"],
        "account_ctr": account["ctr"],
        "account_cvr": account["cvr"],
        "account_cpc": account["cpc"],
        "account_roas": account["roas"],
        "target_cpa": float(target_cpa or 0.0),
        "wasted_min_cost": float(thresholds.get("wasted_min_cost", 30.0)),
        "wasted_min_clicks": float(thresholds.get("wasted_min_clicks", 5)),
        "period_days": period_days,
        "currency": currency,
    }


def prepare_campaign_frame(campaigns: pd.DataFrame, target_cpa: float) -> pd.DataFrame:
    if campaigns is None or campaigns.empty:
        return campaigns
    out = campaigns.copy()
    out["cost_share"] = safe_div(out["cost"], out["cost"].sum())
    out["cpa_vs_target"] = safe_div(out["cpa"], target_cpa) if target_cpa else float("nan")
    return out


def generate(
    ruleset: RuleSet,
    campaigns: pd.DataFrame | None,
    terms: pd.DataFrame | None,
    context: dict[str, Any],
) -> tuple[pd.DataFrame, list[str]]:
    """Uruchamia reguły i zwraca posortowane rekomendacje (najważniejsze na górze)."""
    frames = {}
    if campaigns is not None and not campaigns.empty:
        frames["campaign"] = prepare_campaign_frame(campaigns, context.get("target_cpa", 0))
    if terms is not None and not terms.empty:
        frames["search_term"] = terms
    findings, errors = run_rules(ruleset, frames, context)
    return prioritize(findings), errors


def prioritize(findings: pd.DataFrame) -> pd.DataFrame:
    if findings.empty:
        return findings.assign(priority=pd.Series(dtype=float))
    out = findings.copy()
    sev = out["severity"].map(SEVERITIES).fillna(1)
    impact = out["impact"].clip(lower=0).fillna(0)
    # Najpierw severity, w ramach severity – kwota wpływu.
    out["priority"] = sev * 1_000_000 + impact.clip(upper=999_999)
    out = out.sort_values(["priority", "cost"], ascending=False).reset_index(drop=True)
    out.insert(0, "no", range(1, len(out) + 1))
    return out


def summarize(findings: pd.DataFrame) -> pd.DataFrame:
    """Podsumowanie po kategoriach: liczba rekomendacji i łączny wpływ."""
    if findings.empty:
        return pd.DataFrame(columns=["category", "label", "count", "impact"])
    out = (
        findings.groupby("category")
        .agg(count=("rule_id", "size"), impact=("impact", lambda s: s.clip(lower=0).sum()))
        .reset_index()
    )
    out["label"] = out["category"].map(CATEGORY_LABELS).fillna(out["category"])
    return out.sort_values("impact", ascending=False)[["category", "label", "count", "impact"]]
