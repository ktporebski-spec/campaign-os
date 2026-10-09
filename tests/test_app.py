"""Testy dymne interfejsu Streamlit (bez przeglądarki)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app():
    return AppTest.from_file(APP, default_timeout=60).run()


def test_app_renders_with_sample_data(app):
    assert not app.exception
    labels = [m.label for m in app.metric]
    for kpi in ("Spend (PLN)", "Impressions", "Clicks", "CTR", "CPC (PLN)", "Conversions", "CVR", "CPA (PLN)"):
        assert kpi in labels
    assert any(t.label.startswith("✅ Rekomendacje") for t in app.tabs)


@pytest.mark.parametrize("preset", ["Ostatnie 7 dni", "Ostatnie 14 dni", "Cały zakres danych"])
def test_date_presets(app, preset):
    app.selectbox(key="period_preset").select(preset).run()
    assert not app.exception


def test_comparison_toggle_off(app):
    app.toggle(key="compare").set_value(False).run()
    assert not app.exception
    assert all(m.delta in ("", None) for m in app.metric if m.label == "Clicks")


def test_campaign_filter_and_thresholds(app):
    app.sidebar.multiselect[0].select("Search | Buty trailowe").run()
    assert not app.exception
    app.number_input[0].set_value(60.0).run()
    assert not app.exception


def test_invalid_rules_yaml_shows_error(app):
    app.text_area[0].set_value("rules: [broken").run()
    assert not app.exception
    assert any("YAML" in e.value for e in app.error)


def test_condition_tester_bad_expression(app):
    tester = next(t for t in app.text_input if t.label == "Warunek")
    tester.set_value("import os").run()
    assert not app.exception
    assert any("Błąd wyrażenia" in e.value for e in app.error)
