"""Formatowanie liczb w polskim zapisie (1 234,56)."""

from __future__ import annotations

import math

NBSP = " "


def _pl(text: str) -> str:
    return text.replace(",", NBSP).replace(".", ",")


def _missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def fmt_value(value, kind: str, currency: str = "PLN") -> str:
    if _missing(value):
        return "—"
    if kind == "money":
        return f"{_pl(f'{value:,.2f}')} {currency}"
    if kind == "money_compact":
        # Do kart KPI: bez waluty (jest w etykiecie), duże kwoty bez groszy.
        return _pl(f"{value:,.0f}") if abs(value) >= 1000 else _pl(f"{value:,.2f}")
    if kind == "int":
        return _pl(f"{value:,.0f}")
    if kind == "num":
        return _pl(f"{value:,.1f}") if value % 1 else _pl(f"{value:,.0f}")
    if kind == "pct":
        return _pl(f"{value * 100:,.2f}") + "%"
    if kind == "ratio":
        return _pl(f"{value:,.2f}") + "×"
    return str(value)


def fmt_change(change) -> str | None:
    if _missing(change):
        return None
    return _pl(f"{change * 100:+,.1f}") + "%"
