"""Rozpoznawanie i normalizacja opcjonalnych raportów SEM (PL/EN)."""

import pandas as pd
import pytest

from campaign_os.config import SAMPLE_DIR
from campaign_os.ingest import IngestError, detect_report_type, parse_share, read_report, read_report_file
from campaign_os.metrics import aggregate, safe_div
from campaign_os.schema import COVERAGE_ORDER, REPORT_BY_KEY

SAMPLE_TYPES = {
    "campaign_daily.csv": "campaign_daily",
    "search_terms_daily.csv": "search_terms_daily",
    "ad_groups.csv": "ad_groups",
    "keywords.csv": "keywords",
    "ads.csv": "ads",
    "devices.csv": "devices",
    "hour_of_day.csv": "time",
    "locations.csv": "locations",
    "landing_pages.csv": "landing_pages",
    "conversion_actions.csv": "conversion_actions",
    "auction_insights.csv": "auction_insights",
    "audiences.csv": "audiences",
}


def test_sample_data_covers_every_report_type():
    assert set(SAMPLE_TYPES.values()) == set(COVERAGE_ORDER)


@pytest.mark.parametrize("filename,expected", SAMPLE_TYPES.items())
def test_sample_files_are_detected(filename, expected):
    res = read_report_file(SAMPLE_DIR / filename)
    assert res.report_type == expected
    assert not res.df.empty
    if expected != "auction_insights":  # raport statystyk aukcji eksportujemy bez daty
        assert res.df["date"].nunique() >= 30


# Minimalne nagłówki (PL, EN) dla każdego raportu opcjonalnego.
MINIMAL = {
    "ad_groups": ("Kampania;Grupa reklam;Wyświetlenia;Kliknięcia;Koszt\nA;G1;100;10;12,50",
                  "Campaign,Ad group,Impressions,Clicks,Cost\nA,G1,100,10,12.50"),
    "keywords": ("Kampania;Grupa reklam;Słowo kluczowe;Wyświetlenia;Kliknięcia;Koszt\nA;G1;[buty];100;10;12,50",
                 "Campaign,Ad group,Keyword,Impr.,Clicks,Cost\nA,G1,buty,100,10,12.50"),
    "ads": ("Kampania;Grupa reklam;Nagłówek 1;Wyświetlenia;Kliknięcia;Koszt\nA;G1;Buty;100;10;12,50",
            "Campaign,Ad group,Ad ID,Impressions,Clicks,Cost\nA,G1,123,100,10,12.50"),
    "devices": ("Urządzenie;Wyświetlenia;Kliknięcia;Koszt\nTelefony komórkowe;100;10;12,50",
                "Device,Impressions,Clicks,Cost\nMobile phones,100,10,12.50"),
    "time": ("Dzień tygodnia;Godzina;Wyświetlenia;Kliknięcia;Koszt\nponiedziałek;13;100;10;12,50",
             "Hour of day,Impressions,Clicks,Cost\n13,100,10,12.50"),
    "locations": ("Region (lokalizacja użytkownika);Wyświetlenia;Kliknięcia;Koszt\nMazowieckie;100;10;12,50",
                  "City,Impressions,Clicks,Cost\nWarsaw,100,10,12.50"),
    "landing_pages": ("Strona docelowa;Kliknięcia;Koszt\nhttps://x.pl/;10;12,50",
                      "Landing page,Clicks,Cost\nhttps://x.pl/,10,12.50"),
    "conversion_actions": ("Działanie powodujące konwersję;Konwersje\nZakup;3,00",
                           "Conversion action,Conversions\nPurchase,3.00"),
    "auction_insights": ("Domena wyświetlanego URL-a;Udział w wyświetleniach\nTy;45,00%",
                         "Display URL domain,Impr. share\nYou,45.00%"),
    "audiences": ("Wiek;Płeć;Wyświetlenia;Kliknięcia;Koszt\n25-34;Kobiety;100;10;12,50",
                  "Audience segment,Impressions,Clicks,Cost\nIn-market: Shoes,100,10,12.50"),
}


@pytest.mark.parametrize("report", MINIMAL)
@pytest.mark.parametrize("lang", [0, 1], ids=["pl", "en"])
def test_minimal_optional_reports_pl_en(report, lang):
    res = read_report(MINIMAL[report][lang].encode("utf-8"))
    assert res.report_type == report
    assert any("Raport nie zawiera daty" in w for w in res.warnings)
    assert len(res.df) == 1


@pytest.mark.parametrize("columns,expected", [
    (["date", "campaign", "ad_group", "keyword", "search_term"], "search_terms_daily"),
    (["campaign", "ad_group", "keyword", "quality_score"], "keywords"),
    (["date", "campaign", "device"], "devices"),
    (["campaign", "ad_group", "headline_1", "final_url"], "ads"),
    (["campaign", "ad_group", "keyword", "landing_page_experience"], "keywords"),
    (["date", "campaign", "ad_group"], "ad_groups"),
    (["date", "campaign", "search_impression_share"], "campaign_daily"),
    (["date", "conversion_action", "campaign", "device"], "conversion_actions"),
    (["competitor_domain", "impression_share", "campaign"], "auction_insights"),
    (["landing_page", "device"], "landing_pages"),
    (["date", "hour"], "time"),
    (["gender", "age_range"], "audiences"),
])
def test_detection_order(columns, expected):
    assert detect_report_type(columns) == expected


def test_optional_report_missing_required_column():
    with pytest.raises(IngestError, match="Urządzenia: brak wymaganych kolumn: cost"):
        read_report("Device,Impressions,Clicks\nMobile phones,100,10\n")


def test_parse_share_variants():
    assert parse_share(pd.Series(["45,23%", "< 10%", "> 90%", "--"]), "pl").round(4).tolist()[:3] == [0.4523, 0.1, 0.9]
    assert parse_share(pd.Series(["0.45", "0.2"]), "en").tolist() == [0.45, 0.2]


def test_keyword_quality_score_parsing():
    text = (
        "Słowo kluczowe;Kampania;Grupa reklam;Wyświetlenia;Kliknięcia;Koszt;Wynik jakości;Oczekiwany CTR;"
        "Trafność reklamy;Jakość strony docelowej;Udział w wyświetleniach w sieci wyszukiwania;"
        "Utracony udział w wyświetleniach w sieci wyszukiwania (ranking)\n"
        "[buty];A;G;100;10;5,00;4;Poniżej średniej;Średnia;Powyżej średniej;< 10%;85,50%\n"
        "\"nowe\";A;G;10;1;1,00;--;--;--;--;--;--\n"
    )
    df = read_report(text.encode("utf-8")).df.set_index("keyword")
    assert df.loc["buty", "quality_score"] == 4
    assert (df.loc["buty", "expected_ctr"], df.loc["buty", "ad_relevance"], df.loc["buty", "landing_page_experience"]) \
        == ("below", "average", "above")
    assert df.loc["buty", "search_impression_share"] == 0.1
    assert df.loc["buty", "search_lost_is_rank"] == pytest.approx(0.855)
    assert pd.isna(df.loc["nowe", "quality_score"])  # "--" to brak danych, nie zero


def test_device_time_and_location_normalization():
    dev = read_report("Device,Impressions,Clicks,Cost\nMobile phones,1,1,1\nKomputery,1,1,1\nTV screens,1,1,1\n").df
    assert sorted(dev["device"]) == ["desktop", "mobile", "tv"]
    tm = read_report("Day,Hour of day,Impressions,Clicks,Cost\n2026-09-07,13:00,1,1,1\n2026-09-08,7,1,1,1\n").df
    assert tm["hour"].tolist() == [13, 7]
    assert tm["day_of_week"].tolist() == [1, 2]  # wyliczony z daty: pn, wt
    assert tm["day_of_week_label"].tolist() == ["Poniedziałek", "Wtorek"]
    loc = read_report("Kraj/region;Miasto;Wyświetlenia;Kliknięcia;Koszt\nPolska;Kraków;1;1;1\nPolska;;1;1;1\n").df
    assert sorted(loc["location"]) == ["Kraków", "Polska"]


def test_conversion_actions_micro_flag_and_auction_self_row():
    conv = read_report("Działanie powodujące konwersję;Kategoria działania powodującego konwersję;Konwersje\n"
                       "Zakup;Zakup;10\nWizyta /kontakt;Wyświetlenie strony;5\n").df.set_index("conversion_action")
    assert not conv.loc["Zakup", "is_micro"] and conv.loc["Wizyta /kontakt", "is_micro"]
    ai = read_report("Display URL domain,Impr. share,Overlap rate\nYou,40%,--\nrival.pl,< 10%,20%\n").df
    assert ai.set_index("competitor_domain").loc["You", "is_self"]
    assert ai.set_index("competitor_domain").loc["rival.pl", "impression_share"] == 0.1


def test_audiences_build_segment_from_demographics():
    df = read_report("Wiek;Płeć;Wyświetlenia;Kliknięcia;Koszt\n25-34;Kobiety;1;1;1\n").df
    assert df.loc[0, "segment"] == "25-34 / Kobiety"
    assert df.loc[0, "segment_type"] == "Wiek × Płeć"


def test_aggregate_weights_impression_share_by_eligible_impressions():
    df = pd.DataFrame({"campaign": ["A", "A"], "impressions": [100.0, 100.0],
                       "search_impression_share": [0.5, 0.25], "quality_score": [4.0, 8.0]})
    out = aggregate(df, ["campaign"])
    # kwalifikujące się: 200 + 400 → IS = 200 / 600
    assert out.loc[0, "search_impression_share"] == pytest.approx(1 / 3)
    assert out.loc[0, "quality_score"] == 6.0
    assert out.loc[0, "impressions"] == 200


def test_safe_div_series_by_scalar_keeps_all_rows():
    # regresja: wcześniej skalar był zamieniany na 1-elementową serię i wyniki poza 1. wierszem były NaN
    assert safe_div(pd.Series([1.0, 2.0, 3.0]), 2.0).tolist() == [0.5, 1.0, 1.5]
    assert safe_div(pd.Series([1.0]), 0).isna().all()


def test_every_report_spec_is_documented():
    for key in COVERAGE_ORDER:
        spec = REPORT_BY_KEY[key]
        assert spec.required and spec.export_path and spec.description
