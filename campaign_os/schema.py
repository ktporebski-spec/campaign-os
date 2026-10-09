"""Model danych SEM: typy pól, typy raportów, moduły analizy i poziomy analizy.

To jedno źródło prawdy dla importera, pokrycia danych (SEM DATA COVERAGE),
dostępności analiz (BASIC / ADVANCED / FULL) oraz strony DATA REQUIREMENTS.
Model jest celowo płaski i jawny – ma posłużyć jako specyfikacja przyszłego schematu bazy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- pola

# Metryki sumowalne (agregacja: suma).
ADDITIVE = ["impressions", "clicks", "cost", "conversions", "conversion_value", "all_conversions"]
BASE_ADDITIVE = ["impressions", "clicks", "cost", "conversions", "conversion_value"]

# Udziały procentowe (0–1). Agregacja: średnia ważona wyświetleniami kwalifikującymi się
# (impressions / impression share), a gdy brak wyświetleń – zwykła średnia.
SHARES = [
    "search_impression_share", "search_lost_is_budget", "search_lost_is_rank",
    "search_top_is", "search_abs_top_is",
    "impression_share", "overlap_rate", "position_above_rate", "top_of_page_rate",
    "abs_top_of_page_rate", "outranking_share",
    "mobile_friendly_click_rate",
]
IS_SHARES = ["search_impression_share", "search_lost_is_budget", "search_lost_is_rank",
             "search_top_is", "search_abs_top_is"]

# Oceny liczbowe (średnia ważona wyświetleniami).
SCORES = ["quality_score", "mobile_speed_score", "max_cpc"]

# Kategorie normalizowane do stałych kodów.
CATEGORIES = ["expected_ctr", "ad_relevance", "landing_page_experience", "ad_strength", "device",
              "include_in_conversions"]

# Wymiary tekstowe.
DIMENSIONS = [
    "campaign", "campaign_id", "campaign_type", "campaign_status", "currency",
    "ad_group", "ad_group_id", "ad_group_status",
    "keyword", "keyword_status", "match_type", "search_term", "added_excluded",
    "ad_id", "ad_type", "ad_status", "headline_1", "headline_2", "headline_3",
    "description_1", "description_2", "final_url",
    "country", "region", "city", "location", "location_type",
    "landing_page",
    "conversion_action", "conversion_category", "conversion_source",
    "competitor_domain",
    "audience", "age_range", "gender", "household_income", "parental_status",
]
TIME_FIELDS = ["date", "hour", "day_of_week"]

# Pola dodawane przez importer / analizę (nie pochodzą bezpośrednio z pliku).
DERIVED = [
    "day_of_week_label", "slot_type", "slot", "segment", "segment_type", "location",
    "device_label", "is_self", "is_micro",
    "ctr", "cpc", "cvr", "cpa", "roas", "cost_share", "conv_share", "value_share",
    "ctr_index", "cvr_index", "cpa_index", "cvr_rest", "cvr_z", "ctr_z", "ad_name", "slot_order",
    "has_value_column", "cpa_vs_target", "lost_budget_conversions", "is_wasted", "is_high_performer", "expected_conversions",
    "bid_adjustment", "value_per_conversion", "ads_in_group", "ctr_group", "cvr_group",
    "eligible_impressions", "lost_budget_conversions", "own_impression_share", "is_gap",
    "active_days", "has_date", "cvr_change_z", "n_segments", "z_crit",
]

KNOWN_FIELDS = set(ADDITIVE + SHARES + SCORES + CATEGORIES + DIMENSIONS + TIME_FIELDS + DERIVED)

# Normalizacja wartości kategorii: klucz po normalize_header → kod.
CATEGORY_VALUES = {
    "rating": {  # expected_ctr, ad_relevance, landing_page_experience
        "above average": "above", "powyzej sredniej": "above", "ponadprzecietny": "above",
        "average": "average", "srednia": "average", "sredni": "average", "przecietny": "average",
        "przecietna": "average",
        "below average": "below", "ponizej sredniej": "below", "ponizej przecietnej": "below",
    },
    "ad_strength": {
        "excellent": "excellent", "doskonala": "excellent", "doskonaly": "excellent",
        "good": "good", "dobra": "good", "dobry": "good",
        "average": "average", "srednia": "average", "przecietna": "average",
        "poor": "poor", "slaba": "poor", "niska": "poor",
        "pending": "pending", "oczekujaca": "pending", "w toku": "pending",
    },
    "device": {
        "mobile phones": "mobile", "mobile": "mobile", "mobile devices with full browsers": "mobile",
        "telefony komorkowe": "mobile", "urzadzenia mobilne z pelnymi przegladarkami": "mobile",
        "telefony": "mobile", "smartfony": "mobile",
        "computers": "desktop", "computer": "desktop", "desktop": "desktop", "komputery": "desktop",
        "tablets": "tablet", "tablet": "tablet", "tablets with full browsers": "tablet", "tablety": "tablet",
        "tablety z pelnymi przegladarkami": "tablet",
        "tv screens": "tv", "ekrany telewizorow": "tv", "telewizory": "tv",
        "other": "other", "inne": "other", "unknown": "other", "nieznane": "other",
    },
    "include_in_conversions": {"yes": "yes", "tak": "yes", "true": "yes", "no": "no", "nie": "no", "false": "no"},
}
CATEGORY_KIND = {
    "expected_ctr": "rating", "ad_relevance": "rating", "landing_page_experience": "rating",
    "ad_strength": "ad_strength", "device": "device", "include_in_conversions": "include_in_conversions",
}
RATING_LABELS = {"above": "Powyżej średniej", "average": "Średnia", "below": "Poniżej średniej"}
DEVICE_LABELS = {"mobile": "Telefony komórkowe", "desktop": "Komputery", "tablet": "Tablety",
                 "tv": "Ekrany TV", "other": "Inne"}
DAY_NAMES = {
    "monday": 1, "poniedzialek": 1, "mon": 1, "pn": 1,
    "tuesday": 2, "wtorek": 2, "tue": 2, "wt": 2,
    "wednesday": 3, "sroda": 3, "wed": 3, "sr": 3,
    "thursday": 4, "czwartek": 4, "thu": 4, "cz": 4, "czw": 4,
    "friday": 5, "piatek": 5, "fri": 5, "pt": 5,
    "saturday": 6, "sobota": 6, "sat": 6, "sob": 6,
    "sunday": 7, "niedziela": 7, "sun": 7, "nd": 7, "niedz": 7,
}
DAY_LABELS = {1: "Poniedziałek", 2: "Wtorek", 3: "Środa", 4: "Czwartek", 5: "Piątek", 6: "Sobota", 7: "Niedziela"}

# Kategorie / nazwy działań konwersji traktowane jako mikro- lub pośrednie konwersje.
MICRO_CONVERSION_PATTERNS = [
    "page view", "wyswietlenie strony", "pageview", "scroll", "przewiniecie", "engagement",
    "zaangazowanie", "outbound click", "klikniecie", "add to cart", "dodanie do koszyka",
    "begin checkout", "rozpoczecie platnosci", "view item", "wyswietlenie produktu", "session",
    "sesja", "time on site", "czas na stronie",
]


# --------------------------------------------------------------------------- raporty


@dataclass(frozen=True)
class ReportSpec:
    key: str
    label: str            # nazwa w SEM DATA COVERAGE
    title: str            # pełna nazwa raportu
    core: bool            # raport podstawowy (wymagany)
    signature: tuple      # kolumny rozpoznające typ: każda pozycja to krotka alternatyw
    required: tuple       # minimalne kolumny (krotki alternatyw)
    recommended: tuple    # kolumny zalecane
    group_keys: tuple     # klucze agregacji duplikatów (używane te, które występują)
    date_required: bool = False
    metrics: tuple = tuple(BASE_ADDITIVE)
    export_path: str = ""
    description: str = ""
    entity: str = ""      # encja Rule Engine zasilana tym raportem


REPORTS: list[ReportSpec] = [
    ReportSpec(
        key="campaign_daily", label="Campaign", title="Raport kampanii", core=True,
        signature=(("campaign",),),
        required=(("date",), ("campaign",), ("impressions",), ("clicks",), ("cost",)),
        recommended=(("conversions",), ("conversion_value",), ("campaign_type",),
                     ("search_impression_share",), ("search_lost_is_budget",), ("search_lost_is_rank",)),
        group_keys=("date", "campaign"), date_required=True, entity="campaign",
        export_path="Kampanie → Kampanie → Segmenty → Czas → Dzień → Pobierz (CSV)",
        description="KPI konta i kampanii, trendy, porównanie okresów. Kolumny udziału w wyświetleniach "
                    "(Search IS, Lost IS budget/rank) włączają analizę Impression Share.",
    ),
    ReportSpec(
        key="search_terms_daily", label="Search Terms", title="Raport wyszukiwanych haseł", core=True,
        signature=(("search_term",),),
        required=(("date",), ("campaign",), ("search_term",), ("impressions",), ("clicks",), ("cost",)),
        recommended=(("ad_group",), ("keyword",), ("match_type",), ("conversions",)),
        group_keys=("date", "campaign", "ad_group", "search_term", "match_type"), date_required=True,
        entity="search_term",
        export_path="Statystyki i raporty → Wyszukiwane hasła → Segmenty → Czas → Dzień → Pobierz",
        description="Wasted spend, hasła do wykluczenia i nowe słowa kluczowe (opportunities).",
    ),
    ReportSpec(
        key="conversion_actions", label="Conversions", title="Działania powodujące konwersję", core=False,
        signature=(("conversion_action",),),
        required=(("conversion_action",), ("conversions",)),
        recommended=(("campaign",), ("date",), ("conversion_category",), ("conversion_value",),
                     ("include_in_conversions",)),
        group_keys=("date", "campaign", "conversion_action"),
        metrics=("conversions",), entity="conversion_action",
        export_path="Kampanie → Segmenty → Konwersje → Działanie powodujące konwersję → Pobierz",
        description="Skład konwersji: udział mikrokonwersji, działania bez wartości.",
    ),
    ReportSpec(
        key="auction_insights", label="Auction Insights", title="Statystyki aukcji", core=False,
        signature=(("competitor_domain",),),
        required=(("competitor_domain",), ("impression_share",)),
        recommended=(("campaign",), ("overlap_rate",), ("position_above_rate",), ("top_of_page_rate",),
                     ("abs_top_of_page_rate",), ("outranking_share",)),
        group_keys=("date", "campaign", "competitor_domain"), metrics=(), entity="competitor",
        export_path="Kampanie → Statystyki aukcji → Pobierz",
        description="Presja konkurencji: udział w wyświetleniach konkurentów, pozycja powyżej, wygrane aukcje.",
    ),
    ReportSpec(
        key="landing_pages", label="Landing Pages", title="Strony docelowe", core=False,
        signature=(("landing_page",),),
        required=(("landing_page",), ("clicks",), ("cost",)),
        recommended=(("impressions",), ("conversions",), ("date",), ("mobile_friendly_click_rate",),
                     ("mobile_speed_score",)),
        group_keys=("date", "campaign", "landing_page"), entity="landing_page",
        export_path="Strony docelowe → Strony docelowe (lub Rozwinięte strony docelowe) → Pobierz",
        description="Konwersja i jakość mobilna stron docelowych.",
    ),
    ReportSpec(
        key="ads", label="Ads", title="Reklamy / RSA", core=False,
        signature=(("ad_id", "headline_1", "ad_strength", "ad_type", "description_1"),),
        required=(("campaign",), ("ad_group",), ("ad_id", "headline_1"), ("impressions",), ("clicks",), ("cost",)),
        recommended=(("ad_type",), ("ad_strength",), ("final_url",), ("conversions",), ("date",)),
        group_keys=("date", "campaign", "ad_group", "ad_id", "headline_1"), entity="ad",
        export_path="Reklamy → Reklamy → Pobierz",
        description="Skuteczność reklam w grupie (CTR, CVR) i siła reklam RSA.",
    ),
    ReportSpec(
        key="keywords", label="Keywords", title="Słowa kluczowe", core=False,
        signature=(("keyword",),),
        required=(("campaign",), ("ad_group",), ("keyword",), ("impressions",), ("clicks",), ("cost",)),
        recommended=(("match_type",), ("conversions",), ("quality_score",), ("expected_ctr",), ("ad_relevance",),
                     ("landing_page_experience",), ("search_impression_share",), ("search_lost_is_rank",)),
        group_keys=("date", "campaign", "ad_group", "keyword", "match_type"), entity="keyword",
        export_path="Słowa kluczowe → Słowa kluczowe w sieci wyszukiwania → kolumny Wynik jakości → Pobierz",
        description="Skuteczność słów kluczowych, Quality Score i jego składowe, utrata IS przez ranking.",
    ),
    ReportSpec(
        key="devices", label="Devices", title="Urządzenia", core=False,
        signature=(("device",),),
        required=(("device",), ("impressions",), ("clicks",), ("cost",)),
        recommended=(("campaign",), ("date",), ("conversions",)),
        group_keys=("date", "campaign", "device"), entity="device",
        export_path="Kampanie → Segmenty → Urządzenie → Pobierz (lub zakładka Urządzenia)",
        description="Różnice CVR/CPA między urządzeniami i sugerowane korekty stawek.",
    ),
    ReportSpec(
        key="time", label="Time", title="Czas: dzień tygodnia i godzina", core=False,
        signature=(("hour", "day_of_week"),),
        required=(("hour", "day_of_week"), ("impressions",), ("clicks",), ("cost",)),
        recommended=(("date",), ("campaign",), ("conversions",)),
        group_keys=("date", "campaign", "day_of_week", "hour"), entity="time_slot",
        export_path="Kampanie → Segmenty → Czas → Dzień (lub Dzień tygodnia) + Godzina → Pobierz",
        description="Różnice skuteczności w dniach tygodnia i godzinach (harmonogram reklam).",
    ),
    ReportSpec(
        key="locations", label="Locations", title="Lokalizacje", core=False,
        signature=(("location", "region", "city", "country"),),
        required=(("location", "region", "city", "country"), ("impressions",), ("clicks",), ("cost",)),
        recommended=(("campaign",), ("date",), ("conversions",), ("location_type",)),
        group_keys=("date", "campaign", "country", "region", "city", "location"), entity="location",
        export_path="Lokalizacje → Gdzie byli użytkownicy (lub Dopasowane lokalizacje) → Pobierz",
        description="Skuteczność geograficzna i korekty stawek dla lokalizacji.",
    ),
    ReportSpec(
        key="audiences", label="Audiences", title="Odbiorcy / demografia", core=False,
        signature=(("audience", "age_range", "gender", "household_income", "parental_status"),),
        required=(("audience", "age_range", "gender", "household_income", "parental_status"),
                  ("impressions",), ("clicks",), ("cost",)),
        recommended=(("campaign",), ("date",), ("conversions",)),
        group_keys=("date", "campaign", "audience", "age_range", "gender", "household_income", "parental_status"),
        entity="audience",
        export_path="Odbiorcy → Segmenty odbiorców (lub Demografia: Wiek / Płeć) → Pobierz",
        description="Skuteczność segmentów odbiorców i grup demograficznych (obserwacja).",
    ),
    ReportSpec(
        key="ad_groups", label="Ad Groups", title="Grupy reklam", core=False,
        signature=(("ad_group",),),
        required=(("campaign",), ("ad_group",), ("impressions",), ("clicks",), ("cost",)),
        recommended=(("date",), ("conversions",), ("conversion_value",), ("ad_group_status",)),
        group_keys=("date", "campaign", "ad_group"), entity="ad_group",
        export_path="Grupy reklam → Segmenty → Czas → Dzień → Pobierz",
        description="Skuteczność grup reklam w kampaniach.",
    ),
]
REPORT_BY_KEY = {r.key: r for r in REPORTS}

# Kolejność rozpoznawania typu: od najbardziej specyficznych sygnatur. Np. raport haseł zawiera też
# grupę reklam i słowo kluczowe, a raport słów kluczowych – grupę reklam. Raport kampanii jest
# ostatni: rozpoznajemy go, gdy żaden inny wymiar nie pasuje.
DETECTION_ORDER = [
    "search_terms_daily", "conversion_actions", "auction_insights", "landing_pages", "ads", "keywords",
    "devices", "time", "locations", "audiences", "ad_groups", "campaign_daily",
]

# Kolejność wyświetlania w SEM DATA COVERAGE.
COVERAGE_ORDER = ["campaign_daily", "ad_groups", "keywords", "search_terms_daily", "ads", "devices", "time",
                  "locations", "landing_pages", "conversion_actions", "auction_insights", "audiences"]


# --------------------------------------------------------------------------- moduły analizy


@dataclass(frozen=True)
class AnalysisModule:
    key: str
    title: str
    tier: str                         # basic | advanced | full
    reports: tuple                    # wymagane raporty
    columns: tuple = ()               # wymagane kolumny: (raport, krotka alternatyw)
    entity: str = ""                  # encja Rule Engine
    description: str = ""
    rule_prefixes: tuple = field(default_factory=tuple)


MODULES: list[AnalysisModule] = [
    AnalysisModule("campaign_performance", "Campaign performance", "basic", ("campaign_daily",),
                   entity="campaign", rule_prefixes=("CMP_",),
                   description="KPI kampanii, zmiany vs poprzedni okres, CPA vs cel."),
    AnalysisModule("search_term_waste", "Search term waste", "basic", ("search_terms_daily",),
                   entity="search_term", rule_prefixes=("ST_WASTED", "ST_HIGH_CPA", "ST_LOW_CTR"),
                   description="Hasła bez konwersji i z nieakceptowalnym CPA."),
    AnalysisModule("search_term_opportunities", "Search term opportunities", "basic", ("search_terms_daily",),
                   entity="search_term", rule_prefixes=("ST_HIGH_PERFORMER",),
                   description="Hasła do dodania jako słowa kluczowe."),
    AnalysisModule("ad_group_performance", "Ad group performance", "advanced", ("ad_groups",),
                   entity="ad_group", rule_prefixes=("AG_",),
                   description="Grupy reklam bez konwersji, z wysokim CPA i do skalowania."),
    AnalysisModule("keyword_performance", "Keyword performance", "advanced", ("keywords",),
                   entity="keyword", rule_prefixes=("KW_WASTE", "KW_HIGH_CPA", "KW_SCALE"),
                   description="Słowa kluczowe bez konwersji, z wysokim CPA i do skalowania."),
    AnalysisModule("quality_score", "Quality Score (Expected CTR, Ad Relevance, LP Experience)", "advanced",
                   ("keywords",), columns=(("keywords", ("quality_score", "expected_ctr", "ad_relevance",
                                                         "landing_page_experience")),),
                   entity="keyword", rule_prefixes=("KW_LOW_QS", "KW_EXP_CTR", "KW_AD_REL", "KW_LPE"),
                   description="Wynik jakości i jego składowe ważone wyświetleniami."),
    AnalysisModule("ad_performance", "Ad performance", "advanced", ("ads",), entity="ad", rule_prefixes=("AD_",),
                   description="Reklamy odstające od średniej grupy, siła reklam RSA."),
    AnalysisModule("device_differences", "Device differences", "advanced", ("devices",), entity="device",
                   rule_prefixes=("DEV_",), description="Różnice CVR/CPA między urządzeniami."),
    AnalysisModule("time_differences", "Day / hour differences", "advanced", ("time",), entity="time_slot",
                   rule_prefixes=("TIME_",), description="Różnice skuteczności w dniach tygodnia i godzinach."),
    AnalysisModule("impression_share", "Search Impression Share (Lost IS budget / rank)", "full",
                   ("campaign_daily",), columns=(("campaign_daily", ("search_impression_share",
                                                                     "search_lost_is_budget",
                                                                     "search_lost_is_rank")),),
                   entity="campaign", rule_prefixes=("IS_",),
                   description="Udział w wyświetleniach i jego utrata przez budżet lub ranking."),
    AnalysisModule("geographic_performance", "Geographic performance", "full", ("locations",), entity="location",
                   rule_prefixes=("LOC_",), description="Lokalizacje o odmiennej skuteczności."),
    AnalysisModule("landing_page_performance", "Landing page performance", "full", ("landing_pages",),
                   entity="landing_page", rule_prefixes=("LP_",),
                   description="Konwersja stron docelowych i jakość mobilna."),
    AnalysisModule("conversion_composition", "Conversion action composition", "full", ("conversion_actions",),
                   entity="conversion_action", rule_prefixes=("CONV_",),
                   description="Udział mikrokonwersji i działań bez wartości."),
    AnalysisModule("competitive_pressure", "Auction Insights / competitive pressure", "full",
                   ("auction_insights",), entity="competitor", rule_prefixes=("AI_",),
                   description="Konkurenci z wysokim nakładaniem się i pozycją powyżej."),
    AnalysisModule("audience_performance", "Audiences / demographics", "full", ("audiences",), entity="audience",
                   rule_prefixes=("AUD_",), description="Segmenty odbiorców o odmiennej skuteczności."),
]
MODULE_BY_KEY = {m.key: m for m in MODULES}

TIERS = {
    "basic": ("BASIC ANALYSIS", "Raporty podstawowe: kampanie + wyszukiwane hasła."),
    "advanced": ("ADVANCED ANALYSIS", "Struktura konta i segmenty: grupy reklam, słowa kluczowe, reklamy, "
                                      "urządzenia, czas."),
    "full": ("FULL SEM ANALYSIS", "Pełny obraz: udział w wyświetleniach, lokalizacje, strony docelowe, "
                                  "konwersje, konkurencja, odbiorcy."),
}

ENTITY_LABELS = {
    "campaign": "Kampania", "search_term": "Wyszukiwane hasło", "ad_group": "Grupa reklam",
    "keyword": "Słowo kluczowe", "ad": "Reklama", "device": "Urządzenie", "time_slot": "Dzień / godzina",
    "location": "Lokalizacja", "landing_page": "Strona docelowa", "conversion_action": "Działanie konwersji",
    "competitor": "Konkurent", "audience": "Segment odbiorców",
}
ENTITY_REPORT = {r.entity: r.key for r in REPORTS}
ENTITIES = tuple(ENTITY_LABELS)
