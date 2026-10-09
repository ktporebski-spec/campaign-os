"""Wczytywanie i normalizacja raportów CSV z Google Ads (PL/EN).

Obsługiwane warianty eksportu:
* kodowanie UTF-8 (z BOM i bez), UTF-16 ("CSV dla Excela"), CP1250;
* separatory ``,`` ``;`` oraz tabulator;
* wiersze nagłówkowe raportu nad właściwą tabelą (tytuł, zakres dat);
* wiersze podsumowań ("Total:", "Razem", "Łącznie") na końcu pliku;
* liczby w formacie PL ("1 234,56 zł") i EN ("1,234.56"), wartości "--";
* daty ISO, ``dd.mm.yyyy``, ``dd/mm/yyyy`` oraz "Sep 1, 2026" / "1 wrz 2026".
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd

from campaign_os.config import ALIASES_PATH, load_yaml
from campaign_os.metrics import aggregate
from campaign_os.schema import (
    ADDITIVE, BASE_ADDITIVE, CATEGORIES, CATEGORY_KIND, CATEGORY_VALUES, DAY_LABELS, DAY_NAMES,
    DETECTION_ORDER, DEVICE_LABELS, DIMENSIONS as TEXT_DIMENSIONS, MICRO_CONVERSION_PATTERNS, REPORT_BY_KEY,
    REPORTS, SCORES, SHARES,
)

CAMPAIGN_DAILY = "campaign_daily"
SEARCH_TERMS = "search_terms_daily"

REPORT_LABELS = {r.key: r.label for r in REPORTS}

METRIC_COLUMNS = list(BASE_ADDITIVE)
# Kolumny zawsze obecne w raportach podstawowych (zgodność z v0.1).
CORE_DIMENSIONS = {
    CAMPAIGN_DAILY: ["date", "campaign", "campaign_id", "campaign_type", "campaign_status", "currency"],
    SEARCH_TERMS: [
        "date", "campaign", "ad_group", "search_term", "match_type", "keyword",
        "added_excluded", "currency",
    ],
}
DIMENSIONS = CORE_DIMENSIONS
REQUIRED = {r.key: [alt[0] for alt in r.required] for r in REPORTS}
GROUP_KEYS = {r.key: list(r.group_keys) for r in REPORTS}

TOTAL_ROW_PATTERN = re.compile(
    r"^\s*(total|totals|razem|łącznie|lacznie|suma|ogółem|ogolem)\b", re.IGNORECASE
)

PL_MONTHS = {
    "sty": 1, "lut": 2, "mar": 3, "kwi": 4, "maj": 5, "cze": 6,
    "lip": 7, "sie": 8, "wrz": 9, "paź": 10, "paz": 10, "lis": 11, "gru": 12,
}


MISSING_DATE_MESSAGE = (
    "Raport nie zawiera wymiaru daty. W Google Ads dodaj: Segmenty → Czas → Dzień "
    "i ponownie wyeksportuj raport."
)
MISSING_CAMPAIGN_MESSAGE = (
    "Raport nie zawiera kolumny kampanii (Kampania / Campaign). Dodaj ją do raportu "
    "w Google Ads i ponownie wyeksportuj raport."
)


class IngestError(ValueError):
    """Plik nie mógł zostać rozpoznany jako obsługiwany raport."""


@dataclass
class IngestResult:
    df: pd.DataFrame
    report_type: str
    language: str
    column_mapping: dict[str, str]
    ignored_columns: list[str]
    warnings: list[str] = field(default_factory=list)
    source_name: str = ""

    def mapping_lines(self) -> list[str]:
        """Mapowanie w formie czytelnej dla użytkownika, np. "Dzień → date"."""
        return [f"{src} → {dst}" for src, dst in self.column_mapping.items()]


# --------------------------------------------------------------------------- aliasy


def clean_header(text: str) -> str:
    """Nagłówek do wyświetlenia: bez BOM, twardych spacji i zbędnych odstępów."""
    text = str(text).replace("\ufeff", "").replace("\u00a0", " ").replace("\u202f", " ")
    return " ".join(text.split())


def normalize_header(text: str) -> str:
    """Klucz porównawczy nagłówka: małe litery, bez ogonków i interpunkcji."""
    text = str(text).replace("ł", "l").replace("Ł", "L")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


@lru_cache(maxsize=4)
def _alias_index(path: str) -> dict[str, tuple[str, str]]:
    """Zwraca {klucz_nagłówka: (kanoniczna_kolumna, język)}."""
    spec = load_yaml(Path(path)).get("columns", {})
    index: dict[str, tuple[str, str]] = {}
    for canonical, by_lang in spec.items():
        index[normalize_header(canonical)] = (canonical, "en")
        for lang, aliases in (by_lang or {}).items():
            for alias in aliases or []:
                index.setdefault(normalize_header(alias), (canonical, lang))
    return index


def map_columns(columns: list[str], aliases_path: Path = ALIASES_PATH):
    """Mapuje nagłówki na nazwy kanoniczne. Zwraca (mapping, ignored, language)."""
    index = _alias_index(str(aliases_path))
    mapping: dict[str, str] = {}
    ignored: list[str] = []
    votes = {"pl": 0, "en": 0}
    used: set[str] = set()
    for col in columns:
        hit = index.get(normalize_header(col))
        if hit and hit[0] not in used:
            mapping[col] = hit[0]
            used.add(hit[0])
            votes[hit[1]] = votes.get(hit[1], 0) + 1
        else:
            ignored.append(col)
    language = "pl" if votes.get("pl", 0) > votes.get("en", 0) else "en"
    return mapping, ignored, language


# --------------------------------------------------------------------------- odczyt pliku


def decode_bytes(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    # UTF-16 bez BOM: co drugi bajt zerowy.
    sample = raw[:200]
    if sample and sample.count(b"\x00") > len(sample) // 4:
        return raw.decode("utf-16-le" if sample[1:2] == b"\x00" else "utf-16-be")
    for enc in ("utf-8-sig", "cp1250"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _split_line(line: str, sep: str) -> list[str]:
    return next(csv.reader([line], delimiter=sep), [])


def _find_header(lines: list[str], aliases_path: Path) -> tuple[int, str]:
    """Szuka wiersza nagłówka (do 30 pierwszych linii) i separatora."""
    best = (-1, ",", 0)
    for idx, line in enumerate(lines[:30]):
        if not line.strip():
            continue
        for sep in ("\t", ";", ","):
            if sep not in line:
                continue
            cells = _split_line(line, sep)
            mapping, _, _ = map_columns(cells, aliases_path)
            score = len(mapping)
            if score > best[2]:
                best = (idx, sep, score)
    if best[2] < 2:
        raise IngestError(
            "Nie znaleziono wiersza nagłówka z rozpoznawalnymi kolumnami Google Ads "
            "(np. Dzień/Day, Kampania/Campaign, Kliknięcia/Clicks, Koszt/Cost)."
        )
    return best[0], best[1]


# --------------------------------------------------------------------------- liczby i daty


_NUM_CLEAN = re.compile(r"[^0-9,.\-]")


def _detect_decimal(values: pd.Series, language: str) -> str:
    sample = values.dropna().astype(str).str.replace(_NUM_CLEAN, "", regex=True)
    comma = sample.str.contains(r"\d,(?:\d{1,2}|\d{4,})$", regex=True).sum()
    dot = sample.str.contains(r"\d\.(?:\d{1,2}|\d{4,})$", regex=True).sum()
    both_comma_last = sample.str.contains(r"\.\d{3},\d+$", regex=True).sum()
    both_dot_last = sample.str.contains(r",\d{3}\.\d+$", regex=True).sum()
    comma += both_comma_last
    dot += both_dot_last
    if comma > dot:
        return ","
    if dot > comma:
        return "."
    return "," if language == "pl" else "."


def parse_numeric(values: pd.Series, language: str = "en") -> pd.Series:
    """Zamienia tekstowe wartości liczbowe (PL/EN, waluty, %, "--") na float."""
    if pd.api.types.is_numeric_dtype(values):
        return values.astype(float)
    decimal = _detect_decimal(values, language)
    text = values.astype(str).str.strip()
    negative = text.str.match(r"^\(.*\)$")  # księgowy zapis ujemnych: (12,50)
    text = text.str.replace(_NUM_CLEAN, "", regex=True)
    if decimal == ",":
        text = text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    else:
        text = text.str.replace(",", "", regex=False)
    out = pd.to_numeric(text.where(text.str.match(r"^-?\d*\.?\d+$"), None), errors="coerce")
    out = out.where(~negative, -out)
    return out.astype(float)


_DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y",
                 "%b %d, %Y", "%a, %b %d, %Y", "%d %b %Y", "%Y%m%d"]


def _replace_pl_months(text: pd.Series) -> pd.Series:
    def repl(match: re.Match) -> str:
        return f"{PL_MONTHS[match.group(1).lower()]:02d}"

    pattern = re.compile(r"\b(" + "|".join(PL_MONTHS) + r")[a-ząćęłńóśźż]*\.?", re.IGNORECASE)
    replaced = text.str.replace(pattern, repl, regex=True)
    # "1 09 2026" -> "1.09.2026"
    return replaced.str.replace(r"^(\d{1,2})\s+(\d{2})\s+(\d{4})$", r"\1.\2.\3", regex=True)


def parse_dates(values: pd.Series) -> pd.Series:
    """Parsuje daty, wybierając format, który rozpoznaje najwięcej wartości."""
    text = values.astype(str).str.strip()
    if text.str.contains(r"[a-ząćęłńóśźż]{3}", case=False, regex=True).any():
        text_pl = _replace_pl_months(text)
    else:
        text_pl = text
    best = None
    best_count = -1
    for candidate in (text, text_pl):
        for fmt in _DATE_FORMATS:
            parsed = pd.to_datetime(candidate, format=fmt, errors="coerce")
            count = int(parsed.notna().sum())
            if count > best_count:
                best, best_count = parsed, count
            if count == len(candidate):
                return parsed.dt.normalize()
    if best_count <= 0:
        best = pd.to_datetime(text, errors="coerce", dayfirst=True)
    return best.dt.normalize()


# --------------------------------------------------------------------------- główne API


def _has(cols: set[str], alternatives: tuple) -> bool:
    return any(a in cols for a in alternatives)


def detect_report_type(columns: list[str]) -> str:
    """Rozpoznaje typ raportu po kolumnach (kolejność: od najbardziej specyficznych).

    Raporty podstawowe: ``date + campaign + search_term`` → Search Terms, ``date + campaign`` → kampanie.
    Raporty opcjonalne rozpoznajemy po charakterystycznym wymiarze (słowo kluczowe, urządzenie,
    godzina, lokalizacja, strona docelowa, działanie konwersji, domena konkurenta, odbiorcy, grupa reklam).
    """
    cols = set(columns)
    for key in DETECTION_ORDER:
        spec = REPORT_BY_KEY[key]
        if all(_has(cols, alt) for alt in spec.signature):
            if spec.date_required and "date" not in cols:
                raise IngestError(MISSING_DATE_MESSAGE)
            if spec.core and "campaign" not in cols:
                raise IngestError(MISSING_CAMPAIGN_MESSAGE)
            return key
    if "date" not in cols:
        raise IngestError(MISSING_DATE_MESSAGE)
    raise IngestError(MISSING_CAMPAIGN_MESSAGE)


_EMPTY_VALUES = {"", "--", "-", " --", "nan", "None"}


def parse_share(values: pd.Series, language: str = "en") -> pd.Series:
    """Udziały procentowe → ułamek 0–1. "< 10%" → 0.10, "> 90%" → 0.90, "--" → NaN."""
    text = values.astype(str).str.strip()
    nums = parse_numeric(text.str.replace(r"[<>]", "", regex=True), language)
    has_pct = text.str.contains("%", regex=False)
    if has_pct.any() or nums.max(skipna=True) > 1:
        nums = nums / 100
    return nums.clip(lower=0, upper=1)


def parse_category(values: pd.Series, field_name: str) -> pd.Series:
    mapping = CATEGORY_VALUES[CATEGORY_KIND[field_name]]
    keys = values.astype(str).map(normalize_header)
    out = keys.map(mapping)
    if field_name == "device":
        out = out.where(keys.isin(["", "nan"]) | out.notna(), "other")
    return out.astype(object).where(out.notna(), None)


def parse_hour(values: pd.Series) -> pd.Series:
    extracted = values.astype(str).str.extract(r"(\d{1,2})", expand=False)
    hours = pd.to_numeric(extracted, errors="coerce")
    return hours.where(hours.between(0, 23))


def parse_day_of_week(values: pd.Series) -> pd.Series:
    keys = values.astype(str).map(normalize_header)
    numeric = pd.to_numeric(keys, errors="coerce")
    named = keys.map(DAY_NAMES)
    return named.fillna(numeric.where(numeric.between(1, 7)))


def _clean_text(values: pd.Series) -> pd.Series:
    text = values.astype(str).str.strip()
    return text.where(~text.isin(_EMPTY_VALUES), "")


def _is_micro(row_text: pd.Series) -> pd.Series:
    keys = row_text.map(normalize_header)
    return keys.apply(lambda k: any(p in k for p in MICRO_CONVERSION_PATTERNS))


def read_report(
    raw: bytes | str,
    source_name: str = "",
    expected_type: str | None = None,
    aliases_path: Path = ALIASES_PATH,
) -> IngestResult:
    """Wczytuje surowy plik CSV i zwraca znormalizowany DataFrame."""
    text = raw if isinstance(raw, str) else decode_bytes(raw)
    text = text.lstrip("\ufeff")
    lines = text.splitlines()
    if not lines:
        raise IngestError("Plik jest pusty.")
    header_idx, sep = _find_header(lines, aliases_path)
    warnings: list[str] = []
    if header_idx > 0:
        warnings.append(f"Pominięto {header_idx} wiersz(e) nagłówka raportu nad tabelą.")

    body = "\n".join(lines[header_idx:])
    df = pd.read_csv(
        io.StringIO(body), sep=sep, dtype=str, keep_default_na=False,
        skip_blank_lines=True, on_bad_lines="skip", engine="python",
    )
    df.columns = [clean_header(c) for c in df.columns]
    mapping, ignored, language = map_columns(list(df.columns), aliases_path)
    df = df[list(mapping)].rename(columns=mapping)

    report_type = detect_report_type(list(df.columns))
    spec = REPORT_BY_KEY[report_type]
    if expected_type and report_type != expected_type:
        raise IngestError(
            f"Plik wygląda na raport „{REPORT_LABELS[report_type]}”, "
            f"a oczekiwano „{REPORT_LABELS[expected_type]}”."
        )

    if "cost" not in df.columns and "cost_micros" in df.columns:
        df["cost"] = parse_numeric(df["cost_micros"], language) / 1_000_000
        warnings.append("Koszt przeliczono z mikrojednostek (cost_micros).")
    df = df.drop(columns=["cost_micros"], errors="ignore")

    cols = set(df.columns)
    missing = [" / ".join(alt) for alt in spec.required if not _has(cols, alt)]
    if missing:
        raise IngestError(f"{spec.title}: brak wymaganych kolumn: " + ", ".join(missing))

    # Usuń wiersze podsumowań ("Razem", "Total") – sprawdzamy pierwszą kolumnę i wymiary kluczowe.
    check_cols = [df.columns[0]] + [c for c in ("date", "campaign") if c in df.columns]
    check_cols += [a for alt in spec.signature for a in alt if a in df.columns]
    is_total = pd.Series(False, index=df.index)
    for c in dict.fromkeys(check_cols):
        is_total |= df[c].astype(str).str.match(TOTAL_ROW_PATTERN)
    if is_total.any():
        warnings.append(f"Usunięto {int(is_total.sum())} wiersz(y) podsumowań (Total/Razem).")
    df = df[~is_total].copy()

    if "date" in df.columns:
        df["date"] = parse_dates(df["date"])
        bad_dates = int(df["date"].isna().sum())
        if bad_dates:
            warnings.append(f"Pominięto {bad_dates} wiersz(y) bez poprawnej daty.")
            df = df[df["date"].notna()].copy()
    elif not spec.date_required:
        warnings.append("Raport nie zawiera daty – dane traktowane jako suma za okres eksportu "
                        "(bez filtrowania po wybranym zakresie dat).")
    if df.empty:
        raise IngestError("Po normalizacji plik nie zawiera żadnych wierszy z danymi.")

    for col in ADDITIVE:
        if col in df.columns:
            parsed = parse_numeric(df[col], language)
            unparsed = int((parsed.isna() & ~df[col].astype(str).str.strip().isin(_EMPTY_VALUES)).sum())
            if unparsed:
                warnings.append(f"Kolumna {col}: {unparsed} wartości nieliczbowych potraktowano jako 0.")
            df[col] = parsed.fillna(0.0)
        elif col in spec.metrics:
            df[col] = 0.0
            if col in ("conversions", "conversion_value"):
                warnings.append(f"Brak kolumny {col} – przyjęto 0.")
    for col in SHARES:
        if col in df.columns:
            df[col] = parse_share(df[col], language)
    for col in SCORES:
        if col in df.columns:
            df[col] = parse_numeric(df[col], language)
    for col in CATEGORIES:
        if col in df.columns:
            df[col] = parse_category(df[col], col)
    if "hour" in df.columns:
        df["hour"] = parse_hour(df["hour"])
    if "day_of_week" in df.columns:
        df["day_of_week"] = parse_day_of_week(df["day_of_week"])
    for col in TEXT_DIMENSIONS:
        if col in df.columns:
            df[col] = _clean_text(df[col])

    if report_type in CORE_DIMENSIONS:
        for col in CORE_DIMENSIONS[report_type]:
            if col not in df.columns:
                df[col] = ""
    df = _derive(df, report_type, warnings)
    df = aggregate_duplicates(df, report_type)
    return IngestResult(
        df=df,
        report_type=report_type,
        language=language,
        column_mapping=mapping,
        ignored_columns=ignored,
        warnings=warnings,
        source_name=source_name,
    )


def _derive(df: pd.DataFrame, report_type: str, warnings: list[str]) -> pd.DataFrame:
    """Pola pochodne zależne od typu raportu."""
    if report_type == SEARCH_TERMS:
        df["search_term"] = df["search_term"].str.lower()
        df = df[df["search_term"] != ""].copy()
    if "keyword" in df.columns and report_type == "keywords":
        df["keyword"] = df["keyword"].str.strip("[]\"+ ").str.lower()
    if report_type == "time":
        if "day_of_week" not in df.columns and "date" in df.columns:
            df["day_of_week"] = df["date"].dt.dayofweek + 1
        if "day_of_week" in df.columns:
            df["day_of_week_label"] = df["day_of_week"].map(DAY_LABELS).fillna("")
        bad = df[[c for c in ("hour", "day_of_week") if c in df.columns]].isna().all(axis=1)
        if bad.any():
            warnings.append(f"Pominięto {int(bad.sum())} wiersz(y) bez poprawnej godziny / dnia tygodnia.")
            df = df[~bad].copy()
    if report_type == "devices":
        df["device"] = df["device"].fillna("other")
        df["device_label"] = df["device"].map(DEVICE_LABELS).fillna("Inne")
    if report_type == "locations":
        loc_cols = [c for c in ("city", "region", "location", "country") if c in df.columns]
        loc = pd.Series("", index=df.index)
        for c in loc_cols:  # najbardziej szczegółowy dostępny poziom
            loc = loc.where(loc != "", df[c])
        df["location"] = loc
        df = df[df["location"] != ""].copy()
    if report_type == "audiences":
        seg_cols = [c for c in ("audience", "age_range", "gender", "household_income", "parental_status")
                    if c in df.columns]
        labels = {"audience": "Segment", "age_range": "Wiek", "gender": "Płeć",
                  "household_income": "Dochód", "parental_status": "Status rodzicielski"}
        df["segment"] = df[seg_cols].apply(lambda r: " / ".join(v for v in r if v), axis=1)
        df["segment_type"] = df[seg_cols].apply(
            lambda r: " × ".join(labels[c] for c, v in r.items() if v), axis=1)
        df = df[df["segment"] != ""].copy()
    if report_type == "conversion_actions":
        text = df["conversion_action"] + " " + (df["conversion_category"] if "conversion_category" in df.columns else "")
        df["is_micro"] = _is_micro(text)
        df = df[df["conversion_action"] != ""].copy()
    if report_type == "auction_insights":
        dom = df["competitor_domain"].map(normalize_header)
        df["is_self"] = dom.isin(["you", "ty", "twoja domena", "your domain", "ty twoja domena"])
    return df


def aggregate_duplicates(df: pd.DataFrame, report_type: str) -> pd.DataFrame:
    """Sumuje duplikaty (np. ten sam dzień w dwóch plikach) z zachowaniem typów metryk."""
    keys = [k for k in GROUP_KEYS[report_type] if k in df.columns]
    if report_type == "time":
        keys += [k for k in ("day_of_week_label",) if k in df.columns]
    if report_type == "auction_insights":
        keys += ["is_self"]
    if report_type in ("audiences",):
        keys += ["segment", "segment_type"]
    if report_type == "conversion_actions":
        keys += [k for k in ("conversion_category", "is_micro") if k in df.columns]
    out = aggregate(df, keys)
    if report_type in CORE_DIMENSIONS:
        lead = CORE_DIMENSIONS[report_type] + METRIC_COLUMNS
        out = out[lead + [c for c in out.columns if c not in lead]]
    return out


def read_report_file(path: str | Path, expected_type: str | None = None) -> IngestResult:
    path = Path(path)
    return read_report(path.read_bytes(), source_name=path.name, expected_type=expected_type)


@lru_cache(maxsize=4)
def _alias_spec(path: str) -> dict:
    return load_yaml(Path(path)).get("columns", {})


def column_names(canonical: str, aliases_path: Path = ALIASES_PATH) -> dict[str, list[str]]:
    """Nazwy kolumny w eksportach Google Ads: {"pl": [...], "en": [...]} (pierwsza = najczęstsza)."""
    spec = _alias_spec(str(aliases_path)).get(canonical, {}) or {}
    return {"pl": list(spec.get("pl") or []), "en": list(spec.get("en") or [])}
