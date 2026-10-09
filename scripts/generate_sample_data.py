"""Generuje przykładowe raporty Google Ads (60 dni) do data/sample/.

Raporty podstawowe:
* campaign_daily.csv     – eksport PL (nagłówki PL, liczby "1 234,56", wiersz "Razem", Search IS)
* search_terms_daily.csv – eksport EN (nagłówki EN, liczby "1,234.56", wiersz "Total")

Raporty opcjonalne (spójne z powyższymi – wyliczone z tych samych danych):
ad_groups.csv (PL), keywords.csv (PL, Quality Score), ads.csv (EN, RSA), devices.csv (EN),
hour_of_day.csv (PL), locations.csv (PL), landing_pages.csv (EN), conversion_actions.csv (PL),
auction_insights.csv (PL, bez daty – ostatnie 30 dni), audiences.csv (PL).

Dane są deterministyczne (stały seed) i zawierają celowe wzorce: hasła marnujące budżet,
high performers, wzrost CPA w kampanii trailowej, spadek CTR w kampanii konkurencyjnej
oraz kampanię remarketingową bez konwersji w ostatnim okresie.

Użycie:  python scripts/generate_sample_data.py
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"
START = date(2026, 8, 2)
DAYS = 60
SPLIT = START + timedelta(days=30)  # początek "ostatnich 30 dni"
AOV = 340.0  # średnia wartość zamówienia (PLN)
rng = np.random.default_rng(42)
# Osobny generator dla raportów opcjonalnych – raporty podstawowe pozostają identyczne jak w v0.1.
rng2 = np.random.default_rng(7)

# (hasło, grupa reklam, słowo kluczowe, dopasowanie, bazowe wyśw./dzień, CTR, CPC, CVR, tylko_ostatni_okres)
SEARCH_CAMPAIGNS = {
    "Search | Brand": [
        ("biegosfera", "Brand", "biegosfera", "Exact match", 120, 0.30, 0.90, 0.075, False),
        ("biegosfera sklep", "Brand", "biegosfera", "Phrase match", 45, 0.28, 0.95, 0.08, False),
        ("biegosfera kod rabatowy", "Brand", "biegosfera", "Phrase match", 25, 0.35, 0.80, 0.12, False),
        ("biegosfera opinie", "Brand", "biegosfera", "Phrase match", 20, 0.22, 0.70, 0.02, False),
        ("biegosfera zwrot", "Brand", "biegosfera", "Phrase match", 15, 0.25, 0.60, 0.0, False),
    ],
    "Search | Buty do biegania": [
        ("buty do biegania", "Ogólne", "buty do biegania", "Phrase match", 520, 0.055, 2.40, 0.032, False),
        ("buty do biegania damskie", "Damskie", "buty do biegania damskie", "Exact match", 210, 0.07, 2.20, 0.045, False),
        ("buty do biegania męskie", "Męskie", "buty do biegania męskie", "Exact match", 190, 0.065, 2.30, 0.042, False),
        ("najlepsze buty do biegania 2026", "Ogólne", "buty do biegania", "Phrase match", 120, 0.05, 2.00, 0.02, False),
        ("buty do biegania po asfalcie", "Ogólne", "buty do biegania", "Phrase match", 95, 0.07, 1.90, 0.075, False),
        ("buty do biegania dla początkujących", "Ogólne", "buty do biegania", "Phrase match", 80, 0.065, 1.80, 0.08, False),
        ("buty do biegania z amortyzacją", "Ogólne", "buty do biegania", "Phrase match", 70, 0.06, 2.10, 0.05, False),
        ("darmowe buty do biegania", "Ogólne", "buty do biegania", "Phrase match", 85, 0.06, 1.50, 0.0, False),
        ("buty do biegania używane", "Ogólne", "buty do biegania", "Phrase match", 70, 0.06, 1.30, 0.0, False),
        ("buty do biegania allegro", "Ogólne", "buty do biegania", "Phrase match", 110, 0.05, 1.70, 0.002, False),
        ("jak wybrać buty do biegania", "Ogólne", "buty do biegania", "Phrase match", 140, 0.035, 1.20, 0.003, False),
        ("buty do biegania lidl", "Ogólne", "buty do biegania", "Phrase match", 60, 0.07, 1.10, 0.0, False),
        ("naprawa butów do biegania", "Ogólne", "buty do biegania", "Broad match", 90, 0.006, 1.40, 0.0, False),
        ("buty do biegania damskie wyprzedaż", "Damskie", "buty do biegania damskie", "Phrase match", 60, 0.08, 1.60, 0.05, False),
        ("buty do biegania męskie 45", "Męskie", "buty do biegania męskie", "Phrase match", 25, 0.07, 1.90, 0.04, False),
    ],
    "Search | Buty trailowe": [
        ("buty trailowe", "Trail", "buty trailowe", "Exact match", 240, 0.06, 2.10, 0.04, False),
        ("buty trailowe damskie", "Trail", "buty trailowe", "Phrase match", 90, 0.065, 2.00, 0.045, False),
        ("buty do biegania w terenie", "Trail", "buty do biegania w terenie", "Phrase match", 110, 0.055, 2.20, 0.035, False),
        ("buty trailowe gore-tex", "Trail", "buty trailowe", "Phrase match", 60, 0.07, 2.30, 0.085, False),
        ("buty trailowe salomon", "Trail", "buty trailowe", "Phrase match", 75, 0.06, 2.50, 0.04, False),
        ("buty górskie", "Trail", "buty do biegania w terenie", "Broad match", 160, 0.03, 1.60, 0.0, False),
        ("buty trekkingowe", "Trail", "buty do biegania w terenie", "Broad match", 180, 0.025, 1.50, 0.003, False),
        ("buty trailowe outlet wyprzedaż", "Trail", "buty trailowe", "Broad match", 160, 0.07, 1.80, 0.0, True),
    ],
    "Search | Konkurencja": [
        ("nike pegasus", "Nike", "nike pegasus", "Exact match", 230, 0.045, 3.20, 0.018, False),
        ("asics gel nimbus", "Asics", "asics gel nimbus", "Exact match", 180, 0.05, 3.00, 0.022, False),
        ("hoka clifton", "Hoka", "hoka clifton", "Exact match", 140, 0.055, 3.40, 0.025, False),
        ("decathlon buty do biegania", "Ogólne", "buty do biegania sklep", "Broad match", 150, 0.04, 2.40, 0.0, False),
        ("sklep z butami do biegania", "Ogólne", "buty do biegania sklep", "Phrase match", 90, 0.06, 2.60, 0.05, False),
    ],
}

CAMPAIGN_TYPES_PL = {
    "Search | Brand": "Sieć wyszukiwania",
    "Search | Buty do biegania": "Sieć wyszukiwania",
    "Search | Buty trailowe": "Sieć wyszukiwania",
    "Search | Konkurencja": "Sieć wyszukiwania",
    "PMax | Cały asortyment": "Maksymalizacja skuteczności",
    "Display | Remarketing": "Sieć reklamowa",
}

# Kampanie bez raportu search terms: (wyśw./dzień, CTR, CPC, CVR)
OTHER_CAMPAIGNS = {
    "PMax | Cały asortyment": (5200, 0.012, 1.10, 0.035),
    "Display | Remarketing": (9000, 0.0045, 0.95, 0.006),
}


def day_factor(d: date) -> float:
    weekday = 0.85 if d.weekday() >= 5 else 1.0
    trend = 1.0 + 0.004 * (d - START).days  # lekki wzrost ruchu w czasie
    return weekday * trend


def modifiers(campaign: str, term: str, recent: bool) -> tuple[float, float]:
    """Zwraca mnożniki (CTR, CVR) wprowadzające wzorce w ostatnim okresie."""
    ctr_m, cvr_m = 1.0, 1.0
    if recent and campaign == "Search | Buty trailowe":
        cvr_m = 0.55  # wzrost CPA
    if recent and campaign == "Search | Konkurencja":
        ctr_m = 0.6  # spadek CTR
    return ctr_m, cvr_m


def simulate(impr_base: float, ctr: float, cpc: float, cvr: float, factor: float):
    impr = int(rng.poisson(max(impr_base * factor, 0.1)))
    clicks = int(rng.binomial(impr, min(ctr, 1.0))) if impr else 0
    cost = round(clicks * cpc * float(rng.uniform(0.8, 1.2)), 2)
    conv = int(rng.binomial(clicks, min(cvr, 1.0))) if clicks else 0
    value = round(conv * AOV * float(rng.uniform(0.75, 1.3)), 2)
    return impr, clicks, cost, conv, value


def fmt_pl(value: float, decimals: int = 2) -> str:
    text = f"{value:,.{decimals}f}"
    return text.replace(",", " ").replace(".", ",")


def fmt_en(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}"


def ratio(a: float, b: float) -> float | None:
    return a / b if b else None


# --------------------------------------------------------------------------- raporty opcjonalne

# Search IS kampanii: (udział, utrata – budżet, utrata – ranking); None = brak IS (PMax/Display).
IMPRESSION_SHARE = {
    "Search | Brand": (0.82, 0.12, 0.06),
    "Search | Buty do biegania": (0.52, 0.03, 0.45),
    "Search | Buty trailowe": (0.35, 0.25, 0.40),
    "Search | Konkurencja": (0.18, 0.00, 0.82),
}

# Słowo kluczowe → (typ dopasowania, QS, oczekiwany CTR, trafność reklamy, jakość strony, Search IS, Lost IS rank)
ABOVE, AVG, BELOW = "Powyżej średniej", "Średnia", "Poniżej średniej"
KEYWORD_META = {
    "biegosfera": ("Dopasowanie ścisłe", 10, ABOVE, ABOVE, ABOVE, 0.85, 0.03),
    "buty do biegania": ("Dopasowanie do wyrażenia", 5, AVG, AVG, BELOW, 0.45, 0.45),
    "buty do biegania damskie": ("Dopasowanie ścisłe", 7, ABOVE, AVG, AVG, 0.55, 0.30),
    "buty do biegania męskie": ("Dopasowanie ścisłe", 7, ABOVE, AVG, AVG, 0.55, 0.30),
    "buty trailowe": ("Dopasowanie ścisłe", 6, AVG, ABOVE, AVG, 0.40, 0.35),
    "buty do biegania w terenie": ("Dopasowanie do wyrażenia", 3, BELOW, BELOW, AVG, 0.25, 0.60),
    "nike pegasus": ("Dopasowanie ścisłe", 3, BELOW, BELOW, AVG, 0.15, 0.80),
    "asics gel nimbus": ("Dopasowanie ścisłe", 4, AVG, BELOW, AVG, 0.18, 0.78),
    "hoka clifton": ("Dopasowanie ścisłe", 4, BELOW, AVG, AVG, 0.20, 0.75),
    "buty do biegania sklep": ("Dopasowanie przybliżone", 6, AVG, AVG, AVG, 0.30, 0.50),
}

# Reklamy w grupie: (udział wyświetleń, mnożnik CTR, mnożnik CVR, siła reklamy, nagłówek 1)
ADS = {
    "default": [(0.6, 1.15, 1.0, "Good", "Buty do biegania – nowa kolekcja"),
                (0.4, 0.80, 1.0, "Average", "Sprawdź buty do biegania")],
    ("Search | Buty do biegania", "Ogólne"): [
        (0.55, 1.25, 1.0, "Excellent", "Buty do biegania | Darmowa dostawa"),
        (0.45, 0.55, 0.9, "Poor", "Sklep sportowy online")],
    ("Search | Buty trailowe", "Trail"): [
        (0.6, 1.05, 1.15, "Good", "Buty trailowe – przyczepność w terenie"),
        (0.4, 0.95, 0.65, "Average", "Wyprzedaż butów – do -50%")],
}

DEVICES = [  # (nazwa EN, udział wyśw., udział kliknięć, mnożnik CPC, mnożnik CVR)
    ("Mobile phones", 0.65, 0.62, 0.90, 0.70),
    ("Computers", 0.29, 0.32, 1.20, 1.55),
    ("Tablets", 0.06, 0.06, 0.95, 0.90),
]

REGIONS = {  # województwo → (waga ruchu, mnożnik CVR)
    "Mazowieckie": (0.20, 1.35), "Śląskie": (0.12, 1.0), "Wielkopolskie": (0.09, 1.05),
    "Małopolskie": (0.09, 1.1), "Dolnośląskie": (0.08, 1.05), "Łódzkie": (0.06, 0.95),
    "Pomorskie": (0.06, 1.0), "Kujawsko-pomorskie": (0.05, 0.9), "Lubelskie": (0.05, 0.85),
    "Podkarpackie": (0.04, 0.9), "Zachodniopomorskie": (0.04, 0.95), "Warmińsko-mazurskie": (0.03, 0.8),
    "Świętokrzyskie": (0.03, 0.85), "Podlaskie": (0.03, 0.30), "Opolskie": (0.02, 0.9), "Lubuskie": (0.01, 0.5),
}

LANDING_PAGES = {  # ścieżka → (udział kliknięć, mnożnik CVR, mobile-friendly click rate, mobile speed score)
    "/": (0.15, 1.0, 1.0, 7),
    "/buty-do-biegania": (0.33, 1.1, 1.0, 6),
    "/buty-trailowe": (0.18, 0.95, 0.98, 5),
    "/buty-do-biegania/damskie": (0.12, 1.2, 1.0, 6),
    "/blog/jak-wybrac-buty-do-biegania": (0.14, 0.25, 0.72, 3),
    "/promocje": (0.08, 1.3, 0.99, 6),
}

CONVERSION_ACTIONS = [  # (nazwa, kategoria, udział konwersji, czy niesie wartość)
    ("Zakup", "Zakup", 0.76, True),
    ("Połączenie telefoniczne z reklamy", "Kontakt", 0.04, False),
    ("Wyświetlenie strony – Kontakt", "Wyświetlenie strony", 0.20, False),
]

AUDIENCES = [  # (segment, udział ruchu, mnożnik CVR)
    ("Odwiedzający sklep – 30 dni", 0.12, 2.6),
    ("Na rynku: Obuwie sportowe", 0.25, 1.25),
    ("Zainteresowania: Bieganie", 0.30, 0.95),
    ("Zainteresowania: Turystyka górska", 0.10, 0.40),
]

# Konkurenci (fikcyjne domeny): domena → (udział w wyśw., nakładanie, pozycja powyżej, góra strony,
# najwyższa pozycja, udział w wygranych aukcjach)
COMPETITORS = {
    "runmarket.pl": (0.62, 0.55, 0.64, 0.78, 0.41, 0.31),
    "sportowy-outlet.pl": (0.38, 0.34, 0.42, 0.55, 0.18, 0.44),
    "trailshop.pl": (0.21, 0.18, 0.58, 0.61, 0.25, 0.39),
    "maratonczyk.pl": (0.08, 0.07, 0.22, 0.40, 0.08, 0.52),
}
HOUR_WEIGHTS = [0.4, 0.25, 0.15, 0.1, 0.1, 0.2, 0.5, 0.9, 1.2, 1.4, 1.5, 1.5, 1.6, 1.5, 1.4, 1.4, 1.5, 1.6,
                1.8, 2.0, 2.0, 1.8, 1.3, 0.8]
HOUR_CVR = [0.3] * 6 + [0.8] * 3 + [1.0] * 9 + [1.35] * 4 + [0.8] * 2
PL_DAYS = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]


def pct_pl(value: float) -> str:
    return f"{fmt_pl(value * 100)}%"


def jitter(value: float, spread: float = 0.03) -> float:
    return float(min(max(value + rng2.uniform(-spread, spread), 0.0), 1.0))


def impression_share_cells(campaign: str) -> list[str]:
    spec = IMPRESSION_SHARE.get(campaign)
    if spec is None:
        return ["--", "--", "--"]
    share, budget, rank = jitter(spec[0]), jitter(spec[1], 0.02), jitter(spec[2])
    return [pct_pl(share), pct_pl(budget), pct_pl(rank)]


def split(total: float, weights: list[float]) -> np.ndarray:
    """Dzieli liczbę całkowitą losowo wg wag (rozkład wielomianowy)."""
    w = np.asarray(weights, dtype=float)
    if total <= 0 or w.sum() <= 0:
        return np.zeros(len(w))
    return rng2.multinomial(int(round(total)), w / w.sum()).astype(float)


def split_row(row: np.ndarray, impr_w, click_w, cpc_w, cvr_w) -> list[np.ndarray]:
    """Dzieli wiersz (impr, clicks, cost, conv, value) na segmenty o zadanych właściwościach."""
    impr, clicks, cost, conv, value = row
    seg_impr = split(impr, impr_w)
    seg_clicks = np.minimum(split(clicks, click_w), seg_impr)
    cost_w = seg_clicks * np.asarray(cpc_w)
    seg_cost = cost * cost_w / cost_w.sum() if cost_w.sum() else np.zeros(len(seg_clicks))
    seg_conv = split(conv, seg_clicks * np.asarray(cvr_w))
    seg_value = value * seg_conv / conv if conv else np.zeros(len(seg_clicks))
    return [np.array([seg_impr[i], seg_clicks[i], round(seg_cost[i], 2), seg_conv[i], round(seg_value[i], 2)])
            for i in range(len(seg_impr))]


def _write(name: str, header: list[str], rows: list[list], preamble: list[str] | None = None,
           total: list | None = None) -> None:
    path = OUT_DIR / name
    with open(path, "w", encoding="utf-8", newline="") as fh:
        for line in preamble or []:
            fh.write(line + "\n")
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        writer.writerows(rows)
        if total:
            writer.writerow(total)
    print(f"Zapisano {path} ({len(rows)} wierszy)")


def pl_metrics(m) -> list[str]:
    return [fmt_pl(m[0], 0), fmt_pl(m[1], 0), fmt_pl(m[2]), fmt_pl(m[3]), fmt_pl(m[4])]


def en_metrics(m) -> list[str]:
    return [fmt_en(m[0], 0), fmt_en(m[1], 0), fmt_en(m[2]), fmt_en(m[3]), fmt_en(m[4])]


def write_optional_reports(campaign_rows, term_rows, hidden_rows, end) -> None:
    pl_head = ["Wyświetlenia", "Kliknięcia", "Koszt", "Konwersje", "Wartość konw."]
    en_head = ["Impr.", "Clicks", "Cost", "Conversions", "Conv. value"]
    search_campaigns = list(SEARCH_CAMPAIGNS)
    first_group = {c: terms[0][1] for c, terms in SEARCH_CAMPAIGNS.items()}
    first_keyword = {c: terms[0][2] for c, terms in SEARCH_CAMPAIGNS.items()}

    # ------------------------------------------------ ad_groups.csv / keywords.csv (PL)
    ad_groups: dict = {}
    keywords: dict = {}
    for term, match, _, campaign, ad_group, keyword, d, *m in term_rows:
        ad_groups[(d, campaign, ad_group)] = ad_groups.get((d, campaign, ad_group), 0) + np.array(m)
        keywords[(d, campaign, ad_group, keyword)] = keywords.get((d, campaign, ad_group, keyword), 0) + np.array(m)
    for (d, campaign), hidden in hidden_rows.items():  # ruch spoza widocznych haseł
        k = (d, campaign, first_group[campaign])
        ad_groups[k] = ad_groups.get(k, 0) + hidden
        k = (d, campaign, first_group[campaign], first_keyword[campaign])
        keywords[k] = keywords.get(k, 0) + hidden
    rows = [[d.isoformat(), c, g, "Włączona", *pl_metrics(m)] for (d, c, g), m in sorted(ad_groups.items())]
    _write("ad_groups.csv", ["Dzień", "Kampania", "Grupa reklam", "Stan grupy reklam", *pl_head], rows,
           preamble=["Raport grup reklam", f"{START:%d.%m.%Y} - {end:%d.%m.%Y}"])

    rows = []
    for (d, c, g, kw), m in sorted(keywords.items()):
        match, qs, exp_ctr, ad_rel, lpe, share, lost_rank = KEYWORD_META[kw]
        rows.append([d.isoformat(), kw, match, c, g, "Kwalifikujące się", *pl_metrics(m), str(qs), exp_ctr,
                     ad_rel, lpe, pct_pl(jitter(share)), pct_pl(jitter(lost_rank))])
    _write("keywords.csv", ["Dzień", "Słowo kluczowe", "Typ dopasowania", "Kampania", "Grupa reklam",
                            "Stan słowa kluczowego", *pl_head, "Wynik jakości", "Oczekiwany CTR",
                            "Trafność reklamy", "Jakość strony docelowej",
                            "Udział w wyświetleniach w sieci wyszukiwania",
                            "Utracony udział w wyświetleniach w sieci wyszukiwania (ranking)"], rows)

    # ------------------------------------------------ ads.csv (EN)
    rows = []
    ad_ids: dict = {}
    for (d, c, g), m in sorted(ad_groups.items()):
        variants = ADS.get((c, g), ADS["default"])
        parts = split_row(m, [v[0] for v in variants], [v[0] * v[1] for v in variants], [1.0] * len(variants),
                          [v[2] for v in variants])
        for i, (variant, part) in enumerate(zip(variants, parts)):
            ad_id = ad_ids.setdefault((c, g, i), str(7_000_000_000 + len(ad_ids) * 137))
            slug = "buty-trailowe" if "trail" in c.lower() else "buty-do-biegania"
            headline = variant[4] if "Brand" not in c else f"Biegosfera – oficjalny sklep{' (B)' if i else ''}"
            rows.append([c, g, ad_id, "Responsive search ad", variant[3], headline,
                         "Darmowa dostawa od 199 zł", f"https://www.biegosfera.pl/{slug}", d.isoformat(),
                         *en_metrics(part)])
    _write("ads.csv", ["Campaign", "Ad group", "Ad ID", "Ad type", "Ad strength", "Headline 1", "Headline 2",
                       "Final URL", "Day", *en_head], rows)

    # ------------------------------------------------ devices.csv (EN)
    rows = []
    for (d, c), m in sorted(campaign_rows.items()):
        parts = split_row(m, [x[1] for x in DEVICES], [x[2] for x in DEVICES], [x[3] for x in DEVICES],
                          [x[4] for x in DEVICES])
        for (name, *_), part in zip(DEVICES, parts):
            rows.append([d.isoformat(), c, name, *en_metrics(part)])
    _write("devices.csv", ["Day", "Campaign", "Device", *en_head], rows)

    # ------------------------------------------------ hour_of_day.csv (PL, poziom konta)
    daily: dict = {}
    for (d, c), m in campaign_rows.items():
        daily[d] = daily.get(d, 0) + m
    rows = []
    for d, m in sorted(daily.items()):
        parts = split_row(m, HOUR_WEIGHTS, HOUR_WEIGHTS, [1.0] * 24, HOUR_CVR)
        for hour, part in enumerate(parts):
            rows.append([d.isoformat(), PL_DAYS[d.weekday()], str(hour), *pl_metrics(part)])
    _write("hour_of_day.csv", ["Dzień", "Dzień tygodnia", "Godzina", *pl_head], rows)

    # ------------------------------------------------ locations.csv (PL, poziom konta)
    rows = []
    names = list(REGIONS)
    for d, m in sorted(daily.items()):
        w = [REGIONS[n][0] for n in names]
        parts = split_row(m, w, w, [1.0] * len(w), [REGIONS[n][1] for n in names])
        for name, part in zip(names, parts):
            rows.append([d.isoformat(), "Polska", name, *pl_metrics(part)])
    _write("locations.csv", ["Dzień", "Kraj/region", "Region (lokalizacja użytkownika)", *pl_head], rows,
           total=["Razem: lokalizacje", "", "", *pl_metrics(sum(daily.values()))])

    # ------------------------------------------------ landing_pages.csv (EN, kampanie w sieci wyszukiwania)
    search_daily: dict = {}
    for (d, c), m in campaign_rows.items():
        if c in search_campaigns:
            search_daily[d] = search_daily.get(d, 0) + m
    rows = []
    pages = list(LANDING_PAGES)
    for d, m in sorted(search_daily.items()):
        w = [LANDING_PAGES[p][0] for p in pages]
        parts = split_row(m, w, w, [1.0] * len(w), [LANDING_PAGES[p][1] for p in pages])
        for page, part in zip(pages, parts):
            _, _, mobile, speed = LANDING_PAGES[page]
            rows.append([f"https://www.biegosfera.pl{page}", d.isoformat(), *en_metrics(part)[:4],
                         f"{jitter(mobile, 0.02) * 100:.2f}%", str(speed)])
    _write("landing_pages.csv", ["Landing page", "Day", "Impr.", "Clicks", "Cost", "Conversions",
                                 "Mobile-friendly click rate", "Mobile speed score"], rows)

    # ------------------------------------------------ conversion_actions.csv (PL)
    rows = []
    for (d, c), m in sorted(campaign_rows.items()):
        conv, value = m[3], m[4]
        parts = split(conv, [a[2] for a in CONVERSION_ACTIONS])
        for (name, category, _, has_value), n in zip(CONVERSION_ACTIONS, parts):
            if n > 0:
                rows.append([d.isoformat(), c, name, category, fmt_pl(n), fmt_pl(value if has_value else 0)])
    _write("conversion_actions.csv", ["Dzień", "Kampania", "Działanie powodujące konwersję",
                                      "Kategoria działania powodującego konwersję", "Konwersje",
                                      "Wartość konw."], rows)

    # ------------------------------------------------ auction_insights.csv (PL, bez daty: ostatnie 30 dni)
    rows = []
    for c in search_campaigns:
        own_share = IMPRESSION_SHARE[c][0]
        rows.append(["Ty", c, pct_pl(jitter(own_share)), "--", "--", pct_pl(jitter(0.7)), pct_pl(jitter(0.3)), "--"])
        for domain, (share, overlap, above, top, abs_top, outrank) in COMPETITORS.items():
            if c == "Search | Brand" and domain != "runmarket.pl":
                continue
            cells = [jitter(share), jitter(overlap), jitter(above), jitter(top), jitter(abs_top), jitter(outrank)]
            share_txt = "< 10%" if cells[0] < 0.1 else pct_pl(cells[0])
            rows.append([domain, c, share_txt, *[pct_pl(x) for x in cells[1:]]])
    _write("auction_insights.csv", ["Domena wyświetlanego URL-a", "Kampania", "Udział w wyświetleniach",
                                    "Współczynnik nakładania się", "Współczynnik pozycji powyżej",
                                    "Współczynnik wyświetleń u góry strony",
                                    "Współczynnik wyświetleń na najwyższej pozycji na stronie",
                                    "Udział w wygranych aukcjach"], rows,
           preamble=["Statystyki aukcji", f"{SPLIT:%d.%m.%Y} - {end:%d.%m.%Y}"])

    # ------------------------------------------------ audiences.csv (PL, obserwacja w kampaniach Search)
    rows = []
    for (d, c), m in sorted(campaign_rows.items()):
        if c not in search_campaigns:
            continue
        impr, clicks, cost, conv, value = m
        for name, share, cvr_m in AUDIENCES:
            s_clicks = float(rng2.binomial(int(clicks), share))
            s_impr = max(float(rng2.binomial(int(impr), share)), s_clicks)
            cvr = conv / clicks if clicks else 0.0
            s_conv = float(rng2.binomial(int(s_clicks), min(cvr * cvr_m, 1.0))) if s_clicks else 0.0
            s_cost = round(cost * s_clicks / clicks, 2) if clicks else 0.0
            s_value = round(value / conv * s_conv, 2) if conv else 0.0
            rows.append([d.isoformat(), c, name, *pl_metrics([s_impr, s_clicks, s_cost, s_conv, s_value])])
    _write("audiences.csv", ["Dzień", "Kampania", "Segment odbiorców", *pl_head], rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    term_rows = []
    campaign_rows = {}
    hidden_rows = {}

    for offset in range(DAYS):
        d = START + timedelta(days=offset)
        recent = d >= SPLIT
        factor = day_factor(d)

        for campaign, terms in SEARCH_CAMPAIGNS.items():
            totals = np.zeros(5)
            for term, ad_group, keyword, match, impr, ctr, cpc, cvr, recent_only in terms:
                if recent_only and not recent:
                    continue
                ctr_m, cvr_m = modifiers(campaign, term, recent)
                row = simulate(impr, ctr * ctr_m, cpc, cvr * cvr_m, factor)
                if row[0] == 0:
                    continue
                totals += row
                term_rows.append((term, match, "None", campaign, ad_group, keyword, d, *row))
            # Hasła ukryte przez Google (ruch "inne") – ok. 12% ponad sumę widocznych haseł.
            hidden = simulate(totals[0] * 0.12, 0.04, 1.8, 0.02, 1.0)
            hidden_rows[(d, campaign)] = np.array(hidden, dtype=float)
            totals += hidden
            campaign_rows[(d, campaign)] = totals

        for campaign, (impr, ctr, cpc, cvr) in OTHER_CAMPAIGNS.items():
            if campaign == "Display | Remarketing" and recent:
                cvr = 0.0
            campaign_rows[(d, campaign)] = np.array(simulate(impr, ctr, cpc, cvr, factor), dtype=float)

    end = START + timedelta(days=DAYS - 1)

    # ---------------------------------------------------------------- campaign_daily.csv (PL)
    path = OUT_DIR / "campaign_daily.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("Raport kampanii – dziennie\n")
        fh.write(f"{START:%d.%m.%Y} - {end:%d.%m.%Y}\n")
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        writer.writerow([
            "Dzień", "Kampania", "Typ kampanii", "Stan kampanii", "Kod waluty", "Wyświetlenia",
            "Kliknięcia", "CTR", "Śr. CPC", "Koszt", "Konwersje", "Wartość konw.", "Koszt/konw.",
            "Udział w wyświetleniach w sieci wyszukiwania",
            "Utracony udział w wyświetleniach w sieci wyszukiwania (budżet)",
            "Utracony udział w wyświetleniach w sieci wyszukiwania (ranking)",
        ])
        grand = np.zeros(5)
        for (d, campaign), (impr, clicks, cost, conv, value) in sorted(campaign_rows.items()):
            grand += (impr, clicks, cost, conv, value)
            ctr = ratio(clicks, impr)
            cpc = ratio(cost, clicks)
            cpa = ratio(cost, conv)
            writer.writerow([
                d.isoformat(), campaign, CAMPAIGN_TYPES_PL[campaign], "Włączona", "PLN",
                fmt_pl(impr, 0), fmt_pl(clicks, 0),
                f"{fmt_pl(ctr * 100)}%" if ctr is not None else "--",
                fmt_pl(cpc) if cpc is not None else "--",
                fmt_pl(cost), fmt_pl(conv), fmt_pl(value),
                fmt_pl(cpa) if cpa is not None else "0,00",
                *impression_share_cells(campaign),
            ])
        writer.writerow([
            "Razem: konto", "", "", "", "PLN", fmt_pl(grand[0], 0), fmt_pl(grand[1], 0),
            f"{fmt_pl(grand[1] / grand[0] * 100)}%", fmt_pl(grand[2] / grand[1]), fmt_pl(grand[2]),
            fmt_pl(grand[3]), fmt_pl(grand[4]), fmt_pl(grand[2] / max(grand[3], 1)), "--", "--", "--",
        ])
    print(f"Zapisano {path} ({len(campaign_rows)} wierszy)")

    # ---------------------------------------------------------------- search_terms_daily.csv (EN)
    path = OUT_DIR / "search_terms_daily.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("Search terms report\n")
        fh.write(f"{START:%B %-d, %Y} - {end:%B %-d, %Y}\n")
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        writer.writerow([
            "Search term", "Match type", "Added/Excluded", "Campaign", "Ad group", "Keyword", "Day",
            "Currency code", "Impr.", "Clicks", "CTR", "Avg. CPC", "Cost", "Conversions", "Conv. value",
        ])
        grand = np.zeros(5)
        for term, match, added, campaign, ad_group, keyword, d, impr, clicks, cost, conv, value in sorted(
            term_rows, key=lambda r: (r[6], r[3], r[0])
        ):
            grand += (impr, clicks, cost, conv, value)
            ctr = ratio(clicks, impr)
            cpc = ratio(cost, clicks)
            writer.writerow([
                term, match, added, campaign, ad_group, keyword, d.isoformat(), "PLN",
                fmt_en(impr, 0), fmt_en(clicks, 0),
                f"{ctr * 100:.2f}%" if ctr is not None else "--",
                fmt_en(cpc) if cpc is not None else "--",
                fmt_en(cost), fmt_en(conv), fmt_en(value),
            ])
        writer.writerow([
            "Total: Search terms", "", "", "", "", "", "", "PLN", fmt_en(grand[0], 0), fmt_en(grand[1], 0),
            f"{grand[1] / grand[0] * 100:.2f}%", fmt_en(grand[2] / grand[1]), fmt_en(grand[2]),
            fmt_en(grand[3]), fmt_en(grand[4]),
        ])
    print(f"Zapisano {path} ({len(term_rows)} wierszy)")

    write_optional_reports(campaign_rows, term_rows, hidden_rows, end)


if __name__ == "__main__":
    main()
