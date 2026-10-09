"""Pokrycie danych, poziomy analizy i zasada "brak raportu = brak diagnozy"."""

import glob
from datetime import date

import pandas as pd
import pytest

from campaign_os.analysis import run_analysis
from campaign_os.config import SAMPLE_DIR, load_settings
from campaign_os.ingest import read_report_file
from campaign_os.metrics import Period
from campaign_os.rules import load_rules
from campaign_os.sem import analysis_level, coverage, critical_z, module_status, segment_compare

PERIOD = Period(date(2026, 9, 1), date(2026, 9, 30))


@pytest.fixture(scope="module")
def datasets():
    out = {}
    for f in glob.glob(str(SAMPLE_DIR / "*.csv")):
        res = read_report_file(f)
        out[res.report_type] = res.df
    return out


def analyse(datasets, keys=None, **kw):
    ds = {k: v for k, v in datasets.items() if keys is None or k in keys}
    c, t = ds.pop("campaign_daily", None), ds.pop("search_terms_daily", None)
    return run_analysis(c, t, PERIOD, load_settings()["thresholds"], load_rules(), extra=ds, **kw)


@pytest.fixture(scope="module")
def full(datasets):
    return analyse(datasets)


def test_coverage_lists_all_reports_in_order(datasets):
    items = coverage({"campaign_daily": datasets["campaign_daily"]})
    assert [i.label for i in items] == [
        "Campaign", "Ad Groups", "Keywords", "Search Terms", "Ads", "Devices", "Time", "Locations",
        "Landing Pages", "Conversions", "Auction Insights", "Audiences"]
    assert [i.present for i in items][:2] == [True, False]


def test_levels_full(full):
    assert all(info["reached"] for info in full.levels.values())
    assert full.rule_errors == []


def test_levels_basic_only(datasets):
    res = analyse(datasets, keys={"campaign_daily", "search_terms_daily"})
    assert res.levels["basic"]["reached"]
    assert not res.levels["advanced"]["reached"] and res.levels["advanced"]["available"] == 0
    # IS jest dostępny, bo raport kampanii zawiera kolumny Search IS
    assert [s.module.key for s in res.levels["full"]["modules"] if s.available] == ["impression_share"]


def test_no_diagnosis_without_report(datasets):
    res = analyse(datasets, keys={"campaign_daily", "search_terms_daily"})
    assert set(res.recommendations["entity"]) <= {"campaign", "search_term"}
    no_data = {rid for rid, st in res.rule_stats.items() if st.status == "no_data"}
    assert {"DEV_WEAK", "KW_LOW_QS", "CONV_MICRO_SHARE", "AI_HIGH_PRESSURE", "LOC_WEAK"} <= no_data


def test_quality_score_module_requires_qs_columns(datasets):
    kw = datasets["keywords"].drop(columns=["quality_score", "expected_ctr", "ad_relevance",
                                            "landing_page_experience"])
    statuses = {s.module.key: s for s in module_status({"keywords": kw})}
    assert statuses["keyword_performance"].available
    assert not statuses["quality_score"].available and "quality_score" in statuses["quality_score"].reason
    res = analyse({**datasets, "keywords": kw})
    assert res.rule_stats["KW_LOW_QS"].status == "skipped"
    assert not res.recommendations["rule_id"].eq("KW_LOW_QS").any()


def test_expected_patterns_detected_with_evidence(full):
    recs = full.recommendations
    found = set(recs["rule_id"])
    assert {
        "ST_WASTED_SPEND", "ST_HIGH_PERFORMER", "CMP_NO_CONVERSIONS", "IS_LOST_BUDGET_PROFITABLE", "IS_LOST_RANK",
        "KW_LOW_QS", "KW_EXPECTED_CTR_BELOW", "AD_LOW_CTR", "DEV_WEAK", "LP_LOW_CVR", "LP_MOBILE_UNFRIENDLY",
        "CONV_MICRO_SHARE", "CONV_NO_VALUE", "AI_HIGH_PRESSURE", "AUD_STRONG", "AUD_WEAK",
    } <= found
    # EVIDENCE: każda diagnoza ma wypełnione liczby, źródło i okres (bez niewypełnionych pól szablonu)
    assert recs["evidence"].str.len().gt(20).all()
    assert not recs["evidence"].str.contains(r"\{").any()
    assert recs["source"].ne("").all() and recs["data_scope"].ne("").all()
    detail = recs.set_index("rule_id")
    assert detail.loc["DEV_WEAK", "entity_name"] == "Telefony komórkowe"
    assert detail.loc["AI_HIGH_PRESSURE", "data_scope"] == "okres eksportu (raport bez daty)"


def test_segment_rules_respect_sample(datasets):
    # Przy bardzo wysokim progu próby reguły segmentowe nie mogą rekomendować zmian.
    th = {**load_settings()["thresholds"], "min_clicks": 10**7, "min_conversions": 10**6}
    ds = dict(datasets)
    c, t = ds.pop("campaign_daily"), ds.pop("search_terms_daily")
    res = run_analysis(c, t, PERIOD, th, load_rules(), extra=ds)
    segment = res.recommendations["entity"].isin(["device", "time_slot", "location", "audience", "landing_page"])
    assert not segment.any()
    assert res.rule_stats["DEV_WEAK"].insufficient >= 1


def test_segment_compare_z_test():
    df = pd.DataFrame({"device": ["a", "b"], "impressions": [10000.0, 10000.0], "clicks": [1000.0, 1000.0],
                       "cost": [1000.0, 1000.0], "conversions": [20.0, 60.0], "conversion_value": [0.0, 0.0]})
    out = segment_compare(df).set_index("device")
    assert out.loc["a", "cvr_z"] < -4 and out.loc["b", "cvr_z"] > 4
    assert out.loc["a", "expected_conversions"] == pytest.approx(60.0)
    assert out.loc["a", "cpa_index"] == pytest.approx(2.0)
    assert out.loc["a", "bid_adjustment"] == pytest.approx(-0.5)


def test_bonferroni_threshold_grows_with_segments():
    z = critical_z(1.96, pd.Series([1, 3, 24]))
    assert z.iloc[0] == pytest.approx(1.96, abs=0.01)
    assert z.iloc[0] < z.iloc[1] < z.iloc[2]
    assert z.iloc[2] == pytest.approx(3.08, abs=0.02)


def test_campaign_filter_applies_to_optional_reports(datasets):
    res = analyse(datasets, campaigns_filter=["Search | Brand"])
    assert set(res.frames["ad_group"]["campaign"]) == {"Search | Brand"}
    assert any("poziomie konta" in n for n in res.sem_notes)  # raport czasu/lokalizacji nie ma kampanii
