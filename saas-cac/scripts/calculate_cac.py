#!/usr/bin/env python3
"""Deterministic SaaS CAC and gross-margin payback calculator."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


CENT = Decimal("0.01")
RATE_PRECISION = Decimal("0.0001")
FUNNEL_STAGES = (
    "visitors",
    "leads",
    "mqls",
    "sqls",
    "opportunities",
    "new_paying_customers",
)
VIEWS = ("summary", "channels", "funnel", "trend", "cohorts", "full")


class InputError(ValueError):
    """Raised when input data could produce an invalid or ambiguous result."""


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise InputError(f"{field} must be a non-negative number")
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise InputError(f"{field} must be a non-negative number") from None
    if not result.is_finite() or result < 0:
        raise InputError(f"{field} must be a finite, non-negative number")
    return result


def _count(value: Any, field: str) -> int:
    result = _decimal(value, field)
    if result != result.to_integral_value():
        raise InputError(f"{field} must be a whole number")
    return int(result)


def _rate(value: Any, field: str) -> Decimal:
    if isinstance(value, str) and value.strip().endswith("%"):
        result = _decimal(value.strip()[:-1], field) / Decimal(100)
    else:
        result = _decimal(value, field)
    if result > 1:
        raise InputError(
            f"{field} must be between 0 and 1, or a percentage string such as '60%'"
        )
    return result


def _costs(value: Any, field: str) -> tuple[Decimal, dict[str, Decimal]]:
    if isinstance(value, dict):
        if not value:
            raise InputError(f"{field} must not be empty")
        breakdown: dict[str, Decimal] = {}
        for name, amount in value.items():
            if not isinstance(name, str) or not name.strip():
                raise InputError(f"{field} category names must be non-empty strings")
            breakdown[name] = _decimal(amount, f"{field}.{name}")
        return sum(breakdown.values(), Decimal(0)), breakdown
    total = _decimal(value, field)
    return total, {"total": total}


def _safe_div(numerator: Decimal, denominator: Decimal | int) -> Decimal | None:
    if denominator == 0:
        return None
    return numerator / Decimal(denominator)


def _money(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(CENT, rounding=ROUND_HALF_UP)


def _ratio(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(RATE_PRECISION, rounding=ROUND_HALF_UP)


def calculate_record(
    record: dict[str, Any], context: str, warnings: list[str]
) -> dict[str, Any]:
    if "acquisition_costs" not in record:
        raise InputError(f"{context}.acquisition_costs is required")
    if "new_paying_customers" not in record:
        raise InputError(f"{context}.new_paying_customers is required")

    total_cost, breakdown = _costs(
        record["acquisition_costs"], f"{context}.acquisition_costs"
    )
    new_customers = _count(
        record["new_paying_customers"], f"{context}.new_paying_customers"
    )
    cac = _safe_div(total_cost, new_customers)
    if cac is None:
        warnings.append(
            f"{context}: new_paying_customers is 0, so CAC and dependent metrics are undefined."
        )

    metrics: dict[str, Any] = {
        "total_acquisition_cost": _money(total_cost),
        "new_paying_customers": new_customers,
        "cac": _money(cac),
        "arpa": None,
        "monthly_gross_profit_per_customer": None,
        "cac_payback_months": None,
        "gross_margin_ltv": None,
        "ltv_to_cac": None,
        "cost_breakdown": {key: _money(value) for key, value in breakdown.items()},
    }

    payback_fields = ("mrr", "active_paying_customers", "gross_margin_rate")
    supplied = [field for field in payback_fields if field in record]
    if supplied and len(supplied) != len(payback_fields):
        missing = ", ".join(field for field in payback_fields if field not in record)
        warnings.append(f"{context}: payback not calculated; missing {missing}.")
    elif len(supplied) == len(payback_fields):
        mrr = _decimal(record["mrr"], f"{context}.mrr")
        active = _count(
            record["active_paying_customers"],
            f"{context}.active_paying_customers",
        )
        margin = _rate(record["gross_margin_rate"], f"{context}.gross_margin_rate")
        if active == 0:
            warnings.append(
                f"{context}: active_paying_customers is 0, so ARPA and payback are undefined."
            )
        else:
            arpa = mrr / Decimal(active)
            monthly_gp = arpa * margin
            payback = None if cac is None else _safe_div(cac, monthly_gp)
            metrics["arpa"] = _money(arpa)
            metrics["monthly_gross_profit_per_customer"] = _money(monthly_gp)
            metrics["cac_payback_months"] = _money(payback)
            if monthly_gp == 0:
                warnings.append(
                    f"{context}: monthly gross profit per customer is 0, so payback is undefined."
                )

            if "monthly_logo_churn_rate" in record:
                churn = _rate(
                    record["monthly_logo_churn_rate"],
                    f"{context}.monthly_logo_churn_rate",
                )
                if churn == 0:
                    warnings.append(
                        f"{context}: monthly_logo_churn_rate is 0, so simplified LTV is undefined."
                    )
                else:
                    ltv = monthly_gp / churn
                    metrics["gross_margin_ltv"] = _money(ltv)
                    metrics["ltv_to_cac"] = _ratio(
                        None if cac in (None, Decimal(0)) else ltv / cac
                    )
    elif "monthly_logo_churn_rate" in record:
        warnings.append(
            f"{context}: LTV not calculated because payback inputs are missing."
        )

    return metrics


def _calculate_channels(
    payload: dict[str, Any], overall: dict[str, Any], warnings: list[str]
) -> list[dict[str, Any]]:
    rows = payload.get("channels", [])
    if not isinstance(rows, list):
        raise InputError("channels must be an array")
    result = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise InputError(f"channels[{index}] must be an object")
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            raise InputError(f"channels[{index}].name is required")
        if name in seen:
            raise InputError(f"channels contains duplicate name: {name}")
        seen.add(name)
        metrics = calculate_record(row, f"channel {name}", warnings)
        metrics["name"] = name
        total = overall["total_acquisition_cost"]
        metrics["cost_share"] = _ratio(
            _safe_div(metrics["total_acquisition_cost"], total)
        )
        result.append(metrics)

    if result:
        channel_cost = sum(
            (row["total_acquisition_cost"] for row in result), Decimal(0)
        )
        channel_customers = sum(row["new_paying_customers"] for row in result)
        if abs(channel_cost - overall["total_acquisition_cost"]) > CENT:
            warnings.append(
                "channels: channel acquisition costs do not reconcile to the overall total."
            )
        if channel_customers != overall["new_paying_customers"]:
            warnings.append(
                "channels: channel new paying customers do not reconcile to the overall total."
            )
    return result


def _calculate_funnel(
    payload: dict[str, Any], overall: dict[str, Any], warnings: list[str]
) -> list[dict[str, Any]]:
    funnel = payload.get("funnel")
    if funnel is None:
        return []
    if not isinstance(funnel, dict):
        raise InputError("funnel must be an object")
    unknown = sorted(set(funnel) - set(FUNNEL_STAGES))
    if unknown:
        raise InputError(f"funnel has unsupported stages: {', '.join(unknown)}")

    values = [
        (stage, _count(funnel[stage], f"funnel.{stage}"))
        for stage in FUNNEL_STAGES
        if stage in funnel
    ]
    first_count = values[0][1] if values else 0
    result = []
    previous: int | None = None
    for stage, count in values:
        if previous is not None and count > previous:
            warnings.append(
                f"funnel: {stage} exceeds the previous supplied stage; verify stage definitions."
            )
        step_conversion = None if previous in (None, 0) else Decimal(count) / Decimal(previous)
        cumulative = None if first_count == 0 else Decimal(count) / Decimal(first_count)
        cost_per_outcome = _safe_div(overall["total_acquisition_cost"], count)
        result.append(
            {
                "stage": stage,
                "count": count,
                "step_conversion": _ratio(step_conversion),
                "cumulative_conversion": _ratio(cumulative),
                "cost_per_outcome": _money(cost_per_outcome),
            }
        )
        previous = count

    if "new_paying_customers" in funnel:
        funnel_new = _count(funnel["new_paying_customers"], "funnel.new_paying_customers")
        if funnel_new != overall["new_paying_customers"]:
            warnings.append(
                "funnel: new_paying_customers does not reconcile to the overall total."
            )
    return result


def _calculate_trend(
    payload: dict[str, Any], current: dict[str, Any], warnings: list[str]
) -> list[dict[str, Any]]:
    history = payload.get("history", [])
    if not isinstance(history, list):
        raise InputError("history must be an array")
    rows: list[tuple[str, dict[str, Any]]] = []
    periods: set[str] = set()
    for index, item in enumerate(history):
        if not isinstance(item, dict):
            raise InputError(f"history[{index}] must be an object")
        period = item.get("period")
        if not isinstance(period, str) or not period.strip():
            raise InputError(f"history[{index}].period is required")
        if period in periods:
            raise InputError(f"history contains duplicate period: {period}")
        periods.add(period)
        rows.append((period, calculate_record(item, f"history {period}", warnings)))

    current_period = payload["period"]
    if current_period not in periods:
        rows.append((current_period, current))

    result = []
    previous: dict[str, Any] | None = None
    for period, metrics in rows:
        cac_change = None
        payback_change = None
        if previous:
            if previous["cac"] not in (None, Decimal(0)) and metrics["cac"] is not None:
                cac_change = metrics["cac"] / previous["cac"] - 1
            old_payback = previous["cac_payback_months"]
            if old_payback not in (None, Decimal(0)) and metrics["cac_payback_months"] is not None:
                payback_change = metrics["cac_payback_months"] / old_payback - 1
        result.append(
            {
                "period": period,
                "cac": metrics["cac"],
                "cac_change": _ratio(cac_change),
                "cac_payback_months": metrics["cac_payback_months"],
                "payback_change": _ratio(payback_change),
            }
        )
        previous = metrics
    return result


def _calculate_cohorts(payload: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    cohorts = payload.get("cohorts", [])
    if not isinstance(cohorts, list):
        raise InputError("cohorts must be an array")
    result = []
    seen: set[str] = set()
    for index, row in enumerate(cohorts):
        if not isinstance(row, dict):
            raise InputError(f"cohorts[{index}] must be an object")
        name = row.get("cohort")
        if not isinstance(name, str) or not name.strip():
            raise InputError(f"cohorts[{index}].cohort is required")
        if name in seen:
            raise InputError(f"cohorts contains duplicate cohort: {name}")
        seen.add(name)
        total_cost, _ = _costs(row.get("acquisition_costs"), f"cohort {name}.acquisition_costs")
        customers = _count(
            row.get("new_paying_customers"), f"cohort {name}.new_paying_customers"
        )
        monthly_gp = _decimal(
            row.get("monthly_gross_profit_per_customer"),
            f"cohort {name}.monthly_gross_profit_per_customer",
        )
        cac = _safe_div(total_cost, customers)
        payback = None if cac is None else _safe_div(cac, monthly_gp)
        if customers == 0:
            warnings.append(f"cohort {name}: customer count is 0; CAC is undefined.")
        if monthly_gp == 0:
            warnings.append(f"cohort {name}: monthly gross profit is 0; payback is undefined.")
        result.append(
            {
                "cohort": name,
                "total_acquisition_cost": _money(total_cost),
                "new_paying_customers": customers,
                "cac": _money(cac),
                "monthly_gross_profit_per_customer": _money(monthly_gp),
                "cac_payback_months": _money(payback),
            }
        )
    return result


def calculate(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InputError("input must be a JSON object")
    period = payload.get("period")
    currency = payload.get("currency")
    if not isinstance(period, str) or not period.strip():
        raise InputError("period is required")
    if not isinstance(currency, str) or not currency.strip():
        raise InputError("currency is required")

    warnings: list[str] = []
    summary = calculate_record(payload, "overall", warnings)
    result = {
        "meta": {"period": period, "currency": currency.upper()},
        "summary": summary,
        "channels": [],
        "funnel": [],
        "trend": [],
        "cohorts": [],
        "warnings": warnings,
    }
    result["channels"] = _calculate_channels(payload, summary, warnings)
    result["funnel"] = _calculate_funnel(payload, summary, warnings)
    result["trend"] = _calculate_trend(payload, summary, warnings)
    result["cohorts"] = _calculate_cohorts(payload, warnings)
    return result


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _fmt(value: Any, percent: bool = False) -> str:
    if value is None:
        return "—"
    if percent:
        return f"{Decimal(value) * 100:.2f}%"
    if isinstance(value, (Decimal, int, float)):
        return f"{Decimal(str(value)):,.2f}"
    return str(value)


def render_markdown(result: dict[str, Any], view: str) -> str:
    currency = result["meta"]["currency"]
    period = result["meta"]["period"]
    sections: list[str] = [f"# SaaS CAC dashboard — {period}"]

    if view in ("summary", "full"):
        item = result["summary"]
        sections.append(
            "\n## Executive scorecard\n\n"
            "| Metric | Value |\n|---|---:|\n"
            f"| Acquisition cost | {currency} {_fmt(item['total_acquisition_cost'])} |\n"
            f"| New paying customers | {item['new_paying_customers']} |\n"
            f"| CAC | {currency} {_fmt(item['cac'])} |\n"
            f"| ARPA | {currency} {_fmt(item['arpa'])} |\n"
            f"| Monthly gross profit / customer | {currency} {_fmt(item['monthly_gross_profit_per_customer'])} |\n"
            f"| Gross-margin payback | {_fmt(item['cac_payback_months'])} months |\n"
            f"| Gross-margin LTV | {currency} {_fmt(item['gross_margin_ltv'])} |\n"
            f"| LTV / CAC | {_fmt(item['ltv_to_cac'])}x |"
        )

    if view in ("channels", "full"):
        lines = [
            "\n## Channel efficiency",
            "",
            "| Channel | Cost | Customers | CAC | Cost share |",
            "|---|---:|---:|---:|---:|",
        ]
        for item in result["channels"]:
            lines.append(
                f"| {item['name']} | {currency} {_fmt(item['total_acquisition_cost'])} | "
                f"{item['new_paying_customers']} | {currency} {_fmt(item['cac'])} | "
                f"{_fmt(item['cost_share'], True)} |"
            )
        if not result["channels"]:
            lines.append("| No channel data | — | — | — | — |")
        sections.append("\n".join(lines))

    if view in ("funnel", "full"):
        lines = [
            "\n## Acquisition funnel",
            "",
            "| Stage | Count | Step conversion | Cumulative conversion | Cost / outcome |",
            "|---|---:|---:|---:|---:|",
        ]
        for item in result["funnel"]:
            lines.append(
                f"| {item['stage']} | {item['count']} | {_fmt(item['step_conversion'], True)} | "
                f"{_fmt(item['cumulative_conversion'], True)} | {currency} {_fmt(item['cost_per_outcome'])} |"
            )
        if not result["funnel"]:
            lines.append("| No funnel data | — | — | — | — |")
        sections.append("\n".join(lines))

    if view in ("trend", "full"):
        lines = [
            "\n## Period trend",
            "",
            "| Period | CAC | CAC change | Payback | Payback change |",
            "|---|---:|---:|---:|---:|",
        ]
        for item in result["trend"]:
            lines.append(
                f"| {item['period']} | {currency} {_fmt(item['cac'])} | {_fmt(item['cac_change'], True)} | "
                f"{_fmt(item['cac_payback_months'])} months | {_fmt(item['payback_change'], True)} |"
            )
        sections.append("\n".join(lines))

    if view in ("cohorts", "full"):
        lines = [
            "\n## Cohort payback",
            "",
            "| Cohort | Cost | Customers | CAC | Monthly gross profit / customer | Payback |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for item in result["cohorts"]:
            lines.append(
                f"| {item['cohort']} | {currency} {_fmt(item['total_acquisition_cost'])} | "
                f"{item['new_paying_customers']} | {currency} {_fmt(item['cac'])} | "
                f"{currency} {_fmt(item['monthly_gross_profit_per_customer'])} | "
                f"{_fmt(item['cac_payback_months'])} months |"
            )
        if not result["cohorts"]:
            lines.append("| No cohort data | — | — | — | — | — |")
        sections.append("\n".join(lines))

    if result["warnings"]:
        sections.append(
            "\n## Data-quality notes\n\n"
            + "\n".join(f"- {warning}" for warning in result["warnings"])
        )
    return "\n".join(sections) + "\n"


def render_csv(result: dict[str, Any], view: str) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=("view", "item", "metric", "value"))
    writer.writeheader()

    def write(section: str, item: str, metric: str, value: Any) -> None:
        writer.writerow(
            {"view": section, "item": item, "metric": metric, "value": "" if value is None else value}
        )

    if view in ("summary", "full"):
        for metric, value in result["summary"].items():
            if metric != "cost_breakdown":
                write("summary", result["meta"]["period"], metric, value)
    for section, name_key in (("channels", "name"), ("funnel", "stage"), ("trend", "period"), ("cohorts", "cohort")):
        if view not in (section, "full"):
            continue
        for row in result[section]:
            item_name = row[name_key]
            for metric, value in row.items():
                if metric not in (name_key, "cost_breakdown"):
                    write(section, item_name, metric, value)
    for warning in result["warnings"]:
        write("warnings", result["meta"]["period"], "warning", warning)
    return output.getvalue()


def _read_input(path: str) -> dict[str, Any]:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        return json.loads(text)
    except OSError as exc:
        raise InputError(f"cannot read input: {exc}") from None
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON at line {exc.lineno}, column {exc.colno}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Calculate SaaS CAC, gross-margin payback, and dashboard views."
    )
    parser.add_argument("input", help="UTF-8 JSON input path, or - for stdin")
    parser.add_argument("--format", choices=("json", "markdown", "csv"), default="markdown")
    parser.add_argument("--view", choices=VIEWS, default="summary")
    parser.add_argument("--output", help="write output to a UTF-8 file instead of stdout")
    args = parser.parse_args(argv)

    try:
        result = calculate(_read_input(args.input))
        if args.format == "json":
            rendered = json.dumps(_json_value(result), ensure_ascii=False, indent=2) + "\n"
        elif args.format == "csv":
            rendered = render_csv(result, args.view)
        else:
            rendered = render_markdown(result, args.view)
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except InputError as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
