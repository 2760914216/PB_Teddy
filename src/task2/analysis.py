from __future__ import annotations

from decimal import Decimal


def _format_number(value: object) -> str:
    if value is None:
        return "暂无数据"
    if isinstance(value, (int, float, Decimal)):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def compose_analysis(
    question: str,
    resolved_context: dict[str, object],
    query_result: dict[str, object],
) -> str:
    if str(query_result.get("status")) == "no_data":
        metric_name = str(resolved_context.get("metric_name") or "指标")
        stock_abbr = str(resolved_context.get("stock_abbr") or "该公司")
        return f"{stock_abbr}在当前查询条件下没有可用于回答{metric_name}的数据。"

    rows = query_result.get("rows") or []
    if not isinstance(rows, list) or not rows:
        return "未获得可分析的数据。"

    metric_name = str(resolved_context.get("metric_name") or "指标")
    metric_column = str(resolved_context.get("metric_column") or "")
    stock_abbr = str(
        resolved_context.get("stock_abbr") or rows[0].get("stock_abbr") or "该公司"
    )
    intent = str(resolved_context.get("intent") or "single_value")

    if intent != "trend":
        first_row = rows[0]
        report_period = str(
            first_row.get("report_period")
            or resolved_context.get("report_period")
            or "该报告期"
        )
        value = _format_number(first_row.get(metric_column))
        return f"{stock_abbr}{report_period}的{metric_name}为 {value}。"

    numeric_points: list[tuple[str, float]] = []
    for row in rows:
        raw_value = row.get(metric_column)
        if isinstance(raw_value, (int, float, Decimal)):
            numeric_points.append(
                (str(row.get("report_period") or ""), float(raw_value))
            )

    if len(numeric_points) < 2:
        report_period = str(rows[-1].get("report_period") or "最近报告期")
        value = _format_number(rows[-1].get(metric_column))
        return f"{stock_abbr}{report_period}的{metric_name}为 {value}，当前有效时间点不足，暂不展开趋势分析。"

    first_period, first_value = numeric_points[0]
    last_period, last_value = numeric_points[-1]
    delta = last_value - first_value
    if delta > 0:
        direction = "总体上升"
    elif delta < 0:
        direction = "总体下降"
    else:
        direction = "总体持平"

    min_value = min(value for _, value in numeric_points)
    max_value = max(value for _, value in numeric_points)
    if min_value < 0 < max_value:
        shape = "呈现明显波动并跨越盈亏分界"
    elif max_value - min_value > max(abs(max_value), 1.0) * 0.3:
        shape = "波动较为明显"
    else:
        shape = "变化相对平稳"

    return (
        f"{stock_abbr}{first_period}到{last_period}的{metric_name}{direction}，"
        f"由 {_format_number(first_value)} 变为 {_format_number(last_value)}，{shape}。"
    )
