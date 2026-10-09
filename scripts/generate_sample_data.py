"""Generuje przykładowe raporty Google Ads (60 dni) do data/sample/.

* campaign_daily.csv     – eksport w wersji polskiej (nagłówki PL, liczby "1 234,56", wiersz "Razem")
* search_terms_daily.csv – eksport w wersji angielskiej (nagłówki EN, liczby "1,234.56", wiersz "Total")

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


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    term_rows = []
    campaign_rows = {}

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
            ])
        writer.writerow([
            "Razem: konto", "", "", "", "PLN", fmt_pl(grand[0], 0), fmt_pl(grand[1], 0),
            f"{fmt_pl(grand[1] / grand[0] * 100)}%", fmt_pl(grand[2] / grand[1]), fmt_pl(grand[2]),
            fmt_pl(grand[3]), fmt_pl(grand[4]), fmt_pl(grand[2] / max(grand[3], 1)),
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


if __name__ == "__main__":
    main()
