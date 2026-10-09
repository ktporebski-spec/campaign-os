from datetime import date

import pandas as pd
import pytest

from campaign_os import metrics
from campaign_os.analysis import run_analysis
from campaign_os.config import SAMPLE_DIR, load_settings
from campaign_os.ingest import read_report_file
from campaign_os.metrics import Period
from campaign_os.rules import load_rules
from campaign_os.search_terms import SearchTermThresholds, aggregate_terms, classify_terms


@pytest.fixture(scope="module")
def sample():
    c = read_report_file(SAMPLE_DIR / "campaign_daily.csv").df
    t = read_report_file(SAMPLE_DIR / "search_terms_daily.csv").df
    return c, t


def test_previous_period_has_same_length_and_is_adjacent():
    p = Period(date(2026, 9, 1), date(2026, 9, 30))
    prev = metrics.previous_period(p)
    assert prev == Period(date(2026, 8, 2), date(2026, 8, 31))
    assert prev.days == p.days


def test_totals_and_ratios():
    df = pd.DataFrame({"cost": [100.0, 0.0], "impressions": [1000, 0], "clicks": [50, 0],
                       "conversions": [5.0, 0.0], "conversion_value": [400.0, 0.0]})
    t = metrics.totals(df)
    assert t["ctr"] == 0.05 and t["cpc"] == 2.0 and t["cvr"] == 0.1 and t["cpa"] == 20.0 and t["roas"] == 4.0
    r = metrics.add_ratios(df)
    assert pd.isna(r.loc[1, "cpa"]) and pd.isna(r.loc[1, "ctr"])


def test_pct_change_handles_zero_and_nan():
    assert metrics.pct_change(120, 100) == pytest.approx(0.2)
    assert pd.isna(metrics.pct_change(10, 0))
    assert pd.isna(metrics.pct_change(10, float("nan")))


def test_classify_terms():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-01"] * 3),
        "campaign": ["A"] * 3, "ad_group": ["G"] * 3,
        "search_term": ["waste", "star", "meh"],
        "match_type": ["Exact"] * 3,
        "impressions": [100, 100, 100], "clicks": [10, 10, 2],
        "cost": [50.0, 40.0, 5.0], "conversions": [0.0, 4.0, 0.0], "conversion_value": [0.0, 0.0, 0.0],
    })
    th = SearchTermThresholds(target_cpa=20.0, wasted_min_cost=30, wasted_min_clicks=5,
                              high_performer_min_conversions=2, high_performer_max_cpa_ratio=0.8)
    out = classify_terms(aggregate_terms(df), th).set_index("search_term")
    assert out.loc["waste", "segment"] == "Wasted spend"
    assert out.loc["star", "segment"] == "High performer"  # CPA 10 <= 16
    assert out.loc["meh", "segment"] == "Bez konwersji"


def test_full_pipeline_on_sample(sample):
    c, t = sample
    settings = load_settings()
    res = run_analysis(c, t, Period(date(2026, 9, 1), date(2026, 9, 30)), settings["thresholds"], load_rules())
    assert res.rule_errors == []
    assert res.prev_coverage_days == 30
    assert res.kpis.loc["cost", "current"] == pytest.approx(c[c["date"] >= "2026-09-01"]["cost"].sum())
    ids = set(res.recommendations["rule_id"])
    # Wzorce zaszyte w danych przykładowych muszą zostać wykryte.
    assert {"ST_WASTED_SPEND", "ST_HIGH_PERFORMER", "CMP_CPA_INCREASE", "CMP_NO_CONVERSIONS", "CMP_CTR_DROP"} <= ids
    wasted = set(res.terms.loc[res.terms["is_wasted"], "search_term"])
    assert {"darmowe buty do biegania", "buty trailowe outlet wyprzedaż"} <= wasted
    # Priorytety: wysokie przed średnimi.
    sev = res.recommendations["severity"].tolist()
    assert sev.index("medium") > max(i for i, s in enumerate(sev) if s == "high")


def test_pipeline_without_previous_data(sample):
    c, t = sample
    res = run_analysis(c, t, Period(date(2026, 8, 2), date(2026, 8, 31)), {}, load_rules())
    assert res.prev_coverage_days == 0
    assert res.kpis["previous"].isna().all()
    assert any("poprzedniego okresu" in n for n in res.notes)


def test_pipeline_with_search_terms_only(sample):
    _, t = sample
    res = run_analysis(None, t, Period(date(2026, 9, 1), date(2026, 9, 30)), {}, load_rules())
    assert res.kpis.loc["cost", "current"] > 0
    assert any("campaign_daily" in n for n in res.notes)


def test_campaign_filter(sample):
    c, t = sample
    res = run_analysis(c, t, Period(date(2026, 9, 1), date(2026, 9, 30)), {}, load_rules(),
                       campaigns_filter=["Search | Brand"])
    assert res.campaigns["campaign"].tolist() == ["Search | Brand"]
    assert set(res.terms["campaign"]) == {"Search | Brand"}
