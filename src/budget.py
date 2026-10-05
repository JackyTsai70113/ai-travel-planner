"""Presentation helpers for canonical budget intent and cost coverage."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def format_budget_summary(budget: Mapping[str, Any], *, known_total_label: str | None = None) -> str:
    """Describe the user's ceiling separately from the completeness of costs."""
    limit_status = budget.get("limit_status", "unspecified")
    total_status = budget.get("total_status", "complete")
    total = budget.get("total")
    cost = _money(total)
    if total_status == "incomplete":
        cost_text = (
            "已知費用小計尚無金額資料"
            if cost == "費用資料未提供"
            else f"已知費用小計 {cost}（部分費用尚未取得）"
        )
    else:
        cost_text = f"目前已知費用總額 {known_total_label or cost}"

    if limit_status == "unlimited":
        return f"未設定預算上限；{cost_text}"
    if limit_status == "limited" and isinstance(budget.get("limit"), Mapping):
        return f"預算上限 {_money(budget['limit'])}；{cost_text}"
    if total_status == "incomplete":
        return "總額待確認（僅列已知費用小計）"
    return known_total_label or cost


def _money(value: object) -> str:
    if not isinstance(value, Mapping):
        return "費用資料未提供"
    amount, currency = value.get("amount"), value.get("currency", "")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        return "費用資料未提供"
    if isinstance(amount, float) and amount.is_integer():
        amount = int(amount)
    return f"{currency} {amount:,}"
