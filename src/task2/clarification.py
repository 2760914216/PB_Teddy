from __future__ import annotations

from typing import cast


def clarify_if_needed(resolved_context: dict[str, object]) -> dict[str, object]:
    raw_missing_fields = cast(
        list[object], resolved_context.get("missing_fields") or []
    )
    missing_fields = [str(item) for item in raw_missing_fields]
    metric_name = str(resolved_context.get("metric_name") or "该指标")
    intent = str(resolved_context.get("intent") or "single_value")
    recent_years = resolved_context.get("recent_years")

    if "missing_company" in missing_fields:
        return {
            "needs_clarification": True,
            "question": "请说明要查询的公司名称或股票代码。",
            "missing_fields": ["missing_company"],
            "reason": "缺少公司信息",
        }

    if "missing_metric" in missing_fields:
        return {
            "needs_clarification": True,
            "question": "请说明想查询的财务指标，例如利润总额、净利润或营业收入。",
            "missing_fields": ["missing_metric"],
            "reason": "缺少财务指标",
        }

    if "missing_report_period" in missing_fields:
        return {
            "needs_clarification": True,
            "question": f"请问你查询哪一个报告期的{metric_name}？例如 2025 年第三季度或 2024 年年报。",
            "missing_fields": ["missing_report_period"],
            "reason": "缺少报告期",
        }

    if intent == "trend" and isinstance(recent_years, int):
        return {
            "needs_clarification": False,
            "question": None,
            "missing_fields": [],
            "defaulted_range": f"默认按近 {recent_years} 个年度/最新报告期理解",
            "reason": "模糊时间范围已按默认策略解释",
        }

    return {
        "needs_clarification": False,
        "question": None,
        "missing_fields": [],
        "reason": "信息完整，可继续生成查询计划",
    }
