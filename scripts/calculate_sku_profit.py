#!/usr/bin/env python3
"""Calculate SKU contribution profit from a UTF-8 CSV file."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


MONEY_FIELDS = (
    "sale_price",
    "product_cost",
    "packaging_cost",
    "shipping_cost",
    "discount_cost",
    "gift_cost",
    "other_variable_cost",
    "service_provider_fixed_fee",
)
RATE_FIELDS = (
    "platform_commission_rate",
    "creator_commission_rate",
    "service_provider_commission_rate",
)
REQUIRED_FIELDS = ("sku",) + MONEY_FIELDS + RATE_FIELDS


def number(row: dict[str, str], key: str) -> Decimal:
    raw = (row.get(key) or "0").strip().replace(",", "")
    try:
        return Decimal(raw or "0")
    except InvalidOperation as exc:
        raise ValueError(f"字段 {key} 的值不是数字: {raw!r}") from exc


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate(row: dict[str, str]) -> dict[str, str]:
    values = {key: number(row, key) for key in MONEY_FIELDS}
    rates = {key: number(row, key) / Decimal("100") for key in RATE_FIELDS}
    if values["sale_price"] <= 0:
        raise ValueError("sale_price 必须大于0")
    for key, rate in rates.items():
        if rate < 0 or rate > 1:
            raise ValueError(f"{key} 必须在0到100之间")

    price = values["sale_price"]
    platform_fee = price * rates["platform_commission_rate"]
    creator_fee = price * rates["creator_commission_rate"]
    service_fee = (
        price * rates["service_provider_commission_rate"]
        + values["service_provider_fixed_fee"]
    )
    variable_costs = sum(
        values[key]
        for key in (
            "product_cost",
            "packaging_cost",
            "shipping_cost",
            "discount_cost",
            "gift_cost",
            "other_variable_cost",
        )
    )
    contribution = price - variable_costs - platform_fee - creator_fee - service_fee
    margin = contribution / price * Decimal("100")

    return {
        "sku": (row.get("sku") or "未命名SKU").strip(),
        "sale_price": money(price),
        "platform_commission": money(platform_fee),
        "creator_commission": money(creator_fee),
        "service_provider_commission": money(service_fee),
        "total_variable_cost_ex_commission": money(variable_costs),
        "contribution_profit": money(contribution),
        "contribution_margin_pct": money(margin),
        "break_even_cac": money(max(contribution, Decimal("0"))),
        "status": "亏损" if contribution < 0 else "可贡献",
    }


def render_markdown(results: list[dict[str, str]]) -> str:
    headers = [
        "SKU", "成交价", "平台佣金", "达人佣金", "服务商佣金",
        "其他变动成本", "贡献利润", "贡献利润率", "盈亏平衡CAC", "状态",
    ]
    keys = [
        "sku", "sale_price", "platform_commission", "creator_commission",
        "service_provider_commission", "total_variable_cost_ex_commission",
        "contribution_profit", "contribution_margin_pct", "break_even_cac", "status",
    ]
    lines = ["# SKU利润测算", "", "| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for result in results:
        cells = [result[key].replace("|", "\\|") for key in keys]
        cells[7] += "%"
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend([
        "", "> 默认所有比例佣金按实际成交价计提；服务商佣金包含比例佣金与每单固定服务费。",
        "", "## 输入字段", "",
        "所有成本与佣金字段均须提供；没有某项费用时明确填 `0`。佣金率填写百分数，例如 `5` 表示5%。",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="UTF-8 CSV input")
    parser.add_argument("--output", type=Path, required=True, help="Markdown output")
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise SystemExit("CSV缺少表头")
        missing = [field for field in REQUIRED_FIELDS if field not in reader.fieldnames]
        if missing:
            raise SystemExit("CSV缺少字段（没有费用时请明确填0）: " + ", ".join(missing))
        results = []
        for index, row in enumerate(reader, start=2):
            try:
                results.append(calculate(row))
            except ValueError as exc:
                raise SystemExit(f"第{index}行: {exc}") from exc

    if not results:
        raise SystemExit("CSV没有数据行")
    args.output.write_text(render_markdown(results), encoding="utf-8")


if __name__ == "__main__":
    main()
