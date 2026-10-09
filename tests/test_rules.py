import math

import pandas as pd
import pytest

from campaign_os.rules import (
    ExpressionError, compile_expression, evaluate, evaluate_mask, load_rules, parse_rules, render, run_rules,
)

DF = pd.DataFrame({
    "campaign": ["A", "B", "C"],
    "cost": [100.0, 10.0, 50.0],
    "conversions": [0.0, 2.0, 1.0],
    "cpa_change": [float("nan"), 0.5, -0.1],
})


def test_vectorized_conditions():
    assert evaluate_mask("conversions == 0 and cost >= 50", DF).tolist() == [True, False, False]
    assert evaluate_mask("cost > limit or conversions >= 2", DF, {"limit": 60}).tolist() == [True, True, False]
    assert evaluate_mask("not conversions > 0", DF).tolist() == [True, False, False]
    assert evaluate_mask("10 <= cost < 100", DF).tolist() == [False, True, True]
    assert evaluate_mask('campaign == "B"', DF).tolist() == [False, True, False]


def test_nan_comparisons_are_false():
    assert evaluate_mask("cpa_change >= 0.3", DF).tolist() == [False, True, False]


def test_arithmetic_and_division_by_zero():
    res = evaluate("cost / conversions", DF)
    assert math.isnan(res.iloc[0]) and res.iloc[1] == 5.0
    assert evaluate("max(cost, 60)", DF).tolist() == [100.0, 60.0, 60.0]


@pytest.mark.parametrize("expr", [
    "__import__('os').system('echo hi')",
    "cost.__class__",
    "[x for x in cost]",
    "open('x')",
    "lambda: 1",
    "cost if True else 1",
])
def test_unsafe_expressions_rejected(expr):
    with pytest.raises(ExpressionError):
        compile_expression(expr)


def test_unknown_variable_raises():
    with pytest.raises(ExpressionError, match="nieznana"):
        evaluate_mask("foo > 1", DF)


def test_render_polish_number_format_and_missing_values():
    text = render("{cost:,.2f} {ctr:.1%} {cpa:.2f} {missing}", {"cost": 1234.5, "ctr": 0.123, "cpa": float("nan")})
    assert text == "1 234,50 12,3% — {missing}"


def test_parse_rules_reports_errors_and_skips_bad_rules():
    rs = parse_rules("""
rules:
  - {id: OK, entity: campaign, condition: "cost > 1"}
  - {id: BAD_ENTITY, entity: keyword, condition: "cost > 1"}
  - {id: BAD_EXPR, entity: campaign, condition: "cost >"}
  - {id: OK, entity: campaign, condition: "cost > 2"}
  - {id: NO_COND, entity: campaign}
""")
    assert [r.id for r in rs.rules] == ["OK"]
    assert len(rs.errors) == 4


def test_invalid_yaml():
    rs = parse_rules("rules: [unclosed")
    assert rs.rules == [] and rs.errors


def test_run_rules_produces_findings_with_impact():
    rs = parse_rules("""
rules:
  - id: R1
    entity: campaign
    condition: conversions == 0
    severity: high
    message: "{campaign} – {cost:.0f} {currency}"
    impact: cost * 0.5
  - id: R2
    entity: campaign
    condition: cost > 0
    enabled: false
""")
    findings, errors = run_rules(rs, {"campaign": DF}, {"currency": "PLN"})
    assert errors == []
    assert findings["rule_id"].tolist() == ["R1"]
    assert findings.loc[0, "message"] == "A – 100 PLN"
    assert findings.loc[0, "impact"] == 50.0


def test_runtime_error_is_reported_not_raised():
    rs = parse_rules("rules:\n  - {id: R, entity: campaign, condition: 'unknown_col > 1'}\n")
    findings, errors = run_rules(rs, {"campaign": DF}, {})
    assert findings.empty and errors


def test_default_rules_file_is_valid():
    rs = load_rules()
    assert rs.errors == []
    assert len(rs.rules) >= 8
