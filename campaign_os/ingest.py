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

CAMPAIGN_DAILY = "campaign_daily"
SEARCH_TERMS = "search_terms_daily"

REPORT_LABELS = {
    CAMPAIGN_DAILY: "campaign_daily",
    SEARCH_TERMS: "search_terms_daily",
}

METRIC_COLUMNS = ["impressions", "clicks", "cost", "conversions", "conversion_value"]
REQUIRED = {
    CAMPAIGN_DAILY: ["date", "campaign", "impressions", "clicks", "cost"],
    SEARCH_TERMS: ["date", "campaign", "search_term", "impressions", "clicks", "cost"],
}
DIMENSIONS = {
    CAMPAIGN_DAILY: ["date", "campaign", "campaign_id", "campaign_type", "campaign_status", "currency"],
    SEARCH_TERMS: [
        "date", "campaign", "ad_group", "search_term", "match_type", "keyword",
        "added_excluded", "currency",
    ],
}
# Kolumny, po których agregujemy duplikaty (np. ten sam dzień w dwóch plikach / segmentach).
GROUP_KEYS = {
    CAMPAIGN_DAILY: ["date", "campaign"],
    SEARCH_TERMS: ["date", "campaign", "ad_group", "search_term", "match_type"],
}

TOTAL_ROW_PATTERN = re.compile(
    r"^\s*(total|totals|razem|łącznie|lacznie|suma|ogółem|ogolem)\b", re.IGNORECASE
)

PL_MONTHS = {
    "sty": 1, "lut": 2, "mar": 3, "kwi": 4, "maj": 5, "cze": 6,
    "lip": 7, "sie": 8, "wrz": 9, "paź": 10, "paz": 10, "lis": 11, "gru": 12,
}


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


# --------------------------------------------------------------------------- aliasy


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
    if best[2] < 3:
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


def detect_report_type(columns: list[str]) -> str:
    cols = set(columns)
    if "search_term" in cols:
        return SEARCH_TERMS
    if {"date", "campaign"} <= cols:
        return CAMPAIGN_DAILY
    raise IngestError(
        "Nie rozpoznano typu raportu: wymagane kolumny daty i kampanii "
        "(oraz wyszukiwanego hasła dla raportu search terms)."
    )


def read_report(
    raw: bytes | str,
    source_name: str = "",
    expected_type: str | None = None,
    aliases_path: Path = ALIASES_PATH,
) -> IngestResult:
    """Wczytuje surowy plik CSV i zwraca znormalizowany DataFrame."""
    text = raw if isinstance(raw, str) else decode_bytes(raw)
    text = text.lstrip("﻿")
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
    df.columns = [str(c).strip() for c in df.columns]
    mapping, ignored, language = map_columns(list(df.columns), aliases_path)
    df = df[list(mapping)].rename(columns=mapping)

    report_type = detect_report_type(list(df.columns))
    if expected_type and report_type != expected_type:
        raise IngestError(
            f"Plik wygląda na raport „{REPORT_LABELS[report_type]}”, "
            f"a oczekiwano „{REPORT_LABELS[expected_type]}”."
        )

    if "cost" not in df.columns and "cost_micros" in df.columns:
        df["cost"] = parse_numeric(df["cost_micros"], language) / 1_000_000
        warnings.append("Koszt przeliczono z mikrojednostek (cost_micros).")
    df = df.drop(columns=["cost_micros"], errors="ignore")

    missing = [c for c in REQUIRED[report_type] if c not in df.columns]
    if missing:
        raise IngestError("Brak wymaganych kolumn: " + ", ".join(missing))

    # Usuń wiersze podsumowań i puste.
    first_col = df.iloc[:, 0].astype(str)
    is_total = (
        first_col.str.match(TOTAL_ROW_PATTERN)
        | df["date"].astype(str).str.match(TOTAL_ROW_PATTERN)
        | df["campaign"].astype(str).str.match(TOTAL_ROW_PATTERN)
    )
    if is_total.any():
        warnings.append(f"Usunięto {int(is_total.sum())} wiersz(y) podsumowań (Total/Razem).")
    df = df[~is_total].copy()

    df["date"] = parse_dates(df["date"])
    bad_dates = int(df["date"].isna().sum())
    if bad_dates:
        warnings.append(f"Pominięto {bad_dates} wiersz(y) bez poprawnej daty.")
        df = df[df["date"].notna()].copy()
    if df.empty:
        raise IngestError("Po normalizacji plik nie zawiera żadnych wierszy z danymi.")

    for col in METRIC_COLUMNS:
        if col in df.columns:
            parsed = parse_numeric(df[col], language)
            unparsed = int((parsed.isna() & ~df[col].astype(str).str.strip().isin(["", "--", "-", " --"])).sum())
            if unparsed:
                warnings.append(f"Kolumna {col}: {unparsed} wartości nieliczbowych potraktowano jako 0.")
            df[col] = parsed.fillna(0.0)
        else:
            df[col] = 0.0
            if col in ("conversions", "conversion_value"):
                warnings.append(f"Brak kolumny {col} – przyjęto 0.")

    for col in DIMENSIONS[report_type]:
        if col not in df.columns:
            df[col] = ""
        if col != "date":
            df[col] = df[col].astype(str).str.strip()

    if report_type == SEARCH_TERMS:
        df["search_term"] = df["search_term"].str.lower()
        empty_terms = df["search_term"].isin(["", "--"])
        if empty_terms.any():
            df = df[~empty_terms].copy()

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


def aggregate_duplicates(df: pd.DataFrame, report_type: str) -> pd.DataFrame:
    keys = GROUP_KEYS[report_type]
    other_dims = [c for c in DIMENSIONS[report_type] if c not in keys]
    agg = {m: "sum" for m in METRIC_COLUMNS}
    agg.update({d: "first" for d in other_dims})
    out = df.groupby(keys, as_index=False, sort=True, dropna=False).agg(agg)
    return out[DIMENSIONS[report_type] + METRIC_COLUMNS].reset_index(drop=True)


def read_report_file(path: str | Path, expected_type: str | None = None) -> IngestResult:
    path = Path(path)
    return read_report(path.read_bytes(), source_name=path.name, expected_type=expected_type)
