# Campaign OS v0.1-alpha

Aplikacja Streamlit do analizy kampanii Google Ads Search / SEM na podstawie eksportów CSV.
Wgrywasz raporty, wybierasz zakres dat, a Campaign OS liczy KPI, porównuje je z poprzednim
analogicznym okresem, pokazuje pokrycie danych SEM, analizuje słowa kluczowe, hasła, reklamy, segmenty
i konkurencję, a następnie generuje rekomendacje z konfigurowalnego Rule Engine – każdą z **evidence**.

> Zakres: wyłącznie pliki CSV. Bez Google Ads API, GA4, Supabase, AI API i Change Logu.
> Dane żyją tylko w pamięci bieżącej sesji (brak warstwy persistence). Celem tej wersji jest
> ustabilizowanie pełnego modelu danych SEM (`campaign_os/schema.py`) przed zaprojektowaniem bazy.

## Szybki start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Aplikacja otworzy się pod `http://localhost:8501`. Domyślnie korzysta z **danych przykładowych – pełny SEM**
(60 dni fikcyjnego sklepu z butami do biegania, wszystkie 12 typów raportów). Wariant **podstawowy**
zawiera tylko raporty kampanii i haseł. Aby użyć własnych danych, wybierz **Własne pliki CSV** i wgraj
dowolną liczbę raportów naraz.

Aplikacja ma dwie strony: **Analiza** oraz **Data Requirements** (`/data-requirements`) – opis, jakie raporty
można zaimportować, które są wymagane, a które opcjonalne, i jakie minimalne kolumny powinny zawierać
(z szablonami nagłówków PL/EN do pobrania).

## Obsługiwane raporty

Typ raportu jest rozpoznawany automatycznie po nazwach kolumn (PL/EN). Raporty podstawowe są wymagane,
pozostałe – opcjonalne; każdy kolejny raport odblokowuje dodatkowe analizy.

| Raport | Status | Rozpoznawany po | Minimalne kolumny |
|---|---|---|---|
| Campaign | **wymagany** | Dzień + Kampania | Dzień, Kampania, Wyświetlenia, Kliknięcia, Koszt (zalecane: Konwersje, Search IS, Lost IS budżet/ranking) |
| Search Terms | **wymagany** | Dzień + Kampania + Wyszukiwane hasło | jw. + Wyszukiwane hasło |
| Ad Groups | opcjonalny | Grupa reklam | Kampania, Grupa reklam, Wyświetlenia, Kliknięcia, Koszt |
| Keywords | opcjonalny | Słowo kluczowe | Kampania, Grupa reklam, Słowo kluczowe, metryki (zalecane: Wynik jakości i składowe, Search IS) |
| Ads / RSA | opcjonalny | Identyfikator reklamy / Nagłówek 1 / Siła reklamy | Kampania, Grupa reklam, Identyfikator reklamy lub Nagłówek 1, metryki |
| Devices | opcjonalny | Urządzenie | Urządzenie, Wyświetlenia, Kliknięcia, Koszt |
| Time | opcjonalny | Godzina / Dzień tygodnia | Godzina lub Dzień tygodnia, metryki |
| Locations | opcjonalny | Lokalizacja / Region / Miasto / Kraj | lokalizacja, metryki |
| Landing Pages | opcjonalny | Strona docelowa | Strona docelowa, Kliknięcia, Koszt |
| Conversions | opcjonalny | Działanie powodujące konwersję | Działanie powodujące konwersję, Konwersje |
| Auction Insights | opcjonalny | Domena wyświetlanego URL-a | Domena, Udział w wyświetleniach |
| Audiences | opcjonalny | Segment odbiorców / Wiek / Płeć / Dochód | segment, metryki |

W raportach opcjonalnych data jest opcjonalna: raport z kolumną **Dzień** jest filtrowany do wybranego
okresu, raport bez daty (typowo Auction Insights) jest analizowany za cały okres eksportu – i ta informacja
trafia do evidence. Pełne listy kolumn i ścieżki eksportu: strona **Data Requirements**.

### Normalizacja

Raporty eksportowane bezpośrednio z polskiej (lub angielskiej) wersji Google Ads wgrywasz bez
zmieniania nazw kolumn. Typ raportu jest określany automatycznie:

- **raport Search Terms** – gdy są kolumny `date` + `campaign` + `search_term`,
- **raport kampanii** – gdy są co najmniej `date` + `campaign` i żaden inny wymiar,
- **raporty opcjonalne** – po charakterystycznym wymiarze; kolejność sprawdzania jest od najbardziej
  specyficznych (np. raport haseł zawiera też słowo kluczowe i grupę reklam, więc jest sprawdzany pierwszy).

Jeśli w raporcie brakuje daty, aplikacja pokazuje komunikat: *„Raport nie zawiera wymiaru daty.
W Google Ads dodaj: Segmenty → Czas → Dzień i ponownie wyeksportuj raport.”*
Po imporcie w panelu bocznym widać mapowanie kolumn, np. `Dzień → date`, `Kampania → campaign`, `Koszt → cost`.

Najważniejsze aliasy (pełna lista w `config/column_aliases.yaml`):

| Kolumna | PL | EN |
|---|---|---|
| `date` | Dzień, Data | Day, Date |
| `campaign` / `campaign_id` | Kampania / Identyfikator kampanii | Campaign / Campaign ID |
| `ad_group` | Grupa reklam | Ad group |
| `keyword` | Słowo kluczowe | Keyword |
| `search_term` | Wyszukiwane hasło, Wyszukiwane hasła | Search term |
| `match_type` | Typ dopasowania | Match type |
| `impressions` / `clicks` / `cost` | Wyświetlenia (Wyświetl.) / Kliknięcia / Koszt | Impressions (Impr.) / Clicks / Cost |
| `conversions` / `conversion_value` | Konwersje / Wartość konwersji (Wartość konw.) | Conversions / Conversion value (Conv. value) |

Obsługiwane są:

- nagłówki **PL i EN** – bez względu na wielkość liter, zbędne spacje (także twarde) i polskie znaki (`Dzień` = `DZIEN` = `  dzień `),
- kodowania UTF-8, UTF-8 z BOM, **UTF-16** („CSV (Excel)”), CP1250,
- separatory `,` `;` i tabulator,
- wiersze tytułu/zakresu dat nad tabelą oraz wiersze podsumowań („Razem”, „Total”) na końcu,
- liczby `1 234,56 zł`, `1,234.56`, `12,5%`, `--` (separator dziesiętny wykrywany per kolumna),
- daty `YYYY-MM-DD`, `DD.MM.YYYY` oraz `Sep 1, 2026`, `1 wrz 2026`,
- kolumny API (`segments.date`, `metrics.cost_micros` → koszt ÷ 1 000 000),
- udziały `45,23%`, `< 10%`, `> 90%` (→ 0,10 / 0,90), Wynik jakości `--` = brak danych (nie 0),
- oceny QS (`Powyżej średniej` / `Above average` → `above` …), siła reklamy, urządzenia, dni tygodnia i godziny PL/EN.

Metryki nieaddytywne są agregowane poprawnie: Search IS i Lost IS – średnia ważona wyświetleniami
kwalifikującymi się (wyświetlenia ÷ IS), Quality Score – średnia ważona wyświetleniami.

Kolumny pochodne (CTR, Śr. CPC, Koszt/konw.) są pomijane – Campaign OS liczy je sam z wartości bazowych.
Duplikaty (ten sam dzień/kampania/hasło) są sumowane, można więc wgrać kilka plików jednocześnie.
Szczegóły mapowania, ostrzeżenia i podgląd znormalizowanych danych są w zakładce **Dane**.

Jeśli wgrasz tylko raport search terms, KPI zostaną policzone z niego (z ostrzeżeniem, że nie obejmuje
ruchu bez haseł, np. PMax/Display).

## Funkcje

- **SEM DATA COVERAGE** – po imporcie widać, które z 12 typów raportów są dostępne (✓ / missing),
  z liczbą wierszy i zakresem dat (panel boczny + zakładka *SEM Coverage & Analiza*).
- **BASIC / ADVANCED / FULL SEM ANALYSIS** – 15 modułów analizy pogrupowanych w trzy poziomy. Moduł jest
  dostępny tylko, gdy wgrano jego raport (i wymagane kolumny, np. Wynik jakości); niedostępne moduły
  pokazują, czego brakuje, i **nie generują diagnoz**.

  | Poziom | Moduły |
  |---|---|
  | BASIC | campaign performance, search term waste, search term opportunities |
  | ADVANCED | ad group performance, keyword performance, Quality Score (Expected CTR, Ad Relevance, LP Experience), ad performance, device differences, day/hour differences |
  | FULL SEM | Search Impression Share (Lost IS budget/rank), geographic, landing pages, conversion action composition, Auction Insights / competitive pressure, audiences / demographics |

- **Dashboard** – Spend, Impressions, Clicks, CTR, CPC, Conversions, CVR, CPA (+ Conv. value, ROAS)
  ze zmianą vs poprzedni okres; trend dzienny z nałożonym poprzednim okresem; tabela kampanii ze zmianami;
  spend wg kampanii i wykres CPA vs konwersje.
- **Zakres dat** – presety 7/14/30 dni, cały zakres lub własny. **Poprzedni analogiczny okres** to ta sama
  liczba dni bezpośrednio przed wybranym zakresem (np. 01–30.09 → 02–31.08). Gdy brak danych dla
  poprzedniego okresu lub są niepełne, aplikacja to sygnalizuje.
- **Search terms** – agregacja haseł w zakresie, segmentacja (Wasted spend / High performer / Bez konwersji /
  Neutral), gotowe listy wykluczeń i nowych słów kluczowych do skopiowania, wykres koszt vs konwersje,
  analiza n-gramów, eksport CSV.
  - **Wasted spend**: 0 konwersji, koszt ≥ `wasted_min_cost` i kliknięcia ≥ `wasted_min_clicks`.
  - **High performer**: konwersje ≥ `high_performer_min_conversions` i CPA ≤ docelowy CPA × `high_performer_max_cpa_ratio`.
  - Docelowy CPA = wartość z ustawień, a gdy 0 – średni CPA konta w wybranym okresie.
- **Rekomendacje** – wyniki Rule Engine posortowane wg priorytetu (high → low) i szacowanego wpływu (PLN),
  każda z **evidence** (liczby, raport źródłowy, okres danych); filtrowanie po priorytecie, kategorii
  i raporcie źródłowym, widok kart lub tabeli, eksport CSV.
- **Rule Engine** – status każdej reguły (uruchomiona / brak raportu / brak kolumn / błąd), liczba
  rekomendacji i kandydatów odrzuconych z powodu **za małej próby**, edytor YAML działający na żywo (w sesji),
  tester warunków dla każdej dostępnej encji.

Progi analizy można zmieniać w panelu bocznym (*Progi analizy*); domyślne wartości są w `config/settings.yaml`.

## Rule Engine

Reguły są w `config/rules.yaml`:

```yaml
rules:
  - id: CMP_CPA_INCREASE
    name: Wzrost CPA vs poprzedni okres
    entity: campaign            # campaign | search_term | ad_group | keyword | ad | device | time_slot |
                                # location | audience | landing_page | conversion_action | competitor
    condition: cpa_change >= 0.3 and (cvr_change_z <= -z_threshold or cpc_change >= 0.3)
    sample: conversions_prev >= min_conversions and conversions >= min_conversions   # minimalna próba
    severity: high              # high | medium | low
    category: trend
    message: "CPA kampanii „{campaign}” wzrósł o {cpa_change:+.0%} ({cpa_prev:,.2f} → {cpa:,.2f} {currency})."
    evidence: "CVR {cvr_prev:.2%} → {cvr:.2%} (z = {cvr_change_z:.1f}), CPC {cpc_prev:,.2f} → {cpc:,.2f}"
    recommendation: "Sprawdź nowe wyszukiwane hasła, zmiany stawek i konkurencję."
    impact: cost - conversions * cpa_prev   # szacowana kwota (opcjonalnie)
```

Zasady:

- **Brak raportu = brak diagnozy.** Reguła działa tylko na ramce swojej encji, a ta powstaje wyłącznie
  z raportu, który ją opisuje. Gdy raport nie ma potrzebnej kolumny (np. `quality_score`), reguła jest
  pomijana (status „brak kolumn”), a nie zgaduje.
- **Minimalna próba (`sample`).** Obiekty spełniające warunek, ale z próbą poniżej progu
  (`min_clicks` 30, `min_impressions` 300, `min_conversions` 3 – zmienne w panelu bocznym), nie dostają
  rekomendacji; są tylko liczone jako „za mała próba”.
- **Istotność.** Segmenty (urządzenia, godziny, dni, lokalizacje, odbiorcy, strony, grupy reklam, słowa,
  reklamy w grupie) są porównywane z resztą raportu testem z dla dwóch proporcji (`cvr_z`, `ctr_z`).
  Próg `z_crit` zawiera poprawkę Bonferroniego na liczbę porównywanych segmentów, więc 24 godziny czy
  16 województw nie dają „istotnych” różnic przez przypadek.
- **Evidence.** Każda reguła ma szablon `evidence` z liczbami; do każdej diagnozy dołączany jest raport
  źródłowy i okres danych.

- Warunki to wyrażenia z operatorami `and/or/not`, porównaniami (także łańcuchowymi, np. `10 <= cost < 100`),
  `+ - * /` oraz funkcjami `abs/min/max`. Są interpretowane z drzewa AST – **nie** przez `eval`,
  więc plik reguł nie może wykonać dowolnego kodu.
- Zmienne dostępne dla każdej encji są opisane w nagłówku `config/rules.yaml` (m.in. `quality_score`,
  `expected_ctr == "below"`, `search_lost_is_budget`, `cpa_index`, `cvr_z`, `z_crit`, `expected_conversions`,
  `bid_adjustment`, `is_micro`, `overlap_rate`, `position_above_rate`).
- Porównanie z brakującą wartością (np. brak poprzedniego okresu, CPA przy 0 konwersjach) daje fałsz.
- Błędne reguły są pomijane, a błędy wyświetlane w zakładce Rule Engine – aplikacja działa dalej.
- W komunikatach `{pole:,.2f}` formatuje liczby po polsku (`1 234,56`).

Domyślny zestaw (44 reguły): kampanie (CMP_), Impression Share (IS_), wyszukiwane hasła (ST_), grupy
reklam (AG_), słowa kluczowe i Quality Score (KW_), reklamy (AD_), urządzenia (DEV_), dni/godziny (TIME_),
lokalizacje (LOC_), odbiorcy (AUD_), strony docelowe (LP_), konwersje (CONV_), konkurencja (AI_).

## Struktura projektu

```
app.py                      # UI Streamlit (strona Analiza + nawigacja)
views/data_requirements.py  # strona DATA REQUIREMENTS (generowana z schema.py)
campaign_os/
  schema.py                 # model danych SEM: pola, typy raportów, moduły, poziomy analizy
  ingest.py                 # odczyt CSV, rozpoznanie typu raportu i normalizacja kolumn PL/EN
  sem.py                    # coverage, dostępność modułów, ramki encji, testy istotności segmentów
  metrics.py                # KPI, okresy, porównania, agregacja z wagami (IS, QS)
  search_terms.py           # agregacja haseł, wasted spend, high performers, n-gramy
  rules.py                  # Rule Engine (bezpieczny ewaluator wyrażeń)
  recommendations.py        # kontekst reguł, priorytetyzacja
  analysis.py               # pipeline: dane → wyniki
  formatting.py, config.py
config/
  column_aliases.yaml       # mapowanie nagłówków PL/EN
  rules.yaml                # reguły
  settings.yaml             # waluta, progi, domyślny zakres
data/sample/                # przykładowe raporty (60 dni)
scripts/generate_sample_data.py
tests/
```

## Dane przykładowe

`data/sample/` zawiera 60 dni (02.08–30.09.2026) dla 6 kampanii – po jednym pliku na każdy typ raportu,
na przemian w formacie eksportu **PL** (`1 234,56`, „Razem”) i **EN** (`1,234.56`, „Total”):

| Plik | Raport | Format |
|---|---|---|
| `campaign_daily.csv` | Campaign (z Search IS) | PL |
| `search_terms_daily.csv` | Search Terms | EN |
| `ad_groups.csv`, `keywords.csv` (z Wynikiem jakości) | Ad Groups, Keywords | PL |
| `ads.csv`, `devices.csv`, `landing_pages.csv` | Ads / RSA, Devices, Landing Pages | EN |
| `hour_of_day.csv`, `locations.csv`, `conversion_actions.csv`, `audiences.csv` | Time, Locations, Conversions, Audiences | PL |
| `auction_insights.csv` | Auction Insights (bez daty, ostatnie 30 dni, fikcyjne domeny) | PL |

Raporty opcjonalne są wyliczane z tych samych danych co raporty podstawowe (sumy są spójne).
Celowe wzorce do wykrycia: hasła marnujące budżet, high performers, wzrost CPA w kampanii trailowej,
spadek CTR w kampanii konkurencyjnej, remarketing bez konwersji, utrata IS przez budżet (Brand) i ranking,
niski Quality Score słów konkurencyjnych, słaba reklama RSA, gorszy CVR na telefonach, nocne godziny bez
konwersji, słaby segment odbiorców, wolna strona bloga o niskim CVR, mikrokonwersje „Wyświetlenie strony”
(~20% konwersji) i silny konkurent w aukcjach.
Regeneracja (deterministyczna): `python scripts/generate_sample_data.py`.

## Testy

```bash
pip install -r requirements-dev.txt
pytest
```

Testy obejmują normalizację (PL/EN, UTF-16/TSV, CP1250, formaty liczb i dat, wiersze podsumowań),
rozpoznawanie wszystkich 12 typów raportów (minimalne nagłówki PL i EN, kolejność rozpoznawania),
parsowanie udziałów / QS / kategorii, agregację ważoną, coverage i poziomy analizy, zasadę „brak raportu =
brak diagnozy”, progi próby, test z i poprawkę Bonferroniego, Rule Engine (w tym odrzucanie niebezpiecznych
wyrażeń), pełny pipeline na danych przykładowych oraz testy UI (`streamlit.testing`), także strony Data Requirements.
