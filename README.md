# Campaign OS v0.1-alpha

Aplikacja Streamlit do analizy kampanii Google Ads na podstawie eksportów CSV.
Wgrywasz raporty, wybierasz zakres dat, a Campaign OS liczy KPI, porównuje je z poprzednim
analogicznym okresem, analizuje wyszukiwane hasła i generuje rekomendacje z konfigurowalnego Rule Engine.

> Zakres v0.1-alpha: tylko pliki CSV. Bez Google Ads API, GA4, Supabase, AI API i Change Logu.

## Szybki start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Aplikacja otworzy się pod `http://localhost:8501`. Domyślnie korzysta z **danych przykładowych**
(60 dni fikcyjnego sklepu z butami do biegania). Aby użyć własnych danych, wybierz w panelu bocznym
**Własne pliki CSV** i wgraj raporty.

## Obsługiwane raporty

| Raport | Wymagane kolumny | Opcjonalne |
|---|---|---|
| `campaign_daily.csv` | Dzień/Day, Kampania/Campaign, Wyświetlenia/Impr., Kliknięcia/Clicks, Koszt/Cost | Konwersje/Conversions, Wartość konw./Conv. value, Typ kampanii, Stan kampanii, Kod waluty |
| `search_terms_daily.csv` | jw. + Wyszukiwane hasło/Search term | Grupa reklam/Ad group, Typ dopasowania/Match type, Słowo kluczowe/Keyword |

Jak wyeksportować z Google Ads: *Raporty → Kampanie* (lub *Wyszukiwane hasła*), dodaj segment
**Dzień**, a następnie *Pobierz → CSV* lub *CSV (Excel)*.

### Normalizacja

Raporty eksportowane bezpośrednio z polskiej (lub angielskiej) wersji Google Ads wgrywasz bez
zmieniania nazw kolumn. Typ raportu jest określany automatycznie:

- **raport Search Terms** – gdy są kolumny `date` + `campaign` + `search_term`,
- **raport kampanii** – gdy są co najmniej `date` + `campaign`.

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
- kolumny API (`segments.date`, `metrics.cost_micros` → koszt ÷ 1 000 000).

Kolumny pochodne (CTR, Śr. CPC, Koszt/konw.) są pomijane – Campaign OS liczy je sam z wartości bazowych.
Duplikaty (ten sam dzień/kampania/hasło) są sumowane, można więc wgrać kilka plików jednocześnie.
Szczegóły mapowania, ostrzeżenia i podgląd znormalizowanych danych są w zakładce **Dane**.

Jeśli wgrasz tylko raport search terms, KPI zostaną policzone z niego (z ostrzeżeniem, że nie obejmuje
ruchu bez haseł, np. PMax/Display).

## Funkcje

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
  filtrowanie po priorytecie i kategorii, widok kart lub tabeli, eksport CSV.
- **Rule Engine** – lista reguł z liczbą trafień, edytor YAML działający na żywo (w sesji),
  tester warunków na danych kampanii/haseł.

Progi analizy można zmieniać w panelu bocznym (*Progi analizy*); domyślne wartości są w `config/settings.yaml`.

## Rule Engine

Reguły są w `config/rules.yaml`:

```yaml
rules:
  - id: CMP_CPA_INCREASE
    name: Wzrost CPA vs poprzedni okres
    entity: campaign            # campaign | search_term
    condition: conversions_prev >= 3 and conversions >= 1 and cpa_change >= 0.3
    severity: high              # high | medium | low
    category: trend
    action: investigate_cpa
    message: "CPA kampanii „{campaign}” wzrósł o {cpa_change:+.0%} ({cpa_prev:,.2f} → {cpa:,.2f} {currency})."
    recommendation: "Sprawdź nowe wyszukiwane hasła, zmiany stawek i konkurencję."
    impact: cost - conversions * cpa_prev   # szacowana kwota (opcjonalnie)
```

- Warunki to wyrażenia z operatorami `and/or/not`, porównaniami (także łańcuchowymi, np. `10 <= cost < 100`),
  `+ - * /` oraz funkcjami `abs/min/max`. Są interpretowane z drzewa AST – **nie** przez `eval`,
  więc plik reguł nie może wykonać dowolnego kodu.
- Zmienne: metryki encji (`cost`, `clicks`, `ctr`, `cpa`, …), dla kampanii także `<metryka>_prev`,
  `<metryka>_change` (0.3 = +30%), `cost_share`, `cpa_vs_target`; dla haseł `is_wasted`, `is_high_performer`;
  kontekst: `account_cpa`, `account_ctr`, `target_cpa`, `wasted_min_cost`, `period_days`, `currency` itd.
- Porównanie z brakującą wartością (np. brak poprzedniego okresu, CPA przy 0 konwersjach) daje fałsz.
- Błędne reguły są pomijane, a błędy wyświetlane w zakładce Rule Engine – aplikacja działa dalej.
- W komunikatach `{pole:,.2f}` formatuje liczby po polsku (`1 234,56`).

Domyślny zestaw: wasted spend, high performers, hasła z wysokim CPA i niskim CTR; kampanie bez konwersji,
wzrost CPA, spadek konwersji, spadek CTR, CPA powyżej celu, możliwość skalowania i skok wydatków.

## Struktura projektu

```
app.py                      # UI Streamlit
campaign_os/
  ingest.py                 # odczyt CSV, rozpoznanie i normalizacja kolumn PL/EN
  metrics.py                # KPI, okresy, porównania
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

`data/sample/` zawiera 60 dni (02.08–30.09.2026) dla 6 kampanii:

- `campaign_daily.csv` – format eksportu **PL** (nagłówki PL, `1 234,56`, wiersz „Razem”),
- `search_terms_daily.csv` – format eksportu **EN** (nagłówki EN, `1,234.56`, wiersz „Total”).

Dane zawierają celowe wzorce do wykrycia: hasła marnujące budżet (np. „darmowe buty do biegania”),
high performers, wzrost CPA w kampanii trailowej, spadek CTR w kampanii konkurencyjnej i remarketing
bez konwersji w ostatnich 30 dniach. Regeneracja (deterministyczna): `python scripts/generate_sample_data.py`.

## Testy

```bash
pip install -r requirements-dev.txt
pytest
```

Testy obejmują normalizację (PL/EN, UTF-16/TSV, CP1250, formaty liczb i dat, wiersze podsumowań),
metryki i okresy, Rule Engine (w tym odrzucanie niebezpiecznych wyrażeń), pełny pipeline na danych
przykładowych oraz testy dymne UI (`streamlit.testing`).
