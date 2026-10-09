import pandas as pd
import pytest

from campaign_os.config import SAMPLE_DIR
from campaign_os.ingest import (
    CAMPAIGN_DAILY, MISSING_DATE_MESSAGE, SEARCH_TERMS, IngestError, detect_report_type, map_columns,
    normalize_header, parse_dates, parse_numeric, read_report, read_report_file,
)

PL_CAMPAIGN = (
    "Raport kampanii\n"
    "1 wrz 2026 - 2 wrz 2026\n"
    "Dzień,Kampania,Wyświetl.,Kliknięcia,Koszt,Konwersje,Wartość konw.,CTR\n"
    '2026-09-01,Kampania A,"1 234",56,"123,45","2,00","500,00","4,54%"\n'
    "2026-09-02,Kampania A,1000,40,\"80,00\",0,0,\"4,00%\"\n"
    'Razem: konto,,"2 234",96,"203,45","2,00","500,00","4,30%"\n'
)

EN_TERMS = (
    "Search terms report\n"
    "Search term;Match type;Campaign;Ad group;Day;Impr.;Clicks;Cost;Conversions\n"
    "Running Shoes;Exact match;Camp B;AG 1;Sep 1, 2026;1,234;50;1,050.50;3.00\n"
    "free shoes;Broad match;Camp B;AG 1;Sep 2, 2026;300;10;--;0\n"
    "Total: Account;;;;;1,534;60;1,050.50;3.00\n"
)


def test_normalize_header_ignores_case_diacritics_and_punctuation():
    assert normalize_header("Wyświetl.") == normalize_header("wyswietl")
    assert normalize_header("Łączna wartość konw.") == "laczna wartosc konw"


def test_parse_numeric_pl_and_en_formats():
    pl = parse_numeric(pd.Series(["1 234,56 zł", "12,5", "--", "", "(3,10)"]), "pl")
    assert pl.tolist()[:2] == [1234.56, 12.5]
    assert pl.isna().tolist()[2:4] == [True, True]
    assert pl.iloc[4] == -3.10
    en = parse_numeric(pd.Series(["1,234.56", "1,234", "12.5%", "$7.00"]), "en")
    assert en.tolist() == [1234.56, 1234.0, 12.5, 7.0]


def test_parse_numeric_detects_decimal_comma_regardless_of_language():
    assert parse_numeric(pd.Series(["1.234,50", "10,25"]), "en").tolist() == [1234.5, 10.25]


@pytest.mark.parametrize("values", [
    ["2026-09-01", "2026-09-30"],
    ["01.09.2026", "30.09.2026"],
    ["Sep 1, 2026", "Sep 30, 2026"],
    ["1 wrz 2026", "30 wrz 2026"],
])
def test_parse_dates_formats(values):
    parsed = parse_dates(pd.Series(values))
    assert parsed.tolist() == [pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-30")]


def test_read_polish_campaign_report_with_preamble_and_totals():
    res = read_report(PL_CAMPAIGN.encode("utf-8"))
    assert res.report_type == CAMPAIGN_DAILY
    assert res.language == "pl"
    assert len(res.df) == 2
    assert res.df["impressions"].sum() == 2234
    assert res.df["cost"].sum() == pytest.approx(203.45)
    assert "CTR" in res.ignored_columns
    assert any("podsumowań" in w for w in res.warnings)


def test_read_english_search_terms_semicolon_separated():
    res = read_report(EN_TERMS.encode("utf-8"))
    assert res.report_type == SEARCH_TERMS
    assert res.language == "en"
    assert res.df["search_term"].tolist() == ["running shoes", "free shoes"]  # lower-case
    assert res.df["impressions"].tolist() == [1234, 300]
    assert res.df["cost"].tolist() == [1050.5, 0.0]


def test_read_utf16_tab_separated_export():
    tsv = (
        "Dzień\tKampania\tWyświetlenia\tKliknięcia\tKoszt\tKonwersje\n"
        "2026-09-01\tKampania A\t1 234\t56\t123,45\t2\n"
    )
    res = read_report(tsv.encode("utf-16"))
    assert res.df.loc[0, "cost"] == pytest.approx(123.45)
    assert res.df.loc[0, "impressions"] == 1234


def test_cp1250_encoding():
    text = "Dzień;Kampania;Wyświetlenia;Kliknięcia;Koszt\n2026-09-01;Żółta;10;1;2,50\n"
    res = read_report(text.encode("cp1250"))
    assert res.df.loc[0, "campaign"] == "Żółta"


def test_duplicates_are_aggregated():
    text = (
        "Day,Campaign,Impressions,Clicks,Cost\n"
        "2026-09-01,A,10,1,1.00\n"
        "2026-09-01,A,20,2,2.00\n"
    )
    res = read_report(text)
    assert len(res.df) == 1
    assert res.df.loc[0, "clicks"] == 3


def test_missing_conversions_defaults_to_zero_with_warning():
    res = read_report("Day,Campaign,Impressions,Clicks,Cost\n2026-09-01,A,10,1,1.00\n")
    assert res.df.loc[0, "conversions"] == 0
    assert any("conversions" in w for w in res.warnings)


def test_cost_micros_is_converted():
    res = read_report("segments.date,campaign.name,metrics.impressions,metrics.clicks,metrics.cost_micros\n"
                      "2026-09-01,A,10,1,2500000\n")
    assert res.df.loc[0, "cost"] == pytest.approx(2.5)


def test_unrecognized_file_raises():
    with pytest.raises(IngestError):
        read_report("foo,bar,baz\n1,2,3\n")


def test_missing_required_column_raises():
    with pytest.raises(IngestError, match="cost"):
        read_report("Day,Campaign,Impressions,Clicks\n2026-09-01,A,10,1\n")


def test_expected_type_mismatch_raises():
    with pytest.raises(IngestError):
        read_report(EN_TERMS, expected_type=CAMPAIGN_DAILY)


def test_sample_files_cover_at_least_30_days():
    for name, rtype in (("campaign_daily", CAMPAIGN_DAILY), ("search_terms_daily", SEARCH_TERMS)):
        res = read_report_file(SAMPLE_DIR / f"{name}.csv")
        assert res.report_type == rtype
        assert res.df["date"].nunique() >= 30


# --------------------------------------------------------------------------- eksport z polskiego Google Ads

REQUIRED_ALIASES = [
    ("Dzień", "date"), ("Data", "date"), ("Day", "date"), ("Date", "date"),
    ("Kampania", "campaign"), ("Campaign", "campaign"),
    ("Identyfikator kampanii", "campaign_id"), ("Campaign ID", "campaign_id"),
    ("Grupa reklam", "ad_group"), ("Ad group", "ad_group"),
    ("Słowo kluczowe", "keyword"), ("Keyword", "keyword"),
    ("Wyszukiwane hasło", "search_term"), ("Wyszukiwane hasła", "search_term"), ("Search term", "search_term"),
    ("Typ dopasowania", "match_type"), ("Match type", "match_type"),
    ("Wyświetlenia", "impressions"), ("Impressions", "impressions"),
    ("Kliknięcia", "clicks"), ("Clicks", "clicks"),
    ("Koszt", "cost"), ("Cost", "cost"),
    ("Konwersje", "conversions"), ("Conversions", "conversions"),
    ("Wartość konwersji", "conversion_value"), ("Conversion value", "conversion_value"),
]


@pytest.mark.parametrize("header,canonical", REQUIRED_ALIASES)
def test_required_aliases(header, canonical):
    for variant in (header, header.upper(), header.lower(), f"  {header}  ", header.replace(" ", "   ")):
        mapping, _, _ = map_columns([variant])
        assert mapping == {variant: canonical}, variant


def test_aliases_without_polish_characters():
    mapping, _, _ = map_columns(["Dzien", "Wyswietlenia", "Klikniecia", "Wartosc konwersji", "Slowo kluczowe"])
    assert list(mapping.values()) == ["date", "impressions", "clicks", "conversion_value", "keyword"]


PL_SEARCH_TERMS_EXPORT = (
    "Raport wyszukiwanych haseł\n"
    "01.09.2026 - 02.09.2026\n"
    "  DZIEŃ ; Kampania;Grupa  reklam;Wyszukiwane hasła;Typ dopasowania;Słowo kluczowe;"
    "Wyświetlenia;Kliknięcia;Koszt;Konwersje;Wartość konwersji\n"
    "01.09.2026;Search | Buty;Ogólne;Buty do biegania;Dopasowanie do wyrażenia;buty;1 234;56;123,45;2,00;680,50\n"
    "02.09.2026;Search | Buty;Ogólne;darmowe buty;Przybliżone;buty;300;10;12,30;0;0\n"
    "Razem: wyszukiwane hasła;;;;;;1 534;66;135,75;2,00;680,50\n"
)


def test_polish_search_terms_export_semicolon_decimal_comma_ddmmyyyy():
    res = read_report(PL_SEARCH_TERMS_EXPORT.encode("utf-8"))
    assert res.report_type == SEARCH_TERMS
    assert res.mapping_lines()[:4] == [
        "DZIEŃ → date", "Kampania → campaign", "Grupa reklam → ad_group", "Wyszukiwane hasła → search_term",
    ]
    df = res.df.sort_values("date").reset_index(drop=True)
    assert df["date"].tolist() == [pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-02")]
    assert df["cost"].tolist() == [123.45, 12.30]
    assert df["impressions"].tolist() == [1234, 300]
    assert df.loc[0, "conversion_value"] == 680.50
    assert df.loc[0, "search_term"] == "buty do biegania"


def test_polish_campaign_export_comma_separator_iso_dates():
    text = (
        "Dzień,Kampania,Identyfikator kampanii,Wyświetlenia,Kliknięcia,Koszt,Konwersje,Wartość konwersji\n"
        '2026-09-01,Search | Buty,123456,"1 234",56,"123,45","2,50","680,00"\n'
    )
    res = read_report(text.encode("utf-8"))
    assert res.report_type == CAMPAIGN_DAILY
    assert res.df.loc[0, "campaign_id"] == "123456"
    assert res.df.loc[0, "cost"] == 123.45
    assert res.df.loc[0, "conversions"] == 2.5


@pytest.mark.parametrize("columns,expected", [
    (["date", "campaign"], CAMPAIGN_DAILY),
    (["date", "campaign", "cost", "clicks"], CAMPAIGN_DAILY),
    (["date", "campaign", "search_term"], SEARCH_TERMS),
])
def test_detect_report_type(columns, expected):
    assert detect_report_type(columns) == expected


@pytest.mark.parametrize("columns", [["campaign"], ["campaign", "search_term", "cost"]])
def test_detect_report_type_without_date(columns):
    with pytest.raises(IngestError) as exc:
        detect_report_type(columns)
    assert str(exc.value) == MISSING_DATE_MESSAGE


def test_missing_date_message_for_real_export():
    text = "Kampania;Wyszukiwane hasło;Wyświetlenia;Kliknięcia;Koszt\nA;buty;10;1;2,50\n"
    with pytest.raises(IngestError) as exc:
        read_report(text.encode("utf-8"))
    assert str(exc.value) == (
        "Raport nie zawiera wymiaru daty. W Google Ads dodaj: Segmenty → Czas → Dzień "
        "i ponownie wyeksportuj raport."
    )
