"""Rule Engine: reguły definiowane w YAML, oceniane wektorowo na DataFrame.

Warunki to wyrażenia w podzbiorze składni Pythona, np.::

    conversions == 0 and cost >= wasted_min_cost
    cpa_change >= 0.3 and conversions_prev >= 3
    cpa > account_cpa * 1.5

Dozwolone są: liczby, napisy, True/False, nazwy kolumn encji i zmiennych kontekstu,
operatory + - * /, porównania (także łańcuchowe), and/or/not oraz funkcje abs/min/max.
Wyrażenia nie są wykonywane przez ``eval`` – są interpretowane z drzewa AST,
więc plik reguł nie może uruchomić dowolnego kodu.
"""

from __future__ import annotations

import ast
import math
import operator
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from campaign_os.config import RULES_PATH
from campaign_os.schema import ENTITIES, ENTITY_LABELS, ENTITY_REPORT, KNOWN_FIELDS, REPORT_BY_KEY

SEVERITIES = {"high": 3, "medium": 2, "low": 1}
SEVERITY_LABELS = {"high": "Wysoki", "medium": "Średni", "low": "Niski"}


class ExpressionError(ValueError):
    pass


# --------------------------------------------------------------------------- ewaluator


_BIN_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_CMP_OPS = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
    ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
}
_FUNCS = {"abs": "abs", "min": "min", "max": "max"}
_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
    ast.BinOp, ast.Compare, ast.Name, ast.Load, ast.Constant, ast.Call,
    *_BIN_OPS, *_CMP_OPS,
)


def compile_expression(expr: str) -> ast.Expression:
    """Parsuje i waliduje wyrażenie. Rzuca ExpressionError przy niedozwolonej składni."""
    if not isinstance(expr, str) or not expr.strip():
        raise ExpressionError("puste wyrażenie")
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"błąd składni: {exc.msg}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExpressionError(f"niedozwolony element: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS or node.keywords:
                raise ExpressionError("dozwolone funkcje: abs, min, max")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, str, bool)):
            raise ExpressionError(f"niedozwolona stała: {node.value!r}")
    return tree


def expression_names(tree: ast.Expression) -> set[str]:
    funcs = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - funcs


def _as_bool(value, index):
    if isinstance(value, pd.Series):
        return value.fillna(False).astype(bool)
    if isinstance(value, float) and math.isnan(value):
        value = False
    return pd.Series(bool(value), index=index)


def _eval(node: ast.AST, df: pd.DataFrame, ctx: dict[str, Any]):
    if isinstance(node, ast.Expression):
        return _eval(node.body, df, ctx)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in df.columns:
            return df[node.id]
        if node.id in ctx:
            return ctx[node.id]
        if node.id in ("true", "false"):
            return node.id == "true"
        raise ExpressionError(f"nieznana zmienna: {node.id}")
    if isinstance(node, ast.BoolOp):
        values = [_as_bool(_eval(v, df, ctx), df.index) for v in node.values]
        result = values[0]
        for v in values[1:]:
            result = (result & v) if isinstance(node.op, ast.And) else (result | v)
        return result
    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, df, ctx)
        if isinstance(node.op, ast.Not):
            return ~_as_bool(operand, df.index)
        if isinstance(node.op, ast.USub):
            return -operand
        return operand
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left, df, ctx), _eval(node.right, df, ctx)
        if isinstance(node.op, ast.Div):
            if isinstance(right, pd.Series):
                right = right.where(right != 0)
            elif right == 0:
                right = float("nan")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, df, ctx)
        result = None
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, df, ctx)
            part = _CMP_OPS[type(op)](left, right)
            part = _as_bool(part, df.index)
            result = part if result is None else (result & part)
            left = right
        return result
    if isinstance(node, ast.Call):
        args = [_eval(a, df, ctx) for a in node.args]
        name = node.func.id
        if name == "abs":
            if len(args) != 1:
                raise ExpressionError("abs() przyjmuje 1 argument")
            return abs(args[0])
        if len(args) < 2:
            raise ExpressionError(f"{name}() przyjmuje co najmniej 2 argumenty")
        frame = pd.DataFrame({i: (a if isinstance(a, pd.Series) else pd.Series(a, index=df.index))
                              for i, a in enumerate(args)})
        return frame.min(axis=1) if name == "min" else frame.max(axis=1)
    raise ExpressionError(f"niedozwolony element: {type(node).__name__}")


def evaluate(expr: str | ast.Expression, df: pd.DataFrame, ctx: dict[str, Any] | None = None):
    tree = compile_expression(expr) if isinstance(expr, str) else expr
    with np.errstate(all="ignore"):
        return _eval(tree, df, ctx or {})


def evaluate_mask(expr: str | ast.Expression, df: pd.DataFrame, ctx: dict[str, Any] | None = None) -> pd.Series:
    return _as_bool(evaluate(expr, df, ctx), df.index)


# --------------------------------------------------------------------------- formatowanie


class _SafeFormatter(string.Formatter):
    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            return kwargs.get(key, "{" + key + "}")
        return super().get_value(key, args, kwargs)

    def format_field(self, value, format_spec):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return "—"
        try:
            text = super().format_field(value, format_spec)
        except (ValueError, TypeError):
            return str(value)
        if isinstance(value, (int, float, np.number)) and not isinstance(value, bool):
            # Polski zapis liczb: 1 234,56
            text = text.replace(",", "\u00a0").replace(".", ",")
        return text


_FORMATTER = _SafeFormatter()


def render(template: str, values: dict[str, Any]) -> str:
    if not template:
        return ""
    try:
        return _FORMATTER.format(template, **values)
    except (ValueError, IndexError, KeyError):
        return template


# --------------------------------------------------------------------------- reguły

# Minimalna próba, gdy reguła nie definiuje własnej (pole ``sample``).
DEFAULT_SAMPLE = {
    "campaign": "clicks >= min_clicks",
    "search_term": "clicks >= wasted_min_clicks",
    "ad_group": "clicks >= min_clicks",
    "keyword": "clicks >= min_clicks",
    "ad": "impressions >= min_impressions",
    "device": "clicks >= min_clicks",
    "time_slot": "clicks >= min_clicks",
    "location": "clicks >= min_clicks",
    "audience": "clicks >= min_clicks",
    "landing_page": "clicks >= min_clicks",
    "conversion_action": "conversions >= min_conversions",
    "competitor": "impression_share >= 0.1",
}

# Nazwy encji wyświetlane jako "obiekt" rekomendacji.
ENTITY_NAME_FIELD = {
    "campaign": "campaign", "search_term": "search_term", "ad_group": "ad_group", "keyword": "keyword",
    "ad": "ad_name", "device": "device_label", "time_slot": "slot", "location": "location",
    "audience": "segment", "landing_page": "landing_page", "conversion_action": "conversion_action",
    "competitor": "competitor_domain",
}


@dataclass
class Rule:
    id: str
    name: str
    entity: str
    condition: str
    severity: str = "medium"
    category: str = "other"
    action: str = ""
    message: str = ""
    recommendation: str = ""
    evidence: str = ""
    sample: str = ""
    impact: str | None = None
    enabled: bool = True
    _tree: ast.Expression | None = field(default=None, repr=False)
    _impact_tree: ast.Expression | None = field(default=None, repr=False)
    _sample_tree: ast.Expression | None = field(default=None, repr=False)

    @property
    def source_report(self) -> str:
        return REPORT_BY_KEY[ENTITY_REPORT[self.entity]].label


@dataclass
class RuleSet:
    rules: list[Rule]
    errors: list[str]


@dataclass
class RuleStat:
    status: str            # ok | no_data | skipped | error | disabled
    matched: int = 0       # rekomendacje (warunek + wystarczająca próba)
    insufficient: int = 0  # warunek spełniony, ale próba za mała → bez rekomendacji
    reason: str = ""


REQUIRED_RULE_KEYS = ("id", "entity", "condition")


def parse_rules(text: str) -> RuleSet:
    """Parsuje YAML z regułami. Błędne reguły są pomijane i raportowane w ``errors``."""
    errors: list[str] = []
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        return RuleSet([], [f"Błąd YAML: {exc}"])
    raw_rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(raw_rules, list):
        return RuleSet([], ["Plik reguł musi zawierać listę pod kluczem 'rules'."])

    rules: list[Rule] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_rules, start=1):
        if not isinstance(raw, dict):
            errors.append(f"Reguła #{i}: oczekiwano słownika.")
            continue
        rid = str(raw.get("id", f"#{i}"))
        missing = [k for k in REQUIRED_RULE_KEYS if not raw.get(k)]
        if missing:
            errors.append(f"Reguła {rid}: brak pól {', '.join(missing)}.")
            continue
        if rid in seen:
            errors.append(f"Reguła {rid}: zduplikowane id.")
            continue
        if raw["entity"] not in ENTITIES:
            errors.append(f"Reguła {rid}: nieznana encja '{raw['entity']}' (dozwolone: {', '.join(ENTITIES)}).")
            continue
        severity = str(raw.get("severity", "medium")).lower()
        if severity not in SEVERITIES:
            errors.append(f"Reguła {rid}: nieznany severity '{severity}' (high/medium/low).")
            continue
        sample = str(raw.get("sample") or DEFAULT_SAMPLE[raw["entity"]])
        try:
            tree = compile_expression(str(raw["condition"]))
            impact_tree = compile_expression(str(raw["impact"])) if raw.get("impact") else None
            sample_tree = compile_expression(sample)
        except ExpressionError as exc:
            errors.append(f"Reguła {rid}: {exc}.")
            continue
        seen.add(rid)
        rules.append(Rule(
            id=rid,
            name=str(raw.get("name", rid)),
            entity=raw["entity"],
            condition=str(raw["condition"]),
            severity=severity,
            category=str(raw.get("category", "other")),
            action=str(raw.get("action", "")),
            message=str(raw.get("message", "")),
            recommendation=str(raw.get("recommendation", "")),
            evidence=str(raw.get("evidence", "")),
            sample=sample,
            impact=str(raw["impact"]) if raw.get("impact") else None,
            enabled=bool(raw.get("enabled", True)),
            _tree=tree,
            _impact_tree=impact_tree,
            _sample_tree=sample_tree,
        ))
    return RuleSet(rules, errors)


def load_rules(path: Path = RULES_PATH) -> RuleSet:
    return parse_rules(Path(path).read_text(encoding="utf-8"))


FINDING_COLUMNS = [
    "rule_id", "rule_name", "severity", "category", "action", "entity", "entity_name",
    "campaign", "ad_group", "message", "recommendation", "evidence", "source", "data_scope", "impact",
    "cost", "clicks", "conversions", "cpa",
]


def _missing_fields(rule: Rule, df: pd.DataFrame, context: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Zwraca (znane pola nieobecne w raporcie, nieznane nazwy)."""
    names = set()
    for tree in (rule._tree, rule._impact_tree, rule._sample_tree):
        if tree is not None:
            names |= expression_names(tree)
    absent = sorted(n for n in names if n not in df.columns and n not in context and n not in ("true", "false"))
    known = [n for n in absent if n in KNOWN_FIELDS or n.endswith(("_prev", "_change"))]
    unknown = [n for n in absent if n not in known]
    return known, unknown


def _evidence_suffix(rule: Rule, row: pd.Series, context: dict[str, Any]) -> tuple[str, str]:
    source = rule.source_report
    if rule.entity in ("campaign", "search_term") or bool(row.get("has_date", True)):
        scope = context.get("period_label", "")
    else:
        scope = "okres eksportu (raport bez daty)"
    return source, scope


def run_rules(
    ruleset: RuleSet,
    frames: dict[str, pd.DataFrame],
    context: dict[str, Any],
    stats: dict[str, RuleStat] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Uruchamia reguły na encjach. Zwraca (findings, błędy_wykonania).

    Reguła jest uruchamiana tylko, gdy istnieje ramka jej encji (czyli dostarczono raport) i ramka
    zawiera wszystkie potrzebne kolumny. Wiersze spełniające warunek, ale nie spełniające progu próby
    (``sample``), nie generują rekomendacji – są liczone w ``stats[...].insufficient``.
    """
    stats = stats if stats is not None else {}
    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    for rule in ruleset.rules:
        if not rule.enabled:
            stats[rule.id] = RuleStat("disabled")
            continue
        df = frames.get(rule.entity)
        if df is None or df.empty:
            stats[rule.id] = RuleStat("no_data", reason=f"brak raportu {rule.source_report}")
            continue
        known, unknown = _missing_fields(rule, df, context)
        if unknown:
            msg = "nieznana zmienna: " + ", ".join(unknown)
            errors.append(f"Reguła {rule.id}: {msg}")
            stats[rule.id] = RuleStat("error", reason=msg)
            continue
        if known:
            stats[rule.id] = RuleStat("skipped", reason=f"raport {rule.source_report} nie zawiera kolumn: "
                                                        + ", ".join(known))
            continue
        try:
            cond = evaluate_mask(rule._tree, df, context)
            sample_ok = evaluate_mask(rule._sample_tree, df, context)
            matched = df[cond & sample_ok]
            impact = None
            if rule._impact_tree is not None and not matched.empty:
                impact = evaluate(rule._impact_tree, matched, context)
        except (ExpressionError, TypeError, ValueError) as exc:
            errors.append(f"Reguła {rule.id}: {exc}")
            stats[rule.id] = RuleStat("error", reason=str(exc))
            continue
        stats[rule.id] = RuleStat("ok", matched=len(matched), insufficient=int((cond & ~sample_ok).sum()))
        name_field = ENTITY_NAME_FIELD[rule.entity]
        for pos, (_, row) in enumerate(matched.iterrows()):
            values = {**context, **row.to_dict()}
            if isinstance(impact, pd.Series):
                imp = impact.iloc[pos]
            elif impact is not None:
                imp = impact
            else:
                imp = float("nan")
            source, data_scope = _evidence_suffix(rule, row, context)
            findings.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                "severity": rule.severity,
                "category": rule.category,
                "action": rule.action,
                "entity": rule.entity,
                "entity_name": row.get(name_field, ""),
                "campaign": row.get("campaign", ""),
                "ad_group": row.get("ad_group", ""),
                "message": render(rule.message, values),
                "recommendation": render(rule.recommendation, values),
                "evidence": render(rule.evidence, values),
                "source": source,
                "data_scope": data_scope,
                "impact": float(imp) if imp is not None and pd.notna(imp) else float("nan"),
                "cost": row.get("cost", float("nan")),
                "clicks": row.get("clicks", float("nan")),
                "conversions": row.get("conversions", float("nan")),
                "cpa": row.get("cpa", float("nan")),
            })
    return pd.DataFrame(findings, columns=FINDING_COLUMNS), errors
