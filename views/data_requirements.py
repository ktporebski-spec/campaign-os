"""DATA REQUIREMENTS – jakie raporty można zaimportować i jakie kolumny powinny zawierać.

Strona jest generowana z rejestru ``campaign_os.schema`` – tego samego, którego używa importer,
więc opis wymagań zawsze odpowiada temu, co aplikacja faktycznie rozpoznaje.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from campaign_os.ingest import column_names
from campaign_os.schema import COVERAGE_ORDER, MODULES, REPORT_BY_KEY, TIERS


def _label(canonical: str, lang: str) -> str:
    names = column_names(canonical)[lang]
    return names[0] if names else canonical


def _alts(alternatives: tuple, lang: str) -> str:
    return " lub ".join(f"{_label(c, lang)}" for c in alternatives)


def _template(spec, lang: str) -> bytes:
    cols = [alt[0] for alt in spec.required] + [alt[0] for alt in spec.recommended]
    header = ",".join(f'"{_label(c, lang)}"' for c in dict.fromkeys(cols))
    return (header + "\n").encode("utf-8-sig")


st.title("Data Requirements")
st.markdown(
    "Campaign OS działa wyłącznie na plikach CSV wyeksportowanych z Google Ads (nagłówki **PL lub EN**). "
    "Typ raportu jest rozpoznawany automatycznie po nazwach kolumn – nie trzeba ich zmieniać. "
    "**Wymagane** są dwa raporty podstawowe; pozostałe są **opcjonalne** i odblokowują kolejne analizy. "
    "Dane są przetwarzane tylko w bieżącej sesji (nic nie jest zapisywane)."
)

rows = []
for key in COVERAGE_ORDER:
    spec = REPORT_BY_KEY[key]
    modules = [m.title for m in MODULES if key in m.reports]
    rows.append({
        "Raport": spec.label,
        "Status": "Wymagany" if spec.core else "Opcjonalny",
        "Minimalne kolumny (PL)": ", ".join(_alts(a, "pl") for a in spec.required),
        "Minimalne kolumny (EN)": ", ".join(_alts(a, "en") for a in spec.required),
        "Odblokowuje": ", ".join(modules),
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=35 * (len(rows) + 1) + 3,
             column_config={"Minimalne kolumny (PL)": st.column_config.TextColumn(width="large"),
                            "Minimalne kolumny (EN)": st.column_config.TextColumn(width="large"),
                            "Odblokowuje": st.column_config.TextColumn(width="medium")})

st.subheader("Poziomy analizy")
cols = st.columns(3)
for col, (tier, (title, desc)) in zip(cols, TIERS.items()):
    with col.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(desc)
        for m in MODULES:
            if m.tier == tier:
                reports = ", ".join(REPORT_BY_KEY[r].label for r in m.reports)
                extra = ""
                if m.columns:
                    extra = " + kolumny: " + "; ".join(
                        " / ".join(_label(c, "pl") for c in alts) for _, alts in m.columns)
                st.markdown(f"- {m.title} — *{reports}{extra}*")

st.subheader("Szczegóły raportów")
for key in COVERAGE_ORDER:
    spec = REPORT_BY_KEY[key]
    badge = "🟦 Wymagany" if spec.core else "⬜ Opcjonalny"
    with st.expander(f"{badge} · **{spec.label}** — {spec.title}"):
        st.markdown(spec.description)
        st.markdown(f"**Jak wyeksportować (Google Ads PL):** {spec.export_path}")
        signature = " + ".join(_alts(a, "pl") for a in spec.signature)
        st.markdown(f"**Rozpoznawany po kolumnie:** {signature}"
                    + (" (oraz dacie i kampanii)" if spec.core else ""))
        if not spec.date_required:
            st.caption("Data jest opcjonalna: raport z kolumną Dzień jest filtrowany do wybranego okresu, "
                       "raport bez daty jest analizowany za cały okres eksportu.")
        detail = []
        for kind, group in (("Wymagana", spec.required), ("Zalecana", spec.recommended)):
            for alts in group:
                detail.append({
                    "Kolumna": kind,
                    "PL": " / ".join(_label(c, "pl") for c in alts),
                    "EN": " / ".join(_label(c, "en") for c in alts),
                    "Pole w Campaign OS": " / ".join(alts),
                })
        st.dataframe(pd.DataFrame(detail), hide_index=True, width="stretch")
        c1, c2, _ = st.columns([1, 1, 3])
        c1.download_button("⬇️ Szablon nagłówków (PL)", _template(spec, "pl"), f"{key}_pl.csv", "text/csv",
                           key=f"tpl_pl_{key}")
        c2.download_button("⬇️ Szablon nagłówków (EN)", _template(spec, "en"), f"{key}_en.csv", "text/csv",
                           key=f"tpl_en_{key}")

st.subheader("Zasady analizy")
st.markdown(
    "- **Brak raportu = brak diagnozy.** Reguły dla danego obszaru uruchamiają się tylko, gdy wgrano "
    "odpowiedni raport i zawiera on potrzebne kolumny.\n"
    "- **Minimalna próba.** Poniżej progów (domyślnie 30 kliknięć, 300 wyświetleń, 3 konwersje) Campaign OS "
    "nie rekomenduje zmian – w zakładce Rule Engine widać, ile kandydatów odrzucono z powodu małej próby.\n"
    "- **Istotność.** Różnice segmentów (urządzenia, godziny, lokalizacje, odbiorcy, strony, reklamy) są "
    "sprawdzane testem z dla CVR/CTR vs reszta, z poprawką Bonferroniego na liczbę porównywanych segmentów.\n"
    "- **Evidence.** Każda rekomendacja zawiera liczby, na których się opiera, źródłowy raport i okres danych."
)
