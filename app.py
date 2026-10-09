"""Campaign OS v0.1-alpha – analiza raportów Google Ads (Streamlit)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from campaign_os import __version__
from campaign_os.analysis import AnalysisResult, run_analysis
from campaign_os.config import RULES_PATH, SAMPLE_DIR, load_settings
from campaign_os.formatting import fmt_change, fmt_value
from campaign_os.ingest import (
    CAMPAIGN_DAILY, SEARCH_TERMS, IngestError, IngestResult, aggregate_duplicates, read_report,
)
from campaign_os.metrics import KPI_META, Period, previous_period
from campaign_os.recommendations import CATEGORY_LABELS, prepare_campaign_frame, summarize
from campaign_os.rules import (
    ENTITIES, SEVERITY_LABELS, ExpressionError, evaluate_mask, parse_rules,
)
from campaign_os.search_terms import ngram_analysis

st.set_page_config(page_title="Campaign OS", page_icon="📊", layout="wide")

SEVERITY_ICONS = {"high": "🔴", "medium": "🟠", "low": "🔵"}
SEGMENT_COLORS = {
    "Wasted spend": "#d62728",
    "High performer": "#2ca02c",
    "Bez konwersji": "#ff9f43",
    "Neutral": "#8c8c8c",
}
PREV_COLOR = "#a0a7b4"
CUR_COLOR = "#1f6feb"


# =========================================================================== dane


@st.cache_data(show_spinner=False)
def parse_upload(raw: bytes, name: str) -> IngestResult:
    return read_report(raw, source_name=name)


@st.cache_data(show_spinner=False)
def load_sample() -> list[IngestResult]:
    return [
        read_report((SAMPLE_DIR / f"{name}.csv").read_bytes(), source_name=f"{name}.csv")
        for name in (CAMPAIGN_DAILY, SEARCH_TERMS)
    ]


@st.cache_data(show_spinner=False)
def cached_rules(text: str):
    return parse_rules(text)


def combine(results: list[IngestResult], report_type: str) -> pd.DataFrame | None:
    frames = [r.df for r in results if r.report_type == report_type]
    if not frames:
        return None
    if len(frames) == 1:
        return frames[0]
    return aggregate_duplicates(pd.concat(frames, ignore_index=True), report_type)


def default_rules_text() -> str:
    return RULES_PATH.read_text(encoding="utf-8")


# =========================================================================== UI helpers


def kpi_delta_color(key: str) -> str:
    better = KPI_META[key]["better"]
    if better is None:
        return "off"
    return "normal" if better == "up" else "inverse"


def money_cols(currency: str) -> dict:
    return {
        "cost": st.column_config.NumberColumn(f"Spend ({currency})", format="%.2f"),
        "cpc": st.column_config.NumberColumn(f"CPC ({currency})", format="%.2f"),
        "cpa": st.column_config.NumberColumn(f"CPA ({currency})", format="%.2f"),
        "conversion_value": st.column_config.NumberColumn(f"Conv. value ({currency})", format="%.2f"),
        "impact": st.column_config.NumberColumn(f"Wpływ ({currency})", format="%.2f"),
    }


def metric_table_config(currency: str) -> dict:
    cfg = {
        "campaign": st.column_config.TextColumn("Kampania"),
        "ad_group": st.column_config.TextColumn("Grupa reklam"),
        "search_term": st.column_config.TextColumn("Wyszukiwane hasło"),
        "match_type": st.column_config.TextColumn("Dopasowanie"),
        "segment": st.column_config.TextColumn("Segment"),
        "impressions": st.column_config.NumberColumn("Impr.", format="%d"),
        "clicks": st.column_config.NumberColumn("Clicks", format="%d"),
        "ctr": st.column_config.NumberColumn("CTR %", format="%.2f"),
        "conversions": st.column_config.NumberColumn("Conv.", format="%.1f"),
        "cvr": st.column_config.NumberColumn("CVR %", format="%.2f"),
        "roas": st.column_config.NumberColumn("ROAS", format="%.2f"),
        "cost_share": st.column_config.NumberColumn("Udział w koszcie %", format="%.1f"),
        "active_days": st.column_config.NumberColumn("Dni aktywne", format="%d"),
        "cost_change": st.column_config.NumberColumn("Δ Spend %", format="%+.1f"),
        "conversions_change": st.column_config.NumberColumn("Δ Conv. %", format="%+.1f"),
        "cpa_change": st.column_config.NumberColumn("Δ CPA %", format="%+.1f"),
        "ctr_change": st.column_config.NumberColumn("Δ CTR %", format="%+.1f"),
    }
    cfg.update(money_cols(currency))
    return cfg


PCT_COLUMNS = ["ctr", "cvr", "cost_share", "cost_change", "conversions_change", "cpa_change", "ctr_change"]


def for_display(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Wybiera kolumny i przelicza ułamki na procenty (do wyświetlenia)."""
    out = df[[c for c in columns if c in df.columns]].copy()
    for col in PCT_COLUMNS:
        if col in out.columns:
            out[col] = out[col] * 100
    return out


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


# =========================================================================== sidebar


def sidebar(settings: dict):
    st.sidebar.title("📊 Campaign OS")
    st.sidebar.caption(f"v{__version__} · analiza raportów Google Ads")

    source = st.sidebar.radio(
        "Źródło danych", ["Dane przykładowe", "Własne pliki CSV"], horizontal=False,
        help="Dane przykładowe: 60 dni fikcyjnego sklepu z butami do biegania.",
    )
    results: list[IngestResult] = []
    errors: list[str] = []
    if source == "Własne pliki CSV":
        files = st.sidebar.file_uploader(
            "Raporty Google Ads (CSV)", type=["csv", "tsv", "txt"], accept_multiple_files=True,
            help="campaign_daily.csv i/lub search_terms_daily.csv – typ raportu i język nagłówków "
                 "(PL/EN) są rozpoznawane automatycznie.",
        )
        for f in files or []:
            try:
                results.append(parse_upload(f.getvalue(), f.name))
            except IngestError as exc:
                errors.append(f"**{f.name}**: {exc}")
            except Exception as exc:  # noqa: BLE001 – pokaż użytkownikowi, nie wywracaj aplikacji
                errors.append(f"**{f.name}**: nieoczekiwany błąd odczytu ({type(exc).__name__}: {exc})")
    else:
        results = load_sample()

    for err in errors:
        st.sidebar.error(err)
    return results


def date_controls(min_d: date, max_d: date, default_days: int) -> tuple[Period, bool]:
    st.sidebar.subheader("Zakres dat")
    presets = {
        "Ostatnie 7 dni": 7, "Ostatnie 14 dni": 14, "Ostatnie 30 dni": 30,
        "Cały zakres danych": None, "Własny zakres": "custom",
    }
    default_label = next((k for k, v in presets.items() if v == default_days), "Ostatnie 30 dni")
    choice = st.sidebar.selectbox("Okres", list(presets), index=list(presets).index(default_label),
                                  key="period_preset")
    value = presets[choice]
    if value == "custom":
        default_start = max(min_d, max_d - timedelta(days=default_days - 1))
        picked = st.sidebar.date_input(
            "Od – do", value=(default_start, max_d), min_value=min_d, max_value=max_d, format="DD.MM.YYYY",
        )
        if not isinstance(picked, (tuple, list)) or len(picked) != 2:
            st.sidebar.info("Wybierz datę końcową zakresu.")
            st.stop()
        start, end = picked
    elif value is None:
        start, end = min_d, max_d
    else:
        start, end = max(min_d, max_d - timedelta(days=value - 1)), max_d
    compare = st.sidebar.toggle("Porównaj z poprzednim okresem", value=True, key="compare")
    period = Period(start, end)
    if compare:
        st.sidebar.caption(f"Poprzedni okres: {previous_period(period).label()}")
    return period, compare


def threshold_controls(settings: dict, currency: str) -> dict:
    th = dict(settings.get("thresholds", {}))
    with st.sidebar.expander("Progi analizy", expanded=False):
        th["target_cpa"] = st.number_input(
            f"Docelowy CPA ({currency})", min_value=0.0, value=float(th.get("target_cpa", 0) or 0),
            step=5.0, help="0 = średni CPA konta w wybranym okresie.",
        )
        th["wasted_min_cost"] = st.number_input(
            f"Wasted spend: min. koszt ({currency})", min_value=0.0,
            value=float(th.get("wasted_min_cost", 30.0)), step=5.0,
        )
        th["wasted_min_clicks"] = st.number_input(
            "Wasted spend: min. kliknięć", min_value=0, value=int(th.get("wasted_min_clicks", 5)), step=1,
        )
        th["high_performer_min_conversions"] = st.number_input(
            "High performer: min. konwersji", min_value=0.0,
            value=float(th.get("high_performer_min_conversions", 2)), step=1.0,
        )
        th["high_performer_max_cpa_ratio"] = st.slider(
            "High performer: maks. CPA jako % celu", min_value=0.1, max_value=1.5,
            value=float(th.get("high_performer_max_cpa_ratio", 0.8)), step=0.05,
        )
    return th


# =========================================================================== zakładki


def tab_dashboard(res: AnalysisResult, compare: bool, currency: str):
    st.caption(
        f"Okres: **{res.period.label()}** ({res.period.days} dni)"
        + (f" · porównanie z: {res.prev_period.label()}" if compare else "")
    )
    keys = list(KPI_META)
    for row_keys in (keys[:5], keys[5:]):
        cols = st.columns(len(row_keys))
        for col, key in zip(cols, row_keys):
            meta = KPI_META[key]
            cur, change = res.kpis.loc[key, "current"], res.kpis.loc[key, "change"]
            prev = res.kpis.loc[key, "previous"]
            is_money = meta["fmt"] == "money"
            col.metric(
                f"{meta['label']} ({currency})" if is_money else meta["label"],
                fmt_value(cur, "money_compact" if is_money else meta["fmt"], currency),
                delta=fmt_change(change) if compare else None,
                delta_color=kpi_delta_color(key),
                help=f"Poprzedni okres: {fmt_value(prev, meta['fmt'], currency)}" if compare else None,
                border=True,
            )

    st.subheader("Trend dzienny")
    labels = {k: v["label"] for k, v in KPI_META.items()}
    metric = st.selectbox(
        "Metryka", list(labels), format_func=labels.get, index=0, key="trend_metric",
        label_visibility="collapsed",
    )
    scale = 100 if KPI_META[metric]["fmt"] == "pct" else 1
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=res.daily["date"], y=res.daily[metric] * scale, name="Bieżący okres",
        mode="lines+markers", line=dict(color=CUR_COLOR, width=2.5), marker=dict(size=5),
    ))
    if compare and res.prev_coverage_days:
        prev = res.daily_prev.iloc[: len(res.daily)]
        fig.add_trace(go.Scatter(
            x=res.daily["date"].iloc[: len(prev)], y=prev[metric] * scale, name="Poprzedni okres",
            mode="lines", line=dict(color=PREV_COLOR, width=2, dash="dash"),
            customdata=prev["date"].dt.strftime("%d.%m.%Y"),
            hovertemplate="%{customdata}: %{y:,.2f}<extra>Poprzedni okres</extra>",
        ))
    fig.update_layout(
        height=340, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis_title=labels[metric] + (" (%)" if scale == 100 else ""),
    )
    st.plotly_chart(fig, width="stretch")

    st.subheader("Kampanie")
    camp = res.campaigns
    if camp.empty:
        st.info("Brak danych kampanii w wybranym okresie.")
        return
    cols = ["campaign", "cost", "impressions", "clicks", "ctr", "cpc", "conversions", "cvr", "cpa", "roas"]
    if compare:
        cols = ["campaign", "cost", "cost_change", "impressions", "clicks", "ctr", "ctr_change", "cpc",
                "conversions", "conversions_change", "cvr", "cpa", "cpa_change", "roas"]
    st.dataframe(
        for_display(camp, cols), hide_index=True, column_config=metric_table_config(currency), width="stretch",
    )

    c1, c2 = st.columns(2)
    with c1:
        bars = camp[["campaign", "cost"]].assign(okres="Bieżący")
        if compare and res.prev_coverage_days:
            bars = pd.concat([bars, camp[["campaign", "cost_prev"]].rename(columns={"cost_prev": "cost"})
                             .assign(okres="Poprzedni")])
        fig = px.bar(
            bars, x="cost", y="campaign", color="okres", barmode="group", orientation="h",
            color_discrete_map={"Bieżący": CUR_COLOR, "Poprzedni": PREV_COLOR},
            labels={"cost": f"Spend ({currency})", "campaign": "", "okres": ""},
            title="Spend wg kampanii",
        )
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10), yaxis=dict(autorange="reversed"),
                          legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0))
        st.plotly_chart(fig, width="stretch")
    with c2:
        scatter = camp[camp["conversions"] > 0]
        if scatter.empty:
            st.info("Brak kampanii z konwersjami w wybranym okresie.")
        else:
            fig = px.scatter(
                scatter, x="conversions", y="cpa", size="cost", text="campaign", size_max=45,
                labels={"conversions": "Conversions", "cpa": f"CPA ({currency})"},
                title="CPA vs konwersje (wielkość = spend)",
            )
            target = res.context.get("target_cpa", 0)
            if target:
                fig.add_hline(y=target, line_dash="dot", line_color="#d62728",
                              annotation_position="bottom right", annotation_text=f"Cel CPA {target:,.2f}".replace(",", " ").replace(".", ","))
            fig.update_traces(textposition="top center", cliponaxis=False, marker=dict(color=CUR_COLOR, opacity=0.65))
            fig.update_layout(height=360, margin=dict(l=10, r=40, t=70, b=10))
            st.plotly_chart(fig, width="stretch")


def tab_search_terms(res: AnalysisResult, currency: str):
    terms = res.terms
    if terms is None:
        st.info("Wgraj raport **search_terms_daily.csv**, aby zobaczyć analizę wyszukiwanych haseł.")
        return
    if terms.empty:
        st.info("Brak wyszukiwanych haseł w wybranym okresie.")
        return
    s = res.terms_summary
    th = res.thresholds
    c = st.columns(4)
    c[0].metric("Wyszukiwane hasła", fmt_value(s["terms"], "int"), border=True)
    c[1].metric("Wasted spend", fmt_value(s["wasted_cost"], "money", currency),
                delta=f"{fmt_value(s['wasted_share'], 'pct')} kosztu haseł", delta_color="off", delta_arrow="off", border=True,
                help=f"{s['wasted_terms']} haseł: 0 konwersji, koszt ≥ {th.wasted_min_cost:g} {currency}, "
                     f"kliknięcia ≥ {th.wasted_min_clicks}.")
    c[2].metric("High performers", fmt_value(s["hp_terms"], "int"),
                delta=f"{fmt_value(s['hp_conv_share'], 'pct')} konwersji", delta_color="off", delta_arrow="off", border=True,
                help=f"Konwersje ≥ {th.high_performer_min_conversions:g} i CPA ≤ "
                     f"{th.high_performer_max_cpa_ratio:.0%} celu.")
    c[3].metric("Docelowy CPA", fmt_value(th.target_cpa, "money", currency),
                delta=res.target_cpa_source, delta_color="off", delta_arrow="off", border=True)

    cfg = metric_table_config(currency)
    base_cols = ["search_term", "campaign", "ad_group", "match_type", "cost", "clicks", "impressions",
                 "ctr", "conversions", "cvr", "cpa", "cost_share"]

    t1, t2, t3, t4 = st.tabs(["🔴 Wasted spend", "🟢 High performers", "📋 Wszystkie hasła", "🔤 N-gramy"])
    with t1:
        wasted = terms[terms["is_wasted"]]
        if wasted.empty:
            st.success("Brak haseł spełniających kryteria wasted spend. 🎉")
        else:
            wasted_cols = [c for c in base_cols if c not in ("conversions", "cvr", "cpa")]
            st.dataframe(for_display(wasted, wasted_cols), hide_index=True, column_config=cfg, width="stretch")
            st.markdown("**Lista wykluczeń do skopiowania** (dopasowanie ścisłe):")
            st.code("\n".join(f"[{t}]" for t in wasted["search_term"].drop_duplicates()), language=None)
    with t2:
        hp = terms[terms["is_high_performer"]]
        if hp.empty:
            st.info("Brak haseł spełniających kryteria high performer.")
        else:
            st.dataframe(for_display(hp, base_cols), hide_index=True, column_config=cfg, width="stretch")
            st.markdown("**Słowa kluczowe do dodania** (dopasowanie ścisłe):")
            st.code("\n".join(f"[{t}]" for t in hp["search_term"].drop_duplicates()), language=None)
    with t3:
        f1, f2 = st.columns([1, 2])
        segments = f1.multiselect("Segment", list(SEGMENT_COLORS), default=list(SEGMENT_COLORS))
        query = f2.text_input("Szukaj hasła", placeholder="np. buty trailowe")
        view = terms[terms["segment"].isin(segments)]
        if query:
            view = view[view["search_term"].str.contains(query.strip().lower(), regex=False)]
        st.dataframe(for_display(view, ["segment"] + base_cols), hide_index=True, column_config=cfg,
                     width="stretch")
        st.download_button("⬇️ Pobierz CSV", csv_bytes(view), "search_terms_analysis.csv", "text/csv")

        fig = px.scatter(
            terms, x="cost", y="conversions", color="segment", hover_name="search_term",
            hover_data={"campaign": True, "clicks": True, "cpa": ":.2f"},
            color_discrete_map=SEGMENT_COLORS,
            labels={"cost": f"Spend ({currency})", "conversions": "Conversions", "segment": ""},
            title="Hasła: koszt vs konwersje",
        )
        fig.update_traces(marker=dict(size=10, opacity=0.75))
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, width="stretch")
    with t4:
        n = st.radio("Długość n-gramu", [1, 2, 3], horizontal=True, format_func=lambda x: f"{x} słowo/a")
        grams = ngram_analysis(terms, n=n)
        if grams.empty:
            st.info("Za mało danych do analizy n-gramów.")
        else:
            st.caption("Metryki zsumowane po wszystkich hasłach zawierających dany fragment.")
            st.dataframe(
                for_display(grams, ["ngram", "terms", "cost", "clicks", "conversions", "cvr", "cpa", "ctr"]),
                hide_index=True, width="stretch",
                column_config={**cfg, "ngram": st.column_config.TextColumn("N-gram"),
                               "terms": st.column_config.NumberColumn("Haseł", format="%d")},
            )


def tab_recommendations(res: AnalysisResult, currency: str):
    recs = res.recommendations
    for err in res.rule_errors:
        st.error(err)
    if recs.empty:
        st.success("Brak rekomendacji dla wybranego okresu – reguły nie wykryły problemów.")
        return

    summary = summarize(recs)
    cols = st.columns(min(len(summary), 6))
    for col, row in zip(cols, summary.itertuples()):
        col.metric(row.label, f"{row.count}", delta=fmt_value(row.impact, "money", currency) if row.impact else None,
                   delta_color="off", delta_arrow="off", border=True)

    f1, f2, f3 = st.columns([1, 2, 1])
    sev = f1.multiselect("Priorytet", list(SEVERITY_LABELS), default=list(SEVERITY_LABELS),
                         format_func=lambda s: f"{SEVERITY_ICONS[s]} {SEVERITY_LABELS[s]}")
    cats = sorted(recs["category"].unique(), key=lambda c: list(CATEGORY_LABELS).index(c)
                  if c in CATEGORY_LABELS else 99)
    cat = f2.multiselect("Kategoria", cats, default=cats, format_func=lambda c: CATEGORY_LABELS.get(c, c))
    layout = f3.radio("Widok", ["Karty", "Tabela"], horizontal=True)
    view = recs[recs["severity"].isin(sev) & recs["category"].isin(cat)]
    st.caption(
        f"{len(view)} z {len(recs)} rekomendacji · posortowane wg priorytetu i szacowanego wpływu. "
        "Wpływ to szacowana kwota, której dotyczy rekomendacja (np. koszt do zaoszczędzenia "
        "lub nadwyżka wartości konwersji względem docelowego CPA)."
    )

    if layout == "Tabela":
        cols = ["no", "severity", "category", "rule_name", "entity_name", "campaign", "message",
                "recommendation", "impact"]
        st.dataframe(
            view[cols], hide_index=True, width="stretch",
            column_config={
                "no": st.column_config.NumberColumn("#", format="%d"),
                "severity": st.column_config.TextColumn("Priorytet"),
                "category": st.column_config.TextColumn("Kategoria"),
                "rule_name": st.column_config.TextColumn("Reguła"),
                "entity_name": st.column_config.TextColumn("Obiekt"),
                "campaign": st.column_config.TextColumn("Kampania"),
                "message": st.column_config.TextColumn("Znalezisko", width="large"),
                "recommendation": st.column_config.TextColumn("Rekomendacja", width="large"),
                **money_cols(currency),
            },
        )
    else:
        limit = 30
        for row in view.head(limit).itertuples():
            with st.container(border=True):
                head, impact = st.columns([5, 1])
                head.markdown(
                    f"{SEVERITY_ICONS.get(row.severity, '')} **{row.no}. {row.rule_name}** · "
                    f"{CATEGORY_LABELS.get(row.category, row.category)} · `{row.rule_id}`"
                )
                if pd.notna(row.impact) and row.impact > 0:
                    impact.markdown(f"**{fmt_value(row.impact, 'money', currency)}**")
                st.markdown(row.message)
                st.markdown(f"👉 {row.recommendation}")
        if len(view) > limit:
            st.caption(f"Pokazano {limit} najważniejszych – pełna lista w widoku „Tabela” lub w pliku CSV.")
    st.download_button("⬇️ Pobierz rekomendacje (CSV)", csv_bytes(view.drop(columns=["priority"])),
                       "recommendations.csv", "text/csv")


def tab_rule_engine(res: AnalysisResult, ruleset, frames: dict[str, pd.DataFrame]):
    st.markdown(
        "Reguły są zdefiniowane w YAML (`config/rules.yaml`). Każda reguła ma warunek oceniany dla "
        "każdej kampanii lub wyszukiwanego hasła w wybranym okresie. Zmiany wprowadzone poniżej "
        "obowiązują w bieżącej sesji – pobierz plik, aby zapisać je na stałe."
    )
    hits = res.recommendations["rule_id"].value_counts() if not res.recommendations.empty else pd.Series(dtype=int)
    table = pd.DataFrame([{
        "Aktywna": r.enabled, "ID": r.id, "Nazwa": r.name, "Encja": r.entity,
        "Priorytet": f"{SEVERITY_ICONS[r.severity]} {SEVERITY_LABELS[r.severity]}",
        "Warunek": r.condition, "Trafienia": int(hits.get(r.id, 0)),
    } for r in ruleset.rules])
    st.dataframe(table, hide_index=True, width="stretch", height=35 * (len(table) + 1) + 3,
                 column_config={"Warunek": st.column_config.TextColumn(width="large")})

    st.subheader("Edytor reguł")
    st.text_area("rules.yaml", key="rules_text", height=420, label_visibility="collapsed")
    for err in ruleset.errors:
        st.error(err)
    if not ruleset.errors:
        st.caption(f"✅ Poprawnie wczytano {len(ruleset.rules)} reguł.")
    b1, b2, _ = st.columns([1, 1, 3])
    b1.button("↩️ Przywróć domyślne", on_click=lambda: st.session_state.update(rules_text=default_rules_text()))
    b2.download_button("⬇️ Pobierz rules.yaml", st.session_state["rules_text"].encode("utf-8"), "rules.yaml",
                       "text/yaml")

    st.subheader("Tester warunków")
    c1, c2 = st.columns([1, 3])
    entity = c1.selectbox("Encja", ENTITIES, format_func=lambda e: {"campaign": "Kampanie",
                                                                    "search_term": "Wyszukiwane hasła"}[e])
    expr = c2.text_input("Warunek", value="conversions == 0 and cost >= 50")
    df = frames.get(entity)
    if df is None or df.empty:
        st.info("Brak danych dla tej encji.")
        return
    with st.expander("Dostępne zmienne"):
        st.markdown("**Kolumny:** " + ", ".join(f"`{c}`" for c in df.columns))
        st.markdown("**Kontekst:** " + ", ".join(f"`{k}` = {v:.4g}" if isinstance(v, float) else f"`{k}` = {v}"
                                                 for k, v in res.context.items()))
    try:
        mask = evaluate_mask(expr, df, res.context)
    except (ExpressionError, TypeError, ValueError) as exc:
        st.error(f"Błąd wyrażenia: {exc}")
        return
    st.caption(f"Pasuje {int(mask.sum())} z {len(df)} wierszy.")
    key_cols = ["search_term", "campaign"] if entity == "search_term" else ["campaign"]
    st.dataframe(
        for_display(df[mask], key_cols + ["cost", "clicks", "ctr", "conversions", "cvr", "cpa"]),
        hide_index=True, width="stretch", column_config=metric_table_config(res.context["currency"]),
    )


def tab_data(results: list[IngestResult]):
    if not results:
        st.info("Brak wczytanych plików.")
        return
    for r in results:
        with st.expander(f"📄 {r.source_name} → {r.report_type}", expanded=False):
            c = st.columns(4)
            c[0].metric("Typ raportu", r.report_type)
            c[1].metric("Język nagłówków", r.language.upper())
            c[2].metric("Wiersze", fmt_value(len(r.df), "int"))
            c[3].metric("Zakres dat", f"{r.df['date'].min():%d.%m} – {r.df['date'].max():%d.%m.%Y}")
            for w in r.warnings:
                st.caption(f"ℹ️ {w}")
            mapping = pd.DataFrame(
                [{"Kolumna w pliku": k, "Kolumna kanoniczna": v} for k, v in r.column_mapping.items()]
                + [{"Kolumna w pliku": k, "Kolumna kanoniczna": "— (pominięta)"} for k in r.ignored_columns]
            )
            st.dataframe(mapping, hide_index=True, width="stretch")
            st.markdown("**Podgląd danych po normalizacji**")
            st.dataframe(r.df.head(200), hide_index=True, width="stretch")
            st.download_button("⬇️ Pobierz znormalizowany CSV", csv_bytes(r.df), f"normalized_{r.report_type}.csv",
                               "text/csv", key=f"dl_{r.source_name}")


# =========================================================================== main


def main():
    settings = load_settings()
    currency_default = settings.get("currency", "PLN")
    if "rules_text" not in st.session_state:
        st.session_state["rules_text"] = default_rules_text()

    results = sidebar(settings)
    campaign_df = combine(results, CAMPAIGN_DAILY)
    terms_df = combine(results, SEARCH_TERMS)

    st.title("Campaign OS")
    if campaign_df is None and terms_df is None:
        st.info(
            "👈 Wgraj raporty **campaign_daily.csv** i/lub **search_terms_daily.csv** z Google Ads "
            "(nagłówki PL lub EN) albo wybierz **Dane przykładowe** w panelu bocznym."
        )
        st.stop()

    base = campaign_df if campaign_df is not None else terms_df
    currencies = {c for c in base.get("currency", pd.Series(dtype=str)).unique() if c}
    currency = next(iter(currencies)) if len(currencies) == 1 else currency_default

    all_campaigns = sorted(set(base["campaign"]) | (set(terms_df["campaign"]) if terms_df is not None else set()))
    period, compare = date_controls(base["date"].min().date(), base["date"].max().date(),
                                    int(settings.get("default_range_days", 30)))
    selected = st.sidebar.multiselect("Kampanie", all_campaigns, placeholder="Wszystkie kampanie")
    thresholds = threshold_controls(settings, currency)

    ruleset = cached_rules(st.session_state["rules_text"])
    try:
        res = run_analysis(campaign_df, terms_df, period, thresholds, ruleset, currency, selected or None)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    for note in res.notes:
        st.warning(note)
    if len(currencies) > 1:
        st.warning(f"Dane zawierają kilka walut ({', '.join(sorted(currencies))}) – sumy mogą być niespójne.")

    n_recs = len(res.recommendations)
    tabs = st.tabs(["📊 Dashboard", "🔎 Search terms", f"✅ Rekomendacje ({n_recs})", "⚙️ Rule Engine", "🗂️ Dane"])
    with tabs[0]:
        tab_dashboard(res, compare, currency)
    with tabs[1]:
        tab_search_terms(res, currency)
    with tabs[2]:
        tab_recommendations(res, currency)
    with tabs[3]:
        frames = {"campaign": prepare_campaign_frame(res.campaigns, res.context["target_cpa"])}
        if res.terms is not None:
            frames["search_term"] = res.terms
        tab_rule_engine(res, ruleset, frames)
    with tabs[4]:
        tab_data(results)


main()
